#!/usr/bin/env bash
set -euo pipefail

REPO_URL="https://github.com/Rutytoi220/eposctl"
BIN_NAME="eposctl"
INSTALL_DIR="${HOME}/.local/share/eposctl"
BIN_DIR="${HOME}/.local/bin"

echo "Installing ${BIN_NAME} from ${REPO_URL}..."

if command -v uv >/dev/null 2>&1; then
    uv tool install --force "git+${REPO_URL}"
elif command -v pipx >/dev/null 2>&1; then
    pipx install --force "git+${REPO_URL}"
else
    mkdir -p "${INSTALL_DIR}" "${BIN_DIR}"
    python3 -m venv "${INSTALL_DIR}/venv"
    "${INSTALL_DIR}/venv/bin/pip" install --upgrade pip >/dev/null
    "${INSTALL_DIR}/venv/bin/pip" install --upgrade "git+${REPO_URL}"
    ln -sf "${INSTALL_DIR}/venv/bin/${BIN_NAME}" "${BIN_DIR}/${BIN_NAME}"
fi

echo ""
echo "Done! Run '${BIN_NAME} tui' to launch the EPOS H3PRO TUI."
echo "(Make sure ~/.local/bin is in your PATH)"
