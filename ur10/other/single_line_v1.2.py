import FreeSimpleGUI as sg
import cv2
import numpy as np
import os
import random
from skimage.draw import line
import time

# --- CONSTANTS ---
CANVAS_SIZE = 600

# --- GUI LAYOUT ---
controls_column = [
    [sg.Text("Image File")],
    [
        sg.Input(size=(25, 1), key="-FILE_PATH-"),
        sg.FileBrowse(file_types=(("Image Files", "*.png *.PNG *.jpg *.JPG *.jpeg *.JPEG"), ("All Files", "*.*"))),
    ],
    
    [sg.Text("1. Density (Total Line Steps)")],
    [sg.Slider(range=(2000, 30000), default_value=8000, orientation="h", size=(20, 15), key="-NUM_STEPS-")],
    
    [sg.Text("2. Chaos (Candidates per step)")],
    # Low = Messy/Organic. High = Straight/Efficient.
    [sg.Slider(range=(5, 100), default_value=15, orientation="h", size=(20, 15), key="-DEFINITION-")],
    
    [sg.Text("3. Shading (Ink Depletion Rate)")], 
    # Low = Rich texture (many passes). High = Wireframe (single pass).
    [sg.Slider(range=(1, 100), default_value=15, orientation="h", size=(20, 15), key="-DEPLETION-")],
    
    [sg.HorizontalSeparator()],
    
    [sg.Text("Max Line Length (px)")],
    [sg.Slider(range=(10, 300), default_value=150, orientation="h", size=(20, 15), key="-MAX_LENGTH-")],

    [sg.Text("Min Line Length (px)")],
    [sg.Slider(range=(2, 50), default_value=5, orientation="h", size=(20, 15), key="-MIN_LENGTH-")],
    
    [sg.HorizontalSeparator()],

    [sg.Text("Contrast (Linear)")],
    [sg.Slider(range=(0, 200), default_value=50, orientation="h", size=(20, 15), key="-CONTRAST-")],
    
    # --- NEW GAMMA SLIDER ---
    [sg.Text("Shadow Depth (Gamma)")],
    # > 1.0 makes shadows darker/richer. < 1.0 lifts shadows.
    [sg.Slider(range=(0.1, 3.0), default_value=1.0, resolution=0.1, orientation="h", size=(20, 15), key="-GAMMA-")],
    
    [sg.Checkbox("Invert Image (Uncheck for dark backgrounds)", default=True, key="-INVERT-")],
    
    [sg.HorizontalSeparator()],
    [sg.Button("1. Preview Target", key="-PREVIEW-"), sg.Button("2. Generate Path", key="-PROCESS-"), sg.Button("3. Save SVG", key="-SAVE-")],
    [sg.Text("Status: Idle", key="-STATUS-", size=(35, 2))]
]

path_column = [
    [sg.Text("Robot Path Simulation")],
    [sg.Graph(
        canvas_size=(CANVAS_SIZE, CANVAS_SIZE),
        graph_bottom_left=(0, 0),
        graph_top_right=(CANVAS_SIZE, CANVAS_SIZE),
        background_color='white',
        key="-GRAPH-"
    )]
]

layout = [[sg.Column(controls_column), sg.VSeperator(), sg.Column(path_column)]]
window = sg.Window("Robot 'Pintr' Controller V3 (Gamma)", layout, finalize=True)

# --- ALGORITHM FUNCTIONS ---

