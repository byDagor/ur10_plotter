"""Centerline vectorizer: trace a line drawing into single-stroke polylines.

Turns a raster line drawing (dark lines on white, or the inverse) into a vpype
Document where every drawn line is ONE pen stroke down its centerline. Thickness
is discarded: a thick or double-drawn outline collapses to a single line, so the
robot redraws the picture line-for-line without multiple passes -- infinite
copies of the same single-line drawing.

Pipeline:
    load -> grayscale -> (blur) -> binarize (Otsu / manual + invert)
      -> skeletonize (skimage, thickness -> 1-px centerline)
        -> trace the skeleton's pixel graph into polylines
          -> drop specks -> simplify (shapely) -> vpype.Document

Trace method: on the 1-px skeleton, a pixel's skeleton-neighbour count is its
degree. Degree-1 pixels are endpoints, degree>=3 are junctions -- both are
"nodes"; degree-2 runs between nodes are edges. We walk each edge once into a
polyline. Pure loops (closed curves like the camera's lens rings, all degree-2,
no node) have no node to start from, so a second pass seeds a walk on any
still-unused edge and returns to its start.

Runs off the UI thread like the other vectorizers, reporting progress through the
EventBridge (-LOG_MESSAGE-) and returning the document via -THREAD_DONE-. Stops
cooperatively on the shared stop_event (the Hatched pattern). Heavy imports
(cv2 / skimage / scipy / shapely) are done inside the worker so a missing one
fails at vectorize time with a clear message rather than at app startup.
"""

import time
import traceback

import numpy as np
import vpype

# 8-connected neighbour offsets (skeleton pixels touch diagonally too).
_NB = [(-1, -1), (-1, 0), (-1, 1),
       (0, -1),           (0, 1),
       (1, -1),  (1, 0),  (1, 1)]


