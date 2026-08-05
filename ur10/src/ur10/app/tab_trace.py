"""Trace tab: recreate a line drawing as single-stroke centerlines.

Traces every line of a raster picture (a found drawing, or one you drew) down its
centerline so each becomes ONE pen stroke -- thickness is ignored, so a thick or
double-drawn outline collapses to a single line. The result is an SVG the UR10
tab plots for infinite copies of the same single-line drawing.

Wraps vectorizers/centerline_vectorizer.py in the shared VectorizerTab machinery,
so it inherits the sidebar+preview layout, Vectorize/Stop, Optimize (linemerge/
linesort for minimal pen travel), and Save SVG unchanged.
"""

import os

import dearpygui.dearpygui as dpg

from vectorizers.centerline_vectorizer import run_centerline_thread

from .vectorizer_tab import VectorizerTab
from .dialogs import open_file, IMAGE_TYPES
from .theme import section


class TraceTab(VectorizerTab):
    name = "Trace"
    prefix = "trace"

    def build(self, parent):
        self._wrap(parent, self._controls)

    def _controls(self):
        section("Trace", pad_top=2)
        with dpg.group(horizontal=True):
            dpg.add_input_text(tag="trace_img", width=-88, hint="Source image")
            dpg.add_button(label="Browse", width=80, callback=self._browse)

        section("Detail")
        dpg.add_slider_int(label="Resolution (px)", tag="trace_maxdim",
                           default_value=1000, min_value=200, max_value=2500, width=-150)
        dpg.add_slider_float(label="Smooth (px)", tag="trace_smooth",
                             default_value=1.0, min_value=0.0, max_value=5.0,
                             format="%.1f", width=-150)
        dpg.add_slider_float(label="Simplify (px)", tag="trace_rdp",
                             default_value=1.0, min_value=0.0, max_value=5.0,
                             format="%.1f", width=-150)
        dpg.add_slider_int(label="Min stroke (px)", tag="trace_minlen",
                           default_value=4, min_value=0, max_value=50, width=-150)
        dpg.add_slider_int(label="Prune spurs (px)", tag="trace_prune",
                           default_value=6, min_value=0, max_value=40, width=-150)

        section("Binarize")
        dpg.add_slider_int(label="Blur", tag="trace_blur", default_value=1,
                           min_value=0, max_value=10, width=-150)
        with dpg.group(horizontal=True):
            dpg.add_checkbox(label="Auto threshold", tag="trace_auto", default_value=True)
            dpg.add_checkbox(label="Invert", tag="trace_invert")
        dpg.add_slider_int(label="Threshold", tag="trace_thresh", default_value=128,
                           min_value=0, max_value=255, width=-150)

        self._vectorize_buttons()
        self._optimize_and_save()

        section("Status")
        dpg.add_child_window(tag=self.log_tag, height=150, autosize_x=True)

    def _browse(self):
        path = open_file(title="Select image", filetypes=IMAGE_TYPES)
        if path:
            dpg.set_value("trace_img", path)

    def vectorize(self):
        img = dpg.get_value("trace_img")
        if not img or not os.path.exists(img):
            self.log(f"Image not found: {img}")
            return
        params = {
            "img_path": img,
            "max_dim": int(dpg.get_value("trace_maxdim")),
            "blur": int(dpg.get_value("trace_blur")),
            "threshold": int(dpg.get_value("trace_thresh")),
            "auto_threshold": bool(dpg.get_value("trace_auto")),
            "invert": bool(dpg.get_value("trace_invert")),
            "smooth": float(dpg.get_value("trace_smooth")),
            "simplify": float(dpg.get_value("trace_rdp")),
            "min_len": float(dpg.get_value("trace_minlen")),
            "prune": int(dpg.get_value("trace_prune")),
        }
        self.log("Starting centerline trace...")
        self._start(run_centerline_thread, (self.bridge, params, self.stop_event))
