"""A dependency-free Windows crosshair overlay.

Run with:  py crosshair_overlay.py
Controls: F6 swap shape, F8 toggle, F7 reload config, F9 restart. Right-click the system
tray icon for colour, size, shape, and exit controls.
"""

from __future__ import annotations

import ctypes
from ctypes import wintypes
import json
from pathlib import Path
import queue
import threading
import tkinter as tk


CONFIG_PATH = Path(__file__).with_name("crosshair.config.json")
ICON_PATH = Path(__file__).with_name("crosshair.ico")
DEFAULT_CONFIG = {
    "ArmLength": 18,
    "Gap": 4,
    "LineThickness": 2,
    "Color": "#00FF00",
    "OutlineColor": "#000000",
    "OutlineThickness": 1,
    "CenterDotSize": 4,
    "ShowCenterDot": True,
    "Style": "classic",
    # Optional per-style overrides. Any omitted setting falls back to the
    # top-level value above.
    "StyleProfiles": {},
    # With an odd-sized reticle on an even-sized display, the closest pixel is
    # naturally 0.5 px above-left of the mathematical display centre.
    "OffsetX": 0,
    "OffsetY": 0,
}
COLOURS = ["#00FF00", "#FF0000", "#00FFFF", "#FFFFFF", "#FFFF00"]

WM_HOTKEY = 0x0312
WM_APP = 0x8000
WM_LBUTTONUP = 0x0202
WM_RBUTTONUP = 0x0205
WM_DISPLAYCHANGE = 0x007E
MOD_NOREPEAT = 0x4000
VK_F6, VK_F7, VK_F8, VK_F9 = range(0x75, 0x79)
HOTKEYS = {1: VK_F8, 2: VK_F7, 3: VK_F6, 4: VK_F9}
GWL_EXSTYLE = -20
GWLP_WNDPROC = -4
WS_EX_TRANSPARENT = 0x20
WS_EX_NOACTIVATE = 0x08000000
WM_NCHITTEST = 0x0084
HTTRANSPARENT = -1
PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
SM_CXSCREEN, SM_CYSCREEN = 0, 1
TRANSPARENT_COLOUR = "#ff00ff"
TRAY_CALLBACK_MESSAGE = WM_APP + 1
NIM_ADD, NIM_DELETE = 0x00000000, 0x00000002
NIF_MESSAGE, NIF_ICON, NIF_TIP = 0x00000001, 0x00000002, 0x00000004
IDI_APPLICATION = 32512
IMAGE_ICON = 1
LR_LOADFROMFILE, LR_DEFAULTSIZE = 0x0010, 0x0040
MF_STRING, MF_POPUP, MF_SEPARATOR, MF_CHECKED = 0x00000000, 0x00000010, 0x00000800, 0x00000008
TPM_LEFTALIGN, TPM_BOTTOMALIGN, TPM_RETURNCMD = 0x0000, 0x0020, 0x0100
MENU_TOGGLE, MENU_RELOAD, MENU_RESTART, MENU_NEXT_SIZE, MENU_DOT, MENU_EXIT = (
    100, 101, 102, 103, 104, 105
)
MENU_COLOUR_BASE = 200
MENU_STYLE_BASE = 300
STYLES = ["classic", "plus", "dot", "t", "four_dots"]
STYLE_LABELS = ["Classic", "Plus", "Dot", "T", "Four dots"]

