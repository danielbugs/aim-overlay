#!/usr/bin/env bash
# A simple desktop crosshair overlay for Fedora/Linux.
# Usage: ./aim-sight.sh [start|stop|toggle|status|tray|profiles|save-profile|delete-profile]
# Styles: classic, t, dot, 4dots, plus, diamond, circle.
# Options: --profile NAME --color red --style classic --size 22.0 --gap 7.0 --thickness 2.0 --opacity 0.75
# Save/use a profile: ./aim-sight.sh --style diamond save-profile --profile diamond
# Activate it: ./aim-sight.sh --profile diamond restart

set -euo pipefail

RUNTIME_DIR="${XDG_RUNTIME_DIR:-/tmp}"
[[ -w "$RUNTIME_DIR" ]] || RUNTIME_DIR="/tmp"
PID_FILE="$RUNTIME_DIR/aim-sight-${UID}.pid"
TRAY_PID_FILE="$RUNTIME_DIR/aim-sight-tray-${UID}.pid"
LEGACY_PID_FILE="${XDG_RUNTIME_DIR:-/tmp}/aim-sight-${UID}.pid"
CONFIG_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/aim-sight"
CONFIG_FILE="$CONFIG_DIR/default.conf"
LEGACY_CONFIG_FILE="${XDG_CONFIG_HOME:-$HOME/.config}/aim-sight.conf"
PROFILE_DIR="$CONFIG_DIR/profiles"
ACTION="start"
PROFILE="${AIM_SIGHT_PROFILE:-}"
PROFILE_EXPLICIT=0
LAST_PROFILE=""
COLOR="${AIM_SIGHT_COLOR:-red}"
STYLE="${AIM_SIGHT_STYLE:-classic}"
SIZE="${AIM_SIGHT_SIZE:-22.0}"
GAP="${AIM_SIGHT_GAP:-7.0}"
THICKNESS="${AIM_SIGHT_THICKNESS:-2.0}"
OPACITY="${AIM_SIGHT_OPACITY:-0.75}"
OUTLINE="${AIM_SIGHT_OUTLINE:-no}"
OUTLINE_THICKNESS="${AIM_SIGHT_OUTLINE_THICKNESS:-1.0}"
ANTIALIAS="yes"
DOT="${AIM_SIGHT_DOT:-yes}"
DOT_SIZE="${AIM_SIGHT_DOT_SIZE:-2.0}"
OFFSET_X="${AIM_SIGHT_OFFSET_X:-0.0}"
OFFSET_Y="${AIM_SIGHT_OFFSET_Y:-0.0}"
COLOR_CYCLE="${AIM_SIGHT_COLOR_CYCLE:-red,green,blue,white,yellow}"

# Move the old standalone config into the default profile location when it
# exists. Copying preserves the legacy file as a safe fallback.
if [[ ! -f "$CONFIG_FILE" && -f "$LEGACY_CONFIG_FILE" ]]; then
    umask 077
    mkdir -p "$CONFIG_DIR"
    cp "$LEGACY_CONFIG_FILE" "$CONFIG_FILE"
fi

# Create a user-editable default profile on first run, then load saved settings.
if [[ ! -f "$CONFIG_FILE" ]]; then
    umask 077
    mkdir -p "$CONFIG_DIR"
    TEMPLATE_FILE="$(dirname "$0")/default.conf"
    if [[ -f "$TEMPLATE_FILE" ]]; then
        cp "$TEMPLATE_FILE" "$CONFIG_FILE"
    else
        printf '%s\n' \
            '# Aim sight settings. Opacity ranges from 0.1 (faint) to 1.0 (solid).' \
            'LAST_PROFILE=' \
            'STYLE=classic  # classic, t, dot, 4dots, plus, diamond, or circle' \
            'COLOR=red' \
            'SIZE=22.0' \
            'GAP=7.0' \
            'THICKNESS=2.0' \
            'OPACITY=0.75' \
            'OUTLINE=no' \
            'OUTLINE_THICKNESS=1.0' \
            'ANTIALIAS=yes' \
            'DOT=yes' \
            'DOT_SIZE=2.0' \
            'OFFSET_X=0.0' \
            'OFFSET_Y=0.0' \
            'COLOR_CYCLE=red,green,blue,white,yellow' > "$CONFIG_FILE"
    fi
