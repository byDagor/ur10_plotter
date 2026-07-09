"""Flow Imager tab: vectorize an image with vpype's flow_img plugin."""

import os

import dearpygui.dearpygui as dpg

from vectorizers.flow_vectorizer import run_vectorize_thread

from .vectorizer_tab import VectorizerTab
from .dialogs import open_file, IMAGE_TYPES
from .theme import section


class FlowTab(VectorizerTab):
    name = "Flow Imager"
    prefix = "flow"

    def build(self, parent):
        self._wrap(parent, self._controls)

    def _controls(self):
        section("Flow Imager", pad_top=2)
        with dpg.group(horizontal=True):
            dpg.add_input_text(tag="flow_img", width=-88, hint="Source image")
            dpg.add_button(label="Browse", width=80, callback=self._browse)
        dpg.add_input_text(label="Noise Coeff", tag="flow_noise", default_value="0.0005",
                           width=120)
        dpg.add_slider_float(label="Min Sep", tag="flow_min_sep", default_value=0.8,
                             min_value=0.5, max_value=10.0, width=-90, format="%.1f")
        dpg.add_slider_float(label="Max Sep", tag="flow_max_sep", default_value=10.0,
                             min_value=1.0, max_value=20.0, width=-90, format="%.1f")
        with dpg.group(horizontal=True):
            dpg.add_text("Min Len mm")
            dpg.add_input_text(tag="flow_min_len", default_value="0", width=60)
            dpg.add_text("Max Len mm")
            dpg.add_input_text(tag="flow_max_len", default_value="1000", width=60)
        dpg.add_input_text(label="Max Size px", tag="flow_max_size", default_value="1600",
                           width=90)
        dpg.add_slider_int(label="N Fields", tag="flow_n_fields", default_value=1,
                           min_value=1, max_value=10, width=-90)
        dpg.add_slider_float(label="Edge Flow", tag="flow_edge", default_value=1.0,
                             min_value=0.0, max_value=10.0, width=-90, format="%.1f")
        dpg.add_slider_float(label="Dark Flow", tag="flow_dark", default_value=1.0,
                             min_value=0.0, max_value=10.0, width=-90, format="%.1f")
        dpg.add_slider_int(label="Rotate", tag="flow_rotate", default_value=0,
                           min_value=0, max_value=360, width=-90)
        with dpg.group(horizontal=True):
            dpg.add_checkbox(label="CMYK", tag="flow_cmyk")
            dpg.add_checkbox(label="K-d Tree", tag="flow_kdt", default_value=True)
            dpg.add_checkbox(label="Trim Border", tag="flow_trim")

        self._vectorize_buttons()
        self._optimize_and_save()

        section("Status")
        dpg.add_child_window(tag=self.log_tag, height=150, autosize_x=True)

    def _browse(self):
        path = open_file(title="Select image", filetypes=IMAGE_TYPES)
        if path:
            dpg.set_value("flow_img", path)

    def vectorize(self):
        img = dpg.get_value("flow_img")
        if not img or not os.path.exists(img):
            self.log(f"Image not found: {img}")
            return
        try:
            noise = float(dpg.get_value("flow_noise").strip())
        except ValueError:
            self.log("Invalid Noise Coeff (must be a number).")
            return

        min_sep = dpg.get_value("flow_min_sep")
        max_sep = dpg.get_value("flow_max_sep")
        cmyk = dpg.get_value("flow_cmyk")
        cmd = f"flow_img -nc {noise} -ms {min_sep}mm -Ms {max_sep}mm"

        n_fields = int(dpg.get_value("flow_n_fields"))
        if n_fields != 1:
            cmd += f" -nf {n_fields}"
        cmd += self._len_flag("-ml", "flow_min_len", "Min Length")
        cmd += self._len_flag("-Ml", "flow_max_len", "Max Length")
        try:
            max_size = int(dpg.get_value("flow_max_size").strip())
            if max_size > 0:
                cmd += f" --max_size {max_size}"
        except ValueError:
            self.log("Ignoring invalid Max Size.")

        edge = dpg.get_value("flow_edge")
        dark = dpg.get_value("flow_dark")
        rotate = int(dpg.get_value("flow_rotate"))
        if edge != 1.0:
            cmd += f" -efm {edge}"
        if dark != 1.0:
            cmd += f" -dfm {dark}"
        if rotate != 0:
            cmd += f" --rotate {rotate}"
        if cmyk:
            cmd += " --cmyk"
        if dpg.get_value("flow_kdt"):
            cmd += " -kdt"
        if dpg.get_value("flow_trim"):
            cmd += " -tm"
        cmd += f' "{img}"'

        self.log("Starting Flow Imager vectorization...")
        self._start(run_vectorize_thread, (self.bridge, cmd, cmyk, self.stop_event))

    def _len_flag(self, flag, tag, label):
        raw = dpg.get_value(tag).strip().replace("mm", "").strip()
        try:
            val = float(raw)
            return f" {flag} {val}mm" if val > 0 else ""
        except ValueError:
            self.log(f"Ignoring invalid {label}: {raw}")
            return ""
