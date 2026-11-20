"""
The nodes that draw. A graph ends a chain: it reads typed data and makes a card.

    Line plot    Line+                    curves, overlaid or stacked
    Histogram    Table                    counts per bin
    Heatmap      Raster, + Points/Polygon a density per sample, with overlays
    Matrix       Matrix                   a comparison matrix as a table
    Scatterplot  Points/Polygon+          points, grain clouds, outlines
    Ternary      Table                    three components, one point per grain
    Bar chart    Proportions              shares with their uncertainty
    Table view   Table                    the rows themselves, sortable

A graph that takes several inputs (the "+ Add input" ones) draws the i-th item
of each together; see `outputs.aligned`.
"""
from workflow_lib import (
    FACTORS, LINE, MATRIX, NodeProblem, POINTS, POLYGON, Port, PROPORTIONS, RASTER, TABLE,
)
from workflow_lib.types import Points, Polygons

from plot_lib import marker_trace

from ..bivariate_plot import POINT_COLOR, draw_raster
from ..comparison import draw_matrix
from ..config import (
    DEFAULT_POINT_SIZE, LAYOUTS, SCATTER_LAYOUTS, SCATTER_SIZES,
)
from ..distributions import build_distribution, draw_curves, note_paragraph
from ..mds_plot import _shepard_section
from ..mixture import draw_proportions
from ..nmf_sources import draw_factors
from ..outputs import aligned, tabbed
from ..sample_pca import draw_report
from ..tables import result_table
from ..thumbnails import MAX_TABLE_ROWS, table_cells
from ..scatter import draw_points
from ..ternary_plot import build_ternary
from .base import (
    CHECKBOX, DATA_PAGE, DIMENSION, DIMENSIONS, Field, NUMBER, Node, SAMPLES,
    SELECT, StepOutput, need_dimensions, table_of,
)

from antioch.elements import Div, P


def _finish(opts, label, charts, titles, contents):
    body, tabview = tabbed(charts, titles, contents)
    return StepOutput(opts.get("title") or label, body, charts, tabview)


# ------------------------------------------------------------------- Line plot

def _run_line_plot(inputs, opts):
    charts, titles, contents = [], [], []
    view = opts.get("view", "pdf")
    for group in aligned(inputs["lines"]):
        many = len(group) > 1
        curves = []
        for lines in group:
            for sample, y in lines.series(view):
                curves.append((f"{sample} · {lines.name}" if many else sample,
                               lines.x, y))
        name = " + ".join(dict.fromkeys(lines.name for lines in group))
        plot = draw_curves(
            charts, curves, title=f"{name} — {view.upper()}",
            x_title=group[0].name if not many else "value",
            y_title="Probability", layout=opts.get("layout", "overlay"),
            style="line", filename=f"{name}_{view}")
        notes = [lines.note for lines in group if lines.note]
        contents.append(Div(note_paragraph(" ".join(dict.fromkeys(notes))), plot)
                        if notes else plot)
        titles.append(name)
    return _finish(opts, "Line plot", charts, titles, contents)


line_plot = Node(
    "line_plot", "Line plot", "Graph",
    [Port("lines", (LINE,), "Lines", multiple=True,
          hint="Add more inputs to overlay their curves on one plot; an NMF's sources "
               "can be one of them")], None,
    [
        Field("view", "View", SELECT, choices={"pdf": "PDF", "cdf": "CDF"},
              hint="Normalized probability density, or cumulative"),
        Field("layout", "Layout", SELECT, choices=LAYOUTS,
              hint="Overlay samples on one plot, or stack one per sample"),
    ],
    _run_line_plot,
    description="Draws the curves of one or more Distribution steps. With "
                "several inputs the curves share one plot.")


# ------------------------------------------------------------------- Histogram

def _run_histogram(inputs, opts):
    rows, sample_col = table_of(inputs, "table")
    charts, contents = [], []
    dimensions = need_dimensions(opts)
    options = {**opts, "view": "histogram"}
    for dimension in dimensions:
        contents.append(build_distribution(charts, rows, sample_col, dimension,
                                           options))
    return _finish(opts, "Histogram", charts, dimensions, contents)


