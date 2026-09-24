#!/usr/bin/env bash
# A simple desktop crosshair overlay for Fedora/Linux.
# Usage: ./aim-sight.sh [start|stop|toggle|status|tray]
# Styles: classic (4 arms), t (no top arm), dot, plus (no center gap).
# Options: --color red --style classic --size 22.0 --gap 7.0 --thickness 2.0 --opacity 0.75

set -euo pipefail

RUNTIME_DIR="${XDG_RUNTIME_DIR:-/tmp}"
[[ -w "$RUNTIME_DIR" ]] || RUNTIME_DIR="/tmp"
PID_FILE="$RUNTIME_DIR/aim-sight-${UID}.pid"
TRAY_PID_FILE="$RUNTIME_DIR/aim-sight-tray-${UID}.pid"
LEGACY_PID_FILE="${XDG_RUNTIME_DIR:-/tmp}/aim-sight-${UID}.pid"
CONFIG_FILE="${XDG_CONFIG_HOME:-$HOME/.config}/aim-sight.conf"
ACTION="start"
COLOR="${AIM_SIGHT_COLOR:-red}"
STYLE="${AIM_SIGHT_STYLE:-classic}"
SIZE="${AIM_SIGHT_SIZE:-22.0}"
GAP="${AIM_SIGHT_GAP:-7.0}"
THICKNESS="${AIM_SIGHT_THICKNESS:-2.0}"
OPACITY="${AIM_SIGHT_OPACITY:-0.75}"
OUTLINE="${AIM_SIGHT_OUTLINE:-no}"
OUTLINE_THICKNESS="${AIM_SIGHT_OUTLINE_THICKNESS:-1.0}"
DOT="${AIM_SIGHT_DOT:-yes}"
DOT_SIZE="${AIM_SIGHT_DOT_SIZE:-2.0}"

# Create a user-editable config on first run, then load saved settings.
if [[ ! -f "$CONFIG_FILE" ]]; then
    umask 077
    mkdir -p "$(dirname "$CONFIG_FILE")"
    printf '%s\n' \
        '# Aim sight settings. Opacity ranges from 0.1 (faint) to 1.0 (solid).' \
        'STYLE=classic  # classic, t, dot, or plus' \
        'COLOR=red' \
        'SIZE=22.0' \
        'GAP=7.0' \
        'THICKNESS=2.0' \
        'OPACITY=0.75' \
        'OUTLINE=no' \
        'OUTLINE_THICKNESS=1.0' \
        'DOT=yes' \
        'DOT_SIZE=2.0' > "$CONFIG_FILE"
fi

# The config is plain shell-style key=value text. It is created by this script
# and lives in the user config directory.
source "$CONFIG_FILE"

usage() {
    sed -n '2,5p' "$0"
    exit 0
}

while (($#)); do
    case "$1" in
        start|stop|toggle|status|tray) ACTION="$1" ;;
        --color) COLOR="${2:?missing color}"; shift ;;
        --style) STYLE="${2:?missing style}"; shift ;;
        --size) SIZE="${2:?missing size}"; shift ;;
        --gap) GAP="${2:?missing gap}"; shift ;;
        --thickness) THICKNESS="${2:?missing thickness}"; shift ;;
        --opacity) OPACITY="${2:?missing opacity}"; shift ;;
        --dot) DOT="${2:?missing yes/no}"; shift ;;
        --dot-size) DOT_SIZE="${2:?missing dot size}"; shift ;;
        -h|--help) usage ;;
        *) echo "Unknown option: $1" >&2; usage ;;
    esac
    shift
done

overlay_pid() {
    local file pid
    for file in "$PID_FILE" "$LEGACY_PID_FILE"; do
        [[ -r "$file" ]] || continue
        pid="$(<"$file")"
        if [[ "$pid" =~ ^[0-9]+$ ]] && kill -0 "$pid" 2>/dev/null; then
            echo "$pid"
            return 0
        fi
    done
    return 1
}

running() {
    overlay_pid >/dev/null
}

