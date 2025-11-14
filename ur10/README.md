# UR10 Plotter

This project contains Python scripts to control a UR10 robot arm as a plotter. It includes tools to convert images into SVG files that can then be sent to the robot for drawing.

## Applications

This repository contains two main GUI applications:

### `vpype_gui_v1.2.py`

A standalone graphical user interface for converting images into vector graphics (SVG files). This tool provides two different methods for vectorization:

*   **Flow Imager:** Uses `vpype`'s `flow_imager` plugin to create vector fields that follow the dark areas of an image, creating a "flow" effect.
*   **Hatched:** Uses the included `hatched.py` library to create hatched patterns from images, representing shading with lines.

This application is intended for generating plotter-friendly SVG files from images.

### `ur10_plotter_gui_v1.0.0.py`

This is the main application for the UR10 plotter project and is currently under development. It will eventually include features for controlling the UR10 robot arm, sending it SVG files to draw, and more. It is based on the same GUI framework as `vpype_gui_v1.2.py`.

## Core Libraries

### `hatched.py`

A Python library that converts an image into a series of lines (a "hatched" pattern) that represent the shading of the image. It uses image processing to find contours and then generates lines to fill those contours. It can create diagonal or circular hatching patterns.

## Usage

To run the GUI applications, you will need to have Python installed with the required dependencies.

```bash
python src/ur10/vpype_gui_v1.2.py
```

or

```bash
python src/ur10/ur10_plotter_gui_v1.0.0.py
```
