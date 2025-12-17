import FreeSimpleGUI as sg
import svgwrite
import os
import tkinter.font

# --- Data Structure ---
class TextObject:
    def __init__(self, text, x, y, font_family, font_size, is_bold, is_italic, line_spacing=1.2):
        self.text = text
        self.x = x
        self.y = y
        self.font_family = font_family
        self.font_size = font_size
        self.is_bold = is_bold
        self.is_italic = is_italic
        self.line_spacing = line_spacing

    def __str__(self):
        style = []
        if self.is_bold: style.append("B")
        if self.is_italic: style.append("I")
        style_str = f"[{','.join(style)}]" if style else ""
        return f"{self.text[:15]}... {style_str} ({self.font_family}, {self.font_size}pt)"

# --- SVG Logic ---
def create_svg_from_objects(filename, width_mm, height_mm, text_objects):
    # Standard SVG 1.1 allows 'x' attributes on tspans for precise alignment
    dwg = svgwrite.Drawing(filename, size=(f'{width_mm}mm', f'{height_mm}mm'))
    dwg.viewbox(0, 0, width_mm, height_mm)
    
    for obj in text_objects:
        font_weight = 'bold' if obj.is_bold else 'normal'
        font_style = 'italic' if obj.is_italic else 'normal'
        lines = obj.text.split('\n')
        
        # Main text element
        text_elem = dwg.text(
            "",
            insert=(obj.x, obj.y),
            font_size=obj.font_size,
            font_weight=font_weight,
            font_style=font_style,
            font_family=obj.font_family
        )
        
        # Add lines
        for i, line in enumerate(lines):
            dy_val = "0" if i == 0 else f"{obj.line_spacing}em"
            # We set 'x' here to ensure every new line starts at the correct left-margin
            tspan = dwg.tspan(line, x=[obj.x], dy=[dy_val])
            text_elem.add(tspan)
            
        dwg.add(text_elem)
    
    dwg.save()
    return os.path.abspath(filename)