tray_running() {
    [[ -r "$TRAY_PID_FILE" ]] && kill -0 "$(<"$TRAY_PID_FILE")" 2>/dev/null
}

start_tray() {
    tray_running && return 0
    command -v python3 >/dev/null || return 0
    python3 - "$TRAY_PID_FILE" "$CONFIG_FILE" "$0" <<'PY' >>"$RUNTIME_DIR/aim-sight-tray.log" 2>&1 &
import os
import signal
import subprocess
import sys

from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import QApplication, QMenu, QSystemTrayIcon

pid_file, config_file, script = sys.argv[1:]
with open(pid_file, "w") as f:
    f.write(str(os.getpid()))

def cleanup(*_):
    try:
        os.unlink(pid_file)
    except FileNotFoundError:
        pass
    app.quit()

signal.signal(signal.SIGTERM, cleanup)
signal.signal(signal.SIGINT, cleanup)
app = QApplication(sys.argv)
app.setQuitOnLastWindowClosed(False)
icon = QIcon.fromTheme("crosshair")
if icon.isNull():
    icon = QIcon.fromTheme("applications-games")
tray = QSystemTrayIcon(icon)
tray.setToolTip("Aim Sight")
menu = QMenu()
toggle_item = menu.addAction("Toggle Aim Sight")
open_item = menu.addAction("Open aim-sight.conf")
menu.addSeparator()
quit_item = menu.addAction("Quit tray icon")
tray.setContextMenu(menu)

def run_action(action):
    subprocess.Popen([script, action], start_new_session=True)

toggle_item.triggered.connect(lambda: run_action("toggle"))
open_item.triggered.connect(lambda: subprocess.Popen(["xdg-open", config_file]))
quit_item.triggered.connect(cleanup)
tray.activated.connect(lambda reason: run_action("toggle") if reason == QSystemTrayIcon.ActivationReason.Trigger else None)
tray.show()
app.exec()
PY
}

stop_overlay() {
    local file pid
    for file in "$PID_FILE" "$LEGACY_PID_FILE"; do
        [[ -r "$file" ]] || continue
        pid="$(<"$file")"
        [[ "$pid" =~ ^[0-9]+$ ]] || { rm -f "$file" 2>/dev/null || true; continue; }
        kill "$pid" 2>/dev/null || true
        for _ in {1..20}; do
            kill -0 "$pid" 2>/dev/null || break
            sleep 0.05
        done
        # The old Tk signal handler could fail while its event loop was busy.
        if kill -0 "$pid" 2>/dev/null; then kill -KILL "$pid" 2>/dev/null || true; fi
        rm -f "$file" 2>/dev/null || true
    done
}

case "$ACTION" in
    tray)
        if tray_running; then exit 0; fi
        command -v python3 >/dev/null || { echo "python3 is required" >&2; exit 1; }
        start_tray
        wait
        exit 0
        ;;
    stop) stop_overlay; exit 0 ;;
    status) running && echo "aim sight is running (PID $(overlay_pid))" || echo "aim sight is stopped"; exit 0 ;;
    toggle) if running; then stop_overlay; exit 0; fi ;;
esac

# Keep the tray control available even after the overlay is toggled off.
start_tray

if running; then
    echo "aim sight is already running (PID $(<"$PID_FILE"))" >&2
    exit 0
fi

command -v python3 >/dev/null || { echo "python3 is required" >&2; exit 1; }

# XWayland permits exact positioning and a true click-through input region.
# Prefer it when DISPLAY is available, even inside a Wayland session.
if [[ -n "${DISPLAY:-}" ]]; then
    export GDK_BACKEND=x11
fi

python3 - "$PID_FILE" "$COLOR" "$STYLE" "$SIZE" "$GAP" "$THICKNESS" "$OPACITY" "$OUTLINE" "$OUTLINE_THICKNESS" "$DOT" "$DOT_SIZE" "$CONFIG_FILE" <<'PY' &
import atexit
import os
import signal
import sys

import cairo
import gi
gi.require_version("Gdk", "3.0")
gi.require_version("Gtk", "3.0")
from gi.repository import Gdk, GLib, Gtk

