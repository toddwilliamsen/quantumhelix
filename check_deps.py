#!/usr/bin/env python3
"""
Quantum Helix dependency freshness watcher.

Queries PyPI for the latest *stable* releases of every package pinned in
``requirements.txt``, reports drift, and can rewrite pins automatically.

This stack (PennyLane / scientific Python) matures quickly — run this often:

  python check_deps.py                 # report only (exit 1 if outdated)
  python check_deps.py --update        # bump requirements.txt to latest stables
  python check_deps.py --check-install # also compare against the active venv

Companions:
  - GitHub Dependabot (.github/dependabot.yml) — weekly PRs
  - setup.sh — runs a non-fatal freshness check after install

Note: ``autoray`` is intentionally locked to the exact version required by the
pinned PennyLane release (PennyLane declares ``autoray==…``). The watcher
resolves that companion pin from PennyLane metadata instead of floating to an
incompatible absolute-latest autoray.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

ROOT = Path(__file__).resolve().parent
REQUIREMENTS_PATH = ROOT / "requirements.txt"
PYPI_JSON = "https://pypi.org/pypi/{package}/json"
USER_AGENT = "Quantum Helix-DepWatcher/1.0 (+local/Quantum Helix)"

# Direct dependencies we pin and watch (constraints like autograd>= are separate).
MANAGED_PACKAGES: Tuple[str, ...] = (
    "pennylane",
    "autoray",
    "pandas",
    "scikit-learn",
    "numpy",
    "streamlit",
    "click",
    "requests",
)

# Companion locks: dependent → parent that declares an exact == requirement.
COMPANION_LOCKS = {
    "autoray": "pennylane",
}

PIN_RE = re.compile(
    r"^\s*(?P<name>[A-Za-z0-9][A-Za-z0-9._-]*)\s*==\s*(?P<version>[^\s#]+)"
)


@dataclass
class Pin:
    name: str
    version: str
    line_index: int


@dataclass
class Drift:
    name: str
    pinned: str
    latest: str
    note: str = ""

    @property
    def is_outdated(self) -> bool:
        return self.pinned != self.latest


def _normalize_name(name: str) -> str:
    return name.replace("_", "-").lower()


def parse_requirements(path: Path) -> Tuple[List[str], Dict[str, Pin]]:
    if not path.exists():
        raise FileNotFoundError(f"requirements file not found: {path}")
    lines = path.read_text(encoding="utf-8").splitlines()
    pins: Dict[str, Pin] = {}
    for idx, line in enumerate(lines):
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        match = PIN_RE.match(stripped)
        if match:
            name = match.group("name")
            pins[_normalize_name(name)] = Pin(
                name=name,
                version=match.group("version").strip(),
                line_index=idx,
            )
    return lines, pins


def _http_get_json(url: str, timeout: float = 30.0) -> dict:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.load(response)
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"PyPI lookup failed ({url}): HTTP {exc.code}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"PyPI lookup failed ({url}): {exc}") from exc


def fetch_latest_stable(package: str, timeout: float = 30.0) -> str:
    """Return the latest stable version published on PyPI for ``package``."""
    payload = _http_get_json(PYPI_JSON.format(package=package), timeout=timeout)
    candidate = str(payload["info"]["version"])
    if _is_stable(candidate) and candidate in payload.get("releases", {}):
        return candidate

    stables: List[str] = []
    for version, files in payload.get("releases", {}).items():
        if files and _is_stable(version):
            stables.append(version)
    if not stables:
        raise RuntimeError(f"No stable releases found on PyPI for {package}")
    return max(stables, key=_version_key)


def fetch_requires_exact_pin(
    parent_package: str,
    parent_version: str,
    child_package: str,
    timeout: float = 30.0,
) -> Optional[str]:
    """
    Read an exact ``child==X`` requirement from a parent's PyPI metadata.

    Used so autoray tracks PennyLane's declared pin rather than a conflicting
    absolute-latest autoray release.
    """
    url = f"https://pypi.org/pypi/{parent_package}/{parent_version}/json"
    payload = _http_get_json(url, timeout=timeout)
    requires = payload.get("info", {}).get("requires_dist") or []
    child_key = _normalize_name(child_package)
    exact = re.compile(
        rf"^{re.escape(child_package)}\s*==\s*([^\s;]+)",
        re.IGNORECASE,
    )
    # Also accept normalized underscore/hyphen variants in requires_dist.
    flex = re.compile(
        r"^([A-Za-z0-9][A-Za-z0-9._-]*)\s*==\s*([^\s;]+)",
        re.IGNORECASE,
    )
    for req in requires:
        if not isinstance(req, str):
            continue
        base = req.split(";", 1)[0].strip()
        match = exact.match(base)
        if match:
            return match.group(1)
        flex_match = flex.match(base)
        if flex_match and _normalize_name(flex_match.group(1)) == child_key:
            return flex_match.group(2)
    return None


def _is_stable(version: str) -> bool:
    return bool(re.match(r"^\d+(\.\d+)*$", version))


def _version_key(version: str) -> Tuple[int, ...]:
    parts: List[int] = []
    for chunk in version.split("."):
        try:
            parts.append(int(chunk))
        except ValueError:
            parts.append(0)
    return tuple(parts)


def target_version_for(
    package: str,
    pins: Dict[str, Pin],
    planned_targets: Dict[str, str],
) -> Tuple[str, str]:
    """
    Resolve the desired pin for a package.

    Returns (target_version, note).
    """
    key = _normalize_name(package)
    if key in COMPANION_LOCKS:
        parent = COMPANION_LOCKS[key]
        parent_key = _normalize_name(parent)
        parent_target = planned_targets.get(parent_key) or (
            fetch_latest_stable(parent)
            if parent_key not in pins
            else None
        )
        # Prefer already-computed parent target (update pass) else latest parent.
        if parent_target is None:
            parent_target = fetch_latest_stable(parent)
        locked = fetch_requires_exact_pin(parent, parent_target, package)
        if locked:
            return locked, f"locked by {parent}=={parent_target}"
        # Fallback: absolute latest if parent stopped pinning exactly.
        return fetch_latest_stable(package), f"no exact lock in {parent}; using PyPI latest"

    return fetch_latest_stable(package), "PyPI latest stable"


def compare_to_pypi(pins: Dict[str, Pin], packages: Sequence[str]) -> List[Drift]:
    # Resolve parents first so companions (autoray) lock to the *target* PennyLane.
    planned: Dict[str, str] = {}
    notes: Dict[str, str] = {}

    # Pass 1: independent packages
    for package in packages:
        key = _normalize_name(package)
        if key in COMPANION_LOCKS:
            continue
        target, note = target_version_for(package, pins, planned)
        planned[key] = target
        notes[key] = note

    # Pass 2: companions
    for package in packages:
        key = _normalize_name(package)
        if key not in COMPANION_LOCKS:
            continue
        target, note = target_version_for(package, pins, planned)
        planned[key] = target
        notes[key] = note

    results: List[Drift] = []
    for package in packages:
        key = _normalize_name(package)
        if key not in pins:
            raise RuntimeError(f"{package} is not pinned with == in requirements.txt")
        results.append(
            Drift(
                name=pins[key].name,
                pinned=pins[key].version,
                latest=planned[key],
                note=notes.get(key, ""),
            )
        )
    return results


def installed_version(package: str) -> Optional[str]:
    try:
        from importlib.metadata import PackageNotFoundError, version
    except ImportError:  # pragma: no cover
        return None
    candidates = [package]
    if package.lower() == "pennylane":
        candidates.append("PennyLane")
    for candidate in candidates:
        try:
            return version(candidate)
        except PackageNotFoundError:
            continue
    return None


def write_updated_requirements(path: Path, drifts: List[Drift]) -> None:
    managed_lines = [f"{d.name}=={d.latest}" for d in drifts]
    # Preserve non-managed constraint lines from the previous file.
    existing = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
    extras: List[str] = []
    for line in existing:
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        pin_match = PIN_RE.match(stripped)
        if pin_match and _normalize_name(pin_match.group("name")) in {
            _normalize_name(p) for p in MANAGED_PACKAGES
        }:
            continue
        extras.append(stripped)

    if not any(x.lower().startswith("autograd") for x in extras):
        extras.append("autograd>=1.8,<1.9")

    pennylane_ver = next(d.latest for d in drifts if _normalize_name(d.name) == "pennylane")
    header = [
        "# Quantum Helix — production dependencies (latest stable pins)",
        "# Regenerated against PyPI. Keep these exact pins in sync via:",
        "#   python check_deps.py --update",
        "#   or GitHub Dependabot (.github/dependabot.yml)",
        "#",
        "# Policy: only stable (non-dev / non-pre-release) versions.",
        "# PennyLane 0.45+ requires Python >= 3.11.",
        f"# autoray is locked to the exact version required by pennylane=={pennylane_ver}.",
        "",
    ]
    body = managed_lines + ["", f"# Compatibility guard declared by PennyLane {pennylane_ver}"] + extras
    path.write_text("\n".join(header + body).rstrip() + "\n", encoding="utf-8")


def print_report(drifts: List[Drift], check_install: bool) -> int:
    width_name = max(len(d.name) for d in drifts)
    print("Quantum Helix dependency freshness report")
    print("=" * 78)
    print(f"{'Package':<{width_name}}  {'Pinned':<12}  {'Target':<12}  Status")
    print("-" * 78)

    outdated = 0
    install_drift = 0
    for drift in drifts:
        status = "UP-TO-DATE" if not drift.is_outdated else "OUTDATED"
        if drift.is_outdated:
            outdated += 1
        suffix = f"  ({drift.note})" if drift.note else ""
        extra = ""
        if check_install:
            installed = installed_version(drift.name)
            if installed is None:
                extra = "  [venv: NOT INSTALLED]"
                install_drift += 1
            elif installed != drift.pinned:
                extra = f"  [venv: {installed} ≠ pin]"
                install_drift += 1
            else:
                extra = f"  [venv: {installed}]"
        print(
            f"{drift.name:<{width_name}}  {drift.pinned:<12}  {drift.latest:<12}  "
            f"{status}{extra}{suffix}"
        )

    print("-" * 78)
    if outdated == 0 and install_drift == 0:
        print("All managed packages match their target stable releases.")
        return 0

    if outdated:
        print(f"{outdated} package(s) behind target.")
        print("Bump pins with:  python check_deps.py --update && pip install -r requirements.txt")
    if install_drift:
        print(f"{install_drift} package(s) differ from the active virtualenv.")
        print("Reinstall with:  pip install -r requirements.txt")
    return 1


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Watch and update Quantum Helix dependency pins against PyPI.",
    )
    parser.add_argument(
        "--update",
        action="store_true",
        help="Rewrite requirements.txt pins to the latest compatible stable versions.",
    )
    parser.add_argument(
        "--check-install",
        action="store_true",
        help="Also compare pinned versions to packages in the active environment.",
    )
    parser.add_argument(
        "--requirements",
        type=Path,
        default=REQUIREMENTS_PATH,
        help="Path to requirements.txt (default: project root).",
    )
    args = parser.parse_args(argv)

    _, pins = parse_requirements(args.requirements)
    missing = [p for p in MANAGED_PACKAGES if _normalize_name(p) not in pins]
    if missing:
        print(
            f"ERROR: requirements.txt is missing exact pins for: {', '.join(missing)}",
            file=sys.stderr,
        )
        return 2

    try:
        drifts = compare_to_pypi(pins, MANAGED_PACKAGES)
    except RuntimeError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    if args.update:
        changed = [d for d in drifts if d.is_outdated]
        if not changed:
            print("requirements.txt already at target stable releases — nothing to update.")
        else:
            write_updated_requirements(args.requirements, drifts)
            print(f"Updated {len(changed)} pin(s) in {args.requirements}:")
            for drift in changed:
                print(f"  {drift.name}: {drift.pinned} → {drift.latest}" + (f" ({drift.note})" if drift.note else ""))
            print("Next: pip install -r requirements.txt && python validate.py")
        _, pins = parse_requirements(args.requirements)
        drifts = compare_to_pypi(pins, MANAGED_PACKAGES)

    return print_report(drifts, check_install=args.check_install)


if __name__ == "__main__":
    raise SystemExit(main())
