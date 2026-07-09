"""Native (OS) open/save file dialogs via tkinter.

Native dialogs give real Explorer/Finder navigation and image thumbnails, which
Dear PyGui's built-in dialog does not. Each call spins up a hidden, transient Tk
root and tears it down immediately.
"""

import os

from .util import project_root

IMAGE_TYPES = [("Images", "*.png *.jpg *.jpeg *.bmp *.gif *.tif *.tiff"), ("All files", "*.*")]
SVG_TYPES = [("SVG files", "*.svg"), ("All files", "*.*")]


def _default_dir():
    d = os.path.join(project_root(), "svg_examples")
    return d if os.path.isdir(d) else project_root()


def open_file(title="Select file", filetypes=SVG_TYPES, initialdir=None):
    try:
        import tkinter as tk
        from tkinter import filedialog
    except Exception:
        return None
    root = tk.Tk()
    root.withdraw()
    root.attributes("-topmost", True)
    try:
        return filedialog.askopenfilename(title=title, initialdir=initialdir or _default_dir(),
                                          filetypes=filetypes)
    finally:
        root.destroy()


def save_file(title="Save As", default_ext=".svg", filetypes=SVG_TYPES, initialdir=None):
    try:
        import tkinter as tk
        from tkinter import filedialog
    except Exception:
        return None
    root = tk.Tk()
    root.withdraw()
    root.attributes("-topmost", True)
    try:
        return filedialog.asksaveasfilename(title=title, defaultextension=default_ext,
                                            initialdir=initialdir or _default_dir(),
                                            filetypes=filetypes)
    finally:
        root.destroy()
