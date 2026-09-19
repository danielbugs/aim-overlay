#!/usr/bin/env python3
"""Cross-platform Aim Sight tray overlay for Windows and Linux.

Requires: PySide6 (``python -m pip install PySide6``)
"""

from __future__ import annotations

import argparse
import math
import os
import re
import signal
import subprocess
import sys
import time
from pathlib import Path

from PySide6.QtCore import QPointF, QRect, Qt, QTimer
from PySide6.QtGui import QColor, QIcon, QPainter, QPainterPath, QPen, QPixmap
from PySide6.QtWidgets import QApplication, QMenu, QSystemTrayIcon, QWidget


if os.name == "nt":
    APP_DIR = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming")) / "aim-sight"
else:
    APP_DIR = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "aim-sight"
CONFIG_FILE = APP_DIR / "default.conf"
PROFILE_DIR = APP_DIR / "profiles"
if os.name == "nt":
    PID_FILE = Path(os.environ.get("LOCALAPPDATA", os.environ.get("TEMP", os.environ.get("TMP", "/tmp")))) / "aim-sight.pid"
else:
    PID_FILE = Path(os.environ.get("XDG_RUNTIME_DIR", "/tmp")) / f"aim-sight-{os.getuid()}.pid"
LEGACY_CONFIG_FILE = Path.home() / ".config" / "aim-sight.conf"

DEFAULTS = {
    "LAST_PROFILE": "",
    "STYLE": "t",
    "COLOR": "white",
    "SIZE": "7.0",
    "GAP": "2.0",
    "THICKNESS": "0.7",
    "OPACITY": "0.9",
    "OUTLINE": "yes",
    "OUTLINE_THICKNESS": "0.6",
    "DOT": "no",
    "DOT_SIZE": "1.0",
    "OFFSET_X": "1.0",
    "OFFSET_Y": "1.0",
    "COLOR_CYCLE": "red,green,blue,white,yellow",
}
STYLES = {"classic", "t", "dot", "4dots", "dots", "plus", "diamond", "circle"}


def bool_value(value: str) -> bool:
    return value.strip().lower() in {"yes", "true", "1", "on"}


def read_conf(path: Path) -> dict[str, str]:
    values = {}
    if not path.exists():
        return values
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip("'\"")
    return values


