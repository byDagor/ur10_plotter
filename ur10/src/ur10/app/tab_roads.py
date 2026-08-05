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

from road_outline_extracter import compass, label, layout, storage, svg
from road_outline_extracter.models import (LabelConfig, LatLon, PlotConfig,
                                           RoadMetadata, RoadRun)

from .tabbase import BaseTab
from .bridge import EventBridge
from .canvas import PreviewCanvas
from .dialogs import save_file
from .tab_text import FONTS
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

        # Label glyph cache: re-render the (expensive) vpype text only when the
        # text/font/size/spacing change; repositioning on nudge/rotate is cheap.
        self._label_glyphs = None
        self._label_glyph_key = None
        self._label_error = None

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
        dpg.add_input_text(label="Real name", tag="roads_realname", width=-90,
                           hint="Mount Hamilton Rd", on_enter=True, callback=self.replot)
        dpg.add_input_text(label="Nickname", tag="roads_nick", width=-90,
                           hint="nickname", on_enter=True, callback=self.replot)
        dpg.add_input_text(label="Date skated", tag="roads_date", width=-90,
                           hint="YYYY-MM-DD", on_enter=True, callback=self.replot)
        dpg.add_button(label="Save Run", width=-1, callback=self.save_run)

        section("Plot")
        dpg.add_input_float(label="Canvas W (mm)", tag="roads_cw", default_value=140.0,
                            width=110, step=0, on_enter=True, callback=self.replot)
        dpg.add_input_float(label="Canvas H (mm)", tag="roads_ch", default_value=216.0,
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

        section("Label")
        dpg.add_checkbox(label="Draw label on canvas", tag="roads_lbl_on",
                         default_value=False, callback=self.replot)
        dpg.add_text("Include", color=TEXT_DIM)
        with dpg.group(horizontal=True):
            dpg.add_checkbox(label="Name", tag="roads_lbl_name", default_value=True,
                             callback=self.replot)
            dpg.add_checkbox(label="Nickname", tag="roads_lbl_nick", default_value=False,
                             callback=self.replot)
        with dpg.group(horizontal=True):
            dpg.add_checkbox(label="Date", tag="roads_lbl_date", default_value=True,
                             callback=self.replot)
            dpg.add_checkbox(label="Coords", tag="roads_lbl_coords", default_value=False,
                             callback=self.replot)
        with dpg.group(horizontal=True):
            dpg.add_checkbox(label="Distance", tag="roads_lbl_dist", default_value=False,
                             callback=self.replot)
            dpg.add_checkbox(label="Descent", tag="roads_lbl_descent", default_value=False,
                             callback=self.replot)
        dpg.add_checkbox(label="Max grade", tag="roads_lbl_grade", default_value=False,
                         callback=self.replot)
        dpg.add_combo(FONTS, label="Font", default_value="futural", tag="roads_lbl_font",
                      width=150, callback=self.replot)
        dpg.add_input_float(label="Text size (mm)", tag="roads_lbl_size", default_value=4.0,
                            width=110, step=0, format="%.1f", on_enter=True, callback=self.replot)
        dpg.add_input_float(label="Line spacing", tag="roads_lbl_spacing", default_value=1.4,
                            width=110, step=0, format="%.2f", on_enter=True, callback=self.replot)
        dpg.add_combo(label.POSITIONS, label="Position", default_value="Bottom Left",
                      tag="roads_lbl_pos", width=150, callback=self.replot)
        dpg.add_input_float(label="Offset X (mm)", tag="roads_lbl_ox", default_value=0.0,
                            width=110, step=0, on_enter=True, callback=self.replot)
        dpg.add_input_float(label="Offset Y (mm)", tag="roads_lbl_oy", default_value=0.0,
                            width=110, step=0, on_enter=True, callback=self.replot)
        dpg.add_input_float(label="Road gap (mm)", tag="roads_lbl_gap", default_value=4.0,
                            width=110, step=0, format="%.1f", on_enter=True, callback=self.replot)

        section("Compass")
        dpg.add_checkbox(label="North compass (bottom-right)", tag="roads_cmp_on",
                         default_value=False, callback=self.replot)
        dpg.add_input_float(label="Size (mm)", tag="roads_cmp_r", default_value=9.0,
                            width=110, step=0, format="%.1f", on_enter=True, callback=self.replot)

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
        except Exception as exc:                              # RouteNotFound / OSM / geometry
            self.bridge.write_event_value("-ROADS_DONE-", (None, str(exc)))
            return
        # Best-effort elevation profile: a separate free API, so never let it fail
        # the extraction -- the road is fully usable without it.
        try:
            from road_outline_extracter import elevation
            self.bridge.write_event_value(
                "-LOG_MESSAGE-", "Fetching elevation profile...")
            elevations = elevation.fetch_elevations(road.line_wgs84)
            road.elevation_loss_m, road.max_grade_pct = elevation.elevation_stats(
                road.line_utm, elevations)
        except Exception as exc:
            self.bridge.write_event_value(
                "-LOG_MESSAGE-", f"Elevation unavailable ({exc}); road extracted without it.")
        self.bridge.write_event_value("-ROADS_DONE-", (road, None))

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
        info = f"{km:.2f} km / {km * 0.621:.2f} mi - {road.n_points} points"
        if road.elevation_loss_m is not None:
            info += f" - {road.elevation_loss_m:.0f} m descent"
        if road.max_grade_pct is not None:
            info += f" - {road.max_grade_pct:.0f}% max grade"
        dpg.set_value("roads_extract_info", info)

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
        dpg.set_value("roads_nick", run.metadata.nickname or "")
        dpg.set_value("roads_realname", run.metadata.real_name or "")
        dpg.set_value("roads_date", run.metadata.date_first_skated or "")
        if run.plot_config:
            self._apply_config(run.plot_config)
        if run.label_config:
            self._apply_label_config(run.label_config)
        self._set_extract_info(run.road)
        self.replot()
        self.log(f"Loaded run '{slug}'.")

    def save_run(self):
        if not self.road:
            self.log("Extract or load a road first.")
            return
        meta = self._read_metadata()
        slug = storage.slug_for(meta)
        try:
            folder = storage.save_road(
                RoadRun(slug=slug, road=self.road, metadata=meta,
                        plot_config=self._read_config(),
                        label_config=self._read_label_config()),
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

    def _read_metadata(self):
        """Build RoadMetadata from the current UI fields (used for label + save)."""
        def clean(tag):
            return (dpg.get_value(tag) or "").strip() or None

        return RoadMetadata(
            nickname=clean("roads_nick"),
            real_name=clean("roads_realname"),
            date_first_skated=clean("roads_date"),
            start=self._start,
            finish=self._finish,
        )

    def _read_label_config(self):
        return LabelConfig(
            enabled=dpg.get_value("roads_lbl_on"),
            show_name=dpg.get_value("roads_lbl_name"),
            show_nickname=dpg.get_value("roads_lbl_nick"),
            show_date=dpg.get_value("roads_lbl_date"),
            show_coords=dpg.get_value("roads_lbl_coords"),
            show_distance=dpg.get_value("roads_lbl_dist"),
            show_elevation_loss=dpg.get_value("roads_lbl_descent"),
            show_max_grade=dpg.get_value("roads_lbl_grade"),
            font=dpg.get_value("roads_lbl_font"),
            size_mm=float(dpg.get_value("roads_lbl_size")),
            line_spacing=float(dpg.get_value("roads_lbl_spacing")),
            position=dpg.get_value("roads_lbl_pos"),
            offset_x_mm=float(dpg.get_value("roads_lbl_ox")),
            offset_y_mm=float(dpg.get_value("roads_lbl_oy")),
            clearance_mm=float(dpg.get_value("roads_lbl_gap")),
            compass_enabled=dpg.get_value("roads_cmp_on"),
            compass_radius_mm=float(dpg.get_value("roads_cmp_r")),
        )

    def _apply_label_config(self, cfg):
        dpg.set_value("roads_lbl_on", cfg.enabled)
        dpg.set_value("roads_lbl_name", cfg.show_name)
        dpg.set_value("roads_lbl_nick", cfg.show_nickname)
        dpg.set_value("roads_lbl_date", cfg.show_date)
        dpg.set_value("roads_lbl_coords", cfg.show_coords)
        dpg.set_value("roads_lbl_dist", cfg.show_distance)
        dpg.set_value("roads_lbl_descent", cfg.show_elevation_loss)
        dpg.set_value("roads_lbl_grade", cfg.show_max_grade)
        dpg.set_value("roads_lbl_font", cfg.font)
        dpg.set_value("roads_lbl_size", cfg.size_mm)
        dpg.set_value("roads_lbl_spacing", cfg.line_spacing)
        dpg.set_value("roads_lbl_pos", cfg.position)
        dpg.set_value("roads_lbl_ox", cfg.offset_x_mm)
        dpg.set_value("roads_lbl_oy", cfg.offset_y_mm)
        dpg.set_value("roads_lbl_gap", cfg.clearance_mm)
        dpg.set_value("roads_cmp_on", cfg.compass_enabled)
        dpg.set_value("roads_cmp_r", cfg.compass_radius_mm)
        self._label_glyph_key = None        # force glyph re-render for the new run

    def _label_strokes(self, config, label_cfg):
        """Label LineStrings (y-up mm) plus the rectangles they occupy, or
        ([], []) if the label is off/empty.

        The glyph geometry is cached by (rows, font); only placement re-runs when
        the user drags position/nudge/spacing (which don't change glyph shape).
        The rectangles let ``layout`` fit the road clear of the label.
        """
        if not label_cfg.enabled:
            return [], []
        try:
            rows = label.build_rows(self._read_metadata(), self.road, label_cfg)
            key = (tuple((r.text, round(r.size_mm, 3), r.is_title)
                         for r in rows), label_cfg.font)
            if key != self._label_glyph_key:
                self._label_glyphs = label.render_rows(rows, label_cfg.font)
                self._label_glyph_key = key
            self._label_error = None
            args = (self._label_glyphs, label_cfg, config.canvas_w_mm,
                    config.canvas_h_mm, config.margin_mm)
            return label.place_rows(*args), label.obstacle_boxes(*args)
        except Exception as exc:            # never let a label glitch kill the preview
            if self._label_error != str(exc):
                self.log(f"Label render error: {exc}")
                self._label_error = str(exc)
            return [], []

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
        config = self._read_config()

        # The label is placed independently of the road's shape, so compute it
        # first: the road is then fit into the largest label-free rectangle.
        label_cfg = self._read_label_config()
        label_strokes, label_boxes = self._label_strokes(config, label_cfg)

        try:
            result = layout.plan(self.road.line_utm, config, obstacles=label_boxes,
                                  clearance_mm=label_cfg.clearance_mm)
        except (ValueError, ZeroDivisionError):
            # Transient bad state (e.g. margin momentarily larger than canvas while
            # typing). Keep the last good preview rather than clearing/logging.
            return
        self.result = result
        n_road_strokes = len(result.strokes)

        # Compose the optional annotations (metadata label + north compass) into
        # the same stroke list, so the preview, the saved SVG, and the robot all
        # get them identically.
        compass_strokes = (
            compass.render(config.rotation_deg, config.canvas_w_mm, config.canvas_h_mm,
                           config.margin_mm, label_cfg.compass_radius_mm)
            if label_cfg.compass_enabled else []
        )
        extras = label_strokes + compass_strokes
        if extras:
            result.strokes = list(result.strokes) + extras

        items, bounds = self._plot_items(result, config)
        self.canvas.set_items(items, bounds)
        info = (
            f"scale {result.scale_mm_per_m * 1000:.0f} mm/km - "
            f"drawn {result.draw_w_mm:.0f} x {result.draw_h_mm:.0f} mm - "
            f"{n_road_strokes} stroke(s)"
        )
        tags = (["label"] if label_strokes else []) + (["compass"] if compass_strokes else [])
        if tags:
            info += " + " + " + ".join(tags)
        elif label_cfg.enabled:
            info += " - label on, but no fields have text (press Enter after typing)"
        dpg.set_value("roads_plot_info", info)

    # ------------------------------------------------------------------ #
    # Export
    # ------------------------------------------------------------------ #
    def save_svg(self):
        self.replot()   # fold in any label field edits not yet committed with Enter
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
        self.replot()   # fold in any label field edits not yet committed with Enter
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
