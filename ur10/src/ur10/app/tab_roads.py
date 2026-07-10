"""Roads tab: extract a real road's centerline from OpenStreetMap, lay it out on
the canvas, and hand the resulting millimeter SVG to the UR10 Control tab.

This wraps the framework-agnostic road_outline_extracter package (relocated from
the standalone Streamlit app) in the same DPG idioms as the vectorizer tabs:

    extract (OSM download + route, off-thread via EventBridge)
      -> layout.plan (rotate -> fit-to-canvas -> multi-stroke), live preview
        -> svg.render (millimeter SVG) -> Save / Send to UR10

The extract stage is the only part that needs the network; osmnx is imported
lazily so app startup doesn't pay for it unless a road is actually extracted.
Saved runs (roads/<slug>/) let you extract once and re-plot later without OSM.
"""

import os
import threading
from pathlib import Path

import dearpygui.dearpygui as dpg

from road_outline_extracter import layout, storage, svg
from road_outline_extracter.models import LatLon, PlotConfig, RoadMetadata, RoadRun

from .tabbase import BaseTab
from .bridge import EventBridge
from .canvas import PreviewCanvas
from .dialogs import save_file
from .util import project_root
from .theme import (section, make_button_theme, SIDEBAR_W, INK, PAPER_EDGE,
                    TEXT_DIM, C_START, C_CONNECT)