histogram = Node(
    "histogram", "Histogram", "Graph",
    [Port("table", (TABLE,), "Table")], None,
    [
        Field("samples", "Samples", SAMPLES, page=DATA_PAGE),
        Field("dimensions", "Dimensions", DIMENSIONS, page=DATA_PAGE,
              hint="Each gets a tab"),
        Field("bin_size", "Bin size", NUMBER,
              hint="Blank picks a round width automatically"),
        Field("layout", "Layout", SELECT, choices=LAYOUTS,
              hint="Overlay samples on one plot, or stack one per sample"),
    ],
    _run_histogram,
    lambda opts, context: ("Select at least one sample." if not opts["samples"]
                           else "Select at least one dimension."
                           if not opts["dimensions"] else None),
    description="Counts the grains of each sample in bins. Reads a table "
                "directly, since a histogram is the data before any smoothing.")


# --------------------------------------------------------------------- Heatmap

def _overlay_traces(layers, sample, matching):
    """
    Overlay layers drawn over one sample's density.

    A group named for a sample goes over that sample only. When none of the
    overlay's names are samples of this raster (a single hull of everything),
    it goes over every figure.
    """
    traces = []
    for layer in layers:
        if isinstance(layer, Points):
            for name, xs, ys in layer.groups:
                if name == sample or not matching:
                    trace = marker_trace(xs, ys, name, color=POINT_COLOR, size=4)
                    trace["showlegend"] = False
                    traces.append(trace)
        elif isinstance(layer, Polygons):
            for name, vertices in layer.shapes:
                if (name == sample or not matching) and vertices:
                    closed = list(vertices) + [vertices[0]]
                    traces.append({
                        "type": "scatter", "mode": "lines", "showlegend": False,
                        "x": [v[0] for v in closed], "y": [v[1] for v in closed],
                        "line": {"color": "#111", "width": 2},
                        "hoverinfo": "skip"})
    return traces


def _names_in(layer):
    if isinstance(layer, Points):
        return {g[0] for g in layer.groups}
    return {name for name, _ in layer.shapes}


def _run_heatmap(inputs, opts):
    charts, titles, contents = [], [], []
    for group in aligned(inputs["raster"] + inputs["overlays"]):
        raster, layers = group[0], group[1:]
        sample_names = {name for name, _ in raster.density_set.entries}
        named = set()
        for layer in layers:
            named |= _names_in(layer)
        matching = named & sample_names
        extras = ((lambda sample, layers=layers, matching=matching:
                   _overlay_traces(layers, sample, matching)) if layers else None)
        contents.append(draw_raster(charts, raster, extras))
        titles.append(raster.name)
    return _finish(opts, "Heatmap", charts, titles, contents)


heatmap = Node(
    "heatmap", "Heatmap", "Graph",
    [Port("raster", (RASTER,), "Raster"),
     Port("overlays", (POINTS, POLYGON), "Overlays", multiple=True,
          optional=True,
          hint="Grains or outlines to draw over each sample's density")], None,
    [],
    _run_heatmap,
    description="Draws each sample's bivariate density as a heatmap. Add "
                "Points or Polygons as inputs to draw over it.")


# ---------------------------------------------------------------------- Matrix

def _run_matrix(inputs, opts):
    matrices = inputs["matrix"][0]
    contents = [draw_matrix(m) for m in matrices]
    return _finish(opts, "Comparison matrix", [], [m.name for m in matrices],
                   contents)


matrix_table = Node(
    "matrix_table", "Matrix table", "Graph",
    [Port("matrix", (MATRIX,), "Matrix")], None, [], _run_matrix,
    description="Shows a Comparison matrix as a table.")


# --------------------------------------------------------------------- Scatter

AXIS_SCALES = {"linear": "Linear", "log": "Logarithmic"}


def _run_scatter(inputs, opts):
    charts, titles, contents = [], [], []
    for group in aligned(inputs["series"]):
        contents.append(draw_points(charts, list(group), opts))
        first = next((g for g in group if isinstance(g, Points)), group[0])
        titles.append(first.name or getattr(first, "title", "")
                      or f"{first.x_title} vs {first.y_title}")
    return _finish(opts, "Scatterplot", charts, titles, contents)


