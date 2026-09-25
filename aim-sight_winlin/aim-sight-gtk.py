#!/usr/bin/env python3
"""Single-process GTK/Cairo overlay and Ayatana tray backend."""

import math
import os
import signal
import subprocess
import sys

import cairo
import gi

gi.require_version("Gdk", "3.0")
gi.require_version("Gtk", "3.0")
gi.require_version("AyatanaAppIndicator3", "0.1")
from gi.repository import AyatanaAppIndicator3, Gdk, GLib, Gtk


PID_FILE, TRAY_PID_FILE, CONFIG_FILE, PROFILE_DIR, SCRIPT, VISIBLE = sys.argv[1:]
VISIBLE = VISIBLE == "yes"
ICON_FILE = os.path.join(os.path.dirname(TRAY_PID_FILE), "aim-sight-tray.svg")

VALUES = {}
CONFIG_MTIME = None
WINDOW = None
INDICATOR = None
DISPLAY = Gdk.Display.get_default()
if DISPLAY is None:
    raise RuntimeError("GTK could not connect to a graphical display")
WAYLAND = "wayland" in DISPLAY.get_name().lower()
SHUTTING_DOWN = False


def read_config():
    def read_file(path):
        values = {}
        try:
            with open(path, encoding="utf-8") as config:
                for line in config:
                    line = line.strip()
                    if not line or line.startswith("#") or "=" not in line:
                        continue
                    key, value = line.split("=", 1)
                    values[key.strip()] = value.strip().strip("'\"")
        except OSError:
            pass
        return values

    values = read_file(CONFIG_FILE)
    profile = values.get("LAST_PROFILE", "")
    if profile and "/" not in profile and not profile.startswith("."):
        profile_values = read_file(os.path.join(PROFILE_DIR, profile + ".conf"))
        values.update(profile_values)
    return values


def bool_value(value, default=False):
    if value is None:
        return default
    return value.lower() in ("yes", "true", "1", "on")


def write_pid(path):
    with open(path, "w") as pid_file:
        pid_file.write(str(os.getpid()))


def remove_pid(path):
    try:
        os.unlink(path)
    except FileNotFoundError:
        pass


def configure_window():
    global VALUES
    values = read_config()
    style = values.get("STYLE", "classic").lower()
    if style == "dots":
        style = "4dots"
    if style not in ("classic", "t", "dot", "4dots", "plus", "diamond", "circle"):
        style = "classic"
    try:
        size = float(values.get("SIZE", "22.0"))
        gap = float(values.get("GAP", "7.0"))
        thickness = float(values.get("THICKNESS", "2.0"))
        opacity = max(0.05, min(1.0, float(values.get("OPACITY", "0.75"))))
        outline_thickness = float(values.get("OUTLINE_THICKNESS", "1.0"))
        dot_size = float(values.get("DOT_SIZE", "2.0"))
        offset_x = float(values.get("OFFSET_X", "0.0"))
        offset_y = float(values.get("OFFSET_Y", "0.0"))
    except ValueError:
        return False
    if size <= 0 or gap < 0 or thickness <= 0 or outline_thickness < 0 or dot_size <= 0:
        return False
    rgba = Gdk.RGBA()
    if not rgba.parse(values.get("COLOR", "red")):
        return False
    rgba.alpha = opacity
    VALUES = {
        "style": style,
        "size": size,
        "gap": gap,
        "thickness": thickness,
        "opacity": opacity,
        "outline": bool_value(values.get("OUTLINE")),
        "outline_thickness": outline_thickness,
        "antialias": bool_value(values.get("ANTIALIAS"), True),
        "dot": bool_value(values.get("DOT"), True),
        "dot_size": dot_size,
        "offset_x": offset_x,
        "offset_y": offset_y,
        "rgba": rgba,
    }
    diameter = int(round((size * 2) + (gap * 2) + (thickness * 2)))
    if not WAYLAND:
        WINDOW.resize(diameter, diameter)
        geometry = DISPLAY.get_primary_monitor().get_geometry()
        WINDOW.move(
            geometry.x + (geometry.width - diameter) // 2 + round(offset_x),
            geometry.y + (geometry.height - diameter) // 2 + round(offset_y),
        )
    WINDOW.queue_draw()
    return True


