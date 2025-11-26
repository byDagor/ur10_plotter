import FreeSimpleGUI as sg
import vpype
from vpype_cli import execute

import os
import threading
from typing import Union
import cv2
import json
import math

from gui_layout import create_layout
from gui_preview import update_preview
from vectorizers.flow_vectorizer import run_vectorize_thread
from vectorizers.hatched_vectorizer import run_hatched_thread
from robot.ur10_controller import UR10Controller, SAFE_Z_OFFSET
from robot.svg_parser import parse_svg


def main():
    """
    Main event loop for the application.
    """
    
    layout = create_layout()
    window = sg.Window("PLOTTUR10", layout, finalize=True, resizable=True)
    
    # Load home position from config file
    home_pose = None
    try:
        with open("home_config.json", "r") as f:
            config = json.load(f)
            home_pose = config.get("pose")
            corner = config.get("corner", "Top Left")
            if home_pose:
                pose_str = ", ".join([f"{x:.3f}" for x in home_pose])
                window["-HOME_POSE_DISPLAY-"].update(pose_str)
                window["-CANVAS_CORNER-"].update(corner)
                print(f"Loaded home position: {pose_str}")
    except FileNotFoundError:
        print("home_config.json not found. Please set a home position.")
    except (json.JSONDecodeError, KeyError):
        print("Error reading home_config.json. File might be corrupted.")

    window["-GRAPH-"].hide_row()
    document: Union[vpype.Document, None] = None
    ur10_controller: Union[UR10Controller, None] = None
    svg_path_list = []
    scaled_dims = {"width": 0, "height": 0}
    update_preview(window, None, is_cmyk=False) # Pass default CMYK flag

    # --- Event Loop ---
    try:
        while True:
            event, values = window.read()

            if event == sg.WIN_CLOSED:
                break
            
            if event == "-LOG_MESSAGE-":
                active_tab = values["-TABGROUP-"]
                if active_tab == "-TAB_FLOW-":
                    window["-LOG_FLOW-"].print(values[event])
                elif active_tab == "-TAB_HATCHED-":
                    window["-LOG_HATCHED-"].print(values[event])
                else:
                    # Fallback for any other case
                    print(f"Log message from unhandled tab '{active_tab}': {values[event]}")
                continue
            
            try:
                # --- Vectorize Image Event ---
                if event == "-BTN_VECTORIZE_FLOW-":
                    print("Vectorizing image with Flow Imager...")
                    
                    img_path = values["-IMG_PATH_FLOW-"]
                    noise_str = values["-FLOW_NOISE-"].strip()
                    min_sep = values["-FLOW_MIN_SEP-"]
                    max_sep = values["-FLOW_MAX_SEP-"]
                    cmyk = values["-FLOW_CMYK-"]
                    
                    n_fields = int(values["-FLOW_N_FIELDS-"])
                    min_len_str = values["-FLOW_MIN_LEN-"].strip().replace("mm", "").strip()
                    max_len_str = values["-FLOW_MAX_LEN-"].strip().replace("mm", "").strip()
                    max_size_str = values["-FLOW_MAX_SIZE-"].strip().replace("px", "").strip()
                    edge_flow = values["-FLOW_EDGE-"]
                    dark_flow = values["-FLOW_DARK-"]
                    rotate = int(values["-FLOW_ROTATE-"])
                    kdt = values["-FLOW_KDT-"]
                    trim = values["-FLOW_TRIM-"]
                    
                    if not img_path or not os.path.exists(img_path):
                        print(f"Error: Image file not found or not specified: {img_path}")
                        continue
                    
                    try:
                        noise = float(noise_str)
                        cmd_string = f"flow_img -nc {noise} -ms {min_sep}mm -Ms {max_sep}mm"
                    except ValueError:
                        print(f"Invalid Noise Coeff: {noise_str}. Must be a number.")
                        continue
                        
                    if n_fields != 1:
                        cmd_string += f" -nf {n_fields}"
                        
                    try:
                        min_len = float(min_len_str)
                        if min_len > 0:
                            cmd_string += f" -ml {min_len}mm"
                    except ValueError:
                        print(f"Ignoring invalid Min Length: {min_len_str}")

                    try:
                        max_len = float(max_len_str)
                        if max_len > 0:
                            cmd_string += f" -Ml {max_len}mm"
                    except ValueError:
                        print(f"Ignoring invalid Max Length: {max_len_str}")

                    try:
                        max_size = int(max_size_str)
                        if max_size > 0:
                            cmd_string += f" --max_size {max_size}"
                    except ValueError:
                        print(f"Ignoring invalid Max Size: {max_size_str}")

                    if edge_flow != 1.0:
                        cmd_string += f" -efm {edge_flow}"
                    
                    if dark_flow != 1.0:
                        cmd_string += f" -dfm {dark_flow}"
                    
                    if rotate != 0:
                        cmd_string += f" --rotate {rotate}"
                    
                    if cmyk:
                        cmd_string += " --cmyk"
                    
                    if kdt:
                        cmd_string += " -kdt"
                    
                    if trim:
                        cmd_string += " -tm"
                    
                    cmd_string += f" \"{img_path}\""
                    
                    # --- THREADING LOGIC ---
                    window["-LOG_FLOW-"].print("Starting Flow Imager vectorization... please wait.")
                    
                    # 2. Start the worker thread
                    threading.Thread(
                        target=run_vectorize_thread,
                        args=(window, cmd_string, cmyk), # Pass the CMYK flag
                        daemon=True
                    ).start()
                    # -----------------------------
                
                # --- Hatched Vectorize Event ---
                elif event == "-BTN_VECTORIZE_HATCHED-":
                    print("Vectorizing image with Hatched...")
                    
                    img_path = values["-IMG_PATH_HATCHED-"]
                    if not img_path or not os.path.exists(img_path):
                        print(f"Error: Image file not found or not specified: {img_path}")
                        continue
                    
                    # --- PARSE ALL PARAMETERS ---
                    params = {}
                    params["img_path"] = img_path
                    params["cmyk"] = values["-HATCHED_CMYK-"]
                    params["invert"] = values["-HATCHED_INVERT-"]
                    params["lines"] = values["-HATCHED_LINES-"]
                    params["hatch"] = values["-HATCHED_HATCH-"]
                    params["pitch"] = values["-HATCHED_PITCH-"]
                    params["blur"] = values["-HATCHED_BLUR-"]
                    params["circular"] = values["-HATCHED_CIRCULAR-"]
                    params["image_scale"] = values["-HATCHED_SCALE-"]
                    params["h_mirror"] = values["-HATCHED_HMIRROR-"]

                    # Parse interpolation
                    params["interpolation"] = cv2.INTER_LINEAR if values["-HATCHED_INTERP-"] == "INTER_LINEAR" else cv2.INTER_NEAREST
                    
                    # Parse offset
                    try:
                        params["offset"] = float(values["-HATCHED_OFFSET-"].strip())
                    except ValueError:
                        print(f"Invalid Offset: {values['-HATCHED_OFFSET-']}. Using 0.0.")
                        params["offset"] = 0.0
                    
                    # Parse center
                    try:
                        center_coords = [float(c) for c in values["-HATCHED_CENTER-"].strip().split()]
                        if len(center_coords) == 2:
                            params["center"] = (center_coords[0], center_coords[1])
                        else:
                            raise ValueError("Center must be two numbers")
                    except ValueError:
                        print(f"Invalid Center: {values['-HATCHED_CENTER-']}. Using (0.5, 0.5).")
                        params["center"] = (0.5, 0.5)

                    # Parse angles
                    try:
                        angles = [float(a) for a in values["-HATCHED_ANGLES-"].strip().split()]
                        if not angles:
                            angles = [45.0] # Default if empty
                        params["angle"] = angles
                        print(f"Using hatch angles: {angles}")
                        
                    except ValueError:
                        print(f"Invalid Hatch Angles: {values['-HATCHED_ANGLES-']}. Using 45.")
                        params["angle"] = [45.0] # Pass as a list

                    # Parse levels
                    try:
                        levels = [int(l) for l in values["-HATCHED_LEVELS-"].strip().split() if 0 < int(l) < 255]
                        if not levels:
                            levels = (64, 128, 192) # Default if empty
                        params["levels"] = tuple(levels)
                    except ValueError:
                        print(f"Invalid Levels: {values['-HATCHED_LEVELS-']}. Using defaults.")
                        params["levels"] = (64, 128, 192)
                    # --- END PARSING ---
                    
                    # --- THREADING LOGIC ---
                    window["-LOG_HATCHED-"].print("Starting Hatched vectorization... please wait.")
                    
                    threading.Thread(
                        target=run_hatched_thread, # Call the thread function
                        args=(window, params),      # Pass the parsed params dict
                        daemon=True
                    ).start()

                # --- Event for when the thread is done ---
                elif event == "-THREAD_DONE-":
                    # 1. Get results from the event
                    doc_from_thread, message, is_cmyk = values[event]
                    
                    # Check if this is from the robot thread
                    if message in ("Real-time path execution complete.", "Real-time path execution stopped."):
                        window["-UR10_STATUS-"].print(message)
                        window["-BTN_START-"].update(disabled=False)
                        window["-BTN_PAUSE-"].update(text="Pause", disabled=True)
                        window["-BTN_STOP-"].update(disabled=True)
                        window["-BTN_UR10_HOME-"].update(disabled=False)
                        window["-BTN_CHECK_CANVAS-"].update(disabled=False)
                        continue

                    # 2. Re-enable buttons and hide loading text
                    window["-BTN_VECTORIZE_FLOW-"].update(disabled=False)
                    window["-BTN_VECTORIZE_HATCHED-"].update(disabled=False)
                    window["-BTN_OPTIMIZE-"].update(disabled=False)
                    window["-BTN_OPTIMIZE-HATCHED-"].update(disabled=False)
                    
                    # 3. Handle results
                    if message and message != "Flow Imager vectorization complete." and message != "Hatched vectorization complete.":
                        print(f"Thread Error: {message}")
                        sg.popup_error(f"Vectorization Failed:\n\n{message}")
                    elif doc_from_thread:
                        document = doc_from_thread  # Store the new document
                        active_tab = values["-TABGROUP-"]
                        log_key = "-LOG_FLOW-" if active_tab == "-TAB_FLOW-" else "-LOG_HATCHED-"
                        window[log_key].print(message)
                        # Pass the checkbox value to the preview function
                        update_preview(window, document, is_cmyk=is_cmyk)
                    else:
                        active_tab = values["-TABGROUP-"]
                        log_key = "-LOG_FLOW-" if active_tab == "-TAB_FLOW-" else "-LOG_HATCHED-"
                        window[log_key].print("Thread finished but document is empty.")
                        document = None # Clear the old document
                        update_preview(window, None, is_cmyk=False) # Show a blank screen
                
                # --- Optimize Event ---
                elif event in ("-BTN_OPTIMIZE-", "-BTN_OPTIMIZE-HATCHED-"):
                    if document is None:
                        print("No drawing to optimize. Generate or vectorize first.")
                        continue
                    
                    log_key = "-LOG_FLOW-" if event == "-BTN_OPTIMIZE-" else "-LOG_HATCHED-"
                    window[log_key].print("Optimizing drawing... please wait.")
                    
                    if event == "-BTN_OPTIMIZE-":
                        merge_tol = values["-OPT_MERGE-"].strip().replace("mm", "").strip()
                        simplify_tol = values["-OPT_SIMPLIFY-"].strip().replace("mm", "").strip()
                    else:
                        merge_tol = values["-OPT_MERGE-HATCHED-"].strip().replace("mm", "").strip()
                        simplify_tol = values["-OPT_SIMPLIFY-HATCHED-"].strip().replace("mm", "").strip()

                    cmd_string = f"linemerge -t {merge_tol}mm linesimplify -t {simplify_tol}mm linesort"
                    
                    print(f"Running command: vpype {cmd_string}")
                    # This is fast, so no thread is needed
                    document = execute(cmd_string, document=document)
                    
                    if document:
                        window[log_key].print("Optimization complete. Updating preview.")
                        
                        # Check which tab is active to get the right CMYK value
                        active_tab_key = values["-TABGROUP-"]
                        is_cmyk = False
                        if active_tab_key == "-TAB_FLOW-":
                            is_cmyk = values["-FLOW_CMYK-"]
                        elif active_tab_key == "-TAB_HATCHED-":
                            is_cmyk = values["-HATCHED_CMYK-"]
                            
                        update_preview(window, document, is_cmyk=is_cmyk)
                    else:
                        window[log_key].print("Optimization failed.")

                # --- Save Event ---
                elif event in ("-BTN_SAVE-", "-BTN_SAVE-HATCHED-"):
                    if document is None:
                        print("Error: No document to save. Generate or vectorize first.")
                        continue

                    save_path = sg.popup_get_file(
                        "Save As",
                        save_as=True,
                        no_window=True,
                        default_extension=".svg",
                        file_types=(("SVG Files", "*.svg"),)
                    )

                    log_key = "-LOG_FLOW-" if event == "-BTN_SAVE-" else "-LOG_HATCHED-"

                    if save_path:
                        try:
                            window[log_key].print(f"Saving SVG to {save_path}...")
                            with open(save_path, "w", encoding="utf-8") as f:
                                vpype.write_svg(f, document)
                            window[log_key].print("SVG file saved successfully.")
                        except Exception as e:
                            print(f"Error saving file: {e}")
                            sg.popup_error(f"Error saving file: {e}")
                    else:
                        window[log_key].print("SVG save cancelled.")
                
                # --- UR10 Control Events ---
                elif event == "-BTN_UR10_CONNECT-":
                    if ur10_controller is None or not ur10_controller.is_connected:
                        ip = values["-UR10_IP-"]
                        window["-UR10_STATUS-"].print(f"Connecting to UR10 at {ip}...")
                        ur10_controller = UR10Controller(ip)
                        if ur10_controller.connect():
                            window["-UR10_STATUS-"].print("Successfully connected.")
                            window["-BTN_UR10_CONNECT-"].update(text="Disconnect")
                            window["-BTN_START-"].update(disabled=False)
                            window["-BTN_UR10_HOME-"].update(disabled=False)
                            window["-BTN_SET_HOME-"].update(disabled=False)
                            window["-BTN_CHECK_CANVAS-"].update(disabled=False)
                        else:
                            window["-UR10_STATUS-"].print("Connection failed.")
                            ur10_controller = None
                    else:
                        ur10_controller.disconnect()
                        window["-UR10_STATUS-"].print("Disconnected.")
                        window["-BTN_UR10_CONNECT-"].update(text="Connect to UR10")
                        window["-BTN_START-"].update(disabled=True)
                        window["-BTN_PAUSE-"].update(disabled=True)
                        window["-BTN_STOP-"].update(disabled=True)
                        window["-BTN_UR10_HOME-"].update(disabled=True)
                        window["-BTN_SET_HOME-"].update(disabled=True)
                        window["-BTN_CHECK_CANVAS-"].update(disabled=True)
                        ur10_controller = None

                elif event == "-BTN_SET_HOME-":
                    if ur10_controller and ur10_controller.is_connected:
                        window["-UR10_STATUS-"].print("Getting current robot position...")
                        current_pose = ur10_controller.get_current_pose()
                        if current_pose:
                            home_pose = current_pose
                            config = {
                                "pose": home_pose,
                                "corner": values["-CANVAS_CORNER-"]
                            }
                            with open("home_config.json", "w") as f:
                                json.dump(config, f)
                            
                            pose_str = ", ".join([f"{x:.3f}" for x in home_pose])
                            window["-HOME_POSE_DISPLAY-"].update(pose_str)
                            window["-UR10_STATUS-"].print(f"Home position set to: {pose_str}")
                        else:
                            window["-UR10_STATUS-"].print("Failed to get current position.")
                    else:
                        window["-UR10_STATUS-"].print("Error: Not connected to the robot.")

                elif event == "-BTN_START-":
                    if ur10_controller and ur10_controller.is_connected:
                        svg_file = values["-SVG_PATH-"]
                        if not svg_file or not os.path.exists(svg_file):
                            window["-UR10_STATUS-"].print("Error: SVG file not found.")
                            continue
                        
                        if not home_pose:
                            window["-UR10_STATUS-"].print("Error: Home position not set.")
                            continue

                        try:
                            canvas_width_mm = float(values["-CANVAS_WIDTH-"])
                            canvas_height_mm = float(values["-CANVAS_HEIGHT-"])
                            dry_run = values["-DRY_RUN-"]
                            corner = values["-CANVAS_CORNER-"]
                            rotation_angle = values["-GLOBAL_ROTATION-"]
                            
                            speed_control = [values["-PLOT_SPEED-"]]
                            acceleration = values["-PLOT_ACCEL-"]

                            window["-UR10_STATUS-"].print(f"Parsing SVG file: {svg_file}")
                            home_x, home_y, home_z, home_rx, home_ry, home_rz = home_pose
                            
                            path, width, height = parse_svg(
                                svg_file, home_x, home_y, home_z, home_rx, home_ry, home_rz,
                                canvas_width_mm, canvas_height_mm, dry_run, corner,
                                safe_z_offset=SAFE_Z_OFFSET, rotation_angle=rotation_angle
                            )
                            scaled_dims["width"] = width
                            scaled_dims["height"] = height
                            
                            if path:
                                window["-BTN_START-"].update(disabled=True)
                                window["-BTN_PAUSE-"].update(disabled=False)
                                window["-BTN_STOP-"].update(disabled=False)
                                window["-BTN_UR10_HOME-"].update(disabled=True)
                                window["-BTN_CHECK_CANVAS-"].update(disabled=True)
                                window["-REALTIME_GRAPH-"].erase()

                                threading.Thread(
                                    target=ur10_controller.execute_path_realtime,
                                    args=(path, home_pose, speed_control, acceleration, window, dry_run),
                                    daemon=True
                                ).start()
                            else:
                                window["-UR10_STATUS-"].print("Error: Could not parse SVG path.")

                        except ValueError:
                            window["-UR10_STATUS-"].print("Error: Invalid Canvas Width or Height. Please enter numbers.")
                        except Exception as e:
                            window["-UR10_STATUS-"].print(f"An error occurred: {e}")
                    else:
                        window["-UR10_STATUS-"].print("Error: Not connected to the robot.")

                elif event == "-DRAW_LINE-":
                    start_point, end_point = values[event]
                    
                    graph_size = window["-REALTIME_GRAPH-"].CanvasSize
                    width = scaled_dims["width"]
                    height = scaled_dims["height"]
                    corner = values["-CANVAS_CORNER-"]
                    home_x, home_y = home_pose[0], home_pose[1]
                    rotation_angle = values["-GLOBAL_ROTATION-"]

                    def unrotate_point(p_rotated):
                        angle_rad = math.radians(-(rotation_angle + 45))
                        cos_a = math.cos(angle_rad)
                        sin_a = math.sin(angle_rad)
                        x_r, y_r = p_rotated[0], p_rotated[1]
                        
                        x_unrotated = home_x + (x_r - home_x) * cos_a - (y_r - home_y) * sin_a
                        y_unrotated = home_y + (x_r - home_x) * sin_a + (y_r - home_y) * cos_a
                        
                        return (x_unrotated, y_unrotated)

                    start_unrotated = unrotate_point(start_point)
                    end_unrotated = unrotate_point(end_point)
                    
                    def transform_coordinates(x, y):
                        # Determine bounding box based on corner
                        if corner == "Top Left":
                            min_x, max_x = home_x, home_x + width
                            min_y, max_y = home_y - height, home_y
                        elif corner == "Top Right":
                            min_x, max_x = home_x - width, home_x
                            min_y, max_y = home_y - height, home_y
                        elif corner == "Bottom Left":
                            min_x, max_x = home_x, home_x + width
                            min_y, max_y = home_y, home_y + height
                        elif corner == "Bottom Right":
                            min_x, max_x = home_x - width, home_x
                            min_y, max_y = home_y, home_y + height
                        else: # Default to Top Left
                            min_x, max_x = home_x, home_x + width
                            min_y, max_y = home_y - height, home_y

                        # Normalize robot coordinates (0-1)
                        norm_x = (x - min_x) / (max_x - min_x) if (max_x - min_x) != 0 else 0
                        norm_y = (y - min_y) / (max_y - min_y) if (max_y - min_y) != 0 else 0
                        
                        # Scale to graph size
                        graph_x = norm_x * graph_size[0]
                        graph_y = graph_size[1] - (norm_y * graph_size[1]) # Invert Y-axis
                        return graph_x, graph_y
                    
                    x1, y1 = transform_coordinates(start_unrotated[0], start_unrotated[1])
                    x2, y2 = transform_coordinates(end_unrotated[0], end_unrotated[1])

                    window["-REALTIME_GRAPH-"].draw_line((x1, y1), (x2, y2), color='black')

                elif event == "-BTN_PAUSE-":
                    if ur10_controller and ur10_controller.is_connected:
                        if not ur10_controller.pause_event.is_set():
                            ur10_controller.pause_event.set()
                            window["-BTN_PAUSE-"].update(text="Resume")
                            window["-UR10_STATUS-"].print("Plotting paused.")
                            window["-BTN_UR10_HOME-"].update(disabled=False)
                            window["-BTN_CHECK_CANVAS-"].update(disabled=False)
                        else:
                            ur10_controller.pause_event.clear()
                            window["-BTN_PAUSE-"].update(text="Pause")
                            window["-UR10_STATUS-"].print("Plotting resumed.")
                            window["-BTN_UR10_HOME-"].update(disabled=True)
                            window["-BTN_CHECK_CANVAS-"].update(disabled=True)

                elif event == "-BTN_STOP-":
                    if ur10_controller and ur10_controller.is_connected:
                        ur10_controller.stop_event.set()
                        window["-BTN_STOP-"].update(disabled=True) 
                        window["-UR10_STATUS-"].print("Stopping plot...")

                elif event == "-BTN_UR10_HOME-":
                    if ur10_controller and ur10_controller.is_connected:
                        if home_pose:
                            window["-UR10_STATUS-"].print("Sending robot to home position...")
                            acceleration = values["-PLOT_ACCEL-"]
                            ur10_controller.go_home(home_pose, acceleration=acceleration)
                            window["-UR10_STATUS-"].print("Robot is at home.")
                        else:
                            window["-UR10_STATUS-"].print("Error: Home position not set.")
                    else:
                        window["-UR10_STATUS-"].print("Error: Not connected to the robot.")

                elif event == "-BTN_CHECK_CANVAS-":
                    if ur10_controller and ur10_controller.is_connected:
                        if not home_pose:
                            window["-UR10_STATUS-"].print("Error: Home position not set.")
                            continue
                        
                        try:
                            canvas_width_m = float(values["-CANVAS_WIDTH-"]) / 1000.0
                            canvas_height_m = float(values["-CANVAS_HEIGHT-"]) / 1000.0
                            corner = values["-CANVAS_CORNER-"]
                            acceleration = values["-PLOT_ACCEL-"]
                            rotation_angle = values["-GLOBAL_ROTATION-"]
                            
                            hx, hy, hz, hrx, hry, hrz = home_pose
                            safe_z = hz + SAFE_Z_OFFSET

                            # 1. Calculate un-rotated corner points
                            if corner == "Top Left":
                                tl, tr, bl, br = (hx, hy), (hx + canvas_width_m, hy), (hx, hy - canvas_height_m), (hx + canvas_width_m, hy - canvas_height_m)
                                sequence = [tl, tr, br, bl, tl]
                            elif corner == "Top Right":
                                tr, tl, br, bl = (hx, hy), (hx - canvas_width_m, hy), (hx, hy - canvas_height_m), (hx - canvas_width_m, hy - canvas_height_m)
                                sequence = [tr, br, bl, tl, tr]
                            elif corner == "Bottom Left":
                                bl, tl, br, tr = (hx, hy), (hx, hy + canvas_height_m), (hx + canvas_width_m, hy), (hx + canvas_width_m, hy + canvas_height_m)
                                sequence = [bl, tl, tr, br, bl]
                            elif corner == "Bottom Right":
                                br, bl, tr, tl = (hx, hy), (hx - canvas_width_m, hy), (hx, hy + canvas_height_m), (hx - canvas_width_m, hy + canvas_height_m)
                                sequence = [br, tr, tl, bl, br]
                            
                            # 2. Rotate corner points
                            angle_rad = math.radians(rotation_angle + 45)
                            cos_a = math.cos(angle_rad)
                            sin_a = math.sin(angle_rad)
                            
                            def rotate_point(p):
                                px, py = p[0], p[1]
                                x_rot = hx + (px - hx) * cos_a - (py - hy) * sin_a
                                y_rot = hy + (px - hx) * sin_a + (py - hy) * cos_a
                                return (x_rot, y_rot)

                            corners_rotated = [rotate_point(p) for p in sequence]
                            
                            # 3. Create list of poses
                            corner_poses = [(p[0], p[1], safe_z, hrx, hry, hrz) for p in corners_rotated]
                            
                            # 4. Execute in a thread
                            window["-UR10_STATUS-"].print("Moving robot to check canvas corners...")
                            threading.Thread(
                                target=ur10_controller.execute_move_sequence,
                                args=(corner_poses, values["-PLOT_SPEED-"], acceleration),
                                daemon=True
                            ).start()

                        except ValueError:
                            window["-UR10_STATUS-"].print("Error: Invalid Canvas Width or Height.")
                        except Exception as e:
                            window["-UR10_STATUS-"].print(f"An error occurred: {e}")
                    else:
                        window["-UR10_STATUS-"].print("Error: Not connected to the robot.")

                if 'speed_control' in locals():
                    speed_control[0] = values["-PLOT_SPEED-"]



            except Exception as e:
                print("\nAn unexpected error occurred:")
                import traceback
                traceback.print_exc()
                sg.popup_error(f"An unexpected error occurred:\n\n{e}\n\nCheck the log for details.")

    finally:
        # --- End ---
        if ur10_controller and ur10_controller.is_connected:
            ur10_controller.disconnect()
        window.close()

if __name__ == "__main__":
    main()