def write_conf(path: Path, values: dict[str, str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = ["# Aim sight profile."]
    lines += [f"{key}={values.get(key, DEFAULTS[key])}" for key in DEFAULTS if key != "LAST_PROFILE"]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def ensure_config() -> None:
    APP_DIR.mkdir(parents=True, exist_ok=True)
    if not CONFIG_FILE.exists() and os.name != "nt" and LEGACY_CONFIG_FILE.exists():
        CONFIG_FILE.write_text(LEGACY_CONFIG_FILE.read_text(encoding="utf-8"), encoding="utf-8")
    if not CONFIG_FILE.exists():
        template = Path(__file__).with_name("default.conf")
        if template.exists():
            CONFIG_FILE.write_text(template.read_text(encoding="utf-8"), encoding="utf-8")
        else:
            write_conf(CONFIG_FILE, DEFAULTS)


def profile_path(name: str) -> Path:
    windows_reserved = {"con", "prn", "aux", "nul", *(f"com{i}" for i in range(1, 10)), *(f"lpt{i}" for i in range(1, 10))}
    if (not name or name.startswith(".") or name in {".", ".."}
            or re.search(r'[<>:"/\\|?*\x00-\x1f]', name)
            or (os.name == "nt" and name.rstrip(" .").lower() in windows_reserved)):
        raise ValueError(f"Invalid profile name: {name or '<empty>'}")
    return PROFILE_DIR / f"{name}.conf"


def update_last_profile(name: str) -> None:
    values = read_conf(CONFIG_FILE)
    values["LAST_PROFILE"] = name
    lines = CONFIG_FILE.read_text(encoding="utf-8").splitlines() if CONFIG_FILE.exists() else []
    replaced = False
    output = []
    for line in lines:
        if line.strip().startswith("LAST_PROFILE="):
            output.append(f"LAST_PROFILE={name}")
            replaced = True
        else:
            output.append(line)
    if not replaced:
        output.append(f"LAST_PROFILE={name}")
    CONFIG_FILE.write_text("\n".join(output) + "\n", encoding="utf-8")


def effective_settings(profile: str | None = None, overrides: dict | None = None) -> tuple[dict[str, str], str]:
    ensure_config()
    values = DEFAULTS | read_conf(CONFIG_FILE)
    selected = profile or values.get("LAST_PROFILE", "")
    if selected:
        values |= read_conf(profile_path(selected))
    if overrides:
        values.update({key: str(value) for key, value in overrides.items() if value is not None})
    if values.get("STYLE", "").lower() == "dots":
        values["STYLE"] = "4dots"
    if values.get("STYLE", "").lower() not in STYLES:
        raise ValueError(f"Invalid style: {values.get('STYLE')}")
    return values, selected


def active_config_path(profile: str) -> Path:
    return profile_path(profile) if profile else CONFIG_FILE


def update_setting(path: Path, key: str, value: str) -> None:
    lines = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
    prefix = f"{key}="
    output = []
    replaced = False
    for line in lines:
        if line.startswith(prefix):
            output.append(f"{prefix}{value}")
            replaced = True
        else:
            output.append(line)
    if not replaced:
        output.append(f"{prefix}{value}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(output) + "\n", encoding="utf-8")


def cycle_color(values: dict[str, str], profile: str) -> None:
    colors = [item.strip() for item in values.get("COLOR_CYCLE", DEFAULTS["COLOR_CYCLE"]).split(",") if item.strip()]
    if not colors:
        return
    try:
        next_color = colors[(colors.index(values.get("COLOR", "")) + 1) % len(colors)]
    except ValueError:
        next_color = colors[0]
    update_setting(active_config_path(profile), "COLOR", next_color)


def toggle_dot(values: dict[str, str], profile: str) -> None:
    next_value = "no" if bool_value(values.get("DOT", "no")) else "yes"
    update_setting(active_config_path(profile), "DOT", next_value)


def pid_running() -> bool:
    try:
        pid = int(PID_FILE.read_text())
        os.kill(pid, 0)
        return True
    except (OSError, ValueError, FileNotFoundError):
        return False


def stop_process() -> None:
    try:
        pid = int(PID_FILE.read_text())
    except (OSError, ValueError):
        PID_FILE.unlink(missing_ok=True)
        return
    if os.name == "nt":
        subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    else:
        try:
            os.kill(pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
    for _ in range(30):
        if not pid_running():
            break
        time.sleep(0.05)
    PID_FILE.unlink(missing_ok=True)


def start_process(overrides: dict[str, str] | None = None, profile: str = "") -> None:
    if pid_running():
        print(f"aim sight is already running (PID {PID_FILE.read_text().strip()})")
        return
    kwargs = {"start_new_session": True}
    if os.name == "nt":
        kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS
        kwargs.pop("start_new_session", None)
    command = [sys.executable, str(Path(__file__).resolve()), "tray"]
    if profile:
        command += ["--profile", profile]
    option_names = {
        "STYLE": "--style", "COLOR": "--color", "SIZE": "--size",
        "GAP": "--gap", "THICKNESS": "--thickness", "OPACITY": "--opacity",
        "DOT": "--dot", "DOT_SIZE": "--dot-size",
    }
    for key, option in option_names.items():
        if overrides and key in overrides:
            command += [option, overrides[key]]
    subprocess.Popen(command, **kwargs)


class Overlay(QWidget):
    def __init__(self, values: dict[str, str], profile: str):
        super().__init__()
        self.values = values
        self.profile = profile
        self.config_mtime = 0
        self.wayland = bool(os.environ.get("WAYLAND_DISPLAY"))
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Tool | Qt.WindowType.WindowStaysOnTopHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        # Apply command-line overrides on first launch. Subsequent reloads read
        # the selected config file, matching the shell implementation.
        self.reload(overrides=values)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.reload_if_changed)
        self.timer.start(500)

    def reload_if_changed(self) -> None:
        source = profile_path(self.profile) if self.profile else CONFIG_FILE
        try:
            mtime = source.stat().st_mtime_ns
        except FileNotFoundError:
            return
        if mtime != self.config_mtime:
            self.reload()

    def reload(self, profile: str | None = None, overrides: dict | None = None) -> None:
        if profile is not None:
            self.profile = profile
        self.values, selected = effective_settings(self.profile or None, overrides)
        self.profile = selected
        source = profile_path(self.profile) if self.profile else CONFIG_FILE
        self.config_mtime = source.stat().st_mtime_ns if source.exists() else 0
        size = float(self.values["SIZE"])
        gap = float(self.values["GAP"])
        dot_size = max(1.0, float(self.values["DOT_SIZE"]))
        # DOT_SIZE is a radius.  Include the outermost 4-dot and outline
        # pixels when sizing the window so offsets never move artwork into
        # the window edge and make it appear to change size.
        extent = max(size, size + gap + dot_size) + float(self.values["OUTLINE_THICKNESS"])
        diameter = max(32, math.ceil(extent * 2 + float(self.values["THICKNESS"])))
        if self.wayland:
            self.showFullScreen()
        else:
            # availableGeometry() excludes areas reserved by the taskbar. On
            # Windows that moves its center above the game's actual center.
            screen = QApplication.primaryScreen().geometry()
            self.setGeometry(QRect(
                screen.center().x() - diameter // 2 + round(float(self.values["OFFSET_X"])),
                screen.center().y() - diameter // 2 + round(float(self.values["OFFSET_Y"])),
                diameter,
                diameter,
            ))
            self.show()
        self.update()

    def square(self, painter: QPainter, x: float, y: float, side: float, color: QColor) -> None:
        painter.fillRect(QRect(int(round(x - side / 2)), int(round(y - side / 2)), max(1, int(round(side))), max(1, int(round(side)))), color)

    def paintEvent(self, _event) -> None:
        values = self.values
        color = QColor(values["COLOR"])
        color.setAlphaF(max(0.05, min(1.0, float(values["OPACITY"]))))
        outline = bool_value(values["OUTLINE"])
        outline_width = float(values["OUTLINE_THICKNESS"])
        thickness = float(values["THICKNESS"])
        size = float(values["SIZE"])
        gap = float(values["GAP"])
        dot_size = max(1.0, float(values["DOT_SIZE"]))
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.fillRect(self.rect(), Qt.GlobalColor.transparent)
        cx, cy = self.width() / 2, self.height() / 2
        if self.wayland:
            cx += float(values["OFFSET_X"])
            cy += float(values["OFFSET_Y"])
        style = values["STYLE"].lower()

        def square(x, y, side, fill):
            self.square(painter, x, y, side, fill)

        def rect(x, y, width, height, fill):
            painter.fillRect(
                QRect(int(round(x - width / 2)), int(round(y - height / 2)),
                      max(1, int(round(width))), max(1, int(round(height)))), fill
            )

        def dot(x, y):
            if outline:
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(QColor(0, 0, 0, color.alpha()))
                painter.drawEllipse(QPointF(x, y), dot_size + outline_width, dot_size + outline_width)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(color)
            painter.drawEllipse(QPointF(x, y), dot_size, dot_size)

        if style == "4dots":
            distance = size + gap
            for x, y in ((cx, cy - distance), (cx + distance, cy), (cx, cy + distance), (cx - distance, cy)):
                dot(x, y)
        elif style in {"diamond", "circle"}:
            painter.setPen(QPen(QColor(0, 0, 0, color.alpha()), thickness + 2 * outline_width if outline else thickness))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            if style == "diamond":
                path = QPainterPath(QPointF(cx, cy - size))
                for point in ((cx + size, cy), (cx, cy + size), (cx - size, cy)):
                    path.lineTo(*point)
                path.closeSubpath()
                painter.drawPath(path)
            else:
                painter.drawEllipse(QPointF(cx, cy), size, size)
            if outline:
                painter.setPen(QPen(color, thickness))
                if style == "diamond":
                    painter.drawPath(path)
                else:
                    painter.drawEllipse(QPointF(cx, cy), size, size)
        elif style != "dot":
            arm_gap = 0 if style == "plus" else gap
            painter.setPen(Qt.PenStyle.NoPen)
            if outline:
                black = QColor(0, 0, 0, color.alpha())
                if style != "t": rect(cx, cy - size / 2 - arm_gap / 2, thickness + 2 * outline_width, size - arm_gap + 2 * outline_width, black)
                rect(cx, cy + size / 2 + arm_gap / 2, thickness + 2 * outline_width, size - arm_gap + 2 * outline_width, black)
                rect(cx - size / 2 - arm_gap / 2, cy, size - arm_gap + 2 * outline_width, thickness + 2 * outline_width, black)
                rect(cx + size / 2 + arm_gap / 2, cy, size - arm_gap + 2 * outline_width, thickness + 2 * outline_width, black)
            if style != "t": rect(cx, cy - size / 2 - arm_gap / 2, thickness, size - arm_gap, color)
            rect(cx, cy + size / 2 + arm_gap / 2, thickness, size - arm_gap, color)
            rect(cx - size / 2 - arm_gap / 2, cy, size - arm_gap, thickness, color)
            rect(cx + size / 2 + arm_gap / 2, cy, size - arm_gap, thickness, color)
        if bool_value(values["DOT"]) and style != "dots":
            dot(cx, cy)
        painter.end()


class TrayApp:
    def __init__(self, values: dict[str, str], profile: str):
        self.app = QApplication.instance()
        self.profile = profile
        self.overlay = Overlay(values, profile)
        self.pid_written = False
        PID_FILE.parent.mkdir(parents=True, exist_ok=True)
        PID_FILE.write_text(str(os.getpid()))
        self.icon = self.make_icon()
        self.tray = QSystemTrayIcon(self.icon)
        self.tray.setToolTip("Aim Sight")
        self.menu = QMenu()
        self.tray.setContextMenu(self.menu)
        self.populate_menu()
        self.tray.show()

    @staticmethod
    def make_icon() -> QIcon:
        pixmap = QPixmap(32, 32)
        pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pixmap)
        painter.setPen(QPen(QColor("#e8edf2"), 3))
        painter.drawLine(16, 3, 16, 11)
        painter.drawLine(16, 21, 16, 29)
        painter.drawLine(3, 16, 11, 16)
        painter.drawLine(21, 16, 29, 16)
        painter.end()
        return QIcon(pixmap)

    def populate_menu(self) -> None:
        self.menu.clear()
        toggle = self.menu.addAction("Toggle Aim Sight")
        toggle.triggered.connect(lambda: self.overlay.setVisible(not self.overlay.isVisible()))
        self.menu.addAction("Open default.conf", lambda: open_path(CONFIG_FILE))
        self.menu.addAction("Open profiles folder", lambda: open_path(PROFILE_DIR))
        profiles = self.menu.addMenu("Profiles")
        PROFILE_DIR.mkdir(parents=True, exist_ok=True)
        names = sorted(path.stem for path in PROFILE_DIR.glob("*.conf"))
        if names:
            for name in names:
                profiles.addAction(name, lambda name=name: self.select_profile(name))
        else:
            empty = profiles.addAction("No saved profiles")
            empty.setEnabled(False)
        self.menu.addSeparator()
        self.menu.addAction("Restart Aim Sight", self.restart_overlay)
        self.menu.addAction("Reload profiles", self.populate_menu)
        self.menu.addSeparator()
        self.menu.addAction("Quit tray icon", self.quit)

    def select_profile(self, name: str) -> None:
        update_last_profile(name)
        self.overlay.reload(name)

    def restart_overlay(self) -> None:
        self.overlay.reload(self.profile or None)

    def quit(self, remove_pid: bool = True) -> None:
        self.overlay.close()
        self.tray.hide()
        if remove_pid:
            PID_FILE.unlink(missing_ok=True)
        self.app.quit()


def open_path(path: Path) -> None:
    if os.name == "nt":
        os.startfile(str(path))  # type: ignore[attr-defined]
    elif sys.platform == "darwin":
        subprocess.Popen(["open", str(path)])
    else:
        subprocess.Popen(["xdg-open", str(path)])


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Cross-platform Aim Sight overlay")
    parser.add_argument("action", nargs="?", choices=("start", "stop", "toggle", "status", "tray", "restart", "profiles", "save-profile", "delete-profile", "cycle-color", "toggle-dot"), default="start")
    parser.add_argument("--profile")
    parser.add_argument("--style", choices=sorted(STYLES))
    parser.add_argument("--color")
    parser.add_argument("--size")
    parser.add_argument("--gap")
    parser.add_argument("--thickness")
    parser.add_argument("--opacity")
    parser.add_argument("--dot", choices=("yes", "no", "true", "false", "1", "0", "on", "off"))
    parser.add_argument("--dot-size")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    ensure_config()
    if args.action == "profiles":
        PROFILE_DIR.mkdir(parents=True, exist_ok=True)
        print("\n".join(sorted(path.stem for path in PROFILE_DIR.glob("*.conf"))) or f"No profiles saved in {PROFILE_DIR}")
        return 0
    if args.action in {"save-profile", "delete-profile"} and not args.profile:
        raise SystemExit(f"{args.action} requires --profile NAME")
    if args.profile:
        profile_path(args.profile)  # Validate before touching the filesystem.
    if args.action == "delete-profile":
        profile_path(args.profile).unlink(missing_ok=False)
        print(f"Deleted profile '{args.profile}'")
        return 0
    overrides = {key: getattr(args, option) for option, key in (("style", "STYLE"), ("color", "COLOR"), ("size", "SIZE"), ("gap", "GAP"), ("thickness", "THICKNESS"), ("opacity", "OPACITY"), ("dot", "DOT"), ("dot_size", "DOT_SIZE"))}
    overrides = {key: value for key, value in overrides.items() if value is not None}

    # The shell version saves the current command-line/base settings; it does
    # not first load the profile being created.
    if args.action == "save-profile":
        values = DEFAULTS | read_conf(CONFIG_FILE)
        values.update(overrides)
        write_conf(profile_path(args.profile), values)
        print(f"Saved profile '{args.profile}'")
        return 0

    values, selected = effective_settings(args.profile, overrides)
    if args.action == "cycle-color":
        cycle_color(values, selected)
        return 0
    if args.action == "toggle-dot":
        toggle_dot(values, selected)
        return 0
    if args.profile and args.action in {"start", "restart", "toggle"}:
        update_last_profile(args.profile)
    if args.action == "status":
        print("aim sight is running" if pid_running() else "aim sight is stopped")
    elif args.action == "stop":
        stop_process()
    elif args.action == "toggle":
        stop_process() if pid_running() else start_process(overrides, selected)
    elif args.action == "restart":
        stop_process()
        start_process(overrides, selected)
    elif args.action == "start":
        start_process(overrides, selected)
    elif args.action == "tray":
        app = QApplication(sys.argv)
        tray = TrayApp(values, selected)
        signal.signal(signal.SIGTERM, lambda *_: tray.quit())
        signal.signal(signal.SIGINT, lambda *_: tray.quit())
        return app.exec()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