def process_image_for_target(filepath, contrast_val, gamma_val, invert_flag):
    """
    Returns a NORMALIZED FLOAT grid (0.0 to 1.0).
    Higher value = More attraction (Darker in original image).
    """
    original_image = cv2.imread(filepath)
    if original_image is None: return None
    
    # 1. Resize preserving aspect ratio
    orig_h, orig_w = original_image.shape[:2]
    scale = min(CANVAS_SIZE/orig_w, CANVAS_SIZE/orig_h)
    new_w, new_h = int(orig_w * scale), int(orig_h * scale)
    
    img_resized = cv2.resize(original_image, (new_w, new_h), interpolation=cv2.INTER_AREA)
    gray = cv2.cvtColor(img_resized, cv2.COLOR_BGR2GRAY)
    
    # 2. Linear Contrast
    alpha = (contrast_val + 100) / 100.0 
    adjusted = cv2.convertScaleAbs(gray, alpha=alpha, beta=0)
    
    # 3. Gamma Correction (The "Shadow Depth" Magic)
    # We build a Lookup Table (LUT) because it's faster than calculating power for every pixel
    # Gamma > 1.0 pushes midtones to black. Gamma < 1.0 pushes midtones to white.
    if gamma_val <= 0: gamma_val = 0.1 # Safety check
    invGamma = 1.0 / gamma_val
    
    table = np.array([((i / 255.0) ** invGamma) * 255 for i in np.arange(0, 256)]).astype("uint8")
    gamma_corrected = cv2.LUT(adjusted, table)
    
    # 4. Create Float Grid (Gravity Map)
    # We normalize to 0.0 - 1.0
    if invert_flag:
        # 255 (white) becomes 0.0, 0 (black) becomes 1.0
        target = 1.0 - (gamma_corrected / 255.0)
    else:
        # 255 (white) becomes 1.0, 0 (black) becomes 0.0
        target = gamma_corrected / 255.0

    # 5. Pad to square
    full_target = np.zeros((CANVAS_SIZE, CANVAS_SIZE), dtype=np.float32)
    x_pad = (CANVAS_SIZE - new_w) // 2
    y_pad = (CANVAS_SIZE - new_h) // 2
    full_target[y_pad : y_pad + new_h, x_pad : x_pad + new_w] = target
    
    return full_target

def convert_to_bytes(image_array):
    # Helper to display the float array in GUI
    display_img = (image_array * 255).astype(np.uint8)
    is_success, buffer = cv2.imencode(".png", display_img)
    return buffer.tobytes() if is_success else None

