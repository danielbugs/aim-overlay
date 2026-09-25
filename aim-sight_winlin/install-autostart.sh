#!/usr/bin/env bash
# Install and enable the Aim Sight systemd user service.

set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
UNIT_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user"
UNIT_FILE="$UNIT_DIR/aim-sight.service"

command -v systemctl >/dev/null 2>&1 || {
    echo "systemctl is required for the user service." >&2
    exit 1
}

mkdir -p "$UNIT_DIR"
sed "s|@INSTALL_DIR@|$SCRIPT_DIR|g" \
    "$SCRIPT_DIR/aim-sight.service.in" > "$UNIT_FILE"

systemctl --user daemon-reload
systemctl --user enable --now aim-sight.service

echo "Aim Sight autostart service enabled."
echo "Manage it with: systemctl --user status aim-sight.service"
