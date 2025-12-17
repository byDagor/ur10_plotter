import FreeSimpleGUI as sg
import math

# --- SVG Saving Logic ---
def save_as_svg(strokes, filename, width_mm, height_mm, canvas_px):
    svg = [
        f'<?xml version="1.0" encoding="UTF-8" standalone="no"?>',
        f'<svg width="{width_mm}mm" height="{height_mm}mm" viewBox="0 0 {width_mm} {height_mm}" xmlns="http://www.w3.org/2000/svg">',
        f''
    ]
    scale_x = width_mm / canvas_px
    scale_y = height_mm / canvas_px

    for stroke in strokes:
        if len(stroke) < 2: continue
        
        # We are using Top-Left origin for everything now, so this maps 1:1 to SVG
        start_x = stroke[0][0] * scale_x
        start_y = stroke[0][1] * scale_y
        path_data = f"M {start_x:.3f} {start_y:.3f}"
        
        for x, y in stroke[1:]:
            mx = x * scale_x
            my = y * scale_y
            path_data += f" L {mx:.3f} {my:.3f}"
        svg.append(f'  <path d="{path_data}" fill="none" stroke="black" stroke-width="0.5" stroke-linecap="round" stroke-linejoin="round" />')

    svg.append('</svg>')
    with open(filename, 'w') as f:
        f.write('\n'.join(svg))

# --- Redraw Logic ---
def redraw_canvas(graph, strokes, current_stroke):
    graph.erase()
    for stroke in strokes:
        if len(stroke) < 2: continue
        prev = stroke[0]
        for point in stroke[1:]:
            graph.draw_line(prev, point, color='black', width=2)
            prev = point
            
    if len(current_stroke) > 1:
        prev = current_stroke[0]
        for point in current_stroke[1:]:
            graph.draw_line(prev, point, color='black', width=2)
            prev = point

def main():
    sg.theme('SystemDefault')
    CANVAS_SIZE = 600
    
    layout = [
        [sg.Text("Physical Width (mm):"), sg.Input("100", size=(5,1), key='-W-'), 
         sg.Text("Height (mm):"), sg.Input("100", size=(5,1), key='-H-')],
        [sg.Button("Undo", key='-UNDO-'), sg.Button("Redo", key='-REDO-'),
         sg.Push(), sg.Button("Clear", key='-CLEAR-'), sg.Button("Save SVG", key='-SAVE-')],
        [sg.Graph((CANVAS_SIZE, CANVAS_SIZE), 
                  # coordinate system: (0,0) at Top-Left, (600,600) at Bottom-Right
                  graph_bottom_left=(0, CANVAS_SIZE), 
                  graph_top_right=(CANVAS_SIZE, 0), 
                  background_color='white', key='-GRAPH-',
                  enable_events=True, 
                  drag_submits=False,  
                  motion_events=False)] 
    ]

    window = sg.Window('Stickman Plotter Tool', layout, finalize=True)
    graph = window['-GRAPH-']
    
    # --- MANUAL BINDINGS ---
    # Binding directly to Tkinter events
    graph.Widget.bind('<Button-1>', lambda e: window.write_event_value('-START-', (e.x, e.y)))
    graph.Widget.bind('<B1-Motion>', lambda e: window.write_event_value('-DRAG-', (e.x, e.y)))
    graph.Widget.bind('<ButtonRelease-1>', lambda e: window.write_event_value('-STOP-', (e.x, e.y)))

    all_strokes = []
    redo_stack = []
    current_stroke = []
    last_draw_point = None

    while True:
        event, values = window.read()

        if event == sg.WIN_CLOSED:
            break

        # --- 1. START STROKE ---
        if event == '-START-':
            # Raw Tkinter coordinates are Top-Left Origin (0,0)
            # Our Graph is also Top-Left Origin (0,0)
            # So: No math needed!
            x, y = values['-START-']
            
            current_stroke = [(x, y)]
            last_draw_point = (x, y)
            redo_stack = []

        # --- 2. DRAG STROKE ---
        elif event == '-DRAG-':
            x, y = values['-DRAG-']
            
            if last_draw_point:
                # Throttling
                dist = math.hypot(x - last_draw_point[0], y - last_draw_point[1])
                if dist > 3:
                    graph.draw_line(last_draw_point, (x, y), color='black', width=2)
                    current_stroke.append((x, y))
                    last_draw_point = (x, y)

        # --- 3. END STROKE ---
        elif event == '-STOP-':
            if current_stroke:
                if len(current_stroke) > 1:
                    all_strokes.append(current_stroke)
            current_stroke = []
            last_draw_point = None

        # --- TOOLBAR ---
        elif event == '-UNDO-':
            if all_strokes:
                redo_stack.append(all_strokes.pop())
                redraw_canvas(graph, all_strokes, [])
        
        elif event == '-REDO-':
            if redo_stack:
                all_strokes.append(redo_stack.pop())
                redraw_canvas(graph, all_strokes, [])

        elif event == '-CLEAR-':
            graph.erase()
            all_strokes = []
            redo_stack = []
            current_stroke = []

        elif event == '-SAVE-':
            try:
                w_mm = float(values['-W-'])
                h_mm = float(values['-H-'])
                fname = sg.popup_get_file('Save', save_as=True, file_types=(("SVG", "*.svg"),))
                if fname:
                    if not fname.lower().endswith('.svg'): fname += '.svg'
                    save_as_svg(all_strokes, fname, w_mm, h_mm, CANVAS_SIZE)
                    sg.popup(f"Saved: {fname}")
            except ValueError:
                sg.popup_error("Invalid dimensions")

    window.close()

if __name__ == "__main__":
    main()