fi

# The config is plain shell-style key=value text. It is created by this script
# and lives in the user config directory.
source "$CONFIG_FILE"

write_settings() {
    local destination="$1"
    umask 077
    mkdir -p "$(dirname "$destination")"
    printf '%s\n' \
        '# Aim sight profile.' \
        "STYLE=$STYLE" \
        "COLOR=$COLOR" \
        "SIZE=$SIZE" \
        "GAP=$GAP" \
        "THICKNESS=$THICKNESS" \
        "OPACITY=$OPACITY" \
        "OUTLINE=$OUTLINE" \
        "OUTLINE_THICKNESS=$OUTLINE_THICKNESS" \
        "ANTIALIAS=$ANTIALIAS" \
        "DOT=$DOT" \
        "DOT_SIZE=$DOT_SIZE" \
        "OFFSET_X=$OFFSET_X" \
        "OFFSET_Y=$OFFSET_Y" > "$destination"
}

load_profile() {
    [[ -n "$PROFILE" ]] || return 0
    local profile_file="$PROFILE_DIR/$PROFILE.conf"
    if [[ "$PROFILE" == "dots" && ! -f "$profile_file" && -f "$PROFILE_DIR/4dots.conf" ]]; then
        PROFILE="4dots"
        profile_file="$PROFILE_DIR/4dots.conf"
    fi
    [[ -f "$profile_file" ]] || { echo "Profile not found: $PROFILE" >&2; exit 1; }
    source "$profile_file"
}

