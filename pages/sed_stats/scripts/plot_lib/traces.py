"""Builders for the plotly trace dicts this project uses."""


def subplot_axes(row: int):
    """Axis names for a trace in a given 0-indexed subplot row."""
    suffix = "" if row == 0 else str(row + 1)
    return f"x{suffix}", f"y{suffix}"


def stacked_subplot_layout(rows: int, vertical_spacing=None, shared_xaxis=False):
    """
    Axis layout for `rows` subplots stacked top to bottom.

    plotly.js has no make_subplots helper — subplots are just multiple axes
    with stacked `domain` ranges — so this reproduces what
    `make_subplots(rows=n, cols=1)` generates, including its default spacing
    of 0.3/rows and its top-to-bottom row ordering.
    """
    if rows < 1:
        return {}
    if vertical_spacing is None:
        vertical_spacing = 0.3 / rows if rows > 1 else 0.0

    height = (1.0 - vertical_spacing * (rows - 1)) / rows
    layout = {}
    for row in range(rows):
        x_name, y_name = subplot_axes(row)
        suffix = "" if row == 0 else str(row + 1)
        top = 1.0 - row * (height + vertical_spacing)
        bottom = max(0.0, top - height)

        layout[f"xaxis{suffix}"] = {
            "anchor": y_name,
            "domain": [0.0, 1.0],
            # Only the bottom row keeps tick labels when axes are shared
            "showticklabels": True if not shared_xaxis else (row == rows - 1),
        }
        layout[f"yaxis{suffix}"] = {
            "anchor": x_name,
            "domain": [round(bottom, 4), round(top, 4)],
        }
    return layout


def subplot_title(row: int, text: str):
    """Annotation that labels one subplot, as make_subplots' subplot_titles do."""
    _, y_name = subplot_axes(row)
    return {
        "text": text,
        "showarrow": False,
        "xref": "paper",
        "yref": f"{y_name} domain",
        "x": 0.0,
        "y": 1.0,
        "xanchor": "left",
        "yanchor": "bottom",
        "font": {"size": 12},
    }


# White at zero so empty grid reads as blank page rather than "cold", which is
# how Sundell & Saylor (2021) present bivariate density.
DENSITY_COLORSCALE = [
    [0.0, "#ffffff"],
    [0.05, "#e8eef7"],
    [0.25, "#3b6fb6"],
    [0.5, "#2ec4b6"],
    [0.75, "#f5c542"],
    [1.0, "#c1121f"],
]


def heatmap_trace(x, y, z, name=None, colorscale=None, colorbar_title=None,
                  show_scale=True):
    """
    A density grid. `z` is row-major with one row per y value.

    Args:
        x, y: axis coordinates
        z: nested sequence, len(y) rows of len(x)
        colorbar_title: label beside the scale bar
    """
    # Coerced to plain floats: these axes usually arrive as numpy arrays, and
    # numpy scalars do not cross the Pyodide boundary cleanly.
    trace = {
        "type": "heatmap",
        "x": [float(v) for v in x],
        "y": [float(v) for v in y],
        "z": [[float(v) for v in row] for row in z],
        "colorscale": colorscale or DENSITY_COLORSCALE,
        "showscale": show_scale,
        "zsmooth": "best",
    }
    if name:
        trace["name"] = name
    if colorbar_title:
        trace["colorbar"] = {"title": {"text": colorbar_title, "side": "right"}}
    return trace


def series_color(index: int, total: int) -> str:
    """Evenly spaced hues, so series stay distinguishable at any count."""
    return f"hsl({round(360 * index / max(total, 1))}, 70%, 45%)"


def bar_trace(x, y, name, color=None):
    trace = {"type": "bar", "x": list(x), "y": list(y), "name": name}
    if color:
        trace["marker"] = {"color": color}
    return trace


def line_trace(x, y, name, color=None, markers=False):
    """A line. Markers are off by default — on a kernel curve with hundreds of
    grid points they turn the line into a solid smear."""
    trace = {
        "type": "scatter",
        "mode": "lines+markers" if markers else "lines",
        "x": list(x),
        "y": list(y),
        "name": name,
    }
    if color:
        trace["line"] = {"color": color, "width": 2}
        trace["marker"] = {"color": color, "size": 5}
    return trace


def error_bar_trace(x, y, errors, name, color=None, size=9):
    """Points with symmetric vertical error bars."""
    trace = {
        "type": "scatter",
        "mode": "markers",
        "x": list(x),
        "y": list(y),
        "name": name,
        "error_y": {
            "type": "data",
            "array": [float(e) for e in errors],
            "visible": True,
            "thickness": 1.5,
            "width": 6,
        },
    }
    if color:
        trace["marker"] = {"color": color, "size": size}
        trace["error_y"]["color"] = color
    else:
        trace["marker"] = {"size": size}
    return trace