def draw(_widget, cr):
    v = VALUES
    allocation = WINDOW.get_allocation()
    cx, cy = allocation.width / 2, allocation.height / 2
    if WAYLAND:
        cx += v["offset_x"]
        cy += v["offset_y"]
    if not v["antialias"]:
        cx, cy = round(cx * 2) / 2, round(cy * 2) / 2
    half = max(0.5, v["thickness"] / 2)
    gap = 0.0 if v["style"] == "plus" else v["gap"]
    color = v["rgba"]
    cr.set_antialias(cairo.Antialias.BEST if v["antialias"] else cairo.Antialias.NONE)
    cr.set_operator(cairo.OPERATOR_CLEAR)
    cr.paint()
    cr.set_operator(cairo.OPERATOR_SOURCE)
    show_arms = v["style"] not in ("dot", "4dots", "diamond", "circle")

    if v["style"] in ("diamond", "circle"):
        if v["style"] == "diamond":
            points = ((cx, cy - v["size"]), (cx + v["size"], cy),
                      (cx, cy + v["size"]), (cx - v["size"], cy))
            cr.move_to(*points[0])
            for point in points[1:] + (points[0],):
                cr.line_to(*point)
            cr.close_path()
        else:
            cr.arc(cx, cy, v["size"], 0, 2 * math.pi)
        if v["outline"]:
            cr.set_source_rgba(0, 0, 0, color.alpha)
            cr.set_line_width(v["thickness"] + 2 * v["outline_thickness"])
            cr.stroke_preserve()
        cr.set_source_rgba(color.red, color.green, color.blue, color.alpha)
        cr.set_line_width(v["thickness"])
        cr.stroke()

    if v["style"] == "4dots":
        distance = v["size"] + v["gap"]
        for dot_x, dot_y in ((cx, cy - distance), (cx + distance, cy),
                             (cx, cy + distance), (cx - distance, cy)):
            if v["outline"]:
                cr.set_source_rgba(0, 0, 0, color.alpha)
                cr.arc(dot_x, dot_y, v["dot_size"] + v["outline_thickness"], 0, 2 * math.pi)
                cr.fill()
            cr.set_source_rgba(color.red, color.green, color.blue, color.alpha)
            cr.arc(dot_x, dot_y, v["dot_size"], 0, 2 * math.pi)
            cr.fill()

    if v["outline"] and show_arms:
        ot = v["outline_thickness"]
        cr.set_source_rgba(0, 0, 0, color.alpha)
        if v["style"] != "t":
            cr.rectangle(cx - half - ot, cy - v["size"] - ot, v["thickness"] + 2 * ot, v["size"] - gap + 2 * ot)
        cr.rectangle(cx - half - ot, cy + gap - ot, v["thickness"] + 2 * ot, v["size"] - gap + 2 * ot)
        cr.rectangle(cx - v["size"] - ot, cy - half - ot, v["size"] - gap + 2 * ot, v["thickness"] + 2 * ot)
        cr.rectangle(cx + gap - ot, cy - half - ot, v["size"] - gap + 2 * ot, v["thickness"] + 2 * ot)
        cr.fill()
    if show_arms:
        cr.set_source_rgba(color.red, color.green, color.blue, color.alpha)
        if v["style"] != "t":
            cr.rectangle(cx - half, cy - v["size"], v["thickness"], v["size"] - gap)
        cr.rectangle(cx - half, cy + gap, v["thickness"], v["size"] - gap)
        cr.rectangle(cx - v["size"], cy - half, v["size"] - gap, v["thickness"])
        cr.rectangle(cx + gap, cy - half, v["size"] - gap, v["thickness"])
        cr.fill()
    if v["dot"] and v["style"] != "4dots":
        if v["outline"]:
            cr.set_source_rgba(0, 0, 0, color.alpha)
            cr.arc(cx, cy, v["dot_size"] + v["outline_thickness"], 0, 2 * math.pi)
            cr.fill()
            cr.set_source_rgba(color.red, color.green, color.blue, color.alpha)
        cr.arc(cx, cy, v["dot_size"], 0, 2 * math.pi)
        cr.fill()
    return False


def set_visible(visible):
    global VISIBLE
    VISIBLE = visible
    if visible:
        configure_window()
        WINDOW.show_all()
        WINDOW.set_keep_above(True)
        write_pid(PID_FILE)
    else:
        WINDOW.hide()
        remove_pid(PID_FILE)


def toggle_overlay(*_args):
    set_visible(not VISIBLE)


def reload_config(*_args):
    if configure_window() and VISIBLE:
        WINDOW.show_all()
    return True


def keep_above():
    if VISIBLE:
        WINDOW.set_keep_above(True)
        native = WINDOW.get_window()
        if native and hasattr(native, "raise_"):
            native.raise_()
    return True


def run_shell_action(action, profile=None):
    command = [SCRIPT]
    if profile:
        command += ["--profile", profile]
    command.append(action)
    subprocess.Popen(command, start_new_session=True)


def cleanup(*_args):
    global SHUTTING_DOWN
    if SHUTTING_DOWN:
        return
    SHUTTING_DOWN = True
    remove_pid(PID_FILE)
    remove_pid(TRAY_PID_FILE)
    remove_pid(ICON_FILE)
    Gtk.main_quit()


def handle_signal(signum, _frame):
    if signum == signal.SIGTERM or signum == signal.SIGINT:
        GLib.idle_add(cleanup)
    elif signum == signal.SIGUSR1:
        GLib.idle_add(toggle_overlay)
    elif signum == signal.SIGUSR2:
        GLib.idle_add(set_visible, False)
    elif signum == signal.SIGHUP:
        GLib.idle_add(reload_config)


