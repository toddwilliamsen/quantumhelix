#!/usr/bin/env bash
# =============================================================================
# Quantum Helix environment bootstrap
# Compatible with Linux, macOS, and Windows (Git Bash / WSL / PowerShell notes)
# =============================================================================
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "${ROOT_DIR}"

# Colors (safe fallback when stdout is not a TTY)
if [[ -t 1 ]]; then
  C_GREEN='\033[0;32m'
  C_CYAN='\033[0;36m'
  C_YELLOW='\033[1;33m'
  C_RED='\033[0;31m'
  C_BOLD='\033[1m'
  C_RESET='\033[0m'
else
  C_GREEN='' C_CYAN='' C_YELLOW='' C_RED='' C_BOLD='' C_RESET=''
fi

info()  { echo -e "${C_CYAN}[INFO]${C_RESET}  $*"; }
ok()    { echo -e "${C_GREEN}[OK]${C_RESET}    $*"; }
warn()  { echo -e "${C_YELLOW}[WARN]${C_RESET}  $*"; }
fail()  { echo -e "${C_RED}[ERROR]${C_RESET} $*"; exit 1; }

banner() {
  echo -e "${C_BOLD}"
  cat <<'EOF'
  ____                    _                     ____         __                          _
 / __ \                  | |                   / ___|  __ _ / _| ___  _ __ _   _  __ _  __| |
| |  | |_   _  __ _ _ __ | |_ _   _ _ __ ___  \___ \ / _` | |_ / _ \| '__| | | |/ _` |/ _` |
| |  | | | | |/ _` | '_ \| __| | | | '_ ` _ \  ___) | (_| |  _|  __/| |  | |_| | (_| | (_| |
| |__| | |_| | (_| | | | | |_| |_| | | | | | ||____/ \__,_|_|  \___||_|   \__, |\__,_|\__,_|
 \___\_\\__,_|\__,_|_| |_|\__|\__,_|_| |_| |_|                             |___/
EOF
  echo -e "${C_RESET}"
  echo "  Multi-Cloud Hybrid Quantum-Classical Threat Detection Engine"
  echo "  Environment bootstrap"
  echo
}

detect_os() {
  local uname_out
  uname_out="$(uname -s 2>/dev/null || echo Unknown)"
  case "${uname_out}" in
    Linux*)   echo "linux" ;;
    Darwin*)  echo "macos" ;;
    MINGW*|MSYS*|CYGWIN*) echo "windows" ;;
    *)        echo "unknown" ;;
  esac
}

resolve_python() {
  local candidate
  for candidate in python3 python; do
    if command -v "${candidate}" >/dev/null 2>&1; then
      echo "${candidate}"
      return 0
    fi
  done
  return 1
}

version_ge() {
  # Return 0 if $1 >= $2 (both dotted version strings).
  printf '%s\n%s\n' "$2" "$1" | sort -V | head -n1 | grep -qx "$2"
}

banner

OS_FAMILY="$(detect_os)"
info "Detected OS family: ${OS_FAMILY}"

# ---------------------------------------------------------------------------
# 1. Python 3.9+ gate
# ---------------------------------------------------------------------------
PYTHON_BIN="$(resolve_python)" || fail "Python 3 was not found on PATH. Install Python 3.9+ and re-run."

PY_VERSION="$("${PYTHON_BIN}" -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}")')"
PY_MAJOR="$("${PYTHON_BIN}" -c 'import sys; print(sys.version_info.major)')"
PY_MINOR="$("${PYTHON_BIN}" -c 'import sys; print(sys.version_info.minor)')"

info "Found ${PYTHON_BIN} version ${PY_VERSION}"

# PennyLane 0.45+ (current stable) requires Python >= 3.11.
if [[ "${PY_MAJOR}" -lt 3 ]] || { [[ "${PY_MAJOR}" -eq 3 ]] && [[ "${PY_MINOR}" -lt 11 ]]; }; then
  fail "Python 3.11+ is required for the current PennyLane stack (found ${PY_VERSION}). Please upgrade and re-run ./setup.sh"
fi
ok "Python version check passed (>= 3.11)"

if [[ ! -f "${ROOT_DIR}/requirements.txt" ]]; then
  fail "requirements.txt not found in ${ROOT_DIR}"
fi

# ---------------------------------------------------------------------------
# 2. Create virtual environment (.venv)
# ---------------------------------------------------------------------------
if [[ -d "${ROOT_DIR}/.venv" ]]; then
  warn "Existing .venv detected — reusing it"
else
  info "Creating virtual environment at ${ROOT_DIR}/.venv"
  "${PYTHON_BIN}" -m venv "${ROOT_DIR}/.venv"
  ok "Created .venv"
fi

# ---------------------------------------------------------------------------
# 3. Activate based on OS (script + print manual instructions)
# ---------------------------------------------------------------------------
VENV_POSIX_ACTIVATE="${ROOT_DIR}/.venv/bin/activate"
VENV_WIN_ACTIVATE="${ROOT_DIR}/.venv/Scripts/activate"
VENV_WIN_PS1="${ROOT_DIR}/.venv/Scripts/Activate.ps1"

ACTIVATED=0
if [[ -f "${VENV_POSIX_ACTIVATE}" ]]; then
  # shellcheck disable=SC1090
  source "${VENV_POSIX_ACTIVATE}"
  ACTIVATED=1
  ok "Activated POSIX virtualenv (.venv/bin/activate)"
elif [[ -f "${VENV_WIN_ACTIVATE}" ]]; then
  # Git Bash / MSYS on Windows
  # shellcheck disable=SC1090
  source "${VENV_WIN_ACTIVATE}"
  ACTIVATED=1
  ok "Activated Windows virtualenv (.venv/Scripts/activate)"
else
  fail "Could not locate a virtualenv activate script under .venv"
fi

# Prefer the venv python for remaining steps
if command -v python >/dev/null 2>&1; then
  PYTHON_BIN="$(command -v python)"
fi

# ---------------------------------------------------------------------------
# 4. Upgrade pip
# ---------------------------------------------------------------------------
info "Upgrading pip to the latest version…"
"${PYTHON_BIN}" -m pip install --upgrade pip
ok "pip upgraded ($("${PYTHON_BIN}" -m pip --version))"

# ---------------------------------------------------------------------------
# 5. Install dependencies
# ---------------------------------------------------------------------------
info "Installing dependencies from requirements.txt…"
"${PYTHON_BIN}" -m pip install -r "${ROOT_DIR}/requirements.txt"
ok "All Python dependencies installed"

# Ensure this script remains executable for future runs
chmod +x "${ROOT_DIR}/setup.sh" 2>/dev/null || true
chmod +x "${ROOT_DIR}/validate.py" 2>/dev/null || true
chmod +x "${ROOT_DIR}/check_deps.py" 2>/dev/null || true

# Dependency freshness (non-fatal during setup — network / PyPI may be unreachable)
info "Checking dependency freshness against PyPI…"
if "${PYTHON_BIN}" "${ROOT_DIR}/check_deps.py" --check-install; then
  ok "Dependencies match latest compatible stables"
else
  warn "One or more pins lag PyPI (or the venv). Refresh with:"
  warn "  python check_deps.py --update && pip install -r requirements.txt && python validate.py"
fi

# ---------------------------------------------------------------------------
# 6. Success banner + runbook
# ---------------------------------------------------------------------------
echo
echo -e "${C_GREEN}${C_BOLD}"
cat <<'EOF'
+======================================================================+
|                                                                      |
|          Quantum Helix SETUP COMPLETE — READY TO SCAN            |
|                                                                      |
+======================================================================+
EOF
echo -e "${C_RESET}"

echo -e "${C_BOLD}Activate the virtual environment${C_RESET}"
case "${OS_FAMILY}" in
  linux|macos|unknown)
    echo "  source .venv/bin/activate"
    ;;
  windows)
    echo "  Git Bash / WSL :  source .venv/Scripts/activate"
    echo "  PowerShell     :  .\\.venv\\Scripts\\Activate.ps1"
    echo "  cmd.exe        :  .venv\\Scripts\\activate.bat"
    ;;
esac
echo

echo -e "${C_BOLD}Validate the hybrid quantum-classical detector${C_RESET}"
echo "  python validate.py"
echo "  python benchmark.py              # classical vs quantum-kernel scoreboard"
echo

echo -e "${C_BOLD}Keep dependencies on the latest compatible stables${C_RESET}"
echo "  python check_deps.py              # report drift vs PyPI"
echo "  python check_deps.py --update     # bump requirements.txt pins"
echo

echo -e "${C_BOLD}Start the Streamlit SOC GUI${C_RESET}"
echo "  streamlit run app.py"
echo

echo -e "${C_BOLD}Run the CLI threat scanner${C_RESET}"
echo "  python cli.py scan --duration 10 --threshold 0.70"
echo

echo -e "${C_BOLD}Run the orchestration entrypoint${C_RESET}"
echo "  python main.py --events 50 --threshold 0.75"
echo

ok "Setup finished successfully."
exit 0