def marker_trace(x, y, name, color=None, labels=None, size=10):
    """Scatter points, optionally annotated with per-point text labels."""
    trace = {
        "type": "scatter",
        "mode": "markers+text" if labels else "markers",
        "x": list(x),
        "y": list(y),
        "name": name,
    }
    if labels:
        trace["text"] = list(labels)
        trace["textposition"] = "top center"
        trace["textfont"] = {"size": 10}
    if color:
        trace["marker"] = {"color": color, "size": size}
    else:
        trace["marker"] = {"size": size}
    return trace


# Fixed categorical palette, in fixed order — never generated, never cycled by
# rank. Validated for adjacent pairs in both modes; see SCATTER_CAP below for
# the tighter limit that applies to scatter plots.
CATEGORICAL_PALETTE = [
    "#2a78d6",  # blue
    "#eb6834",  # orange
    "#1baf7a",  # aqua
    "#eda100",  # yellow
    "#e87ba4",  # magenta
    "#008300",  # green
    "#4a3aa7",  # violet
    "#e34948",  # red
]

# On a scatter every series can touch every other, so all pairs must separate,
# not just adjacent ones. Only the first three slots clear that bar. Past three,
# colour alone is not enough and marker shape carries identity alongside it.
SCATTER_CAP = 3

# Shapes pair with the palette so identity never rests on hue alone — the
# scatter equivalent of texture, and what keeps the plot readable in print,
# under colour-vision deficiency, and where two hues sit close together.
SERIES_SYMBOLS = [
    "circle", "triangle-up", "square", "diamond", "cross",
    "triangle-down", "pentagon", "x",
]


def categorical_color(index: int) -> str:
    """The palette slot for a 0-indexed series, wrapping past the eighth."""
    return CATEGORICAL_PALETTE[index % len(CATEGORICAL_PALETTE)]


def series_symbol(index: int) -> str:
    """The marker shape paired with `categorical_color` at the same index."""
    return SERIES_SYMBOLS[index % len(SERIES_SYMBOLS)]


def scatter_trace(x, y, name, color=None, symbol=None, size=7, opacity=0.75,
                  hover_x="x", hover_y="y"):
    """
    Raw measurements as points.

    Marks are small and semi-transparent because grain data overplots badly —
    a thousand opaque points is a silhouette, not a distribution. The thin
    surface-coloured outline keeps individual points readable where they pile up.
    """
    trace = {
        "type": "scatter",
        "mode": "markers",
        "x": list(x),
        "y": list(y),
        "name": name,
        "marker": {
            "size": size,
            "opacity": opacity,
            "symbol": symbol or "circle",
            "line": {"width": 0.6, "color": "rgba(255,255,255,0.85)"},
        },
        "hovertemplate": (f"<b>{name}</b><br>{hover_x}: %{{x}}<br>"
                          f"{hover_y}: %{{y}}<extra></extra>"),
    }
    if color:
        trace["marker"]["color"] = color
    return trace


def ternary_trace(a, b, c, name, color=None, symbol=None, size=7, opacity=0.8,
                  labels=None, apex_names=("a", "b", "c")):
    """
    Points on a ternary diagram.

    Plotly places a scatterternary from the three components directly, so the
    caller passes them closed but unprojected; `subplot` ties the trace to the
    ternary axes that `ternary_layout` defines.
    """
    trace = {
        "type": "scatterternary",
        "mode": "markers",
        "a": [float(v) for v in a],
        "b": [float(v) for v in b],
        "c": [float(v) for v in c],
        "name": name,
        "subplot": "ternary",
        "marker": {
            "size": size,
            "opacity": opacity,
            "symbol": symbol or "circle",
            "line": {"width": 0.6, "color": "rgba(255,255,255,0.85)"},
        },
        "hovertemplate": (
            f"<b>{name}</b><br>"
            f"{apex_names[0]}: %{{a:.1f}}<br>"
            f"{apex_names[1]}: %{{b:.1f}}<br>"
            f"{apex_names[2]}: %{{c:.1f}}<extra></extra>"
        ),
    }
    if color:
        trace["marker"]["color"] = color
    if labels:
        trace["mode"] = "markers+text"
        trace["text"] = list(labels)
        trace["textposition"] = "top center"
        trace["textfont"] = {"size": 10}
    return trace


def ternary_layout(apex_names, total=100, show_ticks=True):
    """
    Layout overrides that turn a figure into a ternary one.

    The cartesian axes are hidden explicitly: the shared plot builder always
    sets an x and y axis, and left visible they would frame the triangle with
    an empty square grid.
    """
    axis = {
        "showline": True,
        "linewidth": 1,
        "linecolor": "#b8b2a8",
        "gridcolor": "#e4e0d9",
        "showticklabels": show_ticks,
        "ticks": "outside" if show_ticks else "",
        "tickfont": {"size": 10},
        "min": 0,
    }
    return {
        "ternary": {
            "sum": total,
            "aaxis": {**axis, "title": {"text": apex_names[0]}},
            "baxis": {**axis, "title": {"text": apex_names[1]}},
            "caxis": {**axis, "title": {"text": apex_names[2]}},
            "bgcolor": "rgba(0,0,0,0)",
        },
        "xaxis": {"visible": False},
        "yaxis": {"visible": False},
        "margin": {"l": 70, "r": 70, "t": 70, "b": 70},
    }
