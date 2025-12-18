import FreeSimpleGUI as sg

def create_layout():
    """
    Creates the main GUI layout with a flexible, expanding preview structure.
    """
    sg.theme("DarkGrey2")
    
    # --- Shared settings ---
    CONTROLS_SIZE = (480, 600)
    PREVIEW_SIZE = (600, 600)

    # --- Tab 1: Flow Imager ---
    flow_controls = [
        [sg.Text("Vectorize an image using 'flow_imager'.", font="Helvetica 12")],
        [sg.HorizontalSeparator()],
        [sg.Text("Source Image:", s=(15, 1)), sg.Input(key="-IMG_PATH_FLOW-", s=(30, 1)), sg.FileBrowse(target="-IMG_PATH_FLOW-")],
        [sg.Text("Noise Coeff:", s=(15, 1)), sg.Input("0.0005", key="-FLOW_NOISE-", s=(10, 1))],
        [sg.Text("Min Separation:", s=(15, 1)), sg.Slider(range=(0.5, 10), default_value=0.8, resolution=0.1, orientation="h", key="-FLOW_MIN_SEP-", s=(30, 20))],
        [sg.Text("Max Separation:", s=(15, 1)), sg.Slider(range=(1, 20), default_value=10.0, resolution=0.1, orientation="h", key="-FLOW_MAX_SEP-", s=(30, 20))],
        [sg.Text("Min Length (mm):", s=(15, 1)), sg.Input("0", key="-FLOW_MIN_LEN-", s=(10, 1))],
        [sg.Text("Max Length (mm):", s=(15, 1)), sg.Input("1000", key="-FLOW_MAX_LEN-", s=(10, 1))],
        [sg.Text("Max Size (px):", s=(15, 1)), sg.Input("1600", key="-FLOW_MAX_SIZE-", s=(10, 1))],
        [sg.Text("N Fields:", s=(15, 1)), sg.Slider(range=(1, 10), default_value=1, resolution=1, orientation="h", key="-FLOW_N_FIELDS-", s=(30, 20))],
        [sg.Text("Edge Flow:", s=(15, 1)), sg.Slider(range=(0.0, 10.0), default_value=1.0, resolution=0.1, orientation="h", key="-FLOW_EDGE-", s=(30, 20))],
        [sg.Text("Dark Flow:", s=(15, 1)), sg.Slider(range=(0.0, 10.0), default_value=1.0, resolution=0.1, orientation="h", key="-FLOW_DARK-", s=(30, 20))],
        [sg.Text("Rotate:", s=(15, 1)), sg.Slider(range=(0, 360), default_value=0, resolution=1, orientation="h", key="-FLOW_ROTATE-", s=(30, 20))],
        [sg.Checkbox("Use CMYK Layers", key="-FLOW_CMYK-", default=False), sg.Checkbox("K-d Tree (`-kdt`)", key="-FLOW_KDT-", default=False), sg.Checkbox("Trim Border (`-tm`)", key="-FLOW_TRIM-", default=False)],
        [sg.Button("Vectorize with Flow Imager", key="-BTN_VECTORIZE_FLOW-", expand_x=True, font="Helvetica 10 bold"), sg.Button("Stop", key="-BTN_STOP_FLOW-", expand_x=True, font="Helvetica 10 bold", button_color=("white", "red"), disabled=True)],
        [sg.HorizontalSeparator(pad=((0,0), (10, 10)))],
        [sg.Text("Optimization", font="Helvetica 12")],
        [sg.Text("Merge Tol. (mm):", s=(15, 1)), sg.Input("0.1", key="-OPT_MERGE-", s=(10, 1))],
        [sg.Text("Simplify Tol. (mm):", s=(15, 1)), sg.Input("0.05", key="-OPT_SIMPLIFY-", s=(10, 1))],
        [sg.Button("Optimize Drawing", key="-BTN_OPTIMIZE-", expand_x=True)],
        [sg.HorizontalSeparator(pad=((0,0), (10, 10)))],
        [sg.Button("Save SVG", key="-BTN_SAVE-", expand_x=True, button_color=("white", "green"))],
        [sg.HorizontalSeparator()],
        [sg.Text("Status:")],
        [sg.Multiline(key="-LOG_FLOW-", size=(50, 10), autoscroll=True, disabled=True, expand_x=True)],
    ]
    flow_tab_layout = [[
        sg.Column(flow_controls, scrollable=True, vertical_scroll_only=True, size=CONTROLS_SIZE, pad=(0,0)),
        sg.VSeparator(),
        sg.Column([[sg.Image(key="-PREVIEW_IMAGE_FLOW-", background_color="white", expand_x=True, expand_y=True)]], expand_x=True, expand_y=True, pad=(0,0))
    ]]

    # --- Tab 2: Hatched ---
    hatched_controls = [
        [sg.Text("Vectorize an image using local 'hatched.py'.", font="Helvetica 12")],
        [sg.HorizontalSeparator()],
        [sg.Text("Source Image:", s=(15, 1)), sg.Input(key="-IMG_PATH_HATCHED-", s=(30, 1)), sg.FileBrowse(target="-IMG_PATH_HATCHED-")],
        [sg.Text("Image Scale:", s=(15, 1)), sg.Slider(range=(0.1, 1.0), default_value=0.5, resolution=0.05, orientation="h", key="-HATCHED_SCALE-", s=(30, 20))],
        [sg.Text("Hatch Offset (px):", s=(15, 1)), sg.Input("0.0", key="-HATCHED_OFFSET-", s=(10, 1))],
        [sg.Text("Gaussian Blur (px):", s=(15, 1)), sg.Slider(range=(0.0, 20.0), default_value=1.0, resolution=0.1, orientation="h", key="-HATCHED_BLUR-", s=(30, 20))],
        [sg.Text("Hatch Pitch (px):", s=(15, 1)), sg.Slider(range=(1.0, 20.0), default_value=5.0, resolution=0.1, orientation="h", key="-HATCHED_PITCH-", s=(30, 20))],
        [sg.Text("Hatch Angles:", s=(15, 1)), sg.Input("45", key="-HATCHED_ANGLES-", s=(20, 1)), sg.Text("Space-separated")],
        [sg.Text("Levels:", s=(15, 1)), sg.Input("64 128 192", key="-HATCHED_LEVELS-", s=(20, 1)), sg.Text("Space-separated (0-255)")],
        [sg.Text("Interpolation:", s=(15, 1)), sg.DropDown(["INTER_LINEAR", "INTER_NEAREST"], default_value="INTER_LINEAR", key="-HATCHED_INTERP-", s=(20, 1))],
        [sg.Text("Circular Center:", s=(15, 1)), sg.Input("0.5 0.5", key="-HATCHED_CENTER-", s=(10, 1))],
        [sg.Checkbox("Use CMYK Layers", key="-HATCHED_CMYK-", default=False), sg.Checkbox("Invert", key="-HATCHED_INVERT-", default=False), sg.Checkbox("Circular Hatch", key="-HATCHED_CIRCULAR-", default=False), sg.Checkbox("H-Mirror", key="-HATCHED_HMIRROR-", default=False)],
        [sg.Checkbox("Draw Contours", key="-HATCHED_LINES-", default=True), sg.Checkbox("Draw Hatch Fill", key="-HATCHED_HATCH-", default=True)],
        [sg.Button("Vectorize with Hatched", key="-BTN_VECTORIZE_HATCHED-", expand_x=True, font="Helvetica 10 bold"), sg.Button("Stop", key="-BTN_STOP_HATCHED-", expand_x=True, font="Helvetica 10 bold", button_color=("white", "red"), disabled=True)],
        [sg.HorizontalSeparator(pad=((0,0), (10, 10)))],
        [sg.Text("Optimization", font="Helvetica 12")],
        [sg.Text("Merge Tol. (mm):", s=(15, 1)), sg.Input("0.1", key="-OPT_MERGE-HATCHED-", s=(10, 1))],
        [sg.Text("Simplify Tol. (mm):", s=(15, 1)), sg.Input("0.05", key="-OPT_SIMPLIFY-HATCHED-", s=(10, 1))],
        [sg.Button("Optimize Drawing", key="-BTN_OPTIMIZE-HATCHED-", expand_x=True)],
        [sg.HorizontalSeparator(pad=((0,0), (10, 10)))],
        [sg.Button("Save SVG", key="-BTN_SAVE-HATCHED-", expand_x=True, button_color=("white", "green"))],
        [sg.HorizontalSeparator()],
        [sg.Text("Status:")],
        [sg.Multiline(key="-LOG_HATCHED-", size=(50, 10), autoscroll=True, disabled=True, expand_x=True)],
    ]
    hatched_tab_layout = [[
        sg.Column(hatched_controls, scrollable=True, vertical_scroll_only=True, size=CONTROLS_SIZE, pad=(0,0)),
        sg.VSeparator(),
        sg.Column([[sg.Image(key="-PREVIEW_IMAGE_HATCHED-", background_color="white", expand_x=True, expand_y=True)]], expand_x=True, expand_y=True, pad=(0,0))
    ]]

    # --- Tab 3: Dither ---
    dither_controls = [
        [sg.Text("Vectorize an image using dithering.", font="Helvetica 12")],
        [sg.HorizontalSeparator()],
        [sg.Text("Source Image:", s=(15, 1)), sg.Input(key="-IMG_PATH_DITHER-", s=(30, 1)), sg.FileBrowse(target="-IMG_PATH_DITHER-")],
        [sg.Text("Pen Diameter (mm):", s=(15, 1)), sg.Input("0.35", key="-DITHER_PEN_DIAMETER-", s=(10, 1))],
        [sg.Text("Detail (Horizontal Dots):", s=(15, 1)), sg.Slider(range=(50, 500), default_value=150, resolution=1, orientation="h", key="-DITHER_H_DOTS-", s=(30, 20))],
        [sg.Text("Dithering Method:", s=(15,1)), sg.DropDown(["Floyd-Steinberg", "Ordered (Halftone)", "Stochastic (Random)"], default_value="Floyd-Steinberg", key="-DITHER_METHOD-", s=(30,1), enable_events=True)],
        [
            sg.Column([[sg.Text("Contrast:", s=(15, 1)), sg.Slider(range=(0.1, 3.0), default_value=1.0, resolution=0.1, orientation="h", key="-DITHER_CONTRAST-", s=(30, 20))]], key='-COL_CONTRAST-'),
            sg.Column([[sg.Text("Density:", s=(15, 1)), sg.Slider(range=(0.1, 4.0), default_value=1.0, resolution=0.05, orientation="h", key="-DITHER_DENSITY-", s=(30, 20))]], key='-COL_DENSITY-', visible=False)
        ],
        [sg.Checkbox("Use CMYK Layers", key="-DITHER_CMYK-", default=False, enable_events=True)],
        [sg.pin(sg.Column([
            [sg.HorizontalSeparator()],
            [
                sg.Checkbox("C", key="-DITHER_CMYK_C-", default=True, text_color="cyan"), 
                sg.Checkbox("M", key="-DITHER_CMYK_M-", default=True, text_color="magenta"), 
                sg.Checkbox("Y", key="-DITHER_CMYK_Y-", default=True, text_color="yellow"), 
                sg.Checkbox("K", key="-DITHER_CMYK_K-", default=True, text_color="black")
            ],
            [sg.Text("Pixel Offset:", s=(15, 1)), sg.Input("1", key="-DITHER_PIXEL_OFFSET-", s=(10, 1))],
            [sg.HorizontalSeparator()]
        ], key='-COL_DITHER_CMYK-', visible=False))],
        [sg.Button("Vectorize with Dither", key="-BTN_VECTORIZE_DITHER-", expand_x=True, font="Helvetica 10 bold"), sg.Button("Stop", key="-BTN_STOP_DITHER-", expand_x=True, font="Helvetica 10 bold", button_color=("white", "red"), disabled=True)],
        [sg.HorizontalSeparator(pad=((0,0), (10, 10)))],
        [sg.Text("Optimization", font="Helvetica 12")],
        [sg.Text("Merge Tol. (mm):", s=(15, 1)), sg.Input("0.1", key="-OPT_MERGE-DITHER-", s=(10, 1))],
        [sg.Text("Simplify Tol. (mm):", s=(15, 1)), sg.Input("0.05", key="-OPT_SIMPLIFY-DITHER-", s=(10, 1))],
        [sg.Button("Optimize Drawing", key="-BTN_OPTIMIZE-DITHER-", expand_x=True)],
        [sg.HorizontalSeparator(pad=((0,0), (10, 10)))],
        [sg.Button("Save SVG", key="-BTN_SAVE-DITHER-", expand_x=True, button_color=("white", "green"))],
        [sg.HorizontalSeparator()],
        [sg.Text("Status:")],
        [sg.Multiline(key="-LOG_DITHER-", size=(50, 10), autoscroll=True, disabled=True, expand_x=True)],
    ]
    dither_tab_layout = [[
        sg.Column(dither_controls, scrollable=True, vertical_scroll_only=True, size=CONTROLS_SIZE, pad=(0,0)),
        sg.VSeparator(),
        sg.Column([[sg.Image(key="-PREVIEW_IMAGE_DITHER-", background_color="white", expand_x=True, expand_y=True)]], expand_x=True, expand_y=True, pad=(0,0))
    ]]

    # --- Tab 4: Text ---
    text_editor_controls = [
        [sg.Text("Current Text Object", font=("Arial", 10, "bold"))],
        [sg.Text("Content:")],
        [sg.Multiline("Hello", size=(30, 4), key="-TEXT_INPUT-", enable_events=True)],
        [sg.Text("Font:", size=(5,1)), sg.Combo(["Hershey", "astrology", "cursive", "cyrillic", "futural", "futuram", "gothgbt", "gothgrt", "gothiceng", "gothicger", "gothicita", "gothitt", "greek", "japanese", "markers", "mathlow", "mathupp", "meteorology", "music", "scriptc", "scripts", "symbolic", "timesg", "timesi", "timesib", "timesr", "timesrb"], default_value="futural", size=(20,1), key="-TEXT_FONT-", enable_events=True)],
        [sg.Text("Pos X:", size=(5,1)), sg.Input(20, size=(6,1), key="-TEXT_POS_X-", enable_events=True),
         sg.Text("Pos Y:", size=(5,1)), sg.Input(40, size=(6,1), key="-TEXT_POS_Y-", enable_events=True)],
        [sg.Text("Size:", size=(5,1)), sg.Slider(range=(5, 100), default_value=20, orientation='h', size=(15,10), key="-TEXT_FONT_SIZE-", enable_events=True)],
        [sg.Text("Line Spacing:", size=(15,1)), sg.Input("1.2", size=(10,1), key="-TEXT_LINE_SPACING-", enable_events=True)],
        [sg.Checkbox("Bold", key="-TEXT_BOLD-", enable_events=True), 
         sg.Checkbox("Italic", key="-TEXT_ITALIC-", enable_events=True)],
        [sg.Button("Add New Text", button_color="green", key="-TEXT_ADD-"), 
         sg.Button("Update Selected", button_color="orange", key="-TEXT_UPDATE-", disabled=True),
         sg.Button("Delete", button_color="red", key="-TEXT_DELETE-", disabled=True)]
    ]

    text_list_controls = [
        [sg.Text("Objects on Canvas", font=("Arial", 10, "bold"))],
        [sg.Listbox(values=[], size=(45, 6), key="-TEXT_LIST-", enable_events=True)]
    ]

    text_controls = [
        [sg.Frame("", text_editor_controls)],
        [sg.Frame("", text_list_controls)],
        [sg.Button("Preview", key="-TEXT_PREVIEW-", expand_x=True)],
        [sg.Button("Save SVG", key="-TEXT_SAVE_SVG-", expand_x=True, button_color=("white", "green"), disabled=True)],
        [sg.Text("Status:")],
        [sg.Multiline(key="-LOG_TEXT-", size=(50, 10), autoscroll=True, disabled=True, expand_x=True)],
    ]

    text_tab_layout = [[
        sg.Column(text_controls, scrollable=True, vertical_scroll_only=True, size=CONTROLS_SIZE, pad=(0,0)),
        sg.VSeparator(),
        sg.Column([[sg.Image(key="-PREVIEW_IMAGE_TEXT-", background_color="white", expand_x=True, expand_y=True)]], expand_x=True, expand_y=True, pad=(0,0))
    ]]
    
    # --- Tab 5: UR10 Control ---
    ur10_controls = [
        [sg.Text("UR10 Robot Control", font="Helvetica 12")],
        [sg.HorizontalSeparator()],
        [sg.Text("Robot IP:", s=(15, 1)), sg.Input("10.0.10.208", key="-UR10_IP-", s=(20, 1))],
        [sg.Button("Connect to UR10", key="-BTN_UR10_CONNECT-", expand_x=True)],
        [sg.HorizontalSeparator()],
        [sg.Text("SVG File:", s=(15, 1)), sg.Input(key="-SVG_PATH-", s=(30, 1), enable_events=True), sg.FileBrowse(target="-SVG_PATH-")],
        [sg.Checkbox("Render SVG as dots (for dithered files)", key="-RENDER_AS_DOTS-", default=False)],
        [sg.Text("Home Position:", s=(15,1)), sg.Input("Not Set", key="-HOME_POSE_DISPLAY-", s=(30,1), disabled=True)],
        [sg.Button("Set Home to Current Position", key="-BTN_SET_HOME-", expand_x=True, disabled=True)],
        [sg.Text("Canvas Corner:", s=(15,1)), sg.DropDown(["Top Left", "Top Right", "Bottom Left", "Bottom Right"], default_value="Top Left", key="-CANVAS_CORNER-", s=(20,1), readonly=True)],
        [sg.Text("Global Rotation:", s=(15,1)), sg.DropDown([0, -90, 90, 180], default_value=90, key="-GLOBAL_ROTATION-", s=(20,1), readonly=True)],
        [sg.Text("Canvas Width (mm):", s=(15, 1)), sg.Input("297", key="-CANVAS_WIDTH-", s=(10, 1)), sg.Text("Height (mm):", s=(10, 1)), sg.Input("210", key="-CANVAS_HEIGHT-", s=(10, 1))],
        [sg.Text("Plotting Speed (m/s):", s=(15, 1)), sg.Slider(range=(0.01, 1.0), default_value=0.10, resolution=0.01, orientation="h", key="-PLOT_SPEED-", s=(30, 20))],
        [sg.Text("Acceleration (m/s^2):", s=(15, 1)), sg.Slider(range=(0.05, 2.0), default_value=0.5, resolution=0.01, orientation="h", key="-PLOT_ACCEL-", s=(30, 20))],
        [sg.Checkbox("Dry Run", key="-DRY_RUN-", default=False)],
        [sg.Button("Start Plotting", key="-BTN_START-", expand_x=True, disabled=True, button_color=("white", "green")), sg.Button("Pause", key="-BTN_PAUSE-", expand_x=True, disabled=True, button_color=("white", "orange")), sg.Button("Stop", key="-BTN_STOP-", expand_x=True, disabled=True, button_color=("white", "red"))],
        [sg.Button("Go Home", key="-BTN_UR10_HOME-", expand_x=True, disabled=True), sg.Button("Pen Change", key="-BTN_PEN_CHANGE-", expand_x=True, disabled=True)],
        [sg.Button("Check Canvas", key="-BTN_CHECK_CANVAS-", expand_x=True, disabled=True)],
        [sg.HorizontalSeparator()],
        [sg.Text("Status:")],
        [sg.Multiline(key="-UR10_STATUS-", size=(50, 5), autoscroll=True, disabled=True)],
    ]
    
    ur10_preview_tabs = sg.TabGroup([[
        sg.Tab("SVG Preview", [[sg.Image(key="-SVG_PREVIEW_IMAGE-", background_color="white", expand_x=True, expand_y=True)]], key="-TAB_SVG_PREVIEW-", expand_x=True, expand_y=True),
        sg.Tab("Real-time Drawing", [[sg.Graph(
            canvas_size=PREVIEW_SIZE, 
            graph_bottom_left=(0, PREVIEW_SIZE[1]), 
            graph_top_right=(PREVIEW_SIZE[0], 0), 
            key="-REALTIME_GRAPH-", 
            background_color="white", 
            expand_x=True, 
            expand_y=True
        )]], key="-TAB_REALTIME_DRAWING-", expand_x=True, expand_y=True)
    ]], expand_x=True, expand_y=True)

    ur10_tab_layout = [[
        sg.Column(ur10_controls, scrollable=True, vertical_scroll_only=True, size=CONTROLS_SIZE, pad=(0,0)),
        sg.VSeparator(),
        sg.Column([[ur10_preview_tabs]], expand_x=True, expand_y=True, pad=(0,0))
    ]]
    
    # --- Instructions Tab ---
    LBL_W = 25 # Width of the label column
    DESC_W = 100 # Width of the description column (with wrapping)
    
    instructions_layout = [
        [sg.Text("Parameter Explanations", font="Helvetica 14 bold")],
        [sg.HorizontalSeparator()],
        
        [sg.Text("Flow Imager Parameters", font="Helvetica 12 bold", pad=((0,0),(10,5)))],
        [sg.Text("Noise Coeff:", font="Helvetica 10 bold", size=(LBL_W,1)), sg.Text("Controls 'wiggliness'. 0.0 is smooth, 0.05 is chaotic. (Ratio)", size=(DESC_W, None))],
        [sg.Text("Min/Max Separation:", font="Helvetica 10 bold", size=(LBL_W,1)), sg.Text("Controls line density. (mm)", size=(DESC_W, None))],
        [sg.Text("Min/Max Length:", font="Helvetica 10 bold", size=(LBL_W,1)), sg.Text("Filters lines that are too short or long. (mm)", size=(DESC_W, None))],
        [sg.Text("Max Size:", font="Helvetica 10 bold", size=(LBL_W,1)), sg.Text("Downscales image to this dimension. 1600 is good. (px)", size=(DESC_W, None))],
        [sg.Text("N Fields:", font="Helvetica 10 bold", size=(LBL_W,1)), sg.Text("Overlays multiple flow fields for cross-hatching. (Count)", size=(DESC_W, None))],
        [sg.Text("Edge Flow:", font="Helvetica 10 bold", size=(LBL_W,1)), sg.Text("How strongly lines follow hard edges/outlines. (Multiplier)", size=(DESC_W, None))],
        [sg.Text("Dark Flow:", font="Helvetica 10 bold", size=(LBL_W,1)), sg.Text("How strongly lines swirl around dark areas. (Multiplier)", size=(DESC_W, None))],
        [sg.Text("Rotate:", font="Helvetica 10 bold", size=(LBL_W,1)), sg.Text("Rotates the flow field before drawing. (Degrees)", size=(DESC_W, None))],
        [sg.Text("Use CMYK Layers:", font="Helvetica 10 bold", size=(LBL_W,1)), sg.Text("Separates into C, M, Y, K layers (1-4) for multi-pen plotting.", size=(DESC_W, None))],
        [sg.Text("K-d Tree (-kdt):", font="Helvetica 10 bold", size=(LBL_W,1)), sg.Text("Uses a different search algorithm. Uncheck if you get errors.", size=(DESC_W, None))],
        [sg.Text("Trim Border (-tm):", font="Helvetica 10 bold", size=(LBL_W,1)), sg.Text("Removes lines that are exactly on the image border.", size=(DESC_W, None))],

        [sg.Text("Hatched Parameters", font="Helvetica 12 bold", pad=((0,0),(15,5)))],
        [sg.Text("Image Scale:", font="Helvetica 10 bold", size=(LBL_W,1)), sg.Text("Downscales image. 0.5 = 50%. Improves performance. (Ratio)", size=(DESC_W, None))],
        [sg.Text("Hatch Offset:", font="Helvetica 10 bold", size=(LBL_W,1)), sg.Text("Shifts the starting point of the hatch pattern. (px)", size=(DESC_W, None))],
        [sg.Text("Gaussian Blur:", font="Helvetica 10 bold", size=(LBL_W,1)), sg.Text("Blurs image before finding contours. 0 is sharp, 5 is soft. (px)", size=(DESC_W, None))],
        [sg.Text("Hatch Pitch:", font="Helvetica 10 bold", size=(LBL_W,1)), sg.Text("Base distance between lines in darkest areas. Smaller = denser. (px)", size=(DESC_W, None))],
        [sg.Text("Hatch Angles:", font="Helvetica 10 bold", size=(LBL_W,1)), sg.Text("Direction of lines. 45 is diagonal. 45 135 is cross-hatching. (Degrees)", size=(DESC_W, None))],
        [sg.Text("Levels:", font="Helvetica 10 bold", size=(LBL_W,1)), sg.Text("Grayscale thresholds for shading. e.g., 64 128 192. More = more detail. (0-255)", size=(DESC_W, None))],
        [sg.Text("Interpolation:", font="Helvetica 10 bold", size=(LBL_W,1)), sg.Text("INTER_LINEAR is smooth. INTER_NEAREST is pixelated.", size=(DESC_W, None))],
        [sg.Text("Circular Center:", font="Helvetica 10 bold", size=(LBL_W,1)), sg.Text("Center for circular hatches. 0.5 0.5 is the middle. (Ratio 0.0-1.0)", size=(DESC_W, None))],
        [sg.Text("Invert:", font="Helvetica 10 bold", size=(LBL_W,1)), sg.Text("Inverts the image (hatches light areas instead of dark).", size=(DESC_W, None))],
        [sg.Text("Circular Hatch:", font="Helvetica 10 bold", size=(LBL_W,1)), sg.Text("Switches from diagonal lines to concentric circles.", size=(DESC_W, None))],
        [sg.Text("H-Mirror:", font="Helvetica 10 bold", size=(LBL_W,1)), sg.Text("Flips the image horizontally.", size=(DESC_W, None))],
        [sg.Text("Draw Contours:", font="Helvetica 10 bold", size=(LBL_W,1)), sg.Text("Draws the outlines of the shadow shapes.", size=(DESC_W, None))],
        [sg.Text("Draw Hatch Fill:", font="Helvetica 10 bold", size=(LBL_W,1)), sg.Text("Draws the shading lines inside the contours.", size=(DESC_W, None))],

        [sg.Text("Dither Parameters", font="Helvetica 12 bold", pad=((0,0),(15,5)))],
        [sg.Text("Dot Radius (mm):", font="Helvetica 10 bold", size=(LBL_W,1)), sg.Text("The radius of each dot in the final drawing. Should be half your physical pen's diameter.", size=(DESC_W, None))],
        [sg.Text("Detail (Horizontal Dots):", font="Helvetica 10 bold", size=(LBL_W,1)), sg.Text("The number of possible dot positions horizontally. This controls the output resolution.", size=(DESC_W, None))],
        [sg.Text("Dithering Method:", font="Helvetica 10 bold", size=(LBL_W,1)), sg.Text("The algorithm used to generate the dot pattern.", size=(DESC_W, None))],
        [sg.Text("  - Floyd-Steinberg:", font="Helvetica 10", size=(LBL_W,1)), sg.Text("High-quality, organic-looking error diffusion.", size=(DESC_W, None))],
        [sg.Text("  - Ordered (Halftone):", font="Helvetica 10", size=(LBL_W,1)), sg.Text("Clean, structured, grid-like patterns.", size=(DESC_W, None))],
        [sg.Text("  - Stochastic (Random):", font="Helvetica 10", size=(LBL_W,1)), sg.Text("Noisy, organic, but potentially messy pattern.", size=(DESC_W, None))],
        [sg.Text("Contrast:", font="Helvetica 10 bold", size=(LBL_W,1)), sg.Text("Used by Floyd-Steinberg. Adjusts image contrast before dithering. 1.0 is normal.", size=(DESC_W, None))],
        [sg.Text("Density:", font="Helvetica 10 bold", size=(LBL_W,1)), sg.Text("Used by Ordered and Stochastic methods. Adjusts the overall darkness. (Multiplier)", size=(DESC_W, None))],

        [sg.Text("UR10 Control", font="Helvetica 12 bold", pad=((0,0),(15,5)))],
        [sg.Text("Robot IP:", font="Helvetica 10 bold", size=(LBL_W,1)), sg.Text("The IP address of the UR10 robot.", size=(DESC_W, None))],
        [sg.Text("Connect to UR10:", font="Helvetica 10 bold", size=(LBL_W,1)), sg.Text("Connects to the robot at the specified IP address.", size=(DESC_W, None))],
        [sg.Text("SVG File:", font="Helvetica 10 bold", size=(LBL_W,1)), sg.Text("The SVG file to be plotted by the robot.", size=(DESC_W, None))],
        [sg.Text("Set Home to Current Position:", font="Helvetica 10 bold", size=(LBL_W,1)), sg.Text("Move the robot so the pen is touching the canvas corner. This sets the 'drawing Z-height'. The robot's actual home will be 20mm above this point.", size=(DESC_W, None))],
        [sg.Text("Canvas Corner:", font="Helvetica 10 bold", size=(LBL_W,1)), sg.Text("The corner of the canvas to use as the origin.", size=(DESC_W, None))],
        [sg.Text("SVG Scale:", font="Helvetica 10 bold", size=(LBL_W,1)), sg.Text("The scale of the SVG file.", size=(DESC_W, None))],
        [sg.Text("Dry Run:", font="Helvetica 10 bold", size=(LBL_W,1)), sg.Text("If checked, the robot will move at the higher 'home' Z-height, 20mm above the canvas.", size=(DESC_W, None))],
        [sg.Text("Start Plotting:", font="Helvetica 10 bold", size=(LBL_W,1)), sg.Text("Starts the plotting process.", size=(DESC_W, None))],
        [sg.Text("Pause/Resume:", font="Helvetica 10 bold", size=(LBL_W,1)), sg.Text("Pauses the plotting process and lifts the pen. Press again to resume.", size=(DESC_W, None))],
        [sg.Text("Stop:", font="Helvetica 10 bold", size=(LBL_W,1)), sg.Text("Stops the plotting process and returns the robot to its home position.", size=(DESC_W, None))],
        [sg.Text("Go Home:", font="Helvetica 10 bold", size=(LBL_W,1)), sg.Text("Moves the robot to the safe home position (20mm above the canvas).", size=(DESC_W, None))],
    ]
    instructions_tab = [[sg.Column(instructions_layout, scrollable=True, vertical_scroll_only=True, size=(1080, 600), pad=(0,0))]]

    # --- Main Layout ---
    layout = [[
        sg.Text("PLOTTUR10 GUI", font="Helvetica 18 bold", pad=((0,0), (0, 10)))
    ], [
        sg.TabGroup([[
            sg.Tab("Flow Imager", flow_tab_layout, key="-TAB_FLOW-"),
            sg.Tab("Hatched", hatched_tab_layout, key="-TAB_HATCHED-"),
            sg.Tab("Dither", dither_tab_layout, key="-TAB_DITHER-"),
            sg.Tab("Text", text_tab_layout, key="-TAB_TEXT-"),
            sg.Tab("UR10 Control", ur10_tab_layout, key="-TAB_UR10-"),
            sg.Tab("Instructions", instructions_tab, key="-TAB_INSTRUCTIONS-")
        ]], key="-TABGROUP-", expand_x=True, expand_y=True)
    ]]
    
    return layout
