import FreeSimpleGUI as sg
import vpype
import vpype_flow_imager  # This import is enough to register the plugin
from vpype_cli import execute

import os
import threading
from typing import Union
import cv2

from gui_layout import create_layout
from gui_preview import update_preview
from vectorizers.flow_vectorizer import run_vectorize_thread
from vectorizers.hatched_vectorizer import run_hatched_thread
from robot.ur10_controller import UR10Controller
from robot.svg_parser import parse_svg


def main():
    """
    Main event loop for the application.
    """
    
    layout = create_layout()
    window = sg.Window("Vpype GUI", layout, finalize=True, resizable=True)
    
    window["-GRAPH-"].hide_row()
    document: Union[vpype.Document, None] = None
    ur10_controller: Union[UR10Controller, None] = None
    svg_path_list = []
    update_preview(window, None, is_cmyk=False) # Pass default CMYK flag

    # --- Event Loop ---
    try:
        while True:
            event, values = window.read()

            if event == sg.WIN_CLOSED:
                break
            
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
                    # 1. Disable buttons and show loading text
                    window["-BTN_VECTORIZE_FLOW-"].update(disabled=True)
                    window["-BTN_VECTORIZE_HATCHED-"].update(disabled=True)
                    window["-BTN_OPTIMIZE-"].update(disabled=True)
                    window["-LOADING-"].update(visible=True)
                    
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
                    window["-BTN_VECTORIZE_FLOW-"].update(disabled=True)
                    window["-BTN_VECTORIZE_HATCHED-"].update(disabled=True)
                    window["-BTN_OPTIMIZE-"].update(disabled=True)
                    window["-LOADING-"].update(visible=True)
                    
                    threading.Thread(
                        target=run_hatched_thread, # Call the thread function
                        args=(window, params),      # Pass the parsed params dict
                        daemon=True
                    ).start()

                # --- Event for when the thread is done ---
                elif event == "-THREAD_DONE-":
                    # 1. Get results from the event
                    doc_from_thread, error_message, is_cmyk = values[event]
                    
                    # 2. Re-enable buttons and hide loading text
                    window["-BTN_VECTORIZE_FLOW-"].update(disabled=False)
                    window["-BTN_VECTORIZE_HATCHED-"].update(disabled=False)
                    window["-BTN_OPTIMIZE-"].update(disabled=False)
                    window["-LOADING-"].update(visible=False)
                    
                    # 3. Handle results
                    if error_message:
                        print(f"Thread Error: {error_message}")
                        sg.popup_error(f"Vectorization Failed:\n\n{error_message}")
                    elif doc_from_thread:
                        document = doc_from_thread  # Store the new document
                        print("Thread finished. Updating preview.")
                        # Pass the checkbox value to the preview function
                        update_preview(window, document, is_cmyk=is_cmyk)
                    else:
                        print("Thread finished but document is empty.")
                        document = None # Clear the old document
                        update_preview(window, None, is_cmyk=False) # Show a blank screen
                
                # --- Optimize Event ---
                elif event == "-BTN_OPTIMIZE-":
                    if document is None:
                        print("No drawing to optimize. Generate or vectorize first.")
                        continue
                    
                    print("Optimizing drawing...")
                    
                    merge_tol = values["-OPT_MERGE-"].strip().replace("mm", "").strip()
                    simplify_tol = values["-OPT_SIMPLIFY-"].strip().replace("mm", "").strip()
                    
                    cmd_string = f"linemerge -t {merge_tol}mm linesimplify -t {simplify_tol}mm linesort"
                    
                    print(f"Running command: vpype {cmd_string}")
                    # This is fast, so no thread is needed
                    document = execute(cmd_string, document=document)
                    
                    if document:
                        print("Optimization complete. Updating preview.")
                        
                        # Check which tab is active to get the right CMYK value
                        active_tab_key = values["-TABGROUP-"]
                        is_cmyk = False
                        if active_tab_key == "-TAB_FLOW-":
                            is_cmyk = values["-FLOW_CMYK-"]
                        elif active_tab_key == "-TAB_HATCHED-":
                            is_cmyk = values["-HATCHED_CMYK-"]
                            
                        update_preview(window, document, is_cmyk=is_cmyk)
                    else:
                        print("Optimization failed.")

                # --- Save Event ---
                elif event == "-BTN_SAVE-":
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

                    if save_path:
                        try:
                            print(f"Saving to {save_path}...")
                            with open(save_path, "w", encoding="utf-8") as f:
                                vpype.write_svg(f, document)
                            print("File saved successfuly.")
                        except Exception as e:
                            print(f"Error saving file: {e}")
                            sg.popup_error(f"Error saving file: {e}")
                    else:
                        print("Save cancelled.")
                
                # --- UR10 Control Events ---
                elif event == "-BTN_UR10_CONNECT-":
                    if ur10_controller is None or not ur10_controller.is_connected:
                        ip = values["-UR10_IP-"]
                        window["-UR10_STATUS-"].print(f"Connecting to UR10 at {ip}...")
                        ur10_controller = UR10Controller(ip)
                        if ur10_controller.connect():
                            window["-UR10_STATUS-"].print("Successfully connected.")
                            window["-BTN_UR10_CONNECT-"].update(text="Disconnect")
                            window["-BTN_SEND_SVG-"].update(disabled=False)
                            window["-BTN_UR10_HOME-"].update(disabled=False)
                        else:
                            window["-UR10_STATUS-"].print("Connection failed.")
                            ur10_controller = None
                    else:
                        ur10_controller.disconnect()
                        window["-UR10_STATUS-"].print("Disconnected.")
                        window["-BTN_UR10_CONNECT-"].update(text="Connect to UR10")
                        window["-BTN_SEND_SVG-"].update(disabled=True)
                        window["-BTN_UR10_HOME-"].update(disabled=True)
                        ur10_controller = None

                elif event == "-BTN_SEND_SVG-":
                    if ur10_controller and ur10_controller.is_connected:
                        svg_file = values["-SVG_PATH-"]
                        if not svg_file or not os.path.exists(svg_file):
                            window["-UR10_STATUS-"].print("Error: SVG file not found.")
                            continue
                        
                        try:
                            home_x = float(values["-HOME_X-"])
                            home_y = float(values["-HOME_Y-"])
                            home_z = float(values["-HOME_Z-"])
                            home_rx = float(values["-HOME_RX-"])
                            home_ry = float(values["-HOME_RY-"])
                            home_rz = float(values["-HOME_RZ-"])
                            home_pose = [home_x, home_y, home_z, home_rx, home_ry, home_rz]
                            
                            scale = float(values["-SVG_SCALE-"])
                            dry_run = values["-DRY_RUN-"]
                            
                            window["-UR10_STATUS-"].print(f"Parsing SVG file: {svg_file}")
                            path = parse_svg(svg_file, home_x, home_y, home_z, home_rx, home_ry, home_rz, scale, dry_run)
                            
                            if path:
                                window["-UR10_STATUS-"].print("Sending path to robot...")
                                ur10_controller.execute_path(path, home_pose)
                                window["-UR10_STATUS-"].print("Path execution finished.")
                            else:
                                window["-UR10_STATUS-"].print("Error: Could not parse SVG path.")

                        except ValueError:
                            window["-UR10_STATUS-"].print("Error: Invalid home position or scale values.")
                        except Exception as e:
                            window["-UR10_STATUS-"].print(f"An error occurred: {e}")
                    else:
                        window["-UR10_STATUS-"].print("Error: Not connected to the robot.")

                elif event == "-BTN_UR10_HOME-":
                    if ur10_controller and ur10_controller.is_connected:
                        try:
                            home_x = float(values["-HOME_X-"])
                            home_y = float(values["-HOME_Y-"])
                            home_z = float(values["-HOME_Z-"])
                            home_rx = float(values["-HOME_RX-"])
                            home_ry = float(values["-HOME_RY-"])
                            home_rz = float(values["-HOME_RZ-"])
                            home_pose = [home_x, home_y, home_z, home_rx, home_ry, home_rz]
                            window["-UR10_STATUS-"].print("Sending robot to home position...")
                            ur10_controller.go_home(home_pose)
                            window["-UR10_STATUS-"].print("Robot is at home.")
                        except ValueError:
                            window["-UR10_STATUS-"].print("Error: Invalid home position values.")
                    else:
                        window["-UR10_STATUS-"].print("Error: Not connected to the robot.")


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