pid_file, color_name, style, size, gap, thickness, opacity, outline_name, outline_thickness, dot_name, dot_size, config_file = sys.argv[1:]
size, gap, thickness, outline_thickness, dot_size = map(float, (size, gap, thickness, outline_thickness, dot_size))
opacity = max(0.05, min(1.0, float(opacity)))
outline = outline_name.lower() in ("yes", "true", "1", "on")
dot = dot_name.lower() in ("yes", "true", "1", "on")
config_mtime = None

def remove_pid():
    try:
        os.unlink(pid_file)
    except FileNotFoundError:
        pass

def stop(*_):
    # GTK signal handling can be delayed while a window is being painted.
    # Exiting directly makes `aim-sight.sh stop` dependable.
    remove_pid()
    os._exit(0)

signal.signal(signal.SIGTERM, stop)
signal.signal(signal.SIGINT, stop)
atexit.register(remove_pid)
with open(pid_file, "w") as f:
    f.write(str(os.getpid()))

window = Gtk.Window(type=Gtk.WindowType.TOPLEVEL)
window.set_decorated(False)
window.set_keep_above(True)
window.set_accept_focus(False)
window.set_focus_on_map(False)
window.set_type_hint(Gdk.WindowTypeHint.DOCK)
window.stick()
window.set_skip_taskbar_hint(True)
window.set_skip_pager_hint(True)
window.set_app_paintable(True)

display = Gdk.Display.get_default()
screen = Gdk.Screen.get_default()
visual = screen.get_rgba_visual()
if visual:
    window.set_visual(visual)

rgba = Gdk.RGBA()
if not rgba.parse(color_name):
    rgba.parse("red")
rgba.alpha = opacity

