"""UR10 Control tab: load an SVG, place it, and stream it to the robot."""

import os
import gc
import json
import math
import time
import threading

import dearpygui.dearpygui as dpg

from robot.ur10_controller import UR10Controller, SAFE_Z_OFFSET, RobotStatus
from robot.svg_parser import parse_svg

from .tabbase import BaseTab
from .bridge import EventBridge
from .canvas import PreviewCanvas, bounds_of, svg_to_items, detect_dots
from .theme import (section, make_button_theme, TABBAR_H, INK,
                    C_CONNECT, C_START, C_PAUSE, C_STOP)

DEFAULT_HOME = [0.1886, 0.3004, 0.1230, -0.1804, -3.1278, -0.0213]


def _project_root():
    return os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))


class UR10Tab(BaseTab):
    name = "UR10 Control"
    sidebar_tag = "ur10_sidebar"
    preview_tag = "ur10_preview"
    log_tag = "ur10_log"
    inner_offset = TABBAR_H

    def __init__(self):
        super().__init__()
        self.tab_id = None          # set in build(); lets other tabs switch here
        self.controller = None
        self.connected = False
        self.home_pose = None
        self.is_dots = False
        self._speed_control = None
        self._plot_home = (0.0, 0.0)
        self._plot_unrot = 0.0

        self.svg = PreviewCanvas("ur10_svg", flip_y=False)
        self.rt = PreviewCanvas("ur10_rt", flip_y=True)
        self.canvases = [self.svg, self.rt]

        self.demo_thread = None
        self.demo_stop = threading.Event()

        self.bridge = EventBridge(handlers={
            "-LOG_MESSAGE-": self.log,
            "-DRAW_LINE-": self._on_draw_line,
            "-THREAD_DONE-": self._on_thread_done,
        })

    # ------------------------------------------------------------------ #
    # Layout
    # ------------------------------------------------------------------ #
    def build(self, parent):
        self.tab_id = parent
        with dpg.group(horizontal=True, parent=parent):
            with dpg.child_window(tag=self.sidebar_tag, width=400):
                section("Connection", pad_top=2)
                with dpg.group(horizontal=True):
                    with dpg.drawlist(width=16, height=18):
                        dpg.draw_circle([8, 9], 5, fill=C_STOP, color=C_STOP,
                                        tag="ur10_conn_dot")
                    dpg.add_text("Disconnected", tag="ur10_conn_status")
                dpg.add_input_text(tag="ur10_ip", default_value="10.0.10.208", width=-1)
                dpg.add_button(label="Connect", tag="ur10_btn_connect", width=-1,
                               callback=self.toggle_connect)

                section("Run")
                with dpg.group(horizontal=True):
                    dpg.add_button(label="Start", tag="ur10_btn_start", width=112,
                                   enabled=False, callback=self.start_plot)
                    dpg.add_button(label="Pause", tag="ur10_btn_pause", width=112,
                                   enabled=False, callback=self.toggle_pause)
                    dpg.add_button(label="Stop", tag="ur10_btn_stop", width=-1,
                                   enabled=False, callback=self.stop_robot)
                with dpg.group(horizontal=True):
                    dpg.add_button(label="Go Home", tag="ur10_btn_home", width=112,
                                   enabled=False, callback=self.go_home)
                    dpg.add_button(label="Pen Change", tag="ur10_btn_pen", width=112,
                                   enabled=False, callback=self.pen_change)
                    dpg.add_button(label="Check", tag="ur10_btn_check", width=-1,
                                   enabled=False, callback=self.check_canvas)
                dpg.add_checkbox(label="Dry Run (pen stays lifted)", tag="ur10_dry_run",
                                 enabled=False)

                section("Drawing File")
                with dpg.group(horizontal=True):
                    dpg.add_input_text(tag="ur10_svg_path", width=-88, hint="SVG file path")
                    dpg.add_button(label="Browse", width=80, callback=self.browse)
                dpg.add_button(label="Preview SVG", width=-1, callback=self.preview)
                with dpg.group(horizontal=True):
                    dpg.add_button(label="Demo Draw", tag="ur10_btn_demo", width=-90,
                                   callback=self.demo_draw)
                    dpg.add_button(label="Stop", tag="ur10_btn_demo_stop", width=-1,
                                   callback=self.stop_demo)

                section("Placement")
                dpg.add_input_text(tag="ur10_home_display", default_value="Home: not set",
                                   width=-1, readonly=True)
                dpg.add_button(label="Set Home to Current Position", tag="ur10_btn_sethome",
                               width=-1, enabled=False, callback=self.set_home)
                with dpg.group(horizontal=True):
                    dpg.add_text("Corner")
                    dpg.add_combo(("Top Left", "Top Right", "Bottom Left", "Bottom Right"),
                                  default_value="Top Left", tag="ur10_corner", width=-1,
                                  callback=self._save_placement)
                with dpg.group(horizontal=True):
                    dpg.add_text("Rotation")
                    dpg.add_combo(("0", "-90", "90", "180"), default_value="90",
                                  tag="ur10_rotation", width=90,
                                  callback=self._save_placement)

                section("Canvas")
                with dpg.group(horizontal=True):
                    dpg.add_text("Width mm")
                    dpg.add_input_text(tag="ur10_canvas_w", default_value="297", width=70)
                    dpg.add_text("Height mm")
                    dpg.add_input_text(tag="ur10_canvas_h", default_value="210", width=70)

                section("Motion")
                dpg.add_slider_float(label="Speed (m/s)", tag="ur10_speed", width=-110,
                                     default_value=0.10, min_value=0.01, max_value=1.0,
                                     format="%.2f")
                dpg.add_slider_float(label="Accel (m/s²)", tag="ur10_accel", width=-110,
                                     default_value=0.5, min_value=0.05, max_value=2.0,
                                     format="%.2f")

                section("Status")
                dpg.add_child_window(tag=self.log_tag, height=150, autosize_x=True)

            with dpg.child_window(tag=self.preview_tag, width=-1, no_scrollbar=True):
                with dpg.tab_bar(tag="ur10_preview_tabs"):
                    with dpg.tab(label="SVG Preview", tag="ur10_tab_svg"):
                        self.svg.build()
                    with dpg.tab(label="Real-time Drawing", tag="ur10_tab_rt"):
                        self.rt.build()

    def apply_button_themes(self):
        dpg.bind_item_theme("ur10_btn_connect", make_button_theme(C_CONNECT))
        dpg.bind_item_theme("ur10_btn_start", make_button_theme(C_START))
        dpg.bind_item_theme("ur10_btn_demo", make_button_theme(C_START))
        dpg.bind_item_theme("ur10_btn_pause", make_button_theme(C_PAUSE))
        dpg.bind_item_theme("ur10_btn_stop", make_button_theme(C_STOP))
        dpg.bind_item_theme("ur10_btn_demo_stop", make_button_theme(C_STOP))

    # ------------------------------------------------------------------ #
    # Connection
    # ------------------------------------------------------------------ #
    def toggle_connect(self):
        if self.connected:
            self._teardown_controller()
            self.connected = False
            self._set_connected_ui(False)
            self.log("Disconnected.")
            return
        # Release any prior controller (and its native RTDE handles) BEFORE
        # opening new ones - reconnecting on top of lingering handles can crash
        # the ur_rtde native layer.
        self._teardown_controller()
        ip = dpg.get_value("ur10_ip")
        self.log(f"Connecting to UR10 at {ip} ...")
        try:
            self.controller = UR10Controller(ip)
            ok = self.controller.connect()
        except Exception as exc:
            self._teardown_controller()
            dpg.set_value("ur10_conn_status", "Connection failed")
            self.log(f"Connection error: {exc}")
            return
        if ok:
            self.connected = True
            self._set_connected_ui(True)
            self.log("Connected.")
        else:
            self._teardown_controller()
            dpg.set_value("ur10_conn_status", "Connection failed")
            self.log("Connection failed. Check the IP, and that the robot is in "
                     "Remote Control mode - Local mode blocks the RTDE control interface.")

    def _teardown_controller(self):
        """Deterministically drop the controller so old RTDE native objects are
        released now (via GC) rather than during a later reconnect."""
        if self.controller:
            try:
                self.controller.disconnect()
            except Exception:
                pass
        self.controller = None
        gc.collect()

    def _set_connected_ui(self, connected):
        dpg.set_value("ur10_conn_status", "Connected" if connected else "Disconnected")
        dpg.configure_item("ur10_conn_dot", fill=C_START if connected else C_STOP)
        dpg.set_item_label("ur10_btn_connect", "Disconnect" if connected else "Connect")
        for tag in ("ur10_btn_start", "ur10_btn_home", "ur10_btn_pen", "ur10_btn_check",
                    "ur10_btn_sethome", "ur10_dry_run"):
            dpg.configure_item(tag, enabled=connected)
        # Stop/Pause stay disabled until a plot starts.
        dpg.configure_item("ur10_btn_stop", enabled=False)
        dpg.configure_item("ur10_btn_pause", enabled=False)

    # ------------------------------------------------------------------ #
    # Home / config
    # ------------------------------------------------------------------ #
    def _config_path(self):
        return os.path.join(_project_root(), "home_config.json")

    def _save_placement(self, *args):
        """Persist Corner + Rotation (and the current home pose) to
        home_config.json so the placement survives a relaunch.

        Fires whenever the Corner/Rotation dropdowns change and when Set Home
        writes the pose. It read-modify-writes the existing file so the pose is
        never dropped when only a dropdown changed.
        """
        cfg = {}
        try:
            with open(self._config_path()) as f:
                cfg = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            cfg = {}
        if self.home_pose:
            cfg["pose"] = self.home_pose
        cfg["corner"] = dpg.get_value("ur10_corner")
        cfg["rotation"] = dpg.get_value("ur10_rotation")
        try:
            with open(self._config_path(), "w") as f:
                json.dump(cfg, f)
        except Exception as exc:
            self.log(f"Could not save placement: {exc}")

    def set_home(self):
        if not (self.connected and self.controller):
            self.log("Not connected.")
            return
        pose = self.controller.get_current_pose()
        if not pose:
            self.log("Could not read current pose.")
            return
        self.home_pose = pose
        self._save_placement()
        dpg.set_value("ur10_home_display", ", ".join(f"{v:.3f}" for v in pose))
        self.log("Home set and saved to home_config.json.")

    def load_home(self):
        try:
            with open(self._config_path()) as f:
                cfg = json.load(f)
        except FileNotFoundError:
            self.log("home_config.json not found - using demo default home.")
            return
        except json.JSONDecodeError:
            self.log("home_config.json unreadable.")
            return
        self.home_pose = cfg.get("pose")
        corner = cfg.get("corner", "Bottom Left")
        rotation = str(cfg.get("rotation", "90"))
        # Restore placement independent of the pose, so Corner/Rotation persist
        # even if Home was never set on this machine.
        dpg.set_value("ur10_corner", corner)
        dpg.set_value("ur10_rotation", rotation)
        if self.home_pose:
            dpg.set_value("ur10_home_display",
                          ", ".join(f"{v:.3f}" for v in self.home_pose))
            self.log(f"Loaded home from home_config.json ({corner}, rot {rotation}).")
        else:
            self.log(f"Loaded placement ({corner}, rot {rotation}); home pose not set.")

    # ------------------------------------------------------------------ #
    # File / preview / demo
    # ------------------------------------------------------------------ #
    def browse(self):
        try:
            import tkinter as tk
            from tkinter import filedialog
        except Exception as exc:
            self.log(f"Native file dialog unavailable ({exc}).")
            return
        root = tk.Tk()
        root.withdraw()
        root.attributes("-topmost", True)
        start_dir = os.path.join(_project_root(), "svg_examples")
        if not os.path.isdir(start_dir):
            start_dir = _project_root()
        try:
            path = filedialog.askopenfilename(
                title="Select SVG file", initialdir=start_dir,
                filetypes=[("SVG files", "*.svg"), ("All files", "*.*")])
        finally:
            root.destroy()
        if path:
            dpg.set_value("ur10_svg_path", path)
            self.preview()

    def preview(self):
        path = dpg.get_value("ur10_svg_path")
        if not path or not os.path.exists(path):
            self.log("No SVG selected to preview.")
            return
        try:
            items, bounds, is_dots = svg_to_items(path)
        except Exception as exc:
            self.log(f"Error reading SVG: {exc}")
            return
        if bounds is None:
            self.log("SVG contained no drawable geometry.")
            return
        self.is_dots = is_dots
        self.svg.set_items(items, bounds)
        dpg.set_value("ur10_preview_tabs", "ur10_tab_svg")
        self.log(f"Preview - detected {'dithered dots' if is_dots else 'line art'} "
                 f"({len(items)} elements).")

    def _read_canvas_mm(self):
        return float(dpg.get_value("ur10_canvas_w")), float(dpg.get_value("ur10_canvas_h"))

    def demo_draw(self):
        path = dpg.get_value("ur10_svg_path")
        if not path or not os.path.exists(path):
            self.log("Select an SVG first.")
            return
        self.stop_demo()
        self.demo_stop.clear()
        try:
            w_mm, h_mm = self._read_canvas_mm()
        except ValueError:
            self.log("Canvas width/height must be numbers.")
            return
        corner = dpg.get_value("ur10_corner")
        hx, hy, hz, rx, ry, rz = self.home_pose or DEFAULT_HOME
        # Upright preview: cancel parse_svg's baked-in +45 mount offset.
        paths, w_m, h_m = parse_svg(path, hx, hy, hz, rx, ry, rz, w_mm, h_mm,
                                    dry_run=False, corner=corner,
                                    safe_z_offset=SAFE_Z_OFFSET, rotation_angle=-45)
        if not paths:
            self.log("parse_svg produced no paths.")
            return
        self.is_dots = detect_dots(paths, _path_is_dot)
        all_pts = [(p[0], p[1]) for pa in paths for p in pa]
        self.rt.set_bounds(bounds_of(all_pts))
        dpg.set_value("ur10_preview_tabs", "ur10_tab_rt")
        total = sum(max(len(p) - 1, 1) for p in paths)
        delay = min(0.012, max(0.0006, 2.5 / max(total, 1)))
        self.log(f"Demo drawing {len(paths)} paths ({'dots' if self.is_dots else 'lines'}, "
                 f"scaled {w_m*1000:.0f}×{h_m*1000:.0f} mm).")
        self.demo_thread = threading.Thread(target=self._demo_worker,
                                            args=(paths, self.is_dots, delay), daemon=True)
        self.demo_thread.start()

    def _demo_worker(self, paths, as_dots, delay):
        for path in paths:
            if self.demo_stop.is_set():
                return
            if as_dots:
                self.rt.append_item(("dot", path[0][0], path[0][1], INK))
                time.sleep(delay)
            else:
                for i in range(len(path) - 1):
                    if self.demo_stop.is_set():
                        return
                    a, b = path[i], path[i + 1]
                    self.rt.append_item(("line", a[0], a[1], b[0], b[1], INK))
                    time.sleep(delay)
        self.log("Demo drawing complete.")

    def stop_demo(self):
        running = self.demo_thread is not None and self.demo_thread.is_alive()
        self.demo_stop.set()
        if running:
            self.demo_thread.join(timeout=0.5)
            self.log("Demo draw stopped.")

    # ------------------------------------------------------------------ #
    # Real robot run
    # ------------------------------------------------------------------ #
    def start_plot(self):
        if not (self.connected and self.controller):
            self.log("Not connected.")
            return
        path = dpg.get_value("ur10_svg_path")
        if not path or not os.path.exists(path):
            self.log("SVG file not found.")
            return
        if not self.home_pose:
            self.log("Home position not set.")
            return
        try:
            w_mm, h_mm = self._read_canvas_mm()
        except ValueError:
            self.log("Canvas width/height must be numbers.")
            return
        dry_run = dpg.get_value("ur10_dry_run")
        corner = dpg.get_value("ur10_corner")
        rotation = int(dpg.get_value("ur10_rotation"))
        accel = dpg.get_value("ur10_accel")
        self._speed_control = [dpg.get_value("ur10_speed")]

        hx, hy, hz, rx, ry, rz = self.home_pose
        paths, w_m, h_m = parse_svg(path, hx, hy, hz, rx, ry, rz, w_mm, h_mm,
                                    dry_run, corner, safe_z_offset=SAFE_Z_OFFSET,
                                    rotation_angle=rotation)
        if not paths:
            self.log("Could not parse SVG path.")
            return
        self.is_dots = detect_dots(paths, _path_is_dot)
        # The physical path is rotated (rotation + 45) about home to match the
        # robot's diagonal mount. Un-rotate for the virtual canvas so it shows
        # the drawing upright (same as Demo Draw), independent of the mounting.
        self._plot_home = (hx, hy)
        self._plot_unrot = math.radians(-(rotation + 45))
        disp_pts = [self._to_display(p[0], p[1]) for pa in paths for p in pa]
        self.rt.set_bounds(bounds_of(disp_pts))
        dpg.set_value("ur10_preview_tabs", "ur10_tab_rt")

        self._set_running(True)
        self.log(f"Plotting {len(paths)} paths (scaled {w_m*1000:.0f}×{h_m*1000:.0f} mm)...")
        threading.Thread(
            target=self.controller.execute_path_realtime,
            args=(paths, self.home_pose, self._speed_control, accel, self.bridge, dry_run),
            daemon=True).start()

    def _set_running(self, running):
        dpg.configure_item("ur10_btn_start", enabled=not running)
        dpg.configure_item("ur10_btn_pause", enabled=running, label="Pause")
        dpg.configure_item("ur10_btn_stop", enabled=running)
        for tag in ("ur10_btn_home", "ur10_btn_pen", "ur10_btn_check"):
            dpg.configure_item(tag, enabled=not running)

    def toggle_pause(self):
        if not (self.connected and self.controller):
            return
        if not self.controller.pause_event.is_set():
            self.controller.pause_event.set()
            dpg.set_item_label("ur10_btn_pause", "Resume")
            self.log("Plotting paused.")
        else:
            self.controller.pause_event.clear()
            dpg.set_item_label("ur10_btn_pause", "Pause")
            self.log("Plotting resumed.")

    def stop_robot(self):
        if self.connected and self.controller:
            self.controller.stop_event.set()
            self.log("Robot stop signalled.")

    def go_home(self):
        if self.connected and self.controller and self.home_pose:
            self.log("Going to home position...")
            threading.Thread(target=self.controller.go_home,
                             args=(self.home_pose,), kwargs={"acceleration": dpg.get_value("ur10_accel")},
                             daemon=True).start()

    def pen_change(self):
        if self.connected and self.controller and self.home_pose:
            self.log("Moving to pen change position...")
            threading.Thread(target=self.controller.go_to_pen_change_position,
                             args=(self.home_pose,), daemon=True).start()

    def check_canvas(self):
        if not (self.connected and self.controller and self.home_pose):
            self.log("Not connected or home not set.")
            return
        try:
            w_mm, h_mm = self._read_canvas_mm()
        except ValueError:
            self.log("Canvas width/height must be numbers.")
            return
        w, h = w_mm / 1000.0, h_mm / 1000.0
        corner = dpg.get_value("ur10_corner")
        rotation = int(dpg.get_value("ur10_rotation"))
        accel = dpg.get_value("ur10_accel")
        speed = dpg.get_value("ur10_speed")
        hx, hy, hz, hrx, hry, hrz = self.home_pose
        safe_z = hz + SAFE_Z_OFFSET
        if corner == "Top Left":
            seq = [(hx, hy), (hx + w, hy), (hx + w, hy - h), (hx, hy - h), (hx, hy)]
        elif corner == "Top Right":
            seq = [(hx, hy), (hx, hy - h), (hx - w, hy - h), (hx - w, hy), (hx, hy)]
        elif corner == "Bottom Left":
            seq = [(hx, hy), (hx, hy + h), (hx + w, hy + h), (hx + w, hy), (hx, hy)]
        else:  # Bottom Right
            seq = [(hx, hy), (hx - w, hy), (hx - w, hy + h), (hx, hy + h), (hx, hy)]
        ang = math.radians(rotation + 45)
        cos_a, sin_a = math.cos(ang), math.sin(ang)

        def rot(p):
            px, py = p
            return (hx + (px - hx) * cos_a - (py - hy) * sin_a,
                    hy + (px - hx) * sin_a + (py - hy) * cos_a)

        poses = [(*rot(p), safe_z, hrx, hry, hrz) for p in seq]
        self.log("Checking canvas corners...")
        threading.Thread(target=self.controller.execute_move_sequence,
                         args=(poses, speed, accel), daemon=True).start()

    # ------------------------------------------------------------------ #
    # Bridge handlers (main thread)
    # ------------------------------------------------------------------ #
    def _to_display(self, x, y):
        """Un-rotate a robot-space point back to the canonical (upright) canvas
        frame by inverting the (rotation + 45) mount rotation about home."""
        hx, hy = self._plot_home
        c, s = math.cos(self._plot_unrot), math.sin(self._plot_unrot)
        return (hx + (x - hx) * c - (y - hy) * s,
                hy + (x - hx) * s + (y - hy) * c)

    def _on_draw_line(self, value):
        current, nxt = value
        ax, ay = self._to_display(current[0], current[1])
        if self.is_dots:
            self.rt.append_item(("dot", ax, ay, INK))
        else:
            bx, by = self._to_display(nxt[0], nxt[1])
            self.rt.append_item(("line", ax, ay, bx, by, INK))

    def _on_thread_done(self, value):
        _doc, status, _iscmyk = value
        if isinstance(status, RobotStatus):
            self.log(status.value)
            self._set_running(False)
            if status == RobotStatus.EXECUTION_COMPLETE and self.connected and self.home_pose:
                self.log("Moving to pen change position...")
                threading.Thread(target=self.controller.go_to_pen_change_position,
                                 args=(self.home_pose,), daemon=True).start()

    def on_frame(self):
        # Live speed control while a plot streams.
        if self._speed_control is not None:
            self._speed_control[0] = dpg.get_value("ur10_speed")


def _path_is_dot(p):
    xs = [q[0] for q in p]
    ys = [q[1] for q in p]
    return (max(xs) - min(xs) < 1e-9) and (max(ys) - min(ys) < 1e-9)
