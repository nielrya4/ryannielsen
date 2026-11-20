"""
Scatterplots: raw grain measurements, coloured by sample.

Every other analysis in the app shows a distribution — something estimated from
the grains. This shows the grains. It is the plot to reach for when a density
looks wrong and you want to know whether the data or the kernel is responsible.

`points_from_table` is the step that lifts two columns into `Points`, and
`draw_points` is the graph that plots any Points — grains, an ordination's
samples — with polygons (a hull, a contour) over them.
"""
import math

from antioch.elements import Div, P

from plot_lib import (
    SCATTER_CAP, categorical_color, marker_trace, scatter_trace, series_symbol,
)
from workflow_lib import NodeProblem
from workflow_lib.types import Points, Polygons

from .dataset import paired_by_sample, sample_names
from .plots import make_plot
from .sample_pca import map_traces

CAPTION_STYLE = {"font-size": "13px", "color": "#555", "margin": "0 0 6px 0"}
NOTE_STYLE = {"color": "#6c757d"}

# One neutral colour when nothing is being distinguished.
PLAIN_COLOR = "#4a5568"
LINK_COLOR = "#999"


def points_from_table(rows, sample_col, x_dimension, dimension, opts):
    """
    `dimension` against `x_dimension`, per sample.

    Raises:
        NodeProblem: for an unset or repeated axis, a non-numeric axis, or no
            grain with both values
    """
    if not x_dimension:
        raise NodeProblem("Choose an x dimension.")
    if x_dimension == dimension:
        raise NodeProblem(f"'{dimension}' is already the x dimension; pick a "
                          f"different y dimension.")
    try:
        grouped = paired_by_sample(rows, sample_col, x_dimension, dimension,
                                   opts.get("samples"))
    except ValueError:
        raise NodeProblem(
            f"'{dimension}' is not numeric, so it cannot be a scatter axis.")
    if not grouped:
        raise NodeProblem(f"No paired '{x_dimension}' and '{dimension}' values.")

    total = sum(len(values[0]) for values in grouped.values())
    # Colour keyed to the sample's place in the spreadsheet, not its place in
    # the current selection — so a sample keeps its colour when the selection
    # changes and two outputs stay comparable.
    order = {name: index
             for index, name in enumerate(sample_names(rows, sample_col))}
    return Points(
        x_title=x_dimension, y_title=dimension,
        groups=[(sample, list(v[0]), list(v[1])) for sample, v in grouped.items()],
        note=(f"{total:,} grains across {len(grouped)} "
              f"sample{'s' if len(grouped) != 1 else ''}."),
        meta={"order": order}, name=dimension)


def draw_points(charts, layers, opts):
    """
    Plot one or more layers on shared axes.

    Args:
        layers: Points and Polygons. The first Points layer names the axes and
            the facets; every group, from every layer, is coloured by its name,
            so a hull drawn for a sample matches the sample's points.
        opts: layout ("overlay" or "facet"), color_by_sample, point_size, opacity
    """
    clouds = [layer for layer in layers if isinstance(layer, Points)]
    shapes = [layer for layer in layers if isinstance(layer, Polygons)]
    if not clouds and not shapes:
        raise NodeProblem("A scatterplot needs at least one set of points or one outline.")
    # Outlines alone (a watershed) are drawn as they are; the first layer then names the axes.
    base = clouds[0] if clouds else _OutlinesOnly(shapes[0])
    colors = _Colors(clouds, shapes, opts)
    if opts.get("layout") == "facet" and clouds:
        return _facets(charts, base, clouds, shapes, colors, opts)
    return _overlay(charts, base, clouds, shapes, colors, opts)


class _OutlinesOnly:
    """Stands in for the Points that name a plot's axes when there are none: the axes and title
    come from the first outline."""

    def __init__(self, outline):
        self.x_title, self.y_title = outline.x_title, outline.y_title
        self.title = outline.name or ""
        self.groups, self.meta, self.links, self.note = [], {}, [], ""


def _geographic_ratio(base, clouds, shapes):
    """
    For a plot of longitude against latitude, the y:x scale that makes a degree of latitude look as
    long as a degree of longitude does on the ground at the middle of the data's latitudes (1 / cos latitude), or
    None for any other plot. Without it a watershed is stretched sideways.
    """
    if not (str(base.x_title).startswith("Longitude") and str(base.y_title).startswith("Latitude")):
        return None
    lats = [y for layer in clouds for g in layer.groups for y in g[2]]
    lats += [v[1] for layer in shapes for _, vertices in layer.shapes for v in vertices]
    if not lats:
        return None
    middle = (min(lats) + max(lats)) / 2          # of the extent, not of the vertices' density
    return 1.0 / max(math.cos(math.radians(middle)), 0.05)