scatter = Node(
    "scatter", "Scatterplot", "Graph",
    [Port("series", (POINTS, POLYGON), "Series", multiple=True,
          hint="Add more inputs to draw several sets of points, or outlines "
               "over them, on one plot")], None,
    [
        Field("layout", "Layout", SELECT, choices=SCATTER_LAYOUTS,
              hint="Overlay every sample, or give each its own panel on "
                   "shared axes"),
        Field("color_by_sample", "Colour by sample", CHECKBOX, default=True,
              hint="Each sample gets its own colour and marker shape"),
        Field("point_size", "Point size", SELECT, choices=SCATTER_SIZES,
              default=DEFAULT_POINT_SIZE, cast=int,
              hint="Smaller reads better where grains pile up"),
        Field("x_scale", "X axis", SELECT, choices=AXIS_SCALES, default="linear",
              hint="Log suits sizes and velocities that span orders of magnitude (a Hjulström "
                   "diagram); a value at or below zero cannot be shown on it"),
        Field("y_scale", "Y axis", SELECT, choices=AXIS_SCALES, default="linear"),
        Field("y_reverse", "Reverse the y axis", CHECKBOX,
              hint="The larger value lower down: depth in a core or well, drawdown"),
        Field("equal_scale", "Equal scales on both axes", CHECKBOX,
              hint="A plan map: a unit is as long across as up (ignored on a log axis)"),
    ],
    _run_scatter,
    description="Plots Points: grains from a Points step, or an MDS map. "
                "Polygons drawn over them are matched to samples by name. Polygons alone "
                "(a Watershed's outline) are drawn as they are.")


# --------------------------------------------------------------------- Ternary

def _run_ternary(inputs, opts):
    rows, sample_col = table_of(inputs, "table")
    charts = []
    body = build_ternary(charts, rows, sample_col, None, opts)
    return _finish(opts, "Ternary", charts, ["Ternary"], [body])


def _validate_ternary(opts, context):
    apexes = [opts.get("apex_a"), opts.get("apex_b"), opts.get("apex_c")]
    if not all(apexes):
        return "Choose all three apex dimensions."
    if len(set(apexes)) < 3:
        return "The three apexes must be different dimensions."
    return None


ternary = Node(
    "ternary", "Ternary", "Graph",
    [Port("table", (TABLE,), "Table")], None,
    [
        Field("samples", "Samples", SAMPLES, page=DATA_PAGE),
        Field("apex_a", "Top apex", DIMENSION, numeric_only=True, nth=0,
              page=DATA_PAGE, hint="The component plotted at the peak"),
        Field("apex_b", "Lower-left apex", DIMENSION, numeric_only=True, nth=1,
              page=DATA_PAGE),
        Field("apex_c", "Lower-right apex", DIMENSION, numeric_only=True, nth=2,
              page=DATA_PAGE),
        Field("color_by_sample", "Colour by sample", CHECKBOX, default=True,
              hint="Each sample gets its own colour and marker shape"),
        Field("show_centroids", "Mark sample means", CHECKBOX,
              hint="A star at each sample's mean composition, with a table"),
        Field("point_size", "Point size", SELECT, choices=SCATTER_SIZES,
              default=DEFAULT_POINT_SIZE, cast=int,
              hint="Smaller reads better where grains pile up"),
    ],
    _run_ternary, _validate_ternary,
    description="Three components of a whole, one point per grain.")


# ------------------------------------------------------------------- Bar chart

def _run_bar(inputs, opts):
    charts, titles, contents = [], [], []
    for proportions in inputs["proportions"][0]:
        contents.append(draw_proportions(charts, proportions,
                                         show_fit=opts.get("show_fit", False)))
        titles.append(proportions.name)
    return _finish(opts, "Bar chart", charts, titles, contents)


bar_chart = Node(
    "bar_chart", "Bar chart", "Graph",
    [Port("proportions", (PROPORTIONS,), "Proportions")], None,
    [
        Field("show_fit", "Show model fit", CHECKBOX,
              hint="Also shows how well the model reproduces the sink: the best "
                   "trial curves against it (univariate), or the sink, best "
                   "model and mismatch surfaces (bivariate)"),
    ],
    _run_bar,
    description="Draws a Mixture model's contributions with their "
                "uncertainty, and a table.")


# ------------------------------------------------------------------- Table view

