#!/usr/bin/env bash
# Install runtime dependencies for the GTK/Cairo Linux implementation.

set -euo pipefail

if [[ "$(uname -s)" != "Linux" ]]; then
    echo "This script only supports Linux." >&2
    exit 1
fi

if command -v sudo >/dev/null 2>&1; then
    SUDO=(sudo)
elif [[ "$EUID" -eq 0 ]]; then
    SUDO=()
else
    echo "sudo is required, or run this script as root." >&2
    exit 1
fi

if command -v dnf >/dev/null 2>&1; then
    # Fedora / RHEL-compatible distributions.
    "${SUDO[@]}" dnf install -y \
        python3 python3-gobject python3-cairo gtk3 libayatana-appindicator-gtk3
elif command -v apt-get >/dev/null 2>&1; then
    # Debian / Ubuntu-compatible distributions.
    "${SUDO[@]}" apt-get update
    "${SUDO[@]}" apt-get install -y \
        python3 python3-gi python3-cairo gir1.2-gtk-3.0 \
        gir1.2-ayatanaappindicator3-0.1
elif command -v pacman >/dev/null 2>&1; then
    # Arch / CachyOS-compatible distributions.
    "${SUDO[@]}" pacman -Sy --needed --noconfirm \
        python python-gobject python-cairo gtk3 libayatana-appindicator
else
    echo "Unsupported distribution: no dnf, apt-get, or pacman found." >&2
    echo "Install Python 3, PyGObject, Pycairo, GTK 3, and Ayatana AppIndicator 3 manually." >&2
    exit 1
fi

echo
echo "Checking the GTK and Ayatana AppIndicator imports..."
python3 - <<'PY'
import gi

gi.require_version("Gtk", "3.0")
gi.require_version("AyatanaAppIndicator3", "0.1")
from gi.repository import AyatanaAppIndicator3, Gtk  # noqa: F401
PY

echo "Linux dependencies installed successfully."
