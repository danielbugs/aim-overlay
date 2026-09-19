# Aim Sight

Aim Sight is a lightweight, click-through crosshair overlay for Windows and Linux. It stays above your game or desktop, does not capture mouse input, and can be controlled from a convenient system-tray icon.

The main implementation lives in [`aim-sight_winlin`](aim-sight_winlin/):

- `aim-sight.py` / `aim-sight.pyw` — the portable Python implementation for Windows and Linux.
- `aim-sight.sh` — the dedicated Linux launcher with a native GTK/Ayatana tray menu.
- `profiles/` — ready-to-use style profiles.

## Features

- Transparent, always-on-top crosshair overlay
- Click-through rendering so the overlay does not interfere with games
- Windows and Linux support from the same Python entry point
- Optional dedicated Linux shell implementation
- System-tray icon with quick access to common actions
- Live configuration reload while the overlay is running
- Saved profiles for quickly switching between crosshair styles
- Adjustable color, size, gap, thickness, opacity, outline, center dot, and screen offset
- X11/XWayland and Wayland-aware positioning on Linux

## Cross-platform Python version

The Python version uses [PySide6](https://pypi.org/project/PySide6/) for the overlay window and tray icon.

### Install

From `aim-sight_winlin`, install the dependency with:

```powershell
# Windows
py -m pip install -r requirements.txt
```

```bash
# Linux
python3 -m pip install -r requirements.txt
```

On Windows, `install-requirements.bat` can also be double-clicked to install the requirements.

### Start and control the overlay

Windows:

```powershell
cd aim-sight_winlin
py aim-sight.py tray
```

For a console-free Windows launch, double-click `aim-sight.pyw` or run:

```powershell
pyw aim-sight.pyw tray
```

Linux:

```bash
cd aim-sight_winlin
python3 aim-sight.py tray
```

The command-line actions are available on both platforms:

```text
start          Start the overlay and tray icon
stop           Stop the overlay
toggle         Toggle visibility
restart        Restart the overlay
status         Show whether it is running
tray           Start the tray application
profiles       List saved profiles
save-profile   Save settings as a profile
delete-profile Delete a profile
cycle-color    Switch to the next configured color
toggle-dot     Toggle the center dot
```

For example:

```bash
python3 aim-sight.py --style diamond --color cyan --opacity 0.8 start
python3 aim-sight.py --profile circle restart
python3 aim-sight.py toggle
```

Replace `python3` with `py` on Windows.

## Dedicated Linux shell version

The shell launcher provides a Linux-native alternative that runs the overlay with GTK/Cairo and keeps a tray icon available in the desktop panel:

```bash
cd aim-sight_winlin
chmod +x aim-sight.sh
./aim-sight.sh
```

It supports the same core actions and options:

```bash
./aim-sight.sh start
./aim-sight.sh --profile diamond restart
./aim-sight.sh toggle
./aim-sight.sh status
./aim-sight.sh stop
```

The shell version requires `python3`, GTK 3, PyGObject, Pycairo, and Ayatana AppIndicator 3. Package names vary by distribution. On Debian/Ubuntu-based systems, the required packages are commonly available as:

```bash
sudo apt install python3 python3-gi python3-cairo gir1.2-gtk-3.0 gir1.2-ayatanaappindicator3-0.1
```

The Linux tray menu provides quick access to:

- Toggle Aim Sight
- Toggle the center dot
- Cycle through configured colors
- Switch profiles
- Reload profile files
- Restart the app
- Open the configuration and profiles folder
- Quit the tray icon

## Tray icon

When started normally, Aim Sight keeps a tray icon running alongside the overlay. Right-click it to toggle the crosshair, choose a saved profile, open configuration files, reload profiles, restart the overlay, or quit the application.

The Python tray menu includes `Toggle Aim Sight`, profile selection, `Open default.conf`, `Open profiles folder`, `Restart Aim Sight`, `Reload profiles`, and `Quit tray icon`. The Linux shell launcher additionally exposes center-dot and color-cycle shortcuts.

## Styles and profiles

The included profiles are:

| Profile | Appearance |
| --- | --- |
| `classic` | Four separated crosshair arms |
| `t` | T-shaped crosshair with the top arm removed |
| `dot` | Center dot crosshair |
| `4dots` | Four dots around the center |
| `plus` | Compact plus-shaped crosshair |
| `diamond` | Diamond outline |
| `circle` | Circle outline |

Profiles are plain text `.conf` files. The bundled profiles are in [`aim-sight_winlin/profiles`](aim-sight_winlin/profiles). Select one from the tray menu or from the command line:

```bash
./aim-sight.sh --profile diamond restart
python3 aim-sight.py --profile 4dots restart
```

To create a profile from custom settings:

```bash
./aim-sight.sh --style plus --color yellow --size 9 --gap 3 save-profile --profile my-plus
./aim-sight.sh --profile my-plus restart
```

The equivalent Python command is:

```bash
python3 aim-sight.py --style plus --color yellow --size 9 --gap 3 save-profile --profile my-plus
```

Edit a profile while Aim Sight is running to see valid changes picked up automatically. Invalid or partially edited values are ignored until the file is valid again.

## Configuration

On first run, the application creates a user configuration directory and copies in `default.conf`.

| Platform | Configuration directory |
| --- | --- |
| Windows | `%APPDATA%\\aim-sight` |
| Linux | `$XDG_CONFIG_HOME/aim-sight`, or `~/.config/aim-sight` |

The main file is `default.conf`; saved profiles are stored in the `profiles/` subdirectory. Useful settings include:

```text
STYLE=t
COLOR=white
SIZE=7.0
GAP=2.0
THICKNESS=0.7
OPACITY=0.9
OUTLINE=yes
DOT=no
OFFSET_X=1.0
OFFSET_Y=1.0
```

`LAST_PROFILE` selects a profile automatically at the next launch. `COLOR_CYCLE` controls the colors used by the tray’s cycle-color action.

## Repository layout

```text
aim-overlay/
├── aim-sight_winlin/
│   ├── aim-sight.py       # Portable Python entry point
│   ├── aim-sight.pyw      # Console-free Windows launcher
│   ├── aim-sight.sh       # Dedicated Linux launcher
│   ├── default.conf       # Default settings template
│   └── profiles/          # Built-in style profiles
├── win_aim_overlay/       # Additional Windows overlay implementation
└── LICENSE
```

## License

This project is distributed under the license in [`LICENSE`](LICENSE).