validate_profile_name() {
    [[ -n "$PROFILE" && "$PROFILE" != */* && "$PROFILE" != .* ]] || {
        echo "Invalid profile name: ${PROFILE:-<empty>}" >&2
        exit 1
    }
}

usage() {
    sed -n '2,7p' "$0"
    exit 0
}

while (($#)); do
    case "$1" in
        start|stop|toggle|status|tray|profiles|save-profile|delete-profile|restart|cycle-color|toggle-dot) ACTION="$1" ;;
        --profile) PROFILE="${2:?missing profile name}"; PROFILE_EXPLICIT=1; shift ;;
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

if [[ -z "$PROFILE" && -n "$LAST_PROFILE" ]]; then
    PROFILE="$LAST_PROFILE"
fi
[[ -n "$PROFILE" ]] && validate_profile_name

case "$ACTION" in
    save-profile|delete-profile|profiles) ;;
    *) load_profile ;;
esac

# A selected profile is also the live config source, so edits to that profile
# continue to hot-reload instead of being replaced by the base config.
ACTIVE_CONFIG_FILE="$CONFIG_FILE"
[[ -n "$PROFILE" ]] && ACTIVE_CONFIG_FILE="$PROFILE_DIR/$PROFILE.conf"

update_setting_file() {
    local destination="$1" key="$2" value="$3" temporary
    temporary="$(mktemp "$CONFIG_DIR/.setting.XXXXXX")"
    awk -v key="$key" -v value="$value" '
        BEGIN { prefix = key "="; updated = 0 }
        index($0, prefix) == 1 { print prefix value; updated = 1; next }
        { print }
        END { if (!updated) print prefix value }
    ' "$destination" > "$temporary"
    mv "$temporary" "$destination"
}

cycle_color() {
    local color next_color="" item
    local -a colors
    IFS=',' read -r -a colors <<< "$COLOR_CYCLE"
    for item in "${colors[@]}"; do
        item="${item//[[:space:]]/}"
        [[ -n "$item" ]] || continue
        if [[ -n "$next_color" ]]; then
            next_color="$item"
            break
        fi
        [[ "$item" == "$COLOR" ]] && next_color="__next__"
    done
    if [[ "$next_color" == "__next__" || -z "$next_color" ]]; then
        for item in "${colors[@]}"; do
            item="${item//[[:space:]]/}"
            [[ -n "$item" ]] && { next_color="$item"; break; }
        done
    fi
    [[ -n "$next_color" ]] || exit 0
    update_setting_file "$ACTIVE_CONFIG_FILE" COLOR "$next_color"
}

toggle_center_dot() {
    local next="yes"
    [[ "$DOT" =~ ^(yes|true|1|on)$ ]] && next="no"
    update_setting_file "$ACTIVE_CONFIG_FILE" DOT "$next"
}

case "$ACTION" in
    profiles)
        mkdir -p "$PROFILE_DIR"
        found=0
        for profile in "$PROFILE_DIR"/*.conf; do
            [[ -e "$profile" ]] || continue
            basename "$profile" .conf
            found=1
        done
        ((found)) || echo "No profiles saved in $PROFILE_DIR"
        exit 0
        ;;
    save-profile)
        [[ -n "$PROFILE" ]] || { echo "Usage: $0 save-profile --profile NAME" >&2; exit 1; }
        write_settings "$PROFILE_DIR/$PROFILE.conf"
        echo "Saved profile '$PROFILE' in $PROFILE_DIR"
        exit 0
        ;;
    delete-profile)
        [[ -n "$PROFILE" ]] || { echo "Usage: $0 delete-profile --profile NAME" >&2; exit 1; }
        profile_file="$PROFILE_DIR/$PROFILE.conf"
        [[ -f "$profile_file" ]] || { echo "Profile not found: $PROFILE" >&2; exit 1; }
        rm -f "$profile_file"
        echo "Deleted profile '$PROFILE'"
        exit 0
        ;;
    cycle-color)
        cycle_color
        exit 0
        ;;
    toggle-dot)
        toggle_center_dot
        exit 0
        ;;
esac

save_last_profile() {
    local temporary
    temporary="$(mktemp "$CONFIG_DIR/.default.conf.XXXXXX")"
    awk -v profile="$PROFILE" '
        BEGIN { updated = 0 }
        /^LAST_PROFILE=/ { print "LAST_PROFILE=" profile; updated = 1; next }
        { print }
        END { if (!updated) print "LAST_PROFILE=" profile }
    ' "$CONFIG_FILE" > "$temporary"
    mv "$temporary" "$CONFIG_FILE"
}

if ((PROFILE_EXPLICIT)) && [[ "$ACTION" == start || "$ACTION" == restart || "$ACTION" == toggle ]]; then
    save_last_profile
fi

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
python3 - "$TRAY_PID_FILE" "$CONFIG_FILE" "$0" "$PROFILE_DIR" <<'PY' >>"$RUNTIME_DIR/aim-sight-tray.log" 2>&1 &
import os
import signal
import subprocess
import sys
import atexit

try:
    import gi
    gi.require_version("Gtk", "3.0")
    gi.require_version("AyatanaAppIndicator3", "0.1")
    from gi.repository import AyatanaAppIndicator3, Gtk
except (ImportError, ValueError) as exc:
    raise RuntimeError("GTK3 Ayatana AppIndicator is required for the KDE tray icon") from exc

pid_file, config_file, script, profile_dir = sys.argv[1:]
icon_file = os.path.join(os.path.dirname(pid_file), "aim-sight-tray.svg")
os.makedirs(profile_dir, exist_ok=True)
with open(pid_file, "w") as f:
    f.write(str(os.getpid()))

shutting_down = False

def cleanup(*_):
    global shutting_down
    if shutting_down:
        return
    shutting_down = True
    # The tray owns the overlay while it is running. Closing the tray must
    # not leave a click-through crosshair process behind.
    try:
        subprocess.run(
            [script, "stop"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
            timeout=3,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        pass
    try:
        os.unlink(pid_file)
    except FileNotFoundError:
        pass
    try:
        os.unlink(icon_file)
    except FileNotFoundError:
        pass
    Gtk.main_quit()

signal.signal(signal.SIGTERM, cleanup)
signal.signal(signal.SIGINT, cleanup)
atexit.register(cleanup)

# Use an explicit icon file rather than a theme name. Ayatana AppIndicator is
# KDE Plasma's StatusNotifier-compatible backend and works on Wayland.
with open(icon_file, "w", encoding="utf-8") as f:
    f.write('''<svg xmlns="http://www.w3.org/2000/svg" width="32" height="32" viewBox="0 0 32 32">
<g fill="none" stroke="#e8edf2" stroke-width="3" stroke-linecap="square">
<path d="M16 3v8M16 21v8M3 16h8M21 16h8"/>
</g><circle cx="16" cy="16" r="2" fill="#2b2f36"/>
</svg>''')

def run_action(action, profile=None):
    command = [script]
    if profile:
        command += ["--profile", profile]
    command += [action]
    subprocess.Popen(command, start_new_session=True)

indicator = AyatanaAppIndicator3.Indicator.new(
    "aim-sight", icon_file, AyatanaAppIndicator3.IndicatorCategory.APPLICATION_STATUS
)
indicator.set_status(AyatanaAppIndicator3.IndicatorStatus.ACTIVE)
indicator.set_icon_full(icon_file, "Aim Sight")

menu = Gtk.Menu()
profiles_menu = Gtk.Menu()
profiles_item = Gtk.MenuItem(label="Profiles")
profiles_item.set_submenu(profiles_menu)
menu.append(profiles_item)

def reload_profiles(*_):
    for child in profiles_menu.get_children():
        profiles_menu.remove(child)
    try:
        profiles = sorted(name[:-5] for name in os.listdir(profile_dir) if name.endswith(".conf"))
    except OSError:
        profiles = []
    if profiles:
        for profile in profiles:
            item = Gtk.MenuItem(label=profile)
            item.connect("activate", lambda _item, name=profile: run_action("restart", name))
            profiles_menu.append(item)
    else:
        item = Gtk.MenuItem(label="No saved profiles")
        item.set_sensitive(False)
        profiles_menu.append(item)
    profiles_menu.show_all()

reload_profiles()

menu.append(Gtk.SeparatorMenuItem())
toggle_item = Gtk.MenuItem(label="Toggle Aim Sight")
toggle_item.connect("activate", lambda *_: run_action("toggle"))
menu.append(toggle_item)
dot_item = Gtk.MenuItem(label="Toggle center dot")
dot_item.connect("activate", lambda *_: run_action("toggle-dot"))
menu.append(dot_item)
color_item = Gtk.MenuItem(label="Cycle color")
color_item.connect("activate", lambda *_: run_action("cycle-color"))
menu.append(color_item)
reload_item = Gtk.MenuItem(label="Reload confs")
reload_item.connect("activate", reload_profiles)
menu.append(reload_item)
restart_item = Gtk.MenuItem(label="Restart app")
restart_item.connect("activate", lambda *_: run_action("restart"))
menu.append(restart_item)

menu.append(Gtk.SeparatorMenuItem())
open_profiles_item = Gtk.MenuItem(label="Open confs folder")
open_profiles_item.connect("activate", lambda *_: subprocess.Popen(["xdg-open", profile_dir]))
menu.append(open_profiles_item)
open_item = Gtk.MenuItem(label="Open default.conf")
open_item.connect("activate", lambda *_: subprocess.Popen(["xdg-open", config_file]))
menu.append(open_item)

menu.append(Gtk.SeparatorMenuItem())
quit_item = Gtk.MenuItem(label="Quit tray icon")
quit_item.connect("activate", cleanup)
menu.append(quit_item)
menu.show_all()
indicator.set_menu(menu)
indicator.set_secondary_activate_target(toggle_item)
Gtk.main()
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
    restart) stop_overlay; ;;
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

python3 - "$PID_FILE" "$COLOR" "$STYLE" "$SIZE" "$GAP" "$THICKNESS" "$OPACITY" "$OUTLINE" "$OUTLINE_THICKNESS" "$ANTIALIAS" "$DOT" "$DOT_SIZE" "$OFFSET_X" "$OFFSET_Y" "$ACTIVE_CONFIG_FILE" <<'PY' &
import atexit
import math
import os
import signal
import sys

import cairo
import gi
gi.require_version("Gdk", "3.0")
gi.require_version("Gtk", "3.0")
from gi.repository import Gdk, GLib, Gtk

pid_file, color_name, style, size, gap, thickness, opacity, outline_name, outline_thickness, antialias_name, dot_name, dot_size, offset_x, offset_y, config_file = sys.argv[1:]
size, gap, thickness, outline_thickness, dot_size, offset_x, offset_y = map(float, (size, gap, thickness, outline_thickness, dot_size, offset_x, offset_y))
opacity = max(0.05, min(1.0, float(opacity)))
outline = outline_name.lower() in ("yes", "true", "1", "on")
antialias = antialias_name.lower() in ("yes", "true", "1", "on")
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
    global color_name, style, size, gap, thickness, opacity, outline, outline_thickness, antialias, dot, dot_size, offset_x, offset_y, rgba, diameter, config_mtime
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
        new_antialias_name = values.get("ANTIALIAS", "yes" if antialias else "no")
        new_antialias = new_antialias_name.lower() in ("yes", "true", "1", "on")
        new_dot = values.get("DOT", "yes" if dot else "no").lower() in ("yes", "true", "1", "on")
        new_dot_size = float(values.get("DOT_SIZE", dot_size))
        new_offset_x = float(values.get("OFFSET_X", offset_x))
        new_offset_y = float(values.get("OFFSET_Y", offset_y))
        if new_style == "dots":
            new_style = "4dots"  # Backward-compatible name.
        if new_style not in ("classic", "t", "dot", "4dots", "plus", "diamond", "circle"):
            raise ValueError("invalid style")
        if (new_size <= 0 or new_gap < 0 or new_thickness <= 0 or new_outline_thickness < 0 or new_dot_size <= 0
                or not math.isfinite(new_offset_x) or not math.isfinite(new_offset_y)):
            raise ValueError("invalid dimensions")
        new_rgba = Gdk.RGBA()
        if not new_rgba.parse(new_color):
            raise ValueError("invalid color")
        new_rgba.alpha = new_opacity
    except (OSError, ValueError):
        return True  # Ignore a partially edited/invalid file until it is fixed.
    color_name, style, size, gap, thickness, opacity, outline, outline_thickness, antialias, dot, dot_size, offset_x, offset_y, rgba = (
        new_color, new_style, new_size, new_gap, new_thickness, new_opacity,
        new_outline, new_outline_thickness, new_antialias, new_dot, new_dot_size, new_offset_x, new_offset_y, new_rgba
    )
    diameter = int(round((size * 2) + (gap * 2) + (thickness * 2)))
    if not wayland:
        # set_default_size only affects a window before it is shown. Use
        # resize here so config changes also recenter the live overlay.
        window.resize(diameter, diameter)
        geometry = display.get_primary_monitor().get_geometry()
        window.move(
            geometry.x + (geometry.width - diameter) // 2 + round(offset_x),
            geometry.y + (geometry.height - diameter) // 2 + round(offset_y),
        )
    window.queue_draw()
    return True

def draw(widget, cr):
    allocation = widget.get_allocation()
    # Use the geometric center; placement corrections are controlled by the
    # configurable offsets below.
    cx = allocation.width / 2
    cy = allocation.height / 2
    if wayland:
        cx += offset_x
        cy += offset_y
    if not antialias:
        # Keep non-antialiased circles/dots symmetric on the pixel grid.
        cx = round(cx * 2) / 2
        cy = round(cy * 2) / 2
    half = max(0.5, thickness / 2)
    draw_gap = 0.0 if style == "plus" else gap
    cr.set_antialias(cairo.Antialias.BEST if antialias else cairo.Antialias.NONE)
    cr.set_operator(0)  # CAIRO_OPERATOR_CLEAR: transparent everywhere
    cr.paint()
    cr.set_operator(1)  # CAIRO_OPERATOR_SOURCE
    show_arms = style not in ("dot", "4dots", "diamond", "circle")
    if style in ("diamond", "circle"):
        if style == "diamond":
            points = ((cx, cy - size), (cx + size, cy), (cx, cy + size), (cx - size, cy))
            cr.move_to(*points[0])
            for point in points[1:] + (points[0],):
                cr.line_to(*point)
            cr.close_path()
        else:
            cr.arc(cx, cy, size, 0, 2 * math.pi)
        if outline:
            cr.set_source_rgba(0, 0, 0, rgba.alpha)
            cr.set_line_width(thickness + 2 * outline_thickness)
            cr.stroke_preserve()
        cr.set_source_rgba(rgba.red, rgba.green, rgba.blue, rgba.alpha)
        cr.set_line_width(thickness)
        cr.stroke()
    if style == "4dots":
        radius = dot_size
        dot_distance = size + gap
        for dot_x, dot_y in ((cx, cy - dot_distance), (cx + dot_distance, cy),
                             (cx, cy + dot_distance), (cx - dot_distance, cy)):
            if outline:
                cr.set_source_rgba(0, 0, 0, rgba.alpha)
                cr.arc(dot_x, dot_y, radius + outline_thickness, 0, 2 * math.pi)
                cr.fill()
            cr.set_source_rgba(rgba.red, rgba.green, rgba.blue, rgba.alpha)
            cr.arc(dot_x, dot_y, radius, 0, 2 * math.pi)
            cr.fill()
    if outline and show_arms:
        ot = outline_thickness
        cr.set_source_rgba(0, 0, 0, rgba.alpha)
        if style != "t":
            cr.rectangle(cx - half - ot, cy - size - ot, thickness + 2 * ot, size - draw_gap + 2 * ot)
        cr.rectangle(cx - half - ot, cy + draw_gap - ot, thickness + 2 * ot, size - draw_gap + 2 * ot)
        cr.rectangle(cx - size - ot, cy - half - ot, size - draw_gap + 2 * ot, thickness + 2 * ot)
        cr.rectangle(cx + draw_gap - ot, cy - half - ot, size - draw_gap + 2 * ot, thickness + 2 * ot)
        cr.fill()
    if show_arms:
        cr.set_source_rgba(rgba.red, rgba.green, rgba.blue, rgba.alpha)
        if style != "t":
            cr.rectangle(cx - half, cy - size, thickness, size - draw_gap)
        cr.rectangle(cx - half, cy + draw_gap, thickness, size - draw_gap)
        cr.rectangle(cx - size, cy - half, size - draw_gap, thickness)
        cr.rectangle(cx + draw_gap, cy - half, size - draw_gap, thickness)
        cr.fill()
    if dot and style != "4dots":
        radius = dot_size
        if outline:
            cr.set_source_rgba(0, 0, 0, rgba.alpha)
            cr.arc(cx, cy, radius + outline_thickness, 0, 2 * math.pi)
            cr.fill()
            cr.set_source_rgba(rgba.red, rgba.green, rgba.blue, rgba.alpha)
        cr.arc(cx, cy, radius, 0, 2 * math.pi)
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
        geometry.x + (geometry.width - diameter) // 2 + round(offset_x),
        geometry.y + (geometry.height - diameter) // 2 + round(offset_y),
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
