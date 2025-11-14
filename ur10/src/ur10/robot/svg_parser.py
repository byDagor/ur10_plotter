from xml.dom import minidom
from svg.path import parse_path

def parse_svg(file_path: str, start_x: float, start_y: float, start_z: float, rx: float, ry: float, rz: float, scale: float, dry_run: bool = False):
    """
    Parses an SVG file and converts the path data into a list of robot poses.

    :param file_path: Path to the SVG file.
    :param start_x: Starting X coordinate for the robot.
    :param start_y: Starting Y coordinate for the robot.
    :param start_z: Starting Z coordinate for the robot.
    :param rx: Rotation around X for the robot.
    :param ry: Rotation around Y for the robot.
    :param rz: Rotation around Z for the robot.
    :param scale: Scaling factor for the SVG coordinates.
    :param dry_run: If True, the Z coordinate will not be modified for drawing.
    :return: A list of robot poses.
    """
    line_list = []
    doc = minidom.parse(file_path)
    
    for _, path in enumerate(doc.getElementsByTagName('path')):
        d = path.getAttribute('d')
        parsed = parse_path(d)
        for obj in parsed:
            x = start_x - ((round(obj.end.real, 3) / scale) / 1000)
            y = start_y - ((round(obj.end.imag, 3) / scale) / 1000)
            z = start_z - 20 if not dry_run else start_z
            line_list.append((x, y, z, rx, ry, rz))
            
    doc.unlink()
    return line_list