# --- EVENT LOOP ---
last_generated_segments = []
while True:
    event, values = window.read(timeout=10)
    if event == sg.WIN_CLOSED: break

    # --- PREVIEW BUTTON ---
    if event == "-PREVIEW-":
        filepath = values["-FILE_PATH-"]
        if not os.path.exists(filepath): continue
        
        target_map = process_image_for_target(
            filepath, 
            int(values["-CONTRAST-"]), 
            float(values["-GAMMA-"]), # Pass Gamma
            values["-INVERT-"]
        )
        
        # Invert color for display so it looks like a photo (Ink = Black)
        display_img = 1.0 - target_map
        
        graph = window["-GRAPH-"]
        graph.erase()
        graph.draw_image(data=convert_to_bytes(display_img), location=(0, CANVAS_SIZE))
        window["-STATUS-"].update("Preview: Darker areas = Higher Gravity.")

    # --- PROCESS BUTTON ---
    if event == "-PROCESS-":
        filepath = values["-FILE_PATH-"]
        if not os.path.exists(filepath): continue

        try:
            # Load Params
            num_steps = int(values["-NUM_STEPS-"])
            num_candidates = int(values["-DEFINITION-"]) 
            max_len = int(values["-MAX_LENGTH-"])
            min_len = int(values["-MIN_LENGTH-"])
            depletion_amount = int(values["-DEPLETION-"]) / 255.0 
            
            # Prepare Gravity Map (0.0 = Empty, 1.0 = Needs Ink)
            gravity_map = process_image_for_target(
                filepath, 
                int(values["-CONTRAST-"]), 
                float(values["-GAMMA-"]), # Pass Gamma
                values["-INVERT-"]
            )
            
            graph = window["-GRAPH-"]
            graph.erase()
            
            # Find brightest start point
            start_y, start_x = np.unravel_index(np.argmax(gravity_map), gravity_map.shape)
            current_pos = (int(start_x), int(start_y))
            
            points_batch = [] 
            temp_segments = []
            start_time = time.time()
            
            # --- THE WALKER LOOP ---
            for i in range(num_steps):
                
                # Update GUI every 200 steps
                if i % 200 == 0:
                    window["-STATUS-"].update(f"Drawing step {i}/{num_steps}")
                    if len(points_batch) > 1:
                        for j in range(len(points_batch)-1):
                            p1 = points_batch[j]
                            p2 = points_batch[j+1]
                            # Flip Y for GUI
                            graph.DrawLine((p1[0], CANVAS_SIZE-p1[1]), (p2[0], CANVAS_SIZE-p2[1]), color='black', width=1)
                        points_batch = [points_batch[-1]] 
                    window.refresh()

                best_score = -9999
                best_move = None
                best_rr, best_cc = None, None

                # Test Candidates
                for _ in range(num_candidates):
                    angle = random.uniform(0, 2 * np.pi)
                    length = random.uniform(min_len, max_len)
                    
                    x_new = int(current_pos[0] + np.cos(angle) * length)
                    y_new = int(current_pos[1] + np.sin(angle) * length)
                    
                    # Clip
                    x_new = np.clip(x_new, 0, CANVAS_SIZE - 1)
                    y_new = np.clip(y_new, 0, CANVAS_SIZE - 1)
                    
                    # Get pixels under line
                    rr, cc = line(current_pos[1], current_pos[0], y_new, x_new)
                    
                    # Calculate Score (Average gravity under line)
                    line_values = gravity_map[rr, cc]
                    val_sum = np.sum(line_values)
                    score = val_sum / (len(line_values) + 1)
                    
                    if score > best_score:
                        best_score = score
                        best_move = (x_new, y_new)
                        best_rr, best_cc = rr, cc

                # Execute Move
                if best_move and best_score > 0.05: 
                    # "Eat" the gravity
                    gravity_map[best_rr, best_cc] -= depletion_amount
                    np.clip(gravity_map, 0, 1, out=gravity_map) 
                    
                    points_batch.append(current_pos)
                    points_batch.append(best_move)
                    temp_segments.append((current_pos, best_move))
                    current_pos = best_move
                else:
                    # Jump to a random dark spot if stuck
                    new_y, new_x = np.unravel_index(np.argmax(gravity_map), gravity_map.shape)
                    if gravity_map[new_y, new_x] > 0.1:
                        # Lift pen and move
                        points_batch.append(current_pos) 
                        current_pos = (int(new_x), int(new_y))
                        points_batch.append(current_pos)
                        points_batch = [current_pos]

            total_time = time.time() - start_time
            last_generated_segments = temp_segments
            window["-STATUS-"].update(f"Done in {total_time:.2f}s")

        except Exception as e:
            sg.popup_error(f"Error: {e}")
            print(e)

    # --- SAVE BUTTON ---
    if event == "-SAVE-":
        if not last_generated_segments:
            sg.popup("No path generated yet!", title="Warning")
            continue
            
        filename = sg.popup_get_file("Save SVG", save_as=True, file_types=(("SVG Files", "*.svg"),), default_extension=".svg")
        if filename:
            try:
                # 1. Calculate Bounding Box
                all_x = []
                all_y = []
                for start_pt, end_pt in last_generated_segments:
                    all_x.extend([start_pt[0], end_pt[0]])
                    all_y.extend([start_pt[1], end_pt[1]])
                
                if not all_x:
                     sg.popup("No valid segments found.", title="Error")
                     continue

                min_x, max_x = min(all_x), max(all_x)
                min_y, max_y = min(all_y), max(all_y)
                
                svg_width = max_x - min_x
                svg_height = max_y - min_y
                
                # Safety for perfectly straight lines
                if svg_width == 0: svg_width = 1
                if svg_height == 0: svg_height = 1

                with open(filename, "w") as f:
                    f.write(f'<svg xmlns="http://www.w3.org/2000/svg" width="{svg_width}" height="{svg_height}" viewBox="{min_x} {min_y} {svg_width} {svg_height}">\n')
                    f.write(f'<g fill="none" stroke="black" stroke-width="1">\n')
                    
                    # Optimization: Merge connected segments
                    if last_generated_segments:
                        current_path = [last_generated_segments[0][0]]
                        for start, end in last_generated_segments:
                            if start == current_path[-1]:
                                current_path.append(end)
                            else:
                                # Flush current path
                                pts = " ".join([f"{x},{y}" for x, y in current_path])
                                f.write(f'<polyline points="{pts}" />\n')
                                current_path = [start, end]
                        # Flush last path
                        pts = " ".join([f"{x},{y}" for x, y in current_path])
                        f.write(f'<polyline points="{pts}" />\n')
                        
                    f.write('</g>\n</svg>')
                sg.popup(f"Saved to {filename}")
            except Exception as e:
                sg.popup_error(f"Error saving file: {e}")

window.close()