import vpype as vp
import numpy as np

def _convert_dither_circles_to_points(doc: vp.Document) -> vp.Document:
    """
    Converts a document containing closed polygons (circles) from the dither
    process into a document of zero-length lines (dots) at the center of each circle.
    This is used before saving or optimizing, so the robot gets dot commands.
    """

    new_doc = vp.Document()
    for layer in doc.layers.values():
        converted_lines = [] # Collect lines here
        for line in layer:
            # A circle is a closed polygon. Find its center.
            if len(line) > 2 and line[0] == line[-1]:
                # Calculate the centroid of the polygon vertices
                center_x = np.mean([p.real for p in line[:-1]])
                center_y = np.mean([p.imag for p in line[:-1]])
                # Create a zero-length line at the center
                converted_lines.append(np.array([complex(center_x, center_y), complex(center_x, center_y)]))
            else:
                # Keep other lines as they are
                converted_lines.append(line)
        new_lc = vp.LineCollection(converted_lines) # Create LineCollection from the list
        new_doc.add(new_lc)
    return new_doc