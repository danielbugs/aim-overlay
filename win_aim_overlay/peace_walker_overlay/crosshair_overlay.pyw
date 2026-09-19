"""No-console launcher for crosshair_overlay.py.

Double-click this file, or run ``pyw crosshair_overlay.pyw``.  It starts the
overlay without occupying a terminal; use the tray icon's Exit command to quit.
"""

from crosshair_overlay import CrosshairOverlay


if __name__ == "__main__":
    CrosshairOverlay().run()