class _Colors:
    """The colour and shape each name is drawn with, the same in every layer."""

    def __init__(self, clouds, shapes, opts):
        self.plain = not opts.get("color_by_sample", True)
        self.order = dict(clouds[0].meta.get("order", {})) if clouds else {}
        for layer in clouds + shapes:
            names = ([g[0] for g in layer.groups] if isinstance(layer, Points)
                     else [n for n, _ in layer.shapes])
            for name in names:
                self.order.setdefault(name, len(self.order))

    def of(self, name):
        if self.plain:
            return PLAIN_COLOR, "circle"
        index = self.order.get(name, 0)
        return categorical_color(index), series_symbol(index)


def _traces(base, clouds, shapes, colors, opts, only=None):
    """Every trace for the chosen names (all of them when `only` is None)."""
    traces = []
    for layer in clouds:
        by_column = layer.meta.get("colors") or {}
        if only is None and layer.meta.get("labeled") and (
                "values" in by_column or "groups" in by_column):
            # Samples coloured by a column: drawn together so the colour scale
            # or the groups' legend covers them all.
            names = [g[0] for g in layer.groups]
            traces.extend(map_traces([g[1][0] for g in layer.groups],
                                     [g[2][0] for g in layer.groups], names, by_column))
            if layer.links:
                traces.insert(0, _links(layer.links))
            continue
        for name, xs, ys in layer.groups:
            if only is not None and name != only:
                continue
            color, symbol = colors.of(name)
            if layer.meta.get("labeled"):
                traces.append(marker_trace(xs, ys, name, color=color, labels=[name]))
                continue
            traces.append(scatter_trace(
                xs, ys, name, color=color, symbol=symbol,
                size=opts.get("point_size", 7),
                opacity=opts.get("opacity", 0.75),
                hover_x=layer.x_title, hover_y=layer.y_title))
        if only is None and layer.links:
            traces.insert(0, _links(layer.links))
    underlay = []                     # shaded fields go beneath the points, not over them
    for layer in shapes:
        for name, vertices in layer.shapes:
            # "Reference" means drawn dashed on every panel of a plot of points; with no points
            # the outline is the plot, and is drawn plainly.
            reference = name in layer.reference and bool(clouds)
            if only is not None and name != only and not reference:
                continue
            color = layer.colors.get(name) or colors.of(name)[0]
            path = list(vertices)
            if path and not layer.open:
                path.append(path[0])
            line = {"color": "#444" if reference else color, "width": 2}
            if reference:
                line["dash"] = "dash"
            trace = {
                "type": "scatter", "mode": "lines",
                "name": (name if reference or layer.fill or layer.bare
                         else f"{name} {'line' if layer.open else 'outline'}"),
                "x": [v[0] for v in path], "y": [v[1] for v in path],
                "line": line, "hoverinfo": "skip"}
            if layer.fill and not layer.open:
                trace.update({"fill": "toself", "fillcolor": _with_alpha(color, 0.2),
                              "hoveron": "fills", "hoverinfo": "name"})
                underlay.append(trace)
            else:
                traces.append(trace)
    return underlay + traces


def _with_alpha(color, alpha):
    """An rgba() colour from a "#rrggbb" one (any other form is left as it is, unshaded by alpha)."""
    text = str(color).lstrip("#")
    if len(text) == 6:
        try:
            r, g, b = (int(text[i:i + 2], 16) for i in (0, 2, 4))
            return f"rgba({r},{g},{b},{alpha})"
        except ValueError:
            pass
    return color


def _links(links):
    # A None breaks the line between segments; Plotly reads array entries as
    # values, so a non-numeric entry is simply a gap.
    xs, ys = [], []
    for x0, y0, x1, y1 in links:
        xs.extend([x0, x1, None])
        ys.extend([y0, y1, None])
    return {"type": "scatter", "mode": "lines", "x": xs, "y": ys,
            "name": "Nearest neighbor", "connectgaps": False, "hoverinfo": "skip",
            "line": {"color": LINK_COLOR, "width": 1, "dash": "dash"}}


def _axes(base, ratio=None, opts=None):
    # Measurements have no reason to reach zero; the default "tozero" would pad
    # a temperature axis down to 0 and waste most of the plot.
    axes = {
        "xaxis": {"title": {"text": base.x_title}, "rangemode": "normal"},
        "yaxis": {"title": {"text": base.y_title}, "rangemode": "normal"},
    }
    for key, option in (("xaxis", "x_scale"), ("yaxis", "y_scale")):
        if (opts or {}).get(option) == "log":
            axes[key]["type"] = "log"
    logged = any(a.get("type") == "log" for a in axes.values())
    if (opts or {}).get("equal_scale") and not logged and not ratio:
        ratio = 1.0                                 # a plan map: a unit looks as long either way
    if ratio and not logged:
        axes["yaxis"].update({"scaleanchor": "x", "scaleratio": ratio})
    if (opts or {}).get("y_reverse"):
        axes["yaxis"]["autorange"] = "reversed"     # depth, drawdown: the larger value lower down
    return axes