def _load_binary(path, max_dim, blur, threshold, auto_threshold, invert):
    """Read the image and return a boolean mask (True = ink / line to trace)."""
    import cv2

    img = cv2.imread(path, cv2.IMREAD_GRAYSCALE)
    if img is None:
        raise ValueError(f"Could not read image: {path}")

    h, w = img.shape
    scale = max_dim / float(max(h, w))
    if scale < 1.0:                                   # shrink big images for speed
        img = cv2.resize(img, (max(1, round(w * scale)), max(1, round(h * scale))),
                         interpolation=cv2.INTER_AREA)
    elif scale > 1.0:                                 # enlarge small images so thin
        img = cv2.resize(img, (round(w * scale), round(h * scale)),   # strokes / small
                         interpolation=cv2.INTER_CUBIC)               # text skeletonize
                                                                      # into clean lines

    if blur and blur > 0:
        k = int(blur) * 2 + 1                         # kernel must be odd
        img = cv2.GaussianBlur(img, (k, k), 0)

    # THRESH_BINARY_INV: pixels darker than the threshold become foreground, so
    # dark lines on a light page are the ink we trace.
    if auto_threshold:
        _, mask = cv2.threshold(img, 0, 255,
                                cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    else:
        _, mask = cv2.threshold(img, int(threshold), 255, cv2.THRESH_BINARY_INV)

    if invert:                                        # light lines on a dark page
        mask = 255 - mask
    return mask > 0


def _degree_map(skel):
    """Per-pixel count of 8-connected skeleton neighbours (0 off the skeleton)."""
    from scipy.ndimage import convolve

    kernel = np.array([[1, 1, 1], [1, 0, 1], [1, 1, 1]], dtype=np.uint8)
    deg = convolve(skel.astype(np.uint8), kernel, mode="constant", cval=0)
    return deg * skel                                 # zero out non-skeleton pixels


def _skeleton_neighbours(r, c, skel, h, w):
    """8-connected skeleton pixels adjacent to (r, c)."""
    out = []
    for dr, dc in _NB:
        rr, cc = r + dr, c + dc
        if 0 <= rr < h and 0 <= cc < w and skel[rr, cc]:
            out.append((rr, cc))
    return out


def _prune_spurs(skel, max_len, stop_event=None):
    """Erase short "whisker" branches that dead-end at a junction.

    Skeletonizing a thick/wobbly stroke sprouts little side branches at every
    bump and corner. A spur is a run from an endpoint (degree 1) that reaches a
    junction (degree >=3) within ``max_len`` pixels; we delete its pixels but
    keep the junction. A short run that instead ends at another endpoint is a
    genuine tiny stroke, not a whisker, so it is left for the min-length filter.
    Removing a spur can lower a junction's degree and expose a nested spur, so we
    repeat a few passes until nothing more is removed.
    """
    if max_len <= 0:
        return skel
    h, w = skel.shape
    skel = skel.copy()
    for _pass in range(4):
        if stop_event is not None and stop_event.is_set():
            raise InterruptedError("Centerline trace stopped by user")
        deg = _degree_map(skel)
        remove = set()
        for r, c in np.argwhere(deg == 1):
            ep = (int(r), int(c))
            branch = [ep]
            prev, cur = None, ep
            hit_junction = False
            while len(branch) <= max_len:
                nxt = next((n for n in _skeleton_neighbours(*cur, skel, h, w)
                            if n != prev), None)
                if nxt is None:                       # isolated dead-end: keep it
                    break
                if deg[nxt] >= 3:                     # reached a junction -> spur
                    hit_junction = True
                    break
                if deg[nxt] != 2:                     # another endpoint -> real stroke
                    break
                branch.append(nxt)
                prev, cur = cur, nxt
            if hit_junction and len(branch) <= max_len:
                remove.update(branch)                 # drop spur, keep the junction
        if not remove:
            break
        for r, c in remove:
            skel[r, c] = False
    return skel


def _trace_skeleton(skel, stop_event=None):
    """Walk a 1-px skeleton into a list of polylines (each a list of (x, y)).

    x = column, y = row (image space, y-down) -- matches SVG/preview orientation.
    """
    h, w = skel.shape
    deg = _degree_map(skel)

    def neighbours(r, c):
        return _skeleton_neighbours(r, c, skel, h, w)

    used = set()            # undirected edges already traced (frozenset of 2 px)
    polylines = []

    def walk(start, second):
        """Follow degree-2 pixels from an initial step until the next node."""
        path = [start, second]
        used.add(frozenset((start, second)))
        prev, cur = start, second
        # Continue only while cur is an interior (degree-2) pixel.
        while deg[cur[0], cur[1]] == 2:
            nxt = None
            for n in neighbours(*cur):
                if n != prev:
                    nxt = n
                    break
            if nxt is None:
                break
            edge = frozenset((cur, nxt))
            if edge in used:                          # closed the loop
                path.append(nxt)
                break
            used.add(edge)
            path.append(nxt)
            prev, cur = cur, nxt
        return path

    # Pass 1: start every edge from a node (endpoint deg==1 or junction deg>=3).
    nodes = np.argwhere((deg != 2) & (deg > 0))
    for i, (r, c) in enumerate(nodes):
        if stop_event is not None and (i & 1023) == 0 and stop_event.is_set():
            raise InterruptedError("Centerline trace stopped by user")
        node = (int(r), int(c))
        for n in neighbours(*node):
            if frozenset((node, n)) not in used:
                polylines.append(walk(node, n))

    # Pass 2: pure loops (all degree-2, no node) have no seed above; find any
    # remaining unused edge and walk it back to its start.
    loop_px = np.argwhere(deg == 2)
    for i, (r, c) in enumerate(loop_px):
        if stop_event is not None and (i & 1023) == 0 and stop_event.is_set():
            raise InterruptedError("Centerline trace stopped by user")
        p = (int(r), int(c))
        for n in neighbours(*p):
            if frozenset((p, n)) not in used:
                polylines.append(walk(p, n))

    # (r, c) -> (x, y)
    return [[(float(c), float(r)) for r, c in poly] for poly in polylines]


def _polyline_length(pts):
    arr = np.asarray(pts, dtype=float)
    if len(arr) < 2:
        return 0.0
    return float(np.hypot(*(arr[1:] - arr[:-1]).T).sum())


def _smooth(pts, amount):
    """Smooth a traced polyline to shed the pixel-staircase wobble.

    ``amount`` is the smoothing radius in px (0 = off): features smaller than
    roughly this vanish. We resample the line to anchors spaced along its arc
    length, each the *average* of the traced points near it -- that local
    averaging is the low-pass that erases the +/-1 px staircase -- then fit a
    cubic B-spline through the anchors and resample it densely. Anchoring a
    bounded number of control points (rather than FITPACK's auto-knot smoothing
    spline, which explodes its knot count on jittery data) keeps this fast and
    predictable at every setting. Closed loops (lens rings) are fitted
    periodically so they stay smooth across the seam.
    """
    if amount <= 0 or len(pts) < 4:
        return pts
    from scipy.interpolate import splev, splprep

    arr = np.asarray(pts, dtype=float)
    closed = float(np.hypot(*(arr[0] - arr[-1]))) < 1e-6
    if closed:
        arr = arr[:-1]
    if len(arr) < 4:
        return pts

    # Cumulative arc length, then anchor positions spaced ~`spacing` px apart.
    seg = np.hypot(*np.diff(arr, axis=0).T)
    dist = np.concatenate([[0.0], np.cumsum(seg)])
    length = float(dist[-1])
    if length <= 0:
        return pts
    spacing = 2.0 + 2.0 * amount
    n_anchor = int(min(max(length / spacing + 1, 4), 200))
    targets = np.linspace(0.0, length, n_anchor, endpoint=not closed)

    # Each anchor = mean of the traced points within half a spacing of it.
    half = spacing / 2.0
    lo = np.searchsorted(dist, targets - half, side="left")
    hi = np.searchsorted(dist, targets + half, side="right")
    anchors = np.array([arr[a:b].mean(axis=0) if b > a else arr[min(a, len(arr) - 1)]
                        for a, b in zip(lo, hi)])

    # Drop consecutive duplicate anchors (splprep rejects them).
    keep = [anchors[0]]
    for p in anchors[1:]:
        if np.hypot(*(p - keep[-1])) > 1e-9:
            keep.append(p)
    anchors = np.asarray(keep)
    if len(anchors) < 4:
        return pts

    try:
        tck, _ = splprep([anchors[:, 0], anchors[:, 1]],
                         s=0, per=1 if closed else 0, k=3)
    except Exception:                        # degenerate fit -> leave line as-is
        return pts
    n = int(min(max(length / 2.0, 16), 2000))          # ~1 sample / 2 px
    xs, ys = splev(np.linspace(0.0, 1.0, n), tck)
    out = list(zip(xs.tolist(), ys.tolist()))
    if closed:
        out.append(out[0])
    return out


def _simplify(pts, tol):
    """Douglas-Peucker via shapely; keeps closed loops closed."""
    if tol <= 0 or len(pts) < 3:
        return pts
    from shapely.geometry import LineString

    simplified = LineString(pts).simplify(tol, preserve_topology=False)
    coords = list(simplified.coords)
    return coords if len(coords) >= 2 else pts


def run_centerline_thread(window, params, stop_event):
    """Vectorize an image to single-stroke centerlines (off the UI thread)."""
    try:
        t0 = time.time()
        window.write_event_value("-LOG_MESSAGE-", "Loading and binarizing image...")
        binary = _load_binary(
            params["img_path"],
            max_dim=params["max_dim"],
            blur=params["blur"],
            threshold=params["threshold"],
            auto_threshold=params["auto_threshold"],
            invert=params["invert"],
        )
        if stop_event.is_set():
            raise InterruptedError("Centerline trace stopped by user")

        window.write_event_value("-LOG_MESSAGE-",
                                 "Skeletonizing (collapsing thickness to centerlines)...")
        from skimage.morphology import skeletonize
        skel = skeletonize(binary)
        if not skel.any():
            window.write_event_value(
                "-THREAD_DONE-",
                (None, "No lines found. Try adjusting the threshold or Invert.", False))
            return
        if stop_event.is_set():
            raise InterruptedError("Centerline trace stopped by user")

        prune = int(params.get("prune", 0))
        if prune > 0:
            window.write_event_value("-LOG_MESSAGE-",
                                     "Pruning spurs (removing skeleton whiskers)...")
            skel = _prune_spurs(skel, prune, stop_event)

        window.write_event_value("-LOG_MESSAGE-", "Tracing strokes...")
        polylines = _trace_skeleton(skel, stop_event)

        min_len = float(params["min_len"])
        tol = float(params["simplify"])
        smooth = float(params.get("smooth", 0.0))
        lines = []
        for pts in polylines:
            if _polyline_length(pts) < min_len:       # drop specks / stray pixels
                continue
            pts = _smooth(pts, smooth)                # de-wobble before simplifying
            pts = _simplify(pts, tol)
            if len(pts) < 2:
                continue
            arr = np.ascontiguousarray(np.array(pts, dtype=np.float64))
            lines.append(arr.view(np.complex128).reshape(-1))

        if not lines:
            window.write_event_value(
                "-THREAD_DONE-",
                (None, "No strokes survived filtering. Lower Min stroke length.", False))
            return

        document = vpype.Document()
        document.add(vpype.LineCollection(lines))

        dt = time.time() - t0
        window.write_event_value(
            "-THREAD_DONE-",
            (document, f"Centerline trace complete: {len(lines)} strokes in {dt:.2f}s.",
             False))

    except InterruptedError as exc:
        window.write_event_value("-THREAD_DONE-", (None, f"{exc}", False))
    except Exception as exc:                           # noqa: BLE001 - report to UI
        traceback.print_exc()
        window.write_event_value("-THREAD_DONE-", (None, str(exc), False))
