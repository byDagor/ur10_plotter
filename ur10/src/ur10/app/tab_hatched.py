"""Hatched tab: vectorize an image into hatch lines via the bundled hatched.py."""

import os

import cv2
import dearpygui.dearpygui as dpg

from vectorizers.hatched_vectorizer import run_hatched_thread

from .vectorizer_tab import VectorizerTab
from .dialogs import open_file, IMAGE_TYPES
from .theme import section


class HatchedTab(VectorizerTab):
    name = "Hatched"
    prefix = "hatched"

    def build(self, parent):
        self._wrap(parent, self._controls)

    def _controls(self):
        section("Hatched", pad_top=2)
        with dpg.group(horizontal=True):
            dpg.add_input_text(tag="hatched_img", width=-88, hint="Source image")
            dpg.add_button(label="Browse", width=80, callback=self._browse)
        dpg.add_slider_float(label="Image Scale", tag="hatched_scale", default_value=0.5,
                             min_value=0.1, max_value=1.0, width=-110, format="%.2f")
        dpg.add_input_text(label="Hatch Offset px", tag="hatched_offset",
                           default_value="0.0", width=90)
        dpg.add_slider_float(label="Gaussian Blur", tag="hatched_blur", default_value=1.0,
                             min_value=0.0, max_value=20.0, width=-110, format="%.1f")
        dpg.add_slider_float(label="Hatch Pitch", tag="hatched_pitch", default_value=5.0,
                             min_value=1.0, max_value=20.0, width=-110, format="%.1f")
        dpg.add_input_text(label="Hatch Angles", tag="hatched_angles", default_value="45",
                           width=140)
        dpg.add_input_text(label="Levels", tag="hatched_levels",
                           default_value="64 128 192", width=140)
        dpg.add_combo(("INTER_LINEAR", "INTER_NEAREST"), label="Interp",
                      default_value="INTER_LINEAR", tag="hatched_interp", width=140)
        dpg.add_input_text(label="Circular Center", tag="hatched_center",
                           default_value="0.5 0.5", width=140)
        with dpg.group(horizontal=True):
            dpg.add_checkbox(label="CMYK", tag="hatched_cmyk")
            dpg.add_checkbox(label="Invert", tag="hatched_invert")
            dpg.add_checkbox(label="Circular", tag="hatched_circular")
            dpg.add_checkbox(label="H-Mirror", tag="hatched_hmirror")
        with dpg.group(horizontal=True):
            dpg.add_checkbox(label="Draw Contours", tag="hatched_lines")
            dpg.add_checkbox(label="Draw Hatch Fill", tag="hatched_hatch", default_value=True)

        self._vectorize_buttons()
        self._optimize_and_save()

        section("Status")
        dpg.add_child_window(tag=self.log_tag, height=150, autosize_x=True)

    def _browse(self):
        path = open_file(title="Select image", filetypes=IMAGE_TYPES)
        if path:
            dpg.set_value("hatched_img", path)

    def vectorize(self):
        img = dpg.get_value("hatched_img")
        if not img or not os.path.exists(img):
            self.log(f"Image not found: {img}")
            return

        params = {
            "img_path": img,
            "cmyk": dpg.get_value("hatched_cmyk"),
            "invert": dpg.get_value("hatched_invert"),
            "lines": dpg.get_value("hatched_lines"),
            "hatch": dpg.get_value("hatched_hatch"),
            "pitch": dpg.get_value("hatched_pitch"),
            "blur": dpg.get_value("hatched_blur"),
            "circular": dpg.get_value("hatched_circular"),
            "image_scale": dpg.get_value("hatched_scale"),
            "h_mirror": dpg.get_value("hatched_hmirror"),
            "interpolation": (cv2.INTER_LINEAR if dpg.get_value("hatched_interp") == "INTER_LINEAR"
                              else cv2.INTER_NEAREST),
        }
        try:
            params["offset"] = float(dpg.get_value("hatched_offset").strip())
        except ValueError:
            self.log("Invalid Offset; using 0.0.")
            params["offset"] = 0.0
        try:
            center = [float(c) for c in dpg.get_value("hatched_center").strip().split()]
            params["center"] = (center[0], center[1]) if len(center) == 2 else (0.5, 0.5)
        except (ValueError, IndexError):
            self.log("Invalid Center; using (0.5, 0.5).")
            params["center"] = (0.5, 0.5)
        try:
            angles = [float(a) for a in dpg.get_value("hatched_angles").strip().split()]
            params["angle"] = angles or [45.0]
        except ValueError:
            self.log("Invalid Hatch Angles; using 45.")
            params["angle"] = [45.0]
        try:
            levels = [int(x) for x in dpg.get_value("hatched_levels").strip().split()
                      if 0 < int(x) < 255]
            params["levels"] = tuple(levels) if levels else (64, 128, 192)
        except ValueError:
            self.log("Invalid Levels; using defaults.")
            params["levels"] = (64, 128, 192)

        self.log("Starting Hatched vectorization...")
        self._start(run_hatched_thread, (self.bridge, params, self.stop_event))
