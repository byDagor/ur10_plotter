import FreeSimpleGUI as sg
import vpype
import io
from PIL import Image
import xml.etree.ElementTree as ET

# --- MATPLOTLIB IMPORTS ---
import matplotlib
matplotlib.use('Agg')  # Use the 'Agg' backend for non-GUI rendering
from matplotlib.figure import Figure
from matplotlib.backends.backend_agg import FigureCanvasAgg as FigureCanvas
from matplotlib.patches import Polygon, Circle
from matplotlib.collections import PatchCollection
# --------------------------------

def preview_dots_from_svg(window: sg.Window, file_path: str, max_size: tuple = (600, 600)):
    """
    Manually parses an SVG file to find <line> elements and renders them as dots.
    This bypasses vpype's `read` command, which can incorrectly optimize dot files.
    """
    image_key = "-SVG_PREVIEW_IMAGE-"
    dpi = 100
    fig = Figure(figsize=(max_size[0] / dpi, max_size[1] / dpi), dpi=dpi)
    ax = fig.add_axes([0, 0, 1, 1])
    ax.axis('off')
    ax.set_facecolor('white')
    fig.set_facecolor('white')

    try:
        points = []
        # Register the SVG namespace to correctly find elements
        namespaces = {'svg': 'http://www.w3.org/2000/svg'}
        tree = ET.parse(file_path)
        root = tree.getroot()
        # Find all <line> tags, which are used for our dots
        for line in root.findall('.//svg:line', namespaces):
            try:
                x1 = float(line.get('x1'))
                y1 = float(line.get('y1'))
                # We only need one point from the zero-length line
                points.append((x1, y1))
            except (ValueError, TypeError):
                continue # Ignore lines with invalid coordinates

        if not points:
             window["-UR10_STATUS-"].print("Warning: No valid <line> elements found in SVG for dot preview.")
        else:
            window["-UR10_STATUS-"].print(f"Manually parsed and found {len(points)} dots to render.")
            # Set plot bounds based on the extents of the points
            min_x = min(p[0] for p in points)
            max_x = max(p[0] for p in points)
            min_y = min(p[1] for p in points)
            max_y = max(p[1] for p in points)
            ax.set_xlim(min_x, max_x)
            ax.set_ylim(min_y, max_y)
            ax.invert_yaxis()
            ax.set_aspect('equal', adjustable='box')

            # Use the efficient PatchCollection method to render circles
            patches = [Circle(p, radius=0.1) for p in points]
            p_collection = PatchCollection(patches, facecolor='black', edgecolor='black')
            ax.add_collection(p_collection)

    except Exception as e:
        window["-UR10_STATUS-"].print(f"Error manually parsing SVG: {e}")

    # --- Render the figure to the GUI element ---
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
        # Show a blank white image on error
        img = Image.new('RGB', max_size, color='white')
        bio = io.BytesIO()
        img.save(bio, format='PNG')
        window[image_key].update(data=bio.getvalue())


def _render_document_to_image_element(window: sg.Window, document: vpype.Document, image_key: str, is_cmyk: bool, max_size: tuple = (600, 600)):
    """
    Generic helper to render a vpype.Document to a specific sg.Image element.
    This is used for all previews EXCEPT for dot-based SVGs.
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
                
                # Dither preview uses polygons from memory
                if image_key == "-DITHER_PREVIEW_IMAGE-":
                    patches = []
                    for line in line_collection:
                        if len(line) > 2 and line[0] == line[-1]:
                            polygon_points = [(p.real, p.imag) for p in line]
                            poly = Polygon(polygon_points, closed=True)
                            patches.append(poly)
                    p = PatchCollection(patches, facecolor=color, edgecolor=color, linewidth=0.1)
                    ax.add_collection(p)
                # All other previews render lines
                else:
                    for line in line_collection:
                        x_data = [p.real for p in line]
                        y_data = [p.imag for p in line]
                        ax.plot(x_data, y_data, color=color, linewidth=0.5)
        except Exception as e:
            print(f"Error during Matplotlib rendering for {image_key}: {e}")

    # --- Render the figure to the GUI element ---
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

def update_dither_preview(window: sg.Window, document: vpype.Document, max_size: tuple = (600, 600)):
    """Renders to the -DITHER_PREVIEW_IMAGE- element."""
    _render_document_to_image_element(window, document, "-DITHER_PREVIEW_IMAGE-", False, max_size)