user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32
shell32 = ctypes.windll.shell32
user32.CreatePopupMenu.restype = wintypes.HANDLE
user32.AppendMenuW.argtypes = [wintypes.HANDLE, wintypes.UINT, ctypes.c_size_t, wintypes.LPCWSTR]
user32.AppendMenuW.restype = wintypes.BOOL
user32.DestroyMenu.argtypes = [wintypes.HANDLE]
user32.LoadIconW.argtypes = [wintypes.HANDLE, ctypes.c_void_p]
user32.LoadIconW.restype = wintypes.HANDLE
user32.LoadImageW.argtypes = [
    wintypes.HANDLE, wintypes.LPCWSTR, wintypes.UINT,
    ctypes.c_int, ctypes.c_int, wintypes.UINT,
]
user32.LoadImageW.restype = wintypes.HANDLE
user32.DestroyIcon.argtypes = [wintypes.HANDLE]
shell32.Shell_NotifyIconW.argtypes = [wintypes.DWORD, ctypes.c_void_p]
shell32.Shell_NotifyIconW.restype = wintypes.BOOL
user32.GetWindowLongPtrW.argtypes = [wintypes.HWND, ctypes.c_int]
user32.GetWindowLongPtrW.restype = ctypes.c_ssize_t
user32.SetWindowLongPtrW.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_ssize_t]
user32.SetWindowLongPtrW.restype = ctypes.c_ssize_t
user32.CallWindowProcW.argtypes = [
    ctypes.c_ssize_t,
    wintypes.HWND,
    wintypes.UINT,
    wintypes.WPARAM,
    wintypes.LPARAM,
]
user32.CallWindowProcW.restype = ctypes.c_ssize_t
user32.GetForegroundWindow.restype = wintypes.HWND
user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
user32.GetWindowThreadProcessId.restype = wintypes.DWORD
user32.ShowCursor.argtypes = [wintypes.BOOL]
user32.ShowCursor.restype = ctypes.c_int
kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
kernel32.OpenProcess.restype = wintypes.HANDLE
kernel32.QueryFullProcessImageNameW.argtypes = [wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR, ctypes.POINTER(wintypes.DWORD)]
kernel32.QueryFullProcessImageNameW.restype = wintypes.BOOL
kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
kernel32.CloseHandle.restype = wintypes.BOOL

WNDPROC = ctypes.WINFUNCTYPE(
    ctypes.c_ssize_t,
    wintypes.HWND,
    wintypes.UINT,
    wintypes.WPARAM,
    wintypes.LPARAM,
)


class POINT(ctypes.Structure):
    _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]


class NOTIFYICONDATAW(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.DWORD),
        ("hWnd", wintypes.HWND),
        ("uID", wintypes.UINT),
        ("uFlags", wintypes.UINT),
        ("uCallbackMessage", wintypes.UINT),
        ("hIcon", wintypes.HANDLE),
        ("szTip", wintypes.WCHAR * 128),
        ("dwState", wintypes.DWORD),
        ("dwStateMask", wintypes.DWORD),
        ("szInfo", wintypes.WCHAR * 256),
        ("uVersion", wintypes.UINT),
        ("szInfoTitle", wintypes.WCHAR * 64),
        ("dwInfo", wintypes.DWORD),
        ("guidItem", ctypes.c_byte * 16),
        ("hBalloonIcon", wintypes.HANDLE),
    ]


# These declarations follow the structures above because ctypes resolves the
# pointer type when this module is imported.
user32.GetCursorPos.argtypes = [ctypes.POINTER(POINT)]
user32.GetCursorPos.restype = wintypes.BOOL
user32.TrackPopupMenu.argtypes = [
    wintypes.HANDLE, wintypes.UINT, ctypes.c_int, ctypes.c_int, ctypes.c_int,
    wintypes.HWND, ctypes.c_void_p,
]
user32.TrackPopupMenu.restype = wintypes.UINT


