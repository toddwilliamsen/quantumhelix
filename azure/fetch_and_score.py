#!/usr/bin/env python3
"""
Download Azure dummy telemetry from Blob Storage and score it with Quantum Helix.

Uses Azure CLI under the hood (``az storage blob download``) so no extra Python
Azure SDK packages are required beyond the core project venv.

Example:
  python azure/fetch_and_score.py \\
    --resource-group rg-Quantum Helix-test \\
    --storage-account qssgdummyXXXXXXXX
"""

from __future__ import annotations

import argparse
import json
import logging
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from alerter import AlertOrchestrator
from data_processor import ClassicalFeaturePipeline
from normalization import CloudSecurityEvent, MultiCloudLogParser
from quantum_engine import QuantumThreatDetector

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("azure.fetch_and_score")


def run_az(args: List[str]) -> str:
    completed = subprocess.run(
        ["az", *args],
        check=True,
        capture_output=True,
        text=True,
    )
    return completed.stdout.strip()


def download_blob(
    *,
    account: str,
    container: str,
    blob: str,
    dest: Path,
    account_key: Optional[str] = None,
) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        "storage",
        "blob",
        "download",
        "--account-name",
        account,
        "--container-name",
        container,
        "--name",
        blob,
        "--file",
        str(dest),
        "--overwrite",
        "true",
    ]
    if account_key:
        cmd.extend(["--account-key", account_key])
    else:
        cmd.extend(["--auth-mode", "login"])
    run_az(cmd)
    return dest


def load_ndjson(path: Path) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            rows.append(json.loads(line))
    return rows


def parse_records(raw_events: Iterable[Dict[str, Any]]) -> List[CloudSecurityEvent]:
    parser = MultiCloudLogParser()
    return [parser.parse_azure(raw) for raw in raw_events]


def score_events(
    events: List[CloudSecurityEvent],
    *,
    threshold: float,
) -> int:
    if len(events) < 4:
        raise RuntimeError("Need at least 4 events to fit PCA")

    normals = [e for e in events if e.auth_failures < 5 and e.data_volume_bytes < 1e8]
    fit_set = normals if len(normals) >= 4 else events[: max(4, len(events) // 2)]

    pipeline = ClassicalFeaturePipeline()
    reduced = pipeline.fit_transform(fit_set)
    detector = QuantumThreatDetector(seed=42)
    labels = [
        1.0
        if (e.auth_failures >= 10 and e.data_volume_bytes >= 1e8 and e.api_velocity >= 50)
        else 0.0
        for e in fit_set
    ]
    if sum(labels) >= 1:
        detector.train_on_batch(reduced, labels, steps=8, step_size=0.1)

    alerter = AlertOrchestrator(threshold=threshold, dry_run_webhook=True)
    alerts = 0
    print("\n{:<6} {:<8} {:>8}  {}".format("#", "Cloud", "Score", "Identity"))
    print("-" * 72)
    for idx, event in enumerate(events, start=1):
        score = float(detector.score(pipeline.transform_single(event)))
        status = "ALERT" if score >= threshold else "ok"
        if status == "ALERT":
            alerts += 1
            alerter.evaluate_and_alert(event, score, threshold=threshold)
        print(
            f"{idx:<6} {event.cloud_provider:<8} {score:>8.4f}  "
            f"{status:<5}  {event.normalized_identity[:48]}"
        )
    print("-" * 72)
    print(f"Scored {len(events)} Azure events — alerts={alerts} (threshold={threshold:.2f})")
    return alerts


def main() -> int:
    parser = argparse.ArgumentParser(description="Fetch Azure dummy telemetry and score it")
    parser.add_argument("--resource-group", required=True)
    parser.add_argument("--storage-account", required=True)
    parser.add_argument("--threshold", type=float, default=0.70)
    parser.add_argument(
        "--account-key",
        default=None,
        help="Optional storage account key (otherwise uses az login / AAD)",
    )
    parser.add_argument(
        "--local-dir",
        type=Path,
        default=None,
        help="If set, score from this local generated directory instead of downloading",
    )
    args = parser.parse_args()

    with tempfile.TemporaryDirectory(prefix="qs-azure-") as tmp:
        tmp_path = Path(tmp)
        if args.local_dir:
            base = args.local_dir
            activity_normal = load_ndjson(base / "activity-logs" / "normal.ndjson")
            activity_attack = load_ndjson(base / "activity-logs" / "attacks.ndjson")
        else:
            # Prefer account key from az if not provided
            account_key = args.account_key
            if not account_key:
                try:
                    account_key = run_az(
                        [
                            "storage",
                            "account",
                            "keys",
                            "list",
                            "--resource-group",
                            args.resource_group,
                            "--account-name",
                            args.storage_account,
                            "--query",
                            "[0].value",
                            "-o",
                            "tsv",
                        ]
                    )
                except subprocess.CalledProcessError:
                    account_key = None
                    logger.warning("Falling back to --auth-mode login for blob download")

            normal_path = download_blob(
                account=args.storage_account,
                container="activity-logs",
                blob="normal.ndjson",
                dest=tmp_path / "normal.ndjson",
                account_key=account_key,
            )
            attack_path = download_blob(
                account=args.storage_account,
                container="activity-logs",
                blob="attacks.ndjson",
                dest=tmp_path / "attacks.ndjson",
                account_key=account_key,
            )
            activity_normal = load_ndjson(normal_path)
            activity_attack = load_ndjson(attack_path)

        events = parse_records(activity_normal + activity_attack)
        logger.info(
            "Loaded %d events (%d normal, %d attack)",
            len(events),
            len(activity_normal),
            len(activity_attack),
        )
        score_events(events, threshold=args.threshold)

    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except subprocess.CalledProcessError as exc:
        logger.error("Azure CLI failed: %s", exc.stderr or exc)
        raise SystemExit(1) from exc
