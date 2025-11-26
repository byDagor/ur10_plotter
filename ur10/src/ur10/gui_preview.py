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

def _render_document_to_image_element(window: sg.Window, document: vpype.Document, image_key: str, is_cmyk: bool, max_size: tuple = (600, 600)):
    """
    Generic helper to render a vpype.Document to a specific sg.Image element.
    """
    dpi = 100
    fig = Figure(figsize=(max_size[0] / dpi, max_size[1] / dpi), dpi=dpi)
    ax = fig.add_axes([0, 0, 1, 1])
    ax.axis('off')
    ax.set_facecolor('white')
    fig.set_facecolor('white')

    if document and not document.is_empty():
        try:
            bounds = document.bounds()
            if bounds:
                min_x, min_y, max_x, max_y = bounds
                ax.set_xlim(min_x, max_x)
                ax.set_ylim(min_y, max_y)
                ax.invert_yaxis()
                ax.set_aspect('equal', adjustable='box')
            
            color_map = {1: 'cyan', 2: 'magenta', 3: 'yellow', 4: 'black'}
            for layer_id, line_collection in document.layers.items():
                color = color_map.get(layer_id, 'black') if is_cmyk else 'black'
                for line in line_collection:
                    x_data = [p.real for p in line]
                    y_data = [p.imag for p in line]
                    ax.plot(x_data, y_data, color=color, linewidth=0.5)
        except Exception as e:
            print(f"Error during Matplotlib rendering for {image_key}: {e}")

    try:
        canvas = FigureCanvas(fig)
        canvas.draw()
        buf = canvas.buffer_rgba()
        img = Image.frombytes("RGBA", canvas.get_width_height(), buf)
        png_buffer = io.BytesIO()
        img.save(png_buffer, format="PNG")
        window[image_key].update(data=png_buffer.getvalue())
    except Exception as e:
        print(f"Error saving canvas to PNG for {image_key}: {e}")
        img = Image.new('RGB', max_size, color='white')
        bio = io.BytesIO()
        img.save(bio, format='PNG')
        window[image_key].update(data=bio.getvalue())

def update_preview(window: sg.Window, document: vpype.Document, is_cmyk: bool, max_size: tuple = (600, 600)):
    """Renders to the main -VISUAL- element."""
    _render_document_to_image_element(window, document, "-VISUAL-", is_cmyk, max_size)

def update_svg_preview(window: sg.Window, document: vpype.Document, max_size: tuple = (600, 600)):
    """Renders to the -SVG_PREVIEW_IMAGE- element, always in black."""
    _render_document_to_image_element(window, document, "-SVG_PREVIEW_IMAGE-", False, max_size)

def update_flow_preview(window: sg.Window, document: vpype.Document, is_cmyk: bool, max_size: tuple = (600, 600)):
    """Renders to the -FLOW_PREVIEW_IMAGE- element."""
    _render_document_to_image_element(window, document, "-FLOW_PREVIEW_IMAGE-", is_cmyk, max_size)

def update_hatched_preview(window: sg.Window, document: vpype.Document, is_cmyk: bool, max_size: tuple = (600, 600)):
    """Renders to the -HATCHED_PREVIEW_IMAGE- element."""
    _render_document_to_image_element(window, document, "-HATCHED_PREVIEW_IMAGE-", is_cmyk, max_size)