# --- GUI Logic ---
def main():
    sg.theme('DarkBlue3')

    canvas_w, canvas_h = 210, 297 
    text_objects = [] 
    selected_index = -1 
    
    default_fonts = ["Arial", "Courier", "Times New Roman"]

    # --- Layouts ---
    layout_canvas = [
        [sg.Text("Canvas Size (mm)", font=("Arial", 10, "bold"))],
        [sg.Text("W:", size=(3,1)), sg.Input(canvas_w, size=(6,1), key="-W-", enable_events=True),
         sg.Text("H:", size=(3,1)), sg.Input(canvas_h, size=(6,1), key="-H-", enable_events=True)]
    ]

    layout_editor = [
        [sg.Text("Current Text Object", font=("Arial", 10, "bold"))],
        [sg.Text("Content:")],
        [sg.Multiline("Hello", size=(30, 4), key="-INPUT_TEXT-", enable_events=True)],
        
        [sg.Text("Font:", size=(5,1)), sg.Combo(default_fonts, default_value="Arial", size=(20,1), key="-FONT-", enable_events=True)],
        
        [sg.Text("Pos X:", size=(5,1)), sg.Input(20, size=(6,1), key="-X-", enable_events=True),
         sg.Text("Pos Y:", size=(5,1)), sg.Input(40, size=(6,1), key="-Y-", enable_events=True)],
         
        [sg.Text("Size:", size=(5,1)), sg.Slider(range=(5, 100), default_value=20, orientation='h', size=(15,10), key="-SIZE-", enable_events=True)],
        
        [sg.Checkbox("Bold", key="-BOLD-", enable_events=True), 
         sg.Checkbox("Italic", key="-ITALIC-", enable_events=True)],
        
        [sg.Button("Add New Text", button_color="green", key="-ADD-"), 
         sg.Button("Update Selected", button_color="orange", key="-UPDATE-", disabled=True),
         sg.Button("Delete", button_color="red", key="-DELETE-", disabled=True)]
    ]

    layout_list = [
        [sg.Text("Objects on Canvas", font=("Arial", 10, "bold"))],
        [sg.Listbox(values=[], size=(45, 6), key="-LIST-", enable_events=True)]
    ]

    left_column = [
        [sg.Frame("", layout_canvas)],
        [sg.Frame("", layout_editor)],
        [sg.Frame("", layout_list)],
        # Status bar added below the export button
        [sg.Button("Export SVG", size=(40, 2), button_color="blue")],
        [sg.Text("", size=(40,1), key="-STATUS-", text_color="lightgreen", justification='center')]
    ]

    graph_elem = sg.Graph(
        canvas_size=(400, 600),
        graph_bottom_left=(0, canvas_h),
        graph_top_right=(canvas_w, 0),
        background_color='white',
        key="-GRAPH-"
    )

    layout = [
        [sg.Column(left_column, vertical_alignment='top'),
         sg.VerticalSeparator(),
         sg.Column([[sg.Text("Live Preview", text_color="yellow")], [graph_elem]], vertical_alignment='top')]
    ]

    window = sg.Window("SVG Plotter Studio", layout, finalize=True)

    # --- Font Loading ---
    try:
        all_families = sorted(list(set(tkinter.font.families())))
        clean_fonts = [f for f in all_families if not f.startswith('@') and f.strip()]
        def_font = "Arial" if "Arial" in clean_fonts else clean_fonts[0]
        window["-FONT-"].update(values=clean_fonts, value=def_font)
    except Exception:
        pass

    # --- Preview Logic ---
    def draw_preview(objects, width, height):
        graph = window["-GRAPH-"]
        graph.erase()
        graph.change_coordinates((0, height), (width, 0))
        graph.draw_rectangle((0,0), (width, height), line_color='black')
        
        for obj in objects:
            style_parts = []
            if obj.is_bold: style_parts.append("bold")
            if obj.is_italic: style_parts.append("italic")
            style_string = " ".join(style_parts) if style_parts else "normal"
            
            # Using tuple format for robustness
            font_spec = (obj.font_family, int(obj.font_size), style_string)
            
            graph.draw_text(
                text=obj.text,
                location=(obj.x, obj.y),
                font=font_spec,
                text_location=sg.TEXT_LOCATION_TOP_LEFT, 
                color="black"
            )

    def get_settings_from_gui(values):
        try:
            return TextObject(
                text=values["-INPUT_TEXT-"],
                x=float(values["-X-"]),
                y=float(values["-Y-"]),
                font_family=values["-FONT-"],
                font_size=int(values["-SIZE-"]),
                is_bold=values["-BOLD-"],
                is_italic=values["-ITALIC-"]
            )
        except ValueError:
            return None

    # --- Event Loop ---
    while True:
        event, values = window.read()
        
        if event in (sg.WIN_CLOSED, "Exit"):
            break

        # Clear status on any interaction
        if event != "Export SVG":
             window["-STATUS-"].update("")

        if event in ("-W-", "-H-"):
            try:
                w, h = float(values["-W-"]), float(values["-H-"])
                draw_preview(text_objects, w, h)
            except ValueError: pass

        if event == "-ADD-":
            new_obj = get_settings_from_gui(values)
            if new_obj:
                text_objects.append(new_obj)
                window["-LIST-"].update([str(o) for o in text_objects])
                w, h = float(values["-W-"]), float(values["-H-"])
                draw_preview(text_objects, w, h)

        if event == "-LIST-" and len(values["-LIST-"]) > 0:
            indexes = window["-LIST-"].get_indexes()
            if indexes:
                selected_index = indexes[0]
                obj = text_objects[selected_index]
                
                window["-INPUT_TEXT-"].update(obj.text)
                window["-X-"].update(obj.x)
                window["-Y-"].update(obj.y)
                window["-FONT-"].update(obj.font_family)
                window["-SIZE-"].update(obj.font_size)
                window["-BOLD-"].update(obj.is_bold)
                window["-ITALIC-"].update(obj.is_italic)
                
                window["-UPDATE-"].update(disabled=False)
                window["-DELETE-"].update(disabled=False)

        if event == "-UPDATE-" and selected_index >= 0:
            updated_obj = get_settings_from_gui(values)
            if updated_obj:
                text_objects[selected_index] = updated_obj
                window["-LIST-"].update([str(o) for o in text_objects])
                window["-UPDATE-"].update(disabled=True)
                window["-DELETE-"].update(disabled=True)
                selected_index = -1
                
                w, h = float(values["-W-"]), float(values["-H-"])
                draw_preview(text_objects, w, h)

        if event == "-DELETE-" and selected_index >= 0:
            del text_objects[selected_index]
            window["-LIST-"].update([str(o) for o in text_objects])
            window["-UPDATE-"].update(disabled=True)
            window["-DELETE-"].update(disabled=True)
            selected_index = -1
            
            w, h = float(values["-W-"]), float(values["-H-"])
            draw_preview(text_objects, w, h)

        if event == "Export SVG":
            try:
                # FIX: no_window=True prevents the FreeSimpleGUI helper window from appearing
                # and jumps straight to the OS Save As dialog.
                filename = sg.popup_get_file('Save SVG', 
                                           save_as=True, 
                                           no_window=True,
                                           file_types=(("SVG Files", "*.svg"),), 
                                           default_extension=".svg")
                if filename:
                    path = create_svg_from_objects(
                        filename, 
                        float(values["-W-"]), 
                        float(values["-H-"]), 
                        text_objects
                    )
                    # Show status in window instead of popup
                    window["-STATUS-"].update(f"Saved: {os.path.basename(path)}")
            except Exception as e:
                sg.popup_error(f"Error: {e}")

    window.close()

if __name__ == "__main__":
    main()