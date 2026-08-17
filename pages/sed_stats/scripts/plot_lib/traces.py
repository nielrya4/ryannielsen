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


def series_color(index: int, total: int) -> str:
    """Evenly spaced hues, so series stay distinguishable at any count."""
    return f"hsl({round(360 * index / max(total, 1))}, 70%, 45%)"


def bar_trace(x, y, name, color=None):
    trace = {"type": "bar", "x": list(x), "y": list(y), "name": name}
    if color:
        trace["marker"] = {"color": color}
    return trace


def line_trace(x, y, name, color=None, markers=True):
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