def build_tray():
    global INDICATOR
    with open(ICON_FILE, "w", encoding="utf-8") as icon:
        icon.write('''<svg xmlns="http://www.w3.org/2000/svg" width="32" height="32" viewBox="0 0 32 32">
<g fill="none" stroke="#e8edf2" stroke-width="3" stroke-linecap="square">
<path d="M16 3v8M16 21v8M3 16h8M21 16h8"/>
</g><circle cx="16" cy="16" r="2" fill="#2b2f36"/>
</svg>''')
    indicator = AyatanaAppIndicator3.Indicator.new(
        "aim-sight", ICON_FILE, AyatanaAppIndicator3.IndicatorCategory.APPLICATION_STATUS
    )
    # Keep the GI object alive. If it is collected after this function returns,
    # the overlay remains running but the StatusNotifier item disappears.
    INDICATOR = indicator
    indicator.set_status(AyatanaAppIndicator3.IndicatorStatus.ACTIVE)
    indicator.set_icon_full(ICON_FILE, "Aim Sight")
    menu = Gtk.Menu()
    profiles_menu = Gtk.Menu()
    profiles_item = Gtk.MenuItem(label="Profiles")
    profiles_item.set_submenu(profiles_menu)
    menu.append(profiles_item)

    def reload_profiles(*_args):
        for child in profiles_menu.get_children():
            profiles_menu.remove(child)
        try:
            profiles = sorted(name[:-5] for name in os.listdir(PROFILE_DIR) if name.endswith(".conf"))
        except OSError:
            profiles = []
        if profiles:
            for profile in profiles:
                item = Gtk.MenuItem(label=profile)
                item.connect("activate", lambda _item, name=profile: run_shell_action("restart", name))
                profiles_menu.append(item)
        else:
            empty = Gtk.MenuItem(label="No saved profiles")
            empty.set_sensitive(False)
            profiles_menu.append(empty)
        profiles_menu.show_all()

    reload_profiles()
    menu.append(Gtk.SeparatorMenuItem())
    toggle_item = Gtk.MenuItem(label="Toggle Aim Sight")
    toggle_item.connect("activate", toggle_overlay)
    menu.append(toggle_item)
    dot_item = Gtk.MenuItem(label="Toggle center dot")
    dot_item.connect("activate", lambda *_: run_shell_action("toggle-dot"))
    menu.append(dot_item)
    color_item = Gtk.MenuItem(label="Cycle color")
    color_item.connect("activate", lambda *_: run_shell_action("cycle-color"))
    menu.append(color_item)
    reload_item = Gtk.MenuItem(label="Reload confs")
    reload_item.connect("activate", reload_profiles)
    menu.append(reload_item)
    restart_item = Gtk.MenuItem(label="Restart app")
    restart_item.connect("activate", lambda *_: reload_config())
    menu.append(restart_item)
    menu.append(Gtk.SeparatorMenuItem())
    open_profiles_item = Gtk.MenuItem(label="Open confs folder")
    open_profiles_item.connect("activate", lambda *_: subprocess.Popen(["xdg-open", PROFILE_DIR]))
    menu.append(open_profiles_item)
    open_item = Gtk.MenuItem(label="Open default.conf")
    open_item.connect("activate", lambda *_: subprocess.Popen(["xdg-open", CONFIG_FILE]))
    menu.append(open_item)
    menu.append(Gtk.SeparatorMenuItem())
    quit_item = Gtk.MenuItem(label="Quit tray icon")
    quit_item.connect("activate", cleanup)
    menu.append(quit_item)
    menu.show_all()
    indicator.set_menu(menu)
    indicator.connect("activate", toggle_overlay)
    indicator.set_secondary_activate_target(toggle_item)


os.makedirs(PROFILE_DIR, exist_ok=True)
write_pid(TRAY_PID_FILE)
WINDOW = Gtk.Window(type=Gtk.WindowType.TOPLEVEL)
WINDOW.set_decorated(False)
WINDOW.set_keep_above(True)
WINDOW.set_accept_focus(False)
WINDOW.set_focus_on_map(False)
WINDOW.set_type_hint(Gdk.WindowTypeHint.DOCK)
WINDOW.stick()
WINDOW.set_skip_taskbar_hint(True)
WINDOW.set_skip_pager_hint(True)
WINDOW.set_app_paintable(True)
screen = Gdk.Screen.get_default()
visual = screen.get_rgba_visual()
if visual:
    WINDOW.set_visual(visual)
WINDOW.connect("draw", draw)
configure_window()
build_tray()
for signal_number in (signal.SIGTERM, signal.SIGINT, signal.SIGUSR1, signal.SIGUSR2, signal.SIGHUP):
    signal.signal(signal_number, handle_signal)
if WAYLAND:
    WINDOW.fullscreen()
else:
    WINDOW.realize()
    native = WINDOW.get_window()
    if native:
        if hasattr(native, "set_override_redirect"):
            native.set_override_redirect(True)
        if hasattr(native, "input_shape_combine_region"):
            native.input_shape_combine_region(cairo.Region(), 0, 0)
        if hasattr(native, "raise_"):
            native.raise_()
GLib.timeout_add(500, reload_config)
GLib.timeout_add(1000, keep_above)
if VISIBLE:
    set_visible(True)
else:
    WINDOW.hide()
Gtk.main()
