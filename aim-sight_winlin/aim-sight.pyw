"""No-console launcher for Aim Sight.

Double-click this file (or run ``pyw aim-sight.pyw``) to use the same entry
point as ``aim-sight.py`` without opening a console window.
"""

from pathlib import Path
import runpy


if __name__ == "__main__":
    runpy.run_path(str(Path(__file__).with_name("aim-sight.py")), run_name="__main__")