def reload_config():
    global color_name, style, size, gap, thickness, opacity, outline, outline_thickness, dot, dot_size, rgba, diameter, config_mtime
    try:
        mtime = os.stat(config_file).st_mtime_ns
    except FileNotFoundError:
        return True
    if mtime == config_mtime:
        return True
    config_mtime = mtime
    values = {}
    try:
        with open(config_file, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, value = line.split("=", 1)
                values[key.strip()] = value.strip().strip("'\"")
        new_color = values.get("COLOR", color_name)
        new_style = values.get("STYLE", style).lower()
        new_size = float(values.get("SIZE", size))
        new_gap = float(values.get("GAP", gap))
        new_thickness = float(values.get("THICKNESS", thickness))
        new_opacity = max(0.05, min(1.0, float(values.get("OPACITY", opacity))))
        new_outline_name = values.get("OUTLINE", "yes" if outline else "no")
        new_outline = new_outline_name.lower() in ("yes", "true", "1", "on")
        new_outline_thickness = float(values.get("OUTLINE_THICKNESS", outline_thickness))
        new_dot = values.get("DOT", "yes" if dot else "no").lower() in ("yes", "true", "1", "on")
        new_dot_size = float(values.get("DOT_SIZE", dot_size))
        if new_style not in ("classic", "t", "dot", "plus"):
            raise ValueError("invalid style")
        if new_size <= 0 or new_gap < 0 or new_thickness <= 0 or new_outline_thickness < 0 or new_dot_size <= 0:
            raise ValueError("invalid dimensions")
        new_rgba = Gdk.RGBA()
        if not new_rgba.parse(new_color):
            raise ValueError("invalid color")
        new_rgba.alpha = new_opacity
    except (OSError, ValueError):
        return True  # Ignore a partially edited/invalid file until it is fixed.
    color_name, style, size, gap, thickness, opacity, outline, outline_thickness, dot, dot_size, rgba = (
        new_color, new_style, new_size, new_gap, new_thickness, new_opacity,
        new_outline, new_outline_thickness, new_dot, new_dot_size, new_rgba
    )
    diameter = int(round((size * 2) + (gap * 2) + (thickness * 2)))
    if not wayland:
        # set_default_size only affects a window before it is shown. Use
        # resize here so config changes also recenter the live overlay.
        window.resize(diameter, diameter)
        geometry = display.get_primary_monitor().get_geometry()
        window.move(
            geometry.x + (geometry.width - diameter) // 2,
            geometry.y + (geometry.height - diameter) // 2,
        )
    window.queue_draw()
    return True

def draw(widget, cr):
    allocation = widget.get_allocation()
    # Keep the window integer-aligned, but apply the finer half-pixel
    # correction to the drawn crosshair itself.
    c = min(allocation.width, allocation.height) / 2 + 1.0
    half = max(0.5, thickness / 2)
    draw_gap = 0.0 if style == "plus" else gap
    cr.set_operator(0)  # CAIRO_OPERATOR_CLEAR: transparent everywhere
    cr.paint()
    cr.set_operator(1)  # CAIRO_OPERATOR_SOURCE
    show_arms = style != "dot"
    if outline and show_arms:
        ot = outline_thickness
        cr.set_source_rgba(0, 0, 0, rgba.alpha)
        if style != "t":
            cr.rectangle(c - half - ot, c - size - ot, thickness + 2 * ot, size - draw_gap + 2 * ot)
        cr.rectangle(c - half - ot, c + draw_gap - ot, thickness + 2 * ot, size - draw_gap + 2 * ot)
        cr.rectangle(c - size - ot, c - half - ot, size - draw_gap + 2 * ot, thickness + 2 * ot)
        cr.rectangle(c + draw_gap - ot, c - half - ot, size - draw_gap + 2 * ot, thickness + 2 * ot)
        cr.fill()
    if show_arms:
        cr.set_source_rgba(rgba.red, rgba.green, rgba.blue, rgba.alpha)
        if style != "t":
            cr.rectangle(c - half, c - size, thickness, size - draw_gap)
        cr.rectangle(c - half, c + draw_gap, thickness, size - draw_gap)
        cr.rectangle(c - size, c - half, size - draw_gap, thickness)
        cr.rectangle(c + draw_gap, c - half, size - draw_gap, thickness)
        cr.fill()
    if dot:
        radius = dot_size
        if outline:
            cr.set_source_rgba(0, 0, 0, rgba.alpha)
            cr.arc(c, c, radius + outline_thickness, 0, 6.283185307)
            cr.fill()
            cr.set_source_rgba(rgba.red, rgba.green, rgba.blue, rgba.alpha)
        cr.arc(c, c, radius, 0, 6.283185307)
        cr.fill()
    return False

window.connect("draw", draw)
display_name = Gdk.Display.get_default().get_name().lower()
wayland = "wayland" in display_name
diameter = int(round((size * 2) + (gap * 2) + (thickness * 2)))

if wayland:
    # Wayland does not allow clients to position arbitrary windows. A
    # transparent fullscreen surface keeps the crosshair centered.
    window.fullscreen()
else:
    window.set_default_size(diameter, diameter)
    monitor = display.get_primary_monitor()
    geometry = monitor.get_geometry()
    window.move(
        geometry.x + (geometry.width - diameter) // 2,
        geometry.y + (geometry.height - diameter) // 2,
    )

# On X11, make the overlay input-transparent so it cannot steal game clicks.
window.realize()
if not wayland:
    native = window.get_window()
    if native:
        # Bypass the normal WM stacking rules. Wine games can otherwise
        # place their window above ordinary always-on-top windows.
        if hasattr(native, "set_override_redirect"):
            native.set_override_redirect(True)
        if hasattr(native, "input_shape_combine_region"):
            native.input_shape_combine_region(cairo.Region(), 0, 0)
        if hasattr(native, "raise_"):
            native.raise_()

window.show_all()
window.set_keep_above(True)
window.present()

# Check twice per second so edits to the config appear without restarting.
GLib.timeout_add(500, reload_config)

def keep_above():
    # Some Wine game windows repeatedly reset the stacking order.
    window.set_keep_above(True)
    native = window.get_window()
    if native and hasattr(native, "raise_"):
        native.raise_()
    return True

GLib.timeout_add(1000, keep_above)
Gtk.main()
PY

echo "Aim sight started (opacity $OPACITY). Settings: $CONFIG_FILE"