class RoadsTab(BaseTab):
    name = "Roads"
    sidebar_tag = "roads_sidebar"
    preview_tag = "roads_preview"
    log_tag = "roads_log"

    def __init__(self, ur10_tab=None):
        super().__init__()
        self.ur10_tab = ur10_tab            # for the Send to UR10 handoff
        self.roads_dir = Path(project_root()) / "roads"

        self.road = None                    # ExtractedRoad (current geometry)
        self.result = None                  # last layout.PlotResult
        self.saved_svg_path = None
        self._start = None                  # parsed LatLon endpoints (for saving)
        self._finish = None

        # Preview matches the produced SVG exactly: strokes are flipped to y-down
        # in _plot_items, so the canvas uses flip_y=False like the UR10 SVG preview.
        self.canvas = PreviewCanvas("roads_canvas", flip_y=False)
        self.canvases = [self.canvas]

        self.bridge = EventBridge(handlers={
            "-LOG_MESSAGE-": self.log,
            "-ROADS_DONE-": self._on_extract_done,
        })

    # ------------------------------------------------------------------ #
    # Layout
    # ------------------------------------------------------------------ #
    def build(self, parent):
        with dpg.group(horizontal=True, parent=parent):
            with dpg.child_window(tag=self.sidebar_tag, width=SIDEBAR_W):
                self._controls()
            with dpg.child_window(tag=self.preview_tag, width=-1, no_scrollbar=True):
                self.canvas.build()

    def _controls(self):
        section("Extract Road", pad_top=2)
        dpg.add_text("Drop-in (lat, lon)")
        with dpg.group(horizontal=True):
            dpg.add_input_text(tag="roads_start", width=-68, hint="37.3415, -121.6429")
            dpg.add_button(label="Paste", width=60, user_data="roads_start",
                           callback=self._paste_coords)
        dpg.add_text("Finish (lat, lon)")
        with dpg.group(horizontal=True):
            dpg.add_input_text(tag="roads_finish", width=-68, hint="37.3225, -121.6691")
            dpg.add_button(label="Paste", width=60, user_data="roads_finish",
                           callback=self._paste_coords)
        with dpg.group(horizontal=True):
            dpg.add_text("Network")
            dpg.add_combo(("drive", "all"), default_value="drive",
                          tag="roads_network", width=-1)
        dpg.add_button(label="Extract Road", tag="roads_btn_extract", width=-1,
                       callback=self.extract)
        dpg.add_text("", tag="roads_extract_info", color=TEXT_DIM, wrap=SIDEBAR_W - 40)

        section("Saved Runs")
        with dpg.group(horizontal=True):
            dpg.add_combo(self._list_slugs(), tag="roads_saved", width=-72)
            dpg.add_button(label="Load", width=64, callback=self.load_run)
        dpg.add_button(label="Refresh List", width=-1, callback=self.refresh_runs)
        with dpg.group(horizontal=True):
            dpg.add_input_text(tag="roads_nick", width=-92, hint="nickname")
            dpg.add_button(label="Save Run", width=84, callback=self.save_run)

        section("Plot")
        dpg.add_input_float(label="Canvas W (mm)", tag="roads_cw", default_value=297.0,
                            width=110, step=0, on_enter=True, callback=self.replot)
        dpg.add_input_float(label="Canvas H (mm)", tag="roads_ch", default_value=210.0,
                            width=110, step=0, on_enter=True, callback=self.replot)
        dpg.add_input_float(label="Margin (mm)", tag="roads_margin", default_value=10.0,
                            width=110, step=0, on_enter=True, callback=self.replot)
        dpg.add_input_float(label="Pen width (mm)", tag="roads_pen", default_value=0.7,
                            width=110, step=0, format="%.2f", on_enter=True, callback=self.replot)
        dpg.add_input_int(label="Stroke count", tag="roads_scount", default_value=1,
                          min_value=1, max_value=25, min_clamped=True, max_clamped=True,
                          width=110, step=0, on_enter=True, callback=self.replot)
        dpg.add_input_float(label="Stroke offset (mm)", tag="roads_soffset", default_value=0.65,
                            width=110, step=0, format="%.2f", on_enter=True, callback=self.replot)
        dpg.add_slider_int(label="Rotation (deg)", tag="roads_rot", default_value=0,
                           min_value=-180, max_value=180, width=-120, callback=self.replot)
        dpg.add_input_float(label="Nudge X (mm)", tag="roads_nx", default_value=0.0,
                            width=110, step=0, on_enter=True, callback=self.replot)
        dpg.add_input_float(label="Nudge Y (mm)", tag="roads_ny", default_value=0.0,
                            width=110, step=0, on_enter=True, callback=self.replot)
        dpg.add_text("", tag="roads_plot_info", color=TEXT_DIM, wrap=SIDEBAR_W - 40)

        section("Export")
        dpg.add_button(label="Save SVG...", tag="roads_btn_save", width=-1,
                       callback=self.save_svg)
        dpg.add_button(label="Send to UR10 Control", tag="roads_btn_send", width=-1,
                       callback=self.send_to_ur10)

        section("Status")
        dpg.add_child_window(tag=self.log_tag, height=140, autosize_x=True)

    def apply_button_themes(self):
        dpg.bind_item_theme("roads_btn_extract", make_button_theme(C_START))
        dpg.bind_item_theme("roads_btn_save", make_button_theme(C_START))
        dpg.bind_item_theme("roads_btn_send", make_button_theme(C_CONNECT))

    # ------------------------------------------------------------------ #
    # Extract (off-thread; osmnx imported lazily)
    # ------------------------------------------------------------------ #
    def _paste_coords(self, sender, app_data, user_data):
        """Fill a coordinate field from the system clipboard.

        DPG's input_text doesn't reliably paste with Ctrl+V (and ImGui has no
        right-click menu), so we read the clipboard explicitly. Google Maps copies
        'lat, lon', which LatLon.parse accepts as-is; we validate to give feedback.
        """
        try:
            text = (dpg.get_clipboard_text() or "").strip()
        except Exception as exc:
            self.log(f"Clipboard unavailable: {exc}")
            return
        if not text:
            self.log("Clipboard is empty - copy 'lat, lon' from Google Maps first.")
            return
        dpg.set_value(user_data, text)
        if LatLon.parse(text) is None:
            self.log(f"Pasted '{text}', but that isn't a valid 'lat, lon' pair.")
        else:
            self.log(f"Pasted {text}")

    def extract(self):
        start = LatLon.parse(dpg.get_value("roads_start"))
        finish = LatLon.parse(dpg.get_value("roads_finish"))
        if start is None or finish is None:
            self.log("Enter valid 'lat, lon' for both drop-in and finish "
                     "(e.g. 37.3415, -121.6429).")
            return
        network = dpg.get_value("roads_network")
        self._start, self._finish = start, finish
        dpg.configure_item("roads_btn_extract", enabled=False, label="Extracting...")
        self.log(f"Downloading OSM data and routing ({network})... this can take a while.")
        threading.Thread(target=self._extract_worker,
                         args=(start, finish, network), daemon=True).start()

    def _extract_worker(self, start, finish, network):
        try:
            from road_outline_extracter import pipeline      # lazy: pulls in osmnx
            road = pipeline.extract_road(start, finish, network_type=network)
            self.bridge.write_event_value("-ROADS_DONE-", (road, None))
        except Exception as exc:                              # RouteNotFound / OSM / geometry
            self.bridge.write_event_value("-ROADS_DONE-", (None, str(exc)))

    def _on_extract_done(self, value):
        road, err = value
        dpg.configure_item("roads_btn_extract", enabled=True, label="Extract Road")
        if err is not None:
            self.log(f"Extraction failed: {err}")
            return
        self.road = road
        self._set_extract_info(road)
        km = road.length_m / 1000
        self.log(f"Extracted {km:.2f} km ({road.n_points} points, EPSG:{road.utm_epsg}).")
        self.replot()

    def _set_extract_info(self, road):
        km = road.length_m / 1000
        dpg.set_value("roads_extract_info",
                      f"{km:.2f} km / {km * 0.621:.2f} mi - {road.n_points} points")

    # ------------------------------------------------------------------ #
    # Saved runs (roads/<slug>/)
    # ------------------------------------------------------------------ #
    def _list_slugs(self):
        try:
            return storage.list_roads(self.roads_dir)
        except Exception:
            return []

    def refresh_runs(self):
        dpg.configure_item("roads_saved", items=self._list_slugs())

    def load_run(self):
        slug = dpg.get_value("roads_saved")
        if not slug:
            self.log("Pick a saved run to load.")
            return
        try:
            run = storage.load_road(slug, base_dir=self.roads_dir)
        except Exception as exc:
            self.log(f"Could not load '{slug}': {exc}")
            return
        self.road = run.road
        self._start = run.metadata.start
        self._finish = run.metadata.finish
        if run.metadata.start:
            dpg.set_value("roads_start", f"{run.metadata.start.lat}, {run.metadata.start.lon}")
        if run.metadata.finish:
            dpg.set_value("roads_finish", f"{run.metadata.finish.lat}, {run.metadata.finish.lon}")
        dpg.set_value("roads_nick", run.metadata.nickname or slug)
        if run.plot_config:
            self._apply_config(run.plot_config)
        self._set_extract_info(run.road)
        self.replot()
        self.log(f"Loaded run '{slug}'.")

    def save_run(self):
        if not self.road:
            self.log("Extract or load a road first.")
            return
        nick = dpg.get_value("roads_nick").strip()
        meta = RoadMetadata(nickname=nick or None, start=self._start, finish=self._finish)
        slug = storage.slug_for(meta)
        try:
            folder = storage.save_road(
                RoadRun(slug=slug, road=self.road, metadata=meta,
                        plot_config=self._read_config()),
                base_dir=self.roads_dir,
            )
        except Exception as exc:
            self.log(f"Could not save run: {exc}")
            return
        self.refresh_runs()
        dpg.set_value("roads_saved", slug)
        self.log(f"Saved run '{slug}' -> {folder}")

    # ------------------------------------------------------------------ #
    # Plot (pure, fast, live preview)
    # ------------------------------------------------------------------ #
    def _read_config(self):
        return PlotConfig(
            canvas_w_mm=float(dpg.get_value("roads_cw")),
            canvas_h_mm=float(dpg.get_value("roads_ch")),
            margin_mm=float(dpg.get_value("roads_margin")),
            pen_width_mm=float(dpg.get_value("roads_pen")),
            stroke_count=int(dpg.get_value("roads_scount")),
            stroke_offset_mm=float(dpg.get_value("roads_soffset")),
            rotation_deg=float(dpg.get_value("roads_rot")),
            pos_x_mm=float(dpg.get_value("roads_nx")),
            pos_y_mm=float(dpg.get_value("roads_ny")),
        )

    def _apply_config(self, cfg):
        dpg.set_value("roads_cw", cfg.canvas_w_mm)
        dpg.set_value("roads_ch", cfg.canvas_h_mm)
        dpg.set_value("roads_margin", cfg.margin_mm)
        dpg.set_value("roads_pen", cfg.pen_width_mm)
        dpg.set_value("roads_scount", int(cfg.stroke_count))
        dpg.set_value("roads_soffset", cfg.stroke_offset_mm)
        dpg.set_value("roads_rot", int(cfg.rotation_deg))
        dpg.set_value("roads_nx", cfg.pos_x_mm)
        dpg.set_value("roads_ny", cfg.pos_y_mm)

    def _plot_items(self, result, config):
        """Preview items in the SAME y-down mm space the SVG is authored in, plus
        a canvas-border rectangle so placement/margin/nudge are visible."""
        h = config.canvas_h_mm
        w = config.canvas_w_mm
        items = [("poly", [(0, 0), (w, 0), (w, h), (0, h), (0, 0)], PAPER_EDGE)]
        for stroke in result.strokes:
            pts = [(x, h - y) for x, y in stroke.coords]   # y-up -> SVG y-down
            if len(pts) >= 2:
                items.append(("poly", pts, INK))
        return items, (0, 0, w, h)

    def replot(self, sender=None, app_data=None, user_data=None):
        if not self.road:
            return
        try:
            config = self._read_config()
            result = layout.plan(self.road.line_utm, config)
        except (ValueError, ZeroDivisionError):
            # Transient bad state (e.g. margin momentarily larger than canvas while
            # typing). Keep the last good preview rather than clearing/logging.
            return
        self.result = result
        items, bounds = self._plot_items(result, config)
        self.canvas.set_items(items, bounds)
        dpg.set_value(
            "roads_plot_info",
            f"scale {result.scale_mm_per_m * 1000:.0f} mm/km - "
            f"drawn {result.draw_w_mm:.0f} x {result.draw_h_mm:.0f} mm - "
            f"{len(result.strokes)} stroke(s)",
        )

    # ------------------------------------------------------------------ #
    # Export
    # ------------------------------------------------------------------ #
    def save_svg(self):
        if not self.result:
            self.log("Nothing to export - extract/plot a road first.")
            return
        path = save_file(title="Save Road SVG")
        if not path:
            self.log("Save cancelled.")
            return
        try:
            Path(path).write_text(svg.render(self.result.strokes, self._read_config()))
        except Exception as exc:
            self.log(f"Error saving: {exc}")
            return
        self.saved_svg_path = path
        self.log(f"Saved SVG to {path}.")

    def send_to_ur10(self):
        if not self.result:
            self.log("Nothing to send - extract/plot a road first.")
            return
        config = self._read_config()
        path = os.path.join(project_root(), "road_for_ur10.svg")
        try:
            Path(path).write_text(svg.render(self.result.strokes, config))
        except Exception as exc:
            self.log(f"Could not write SVG: {exc}")
            return
        self.saved_svg_path = path
        if self.ur10_tab is None:
            self.log(f"Saved {path}. Open the UR10 tab and Browse to it.")
            return
        # Match the robot canvas to the SVG's true size so it draws at scale, then
        # preview and switch to the UR10 tab.
        dpg.set_value("ur10_svg_path", path)
        dpg.set_value("ur10_canvas_w", f"{config.canvas_w_mm:g}")
        dpg.set_value("ur10_canvas_h", f"{config.canvas_h_mm:g}")
        self.ur10_tab.preview()
        if self.ur10_tab.tab_id is not None:
            dpg.set_value("mode_tabs", self.ur10_tab.tab_id)
        self.log(f"Sent to UR10 Control ({config.canvas_w_mm:g} x {config.canvas_h_mm:g} mm).")
