import FreeSimpleGUI as sg
import vpype
import io
from PIL import Image

# --- MATPLOTLIB IMPORTS ---
import matplotlib
matplotlib.use('Agg')  # Use the 'Agg' backend for non-GUI rendering
from matplotlib.figure import Figure
from matplotlib.backends.backend_agg import FigureCanvasAgg as FigureCanvas
# --------------------------------

def update_preview(window: sg.Window, document: vpype.Document, is_cmyk: bool, max_size: tuple = (600, 600)):
    """
    Renders a vpype.Document to a PNG using Matplotlib and displays it in the GUI.
    
    :param window: The sg.Window object
    :param document: The vpype.Document to render
    :param is_cmyk: If True, render with CMYK colors. If False, render all black.
    :param max_size: The max dimensions of the preview image
    """
    
    # 1. Create a matplotlib Figure and Axes
    dpi = 100
    fig = Figure(figsize=(max_size[0] / dpi, max_size[1] / dpi), dpi=dpi)
    ax = fig.add_axes([0, 0, 1, 1]) # Use full figure area
    ax.axis('off') # Hide the axes
    ax.set_facecolor('white')
    fig.set_facecolor('white')

    if document is None or document.is_empty():
        pass

    else:
        try:
            # 2. Get bounds and set plot limits
            bounds = document.bounds()
            if bounds:
                min_x, min_y, max_x, max_y = bounds
                ax.set_xlim(min_x, max_x)
                ax.set_ylim(min_y, max_y)
                ax.invert_yaxis()
                
                # Force matplotlib to maintain an equal aspect ratio,
                # adding "sidebars" (letterboxing) as needed.
                ax.set_aspect('equal', adjustable='box')
            
            color_map = { 1: 'cyan', 2: 'magenta', 3: 'yellow', 4: 'black' }

            # 3. Plot every line from the document
            for layer_id, line_collection in document.layers.items():
                
                color = 'black' # Default to black
                if is_cmyk:
                    # If CMYK is checked, try to get the layer color
                    color = color_map.get(layer_id, 'black')
                
                for line in line_collection:
                    x_data = [p.real for p in line]
                    y_data = [p.imag for p in line]
                    ax.plot(x_data, y_data, color=color, linewidth=0.5)

        except Exception as e:
            print(f"Error during Matplotlib rendering: {e}")
            pass

    # 4. Render the figure to a PNG buffer
    try:
        canvas = FigureCanvas(fig)
        canvas.draw()
        buf = canvas.buffer_rgba()
        img = Image.frombytes("RGBA", canvas.get_width_height(), buf)
        png_buffer = io.BytesIO()
        img.save(png_buffer, format="PNG")
        
        # 5. Update the GUI
        window["-VISUAL-"].update(data=png_buffer.getvalue())

    except Exception as e:
        print(f"Error saving Matplotlib canvas to PNG: {e}")
        img = Image.new('RGB', max_size, color='white')
        bio = io.BytesIO()
        img.save(bio, format='PNG')
        window["-VISUAL-"].update(data=bio.getvalue())


def update_svg_preview(window: sg.Window, document: vpype.Document, max_size: tuple = (600, 600)):
    """
    Renders a vpype.Document to a PNG for the SVG preview tab.
    Lines are always rendered in black.
    """
    
    # 1. Create a matplotlib Figure and Axes
    dpi = 100
    fig = Figure(figsize=(max_size[0] / dpi, max_size[1] / dpi), dpi=dpi)
    ax = fig.add_axes([0, 0, 1, 1]) # Use full figure area
    ax.axis('off') # Hide the axes
    ax.set_facecolor('white')
    fig.set_facecolor('white')

    if document is None or document.is_empty():
        pass

    else:
        try:
            # 2. Get bounds and set plot limits
            bounds = document.bounds()
            if bounds:
                min_x, min_y, max_x, max_y = bounds
                ax.set_xlim(min_x, max_x)
                ax.set_ylim(min_y, max_y)
                ax.invert_yaxis()
                ax.set_aspect('equal', adjustable='box')
            
            # 3. Plot every line from the document in black
            for layer_id, line_collection in document.layers.items():
                for line in line_collection:
                    x_data = [p.real for p in line]
                    y_data = [p.imag for p in line]
                    ax.plot(x_data, y_data, color='black', linewidth=0.5)

        except Exception as e:
            print(f"Error during Matplotlib rendering for SVG preview: {e}")
            pass

    # 4. Render the figure to a PNG buffer
    try:
        canvas = FigureCanvas(fig)
        canvas.draw()
        buf = canvas.buffer_rgba()
        img = Image.frombytes("RGBA", canvas.get_width_height(), buf)
        png_buffer = io.BytesIO()
        img.save(png_buffer, format="PNG")
        
        # 5. Update the GUI
        window["-SVG_PREVIEW_IMAGE-"].update(data=png_buffer.getvalue())

    except Exception as e:
        print(f"Error saving Matplotlib canvas to PNG for SVG preview: {e}")
        img = Image.new('RGB', max_size, color='white')
        bio = io.BytesIO()
        img.save(bio, format='PNG')
        window["-SVG_PREVIEW_IMAGE-"].update(data=bio.getvalue())