def _title(base):
    return base.title or f"{base.x_title} vs {base.y_title}"


def _filename(base):
    return f"{base.x_title}_{base.y_title}_scatter".replace(" ", "_")


def _overlay(charts, base, clouds, shapes, colors, opts):
    traces = _traces(base, clouds, shapes, colors, opts)
    wrapper = Div()
    notes = [layer.note for layer in (clouds or shapes) if layer.note]
    unshown = _off_log_axes(clouds, opts)
    if unshown:
        notes.append(f"{unshown:,} point{'s' if unshown != 1 else ''} with a zero or negative value "
                     "cannot be shown on a log axis.")
    if notes:
        wrapper.add(P(" ".join(notes), style=CAPTION_STYLE))
    wrapper.add(Div(make_plot(
        charts, traces, _title(base), base.x_title, base.y_title,
        height=520, show_legend=len(traces) > 1, filename=_filename(base),
        extra_layout=_axes(base, _geographic_ratio(base, clouds, shapes), opts)).element))

    # Past three series, colour alone cannot keep every pair apart — every
    # series touches every other on a scatter, so it is all pairs that have to
    # separate, not just neighbours. Marker shape carries identity too, which is
    # what makes more than three legible; say so rather than implying the
    # colours alone are doing the work.
    grains = [g for layer in clouds if not layer.meta.get("labeled")
              for g in layer.groups]
    if opts.get("color_by_sample", True) and len(grains) > SCATTER_CAP:
        wrapper.add(P(
            f"Beyond {SCATTER_CAP} samples the colours alone stop separating "
            f"reliably, so each sample also has its own marker shape. For many "
            f"samples, 'One plot per sample' reads more clearly.",
            style=NOTE_STYLE))
    return wrapper


def _off_log_axes(clouds, opts):
    """How many points a log axis cannot draw: those at or below zero on a log axis."""
    log_x, log_y = opts.get("x_scale") == "log", opts.get("y_scale") == "log"
    if not (log_x or log_y):
        return 0
    return sum(1 for layer in clouds for _, xs, ys in layer.groups for x, y in zip(xs, ys)
               if (log_x and x <= 0) or (log_y and y <= 0))


def _facets(charts, base, clouds, shapes, colors, opts):
    """
    One panel per sample, on shared axes.

    Shared ranges are the point: panels that each auto-scale would show every
    sample filling its own frame and hide the differences between them.
    """
    names = [g[0] for g in base.groups]
    all_x = [v for layer in clouds for g in layer.groups for v in g[1]]
    all_y = [v for layer in clouds for g in layer.groups for v in g[2]]
    axes = _axes(base, _geographic_ratio(base, clouds, shapes), opts)
    y_range = _padded(all_y, log=opts.get("y_scale") == "log")
    limits = {"xaxis": {**axes["xaxis"], "range": _padded(all_x, log=opts.get("x_scale") == "log")},
              "yaxis": {**axes["yaxis"], "range": y_range[::-1] if opts.get("y_reverse") else y_range}}
    limits["yaxis"].pop("autorange", None)          # an explicit range, already turned round if need be

    wrapper = Div(P(f"{len(names)} samples on shared axes.", style=CAPTION_STYLE))
    for name in names:
        traces = _traces(base, clouds, shapes, colors, opts, only=name)
        wrapper.add(Div(make_plot(
            charts, traces, f"{name} — {base.x_title} vs {base.y_title}",
            base.x_title, base.y_title, height=380, show_legend=False,
            filename=f"{name}_{_filename(base)}", extra_layout=limits).element))
        count = len(dict((g[0], g[1]) for g in base.groups)[name])
        wrapper.add(P(f"n = {count:,}",
                      style={**CAPTION_STYLE, "margin": "0 0 14px 0"}))
    return wrapper


def _padded(values, fraction=0.04, log=False):
    """A range with a little air, so points never sit on the frame; in powers of ten on a log axis
    (where a value that is zero or below cannot be drawn and is left out)."""
    if log:
        values = [math.log10(v) for v in values if v > 0] or [0.0]
    low, high = min(values), max(values)
    pad = (high - low) * fraction or (abs(low) * 0.04 or 1.0)
    return [low - pad, high + pad]