class CrosshairOverlay:
    def __init__(self) -> None:
        self.config = self.load_config()
        self.colour_index = self.get_colour_index()
        self.visible = True
        self.events: queue.Queue[int] = queue.Queue()
        self.stop_hotkeys = threading.Event()
        self.hotkey_thread_id = 0
        # Keep these alive for the lifetime of the Tk window.  If the callback
        # were garbage-collected, Windows could call an invalid function pointer.
        self._original_wndproc: int | None = None
        self._wndproc: WNDPROC | None = None
        self._tray_icon: NOTIFYICONDATAW | None = None
        self._custom_tray_icon = False
        self._cursor_hidden_for_game = False

        self.root = tk.Tk()
        self.root.withdraw()
        self.root.overrideredirect(True)
        self.root.attributes("-topmost", True)
        self.root.configure(bg=TRANSPARENT_COLOUR)
        # This Tk option maps the chosen colour to an alpha-zero colour on Windows.
        self.root.wm_attributes("-transparentcolor", TRANSPARENT_COLOUR)
        self.canvas = tk.Canvas(self.root, highlightthickness=0, bd=0, bg=TRANSPARENT_COLOUR)
        self.canvas.pack()
        self.root.update_idletasks()
        self.make_click_through()
        self.add_tray_icon()
        self.redraw()
        self.root.deiconify()
        self.root.after(25, self.process_events)
        self.root.after(100, self.update_game_cursor)
        threading.Thread(target=self.hotkey_loop, daemon=True).start()

    def load_config(self) -> dict:
        if not CONFIG_PATH.exists():
            CONFIG_PATH.write_text(json.dumps(DEFAULT_CONFIG, indent=2) + "\n", encoding="utf-8")
            return DEFAULT_CONFIG.copy()
        try:
            saved = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
            if not isinstance(saved, dict):
                raise ValueError("Configuration must be an object")
            config = {key: saved.get(key, value) for key, value in DEFAULT_CONFIG.items()}
            profiles = config.get("StyleProfiles")
            config["StyleProfiles"] = profiles if isinstance(profiles, dict) else {}
            return config
        except (OSError, ValueError, json.JSONDecodeError):
            return DEFAULT_CONFIG.copy()

    def get_colour_index(self) -> int:
        colour = str(self.style_config()["Color"]).upper()
        try:
            return [item.upper() for item in COLOURS].index(colour)
        except ValueError:
            return 0

    def numeric(self, name: str, minimum: float = 0, config: dict | None = None) -> float:
        settings = self.config if config is None else config
        try:
            return max(minimum, float(settings[name]))
        except (TypeError, ValueError):
            return float(DEFAULT_CONFIG[name])

    def style(self) -> str:
        value = str(self.config.get("Style", "classic")).strip().lower()
        return value if value in set(STYLES) else "classic"

    def style_config(self) -> dict:
        """Return top-level settings merged with the active style profile."""
        profile = self.config.get("StyleProfiles", {}).get(self.style(), {})
        if not isinstance(profile, dict):
            profile = {}
        merged = dict(self.config)
        merged.update(profile)
        return merged

    def show_centre_dot(self, config: dict | None = None) -> bool:
        settings = self.config if config is None else config
        value = settings.get("ShowCenterDot", True)
        if isinstance(value, str):
            return value.strip().lower() not in {"false", "0", "no", "off"}
        return bool(value)

    def set_style_setting(self, name: str, value: object) -> None:
        profiles = self.config.setdefault("StyleProfiles", {})
        profile = profiles.setdefault(self.style(), {})
        if isinstance(profile, dict):
            profile[name] = value

    def redraw(self) -> None:
        settings = self.style_config()
        arm = self.numeric("ArmLength", config=settings)
        gap = self.numeric("Gap", config=settings)
        thickness = self.numeric("LineThickness", 1, config=settings)
        outline = self.numeric("OutlineThickness", config=settings)
        dot_size = self.numeric("CenterDotSize", config=settings)
        padding = thickness + outline + 4
        # An odd canvas gives every shape an exact integer centre pixel.  This
        # avoids half-pixel line placement, especially with very small sizes.
        size = round(2 * (arm + gap + padding)) + 1
        centre = size // 2
        colour = str(settings["Color"])
        outline_colour = str(settings["OutlineColor"])
        style = self.style()

        self.canvas.configure(width=size, height=size)
        self.root.geometry(f"{size}x{size}+0+0")
        self.canvas.delete("all")
        classic_segments = [
            (centre - gap - arm, centre, centre - gap, centre),
            (centre + gap, centre, centre + gap + arm, centre),
            (centre, centre - gap - arm, centre, centre - gap),
            (centre, centre + gap, centre, centre + gap + arm),
        ]
        if style == "classic":
            segments = classic_segments
        elif style == "plus":
            # A plus is a continuous cross, with no centre gap.
            segments = [
                (centre - gap - arm, centre, centre + gap + arm, centre),
                (centre, centre - gap - arm, centre, centre + gap + arm),
            ]
        elif style == "t":
            segments = [
                classic_segments[0],
                classic_segments[1],
                classic_segments[3],
            ]
        elif style == "four_dots":
            segments = []
        else:
            segments = []

        # The dot shape is itself the centre dot, so it must remain visible
        # regardless of the optional centre-dot setting. Plus is a continuous
        # cross and therefore never needs an additional centre dot.
        should_draw_dot = style == "dot" or (style not in {"dot", "plus", "four_dots"} and
                                             self.show_centre_dot(settings))
        four_dot_centres = []
        if style == "four_dots":
            dot_offset = gap + dot_size
            four_dot_centres = [
                (centre - dot_offset, centre),
                (centre + dot_offset, centre),
                (centre, centre - dot_offset),
                (centre, centre + dot_offset),
            ]

        def paint_dot(x: float, y: float, radius: float, fill: str) -> None:
            self.canvas.create_rectangle(x - radius, y - radius, x + radius,
                                         y + radius, fill=fill, outline="")

        if outline:
            for segment in segments:
                self.draw_arm(segment, outline_colour, thickness + 2 * outline)
            if should_draw_dot:
                radius = dot_size / 2 + outline
                paint_dot(centre, centre, radius, outline_colour)
            for x, y in four_dot_centres:
                paint_dot(x, y, dot_size / 2 + outline, outline_colour)
        for segment in segments:
            self.draw_arm(segment, colour, thickness)
        if should_draw_dot:
            radius = dot_size / 2
            paint_dot(centre, centre, radius, colour)
        for x, y in four_dot_centres:
            paint_dot(x, y, dot_size / 2, colour)
        self.centre_on_primary_display(size)

    def centre_on_primary_display(self, size: int) -> None:
        width = user32.GetSystemMetrics(SM_CXSCREEN)
        height = user32.GetSystemMetrics(SM_CYSCREEN)
        offset_x = round(self.numeric("OffsetX"))
        offset_y = round(self.numeric("OffsetY"))
        self.root.geometry(
            f"+{(width - size) // 2 + offset_x}+{(height - size) // 2 + offset_y}"
        )

    def draw_arm(self, segment: tuple[float, float, float, float], colour: str, width: float) -> None:
        """Draw a horizontal or vertical arm with flat, square ends."""
        x1, y1, x2, y2 = segment
        half_width = width / 2
        if y1 == y2:
            self.canvas.create_rectangle(min(x1, x2), y1 - half_width,
                                         max(x1, x2), y1 + half_width,
                                         fill=colour, outline="")
        else:
            self.canvas.create_rectangle(x1 - half_width, min(y1, y2),
                                         x1 + half_width, max(y1, y2),
                                         fill=colour, outline="")

    def make_click_through(self) -> None:
        hwnd = self.root.winfo_id()
        style = user32.GetWindowLongPtrW(hwnd, GWL_EXSTYLE)
        user32.SetWindowLongPtrW(hwnd, GWL_EXSTYLE, style | WS_EX_TRANSPARENT | WS_EX_NOACTIVATE)
        self.make_hit_test_transparent(hwnd)

    def make_hit_test_transparent(self, hwnd: int) -> None:
        """Ensure the overlay never owns the pointer or changes its cursor.

        ``WS_EX_TRANSPARENT`` only affects painting order; Tk can still win the
        Windows hit test, which makes the arrow cursor reappear over a dot-only
        reticle.  Returning ``HTTRANSPARENT`` hands the hit test to the window
        beneath this overlay instead.
        """
        def window_proc(window: int, message: int, wparam: int, lparam: int) -> int:
            if message == TRAY_CALLBACK_MESSAGE:
                if lparam == WM_RBUTTONUP:
                    self.show_tray_menu()
                elif lparam == WM_LBUTTONUP:
                    self.toggle_visibility()
                return 0
            if message == WM_DISPLAYCHANGE:
                self.restart_overlay()
                return 0
            if message == WM_NCHITTEST:
                return HTTRANSPARENT
            return user32.CallWindowProcW(
                self._original_wndproc, window, message, wparam, lparam
            )

        self._wndproc = WNDPROC(window_proc)
        self._original_wndproc = user32.SetWindowLongPtrW(
            hwnd, GWLP_WNDPROC, ctypes.cast(self._wndproc, ctypes.c_void_p).value
        )

    def add_tray_icon(self) -> None:
        """Add a dependency-free Windows notification-area icon."""
        icon = NOTIFYICONDATAW()
        icon.cbSize = ctypes.sizeof(icon)
        icon.hWnd = self.root.winfo_id()
        icon.uID = 1
        icon.uFlags = NIF_MESSAGE | NIF_ICON | NIF_TIP
        icon.uCallbackMessage = TRAY_CALLBACK_MESSAGE
        if ICON_PATH.exists():
            icon.hIcon = user32.LoadImageW(
                None, str(ICON_PATH), IMAGE_ICON, 0, 0,
                LR_LOADFROMFILE | LR_DEFAULTSIZE,
            )
            self._custom_tray_icon = bool(icon.hIcon)
        if not icon.hIcon:
            icon.hIcon = user32.LoadIconW(None, ctypes.c_void_p(IDI_APPLICATION))
        icon.szTip = "Crosshair Overlay (F8 toggle, F7 reload)"
        if shell32.Shell_NotifyIconW(NIM_ADD, ctypes.byref(icon)):
            self._tray_icon = icon

    def show_tray_menu(self) -> None:
        menu = user32.CreatePopupMenu()
        colours = user32.CreatePopupMenu()
        styles = user32.CreatePopupMenu()
        if not menu or not colours or not styles:
            if menu:
                user32.DestroyMenu(menu)
            if colours:
                user32.DestroyMenu(colours)
            if styles:
                user32.DestroyMenu(styles)
            return
        try:
            user32.AppendMenuW(menu, MF_STRING, MENU_TOGGLE,
                               "Hide crosshair" if self.visible else "Show crosshair")
            user32.AppendMenuW(menu, MF_STRING, MENU_RELOAD, "Reload configuration\tF7")
            user32.AppendMenuW(menu, MF_STRING, MENU_RESTART, "Restart crosshair\tF9")
            user32.AppendMenuW(menu, MF_SEPARATOR, 0, None)
            for index, colour in enumerate(COLOURS):
                flags = MF_STRING | (MF_CHECKED if index == self.colour_index else 0)
                user32.AppendMenuW(colours, flags, MENU_COLOUR_BASE + index, colour)
            user32.AppendMenuW(menu, MF_POPUP, colours, "Colour")
            user32.AppendMenuW(menu, MF_STRING, MENU_NEXT_SIZE, "Next size")
            dot_flags = MF_STRING | (
                MF_CHECKED if self.show_centre_dot(self.style_config()) else 0
            )
            user32.AppendMenuW(menu, dot_flags, MENU_DOT, "Center dot")
            current_style = self.style()
            for index, label in enumerate(STYLE_LABELS):
                flags = MF_STRING | (MF_CHECKED if STYLES[index] == current_style else 0)
                user32.AppendMenuW(styles, flags, MENU_STYLE_BASE + index, label)
            user32.AppendMenuW(menu, MF_POPUP, styles, "Shape")
            user32.AppendMenuW(menu, MF_SEPARATOR, 0, None)
            user32.AppendMenuW(menu, MF_STRING, MENU_EXIT, "Exit")
            position = POINT()
            user32.GetCursorPos(ctypes.byref(position))
            user32.SetForegroundWindow(self.root.winfo_id())
            command = user32.TrackPopupMenu(
                menu, TPM_LEFTALIGN | TPM_BOTTOMALIGN | TPM_RETURNCMD,
                position.x, position.y, 0, self.root.winfo_id(), None
            )
            self.handle_menu_command(command)
        finally:
            user32.DestroyMenu(menu)

    def handle_menu_command(self, command: int) -> None:
        if command == MENU_TOGGLE:
            self.toggle_visibility()
        elif command == MENU_RELOAD:
            self.reload_config()
        elif command == MENU_RESTART:
            self.restart_overlay()
        elif MENU_COLOUR_BASE <= command < MENU_COLOUR_BASE + len(COLOURS):
            self.colour_index = command - MENU_COLOUR_BASE
            self.set_style_setting("Color", COLOURS[self.colour_index])
            self.redraw()
        elif MENU_STYLE_BASE <= command < MENU_STYLE_BASE + len(STYLES):
            self.config["Style"] = STYLES[command - MENU_STYLE_BASE]
            self.redraw()
        elif command == MENU_NEXT_SIZE:
            arm = self.numeric("ArmLength", config=self.style_config())
            self.set_style_setting("ArmLength", 10 if arm >= 30 else arm + 4)
            self.redraw()
        elif command == MENU_DOT:
            self.set_style_setting("ShowCenterDot", not self.show_centre_dot(self.style_config()))
            self.redraw()
        elif command == MENU_EXIT:
            self.close()

    def hotkey_loop(self) -> None:
        self.hotkey_thread_id = kernel32.GetCurrentThreadId()
        registered: list[int] = []
        for identifier, virtual_key in HOTKEYS.items():
            if user32.RegisterHotKey(None, identifier, MOD_NOREPEAT, virtual_key):
                registered.append(identifier)
        message = wintypes.MSG()
        try:
            while not self.stop_hotkeys.is_set():
                result = user32.GetMessageW(ctypes.byref(message), None, 0, 0)
                if result <= 0:
                    break
                if message.message == WM_HOTKEY:
                    self.events.put(message.wParam)
        finally:
            for identifier in registered:
                user32.UnregisterHotKey(None, identifier)

    def process_events(self) -> None:
        while not self.events.empty():
            self.handle_hotkey(self.events.get_nowait())
        if self.root.winfo_exists():
            self.root.after(25, self.process_events)

    def update_game_cursor(self) -> None:
        window = user32.GetForegroundWindow()
        process_id = wintypes.DWORD()
        process_name = ""
        if window and user32.GetWindowThreadProcessId(window, ctypes.byref(process_id)):
            handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, process_id.value)
            if handle:
                try:
                    buffer = ctypes.create_unicode_buffer(1024)
                    length = wintypes.DWORD(len(buffer))
                    if kernel32.QueryFullProcessImageNameW(handle, 0, buffer, ctypes.byref(length)):
                        process_name = Path(buffer.value).name.casefold()
                finally:
                    kernel32.CloseHandle(handle)
        active = process_name == "metal gear solid peace walker.exe"
        if active and not self._cursor_hidden_for_game:
            user32.ShowCursor(False)
            self._cursor_hidden_for_game = True
        elif not active and self._cursor_hidden_for_game:
            user32.ShowCursor(True)
            self._cursor_hidden_for_game = False
        if self.root.winfo_exists():
            self.root.after(100, self.update_game_cursor)

    def handle_hotkey(self, identifier: int) -> None:
        if identifier == 1:
            self.toggle_visibility()
        elif identifier == 2:
            self.reload_config()
        elif identifier == 3:
            self.swap_style()
        elif identifier == 4:
            self.restart_overlay()

    def toggle_visibility(self) -> None:
        self.visible = not self.visible
        self.root.withdraw() if not self.visible else self.root.deiconify()

    def reload_config(self) -> None:
        self.config = self.load_config()
        self.colour_index = self.get_colour_index()
        self.redraw()

    def restart_overlay(self) -> None:
        """Recalculate the overlay position after a display change."""
        self.redraw()
        if self.visible:
            self.root.deiconify()
        else:
            self.root.withdraw()

    def swap_style(self) -> None:
        current_style = self.style()
        self.config["Style"] = STYLES[(STYLES.index(current_style) + 1) % len(STYLES)]
        self.redraw()

    def close(self) -> None:
        self.stop_hotkeys.set()
        if self._cursor_hidden_for_game:
            user32.ShowCursor(True)
            self._cursor_hidden_for_game = False
        if self.hotkey_thread_id:
            user32.PostThreadMessageW(self.hotkey_thread_id, 0x0012, 0, 0)
        if self._tray_icon:
            shell32.Shell_NotifyIconW(NIM_DELETE, ctypes.byref(self._tray_icon))
            if self._custom_tray_icon:
                user32.DestroyIcon(self._tray_icon.hIcon)
            self._tray_icon = None
        self.root.destroy()

    def run(self) -> None:
        self.root.mainloop()


if __name__ == "__main__":
    try:
        CrosshairOverlay().run()
    except tk.TclError as error:
        # A .pyw file has no console; show a useful error if Tk is unavailable.
        ctypes.windll.user32.MessageBoxW(None, str(error), "Crosshair Overlay", 0x10)
