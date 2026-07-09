"""PLOTTUR10 - Dear PyGui front-end entry point.

Run from the project root (the folder containing home_config.json):

    python src/ur10/plottur10.py

This inserts src/ur10 on sys.path so the flat project imports (robot.*,
vectorizers.*, hatched, dither_converter, text_object) resolve, matching the
convention used by the original ur10_plotter_gui.py.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.main import main

if __name__ == "__main__":
    main()