def _run_table_view(inputs, opts):
    rows, sample_col = table_of(inputs, "table")
    chosen = opts.get("samples")
    if chosen is not None:
        rows = [r for r in rows if str(r.get(sample_col, "") or "").strip() in set(chosen)]
    wanted = list(opts.get("columns") or [])
    columns = ([sample_col] + [c for c in wanted if c != sample_col]) if wanted else None
    titles, cells, total = table_cells(rows, columns, limit=MAX_TABLE_ROWS)
    if not titles:
        raise NodeProblem("There is nothing to show: no rows, or none of the chosen columns exist.")
    note = (f"{total:,} row{'s' if total != 1 else ''} × {len(titles)} column{'s' if len(titles) != 1 else ''}"
            + (f"; the first {MAX_TABLE_ROWS:,} are shown" if total > len(cells) else "")
            + ". Click a column's arrow to sort; select cells and copy to paste them elsewhere.")
    body = Div(P(note, style={"font-size": "13px", "color": "#555", "margin": "0 0 6px 0"}),
               result_table(titles, cells, sortable=True))
    return StepOutput(opts.get("title") or "Table", body, [], None, preview=(titles, cells[:6]))


def _validate_table_view(opts, context):
    if opts.get("samples") is not None and not opts["samples"]:
        return "Select at least one sample."
    return None


table_view = Node(
    "table_view", "Table view", "Graph",
    [Port("table", (TABLE,), "Table")], None,
    [
        Field("samples", "Samples", SAMPLES, page=DATA_PAGE),
        Field("columns", "Columns", DIMENSIONS, page=DATA_PAGE,
              hint="Leave all unticked to show every column; the sample column is always shown"),
    ],
    _run_table_view, _validate_table_view,
    description="Shows a table — the spreadsheet, or what a step made of it — as a sortable grid you "
                "can select and copy from. Any step that makes a table can also show it from its "
                "Show output button; this block is for choosing which samples and columns to see.")


# ---------------------------------------------------------------------- Shepard

def _run_shepard(inputs, opts):
    charts, titles, contents = [], [], []
    for points in inputs["points"][0]:
        meta = points.meta
        if "embedding" not in meta:
            raise NodeProblem("This is not an MDS map, so there is no fit to "
                              "check. Connect an MDS step.")
        caption, plot = _shepard_section(
            charts, points.name, meta["matrix"], meta["embedding"],
            meta["non_metric"], meta["stress"])
        contents.append(Div(caption, plot))
        titles.append(points.name)
    return _finish(opts, "MDS fit", charts, titles, contents)


shepard = Node(
    "shepard", "MDS fit (Shepard)", "Graph",
    [Port("points", (POINTS,), "MDS map")], None, [], _run_shepard,
    description="Checks an MDS map: how well the distances on the map reproduce "
                "the dissimilarities it was built from. Points far from the "
                "diagonal are pairs the map distorts.")


# ------------------------------------------------------------------ PCA report

def _run_pca_report(inputs, opts):
    charts, titles, contents = [], [], []
    for points in inputs["points"][0]:
        fit = points.meta.get("sample_pca")
        if fit is None:
            raise NodeProblem("This is not a Sample PCA map, so there is nothing "
                              "to report. Connect a Sample PCA step.")
        contents.append(draw_report(
            charts, fit["result"], fit["dimensions"], fit["labels"],
            fit["categorical"], opts.get("scree", True)))
        titles.append(points.name)
    return _finish(opts, "PCA report", charts, titles, contents)


pca_report = Node(
    "pca_report", "PCA report", "Graph",
    [Port("points", (POINTS,), "Sample PCA")], None,
    [
        Field("scree", "Scree plot", CHECKBOX, default=True,
              hint="Shows how much variance each component carries"),
    ],
    _run_pca_report,
    description="What drives a Sample PCA map: each dimension's share of each "
                "component, the loadings across its bins or categories, and "
                "optionally the scree plot.")


# ------------------------------------------------------------------ NMF report

def _run_nmf_report(inputs, opts):
    charts, titles, contents = [], [], []
    for factors in inputs["factors"][0]:
        contents.append(draw_factors(charts, factors))
        titles.append(factors.name)
    return _finish(opts, "NMF sources", charts, titles, contents)


nmf_report = Node(
    "nmf_report", "NMF report", "Graph",
    [Port("factors", (FACTORS,), "NMF sources")], None, [], _run_nmf_report,
    description="Reports an NMF: how the number of sources was chosen, the sources "
                "themselves, what each sample is made of, and how well the sources "
                "rebuild each sample, with warnings where the data fall short of what "
                "the method needs.")


GRAPH_NODES = [table_view, line_plot, histogram, heatmap, matrix_table, scatter, ternary,
               bar_chart, shepard, pca_report, nmf_report]
