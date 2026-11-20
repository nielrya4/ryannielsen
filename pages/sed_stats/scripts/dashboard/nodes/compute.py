"""
The nodes that turn one kind of data into another.

    Distribution   Table  -> Line | Raster     what each sample looks like
    Points         Table  -> Points             two columns, grain by grain
    Grain PCA      Table  -> Table              PC1 and PC2 added to a copy
    Comparison     Line | Raster -> Matrix      a metric over every sample pair
    MDS            Matrix -> Points             the matrix as a map
    Mixture        Line | Raster -> Proportions the sink as a mix of the others
"""
from workflow_lib import (
    FACTORS, LINE, MATRIX, NodeProblem, Output, POINTS, POLYGON, Port, PROPORTIONS, RASTER,
    TABLE,
)
from workflow_lib.types import Points, Polygons, Raster

from sed_stats import mds as mds_lib
from sed_stats.contour import contour_rings, density_level
from sed_stats.hull import convex_hull

from ..bivariate import prepare_set
from ..combine import combine
from ..comparison import compare, match_sets, metrics_for
from ..config import (
    DEFAULT_GRID, DENSITY_METHODS, GRAIN_WEIGHTINGS, GRID_SIZES, MDS_TYPES,
    MIXTURE_METRICS, MIXTURE_TRIALS, SIGMA_LEVELS,
)
from ..dataset import sample_names
from ..distributions import compute_lines
from ..mixture import unmix_lines, unmix_raster
from ..nmf_sources import factorize_lines, sources_as_lines, weights_matrix
from ..outputs import aligned
from ..pca_axes import run_axes
from ..sample_pca import NO_COLOR, color_groups, fit_sample_pca
from ..scatter import points_from_table
from antioch.elements import Div, P

from .base import (
    CHECKBOX, DATA_PAGE, DIMENSION, DIMENSIONS, Field, NUMBER, Node,
    SAMPLE, SAMPLES, SELECT, StepOutput, need_dimensions, numbered, table_of,
)

UNI, BI = "uni", "bi"
MODES = {UNI: "Univariate — one dimension at a time",
         BI: "Bivariate — each dimension against an x dimension"}


def _bivariate(opts):
    return opts.get("mode") == BI


def _kde(opts):
    return opts.get("density") == "kde" and not _bivariate(opts)


def _x_axis_problem(opts):
    if not opts.get("x_dimension"):
        return "Choose an x dimension."
    if all(d == opts["x_dimension"] for d in opts.get("dimensions", [])):
        return ("The x dimension is the only one chosen; choose a different "
                "y dimension.")
    return None


# ---------------------------------------------------------------- Distribution

def _distribution_output(opts):
    return RASTER if _bivariate(opts) else LINE


def _skipped_note(opts, label, skipped):
    """What to say about the dimensions that could not be done, beside those that were."""
    lines = Div(*[P(f"'{dimension}': {why}", style={"margin": "0 0 3px 0"})
                  for dimension, why in skipped])
    body = Div(P(f"Skipped {len(skipped)} dimension{'s' if len(skipped) != 1 else ''}; the "
                 "rest went ahead.", style={"margin": "0 0 4px 0", "font-weight": "600"}),
               lines, style={"color": "#8a5a00", "font-size": "13px"})
    return StepOutput(opts.get("title") or label, body, [], None)


def _each_dimension(opts, make, label):
    """
    `make(dimension)` for each chosen dimension. One that cannot be done — no data,
    or paired with itself — is skipped with a note rather than losing the others.

    Raises:
        NodeProblem: when none can be done
    """
    batch, skipped = [], []
    for dimension in need_dimensions(opts):
        try:
            batch.append(make(dimension))
        except NodeProblem as problem:
            skipped.append((dimension, str(problem)))
    if not batch:
        raise NodeProblem(skipped[0][1] if len(skipped) == 1
                          else "; ".join(f"'{d}': {why}" for d, why in skipped))
    return batch, (_skipped_note(opts, label, skipped) if skipped else None)


def _run_distribution(inputs, opts):
    rows, sample_col = table_of(inputs, "table")
    if _bivariate(opts):
        return _each_dimension(opts, lambda d: Raster(
            opts["x_dimension"], d, prepare_set(rows, sample_col, d, opts)), "Distribution")
    return _each_dimension(opts, lambda d: compute_lines(rows, sample_col, d, opts),
                           "Distribution")


def _validate_distribution(opts, context):
    if not opts["samples"]:
        return "Select at least one sample."
    if not opts["dimensions"]:
        return "Select at least one dimension."
    return _x_axis_problem(opts) if _bivariate(opts) else None


distribution = Node(
    "distribution", "Distribution", "Describe",
    [Port("table", (TABLE,), "Table")], _distribution_output,
    [
        Field("samples", "Samples", SAMPLES, page=DATA_PAGE),
        Field("dimensions", "Dimensions", DIMENSIONS, page=DATA_PAGE,
              hint="Each becomes its own result; plots of them get a tab each"),
        Field("mode", "Analysis", SELECT, choices=MODES, default=UNI,
              page=DATA_PAGE,
              hint="Univariate describes one dimension as a line; bivariate "
                   "pairs each dimension with an x and describes the pair as "
                   "a surface"),
        Field("density", "Density method", SELECT, choices=DENSITY_METHODS,
              hint="PDP spreads each measurement by its own uncertainty when "
                   "the sheet has one; KDE uses a single bandwidth"),
        Field("sigma_in", "Uncertainty level", SELECT, choices=SIGMA_LEVELS,
              cast=float, when=lambda o: not _kde(o) and o.get("density") != "bins",
              hint="For uncertainty columns that don't say; a '1s' or '2s' "
                   "header overrides it"),
        Field("bandwidth", "KDE bandwidth", NUMBER, when=_kde,
              hint="Blank uses Silverman's rule on the pooled samples"),
        Field("bin_size", "Bin size", NUMBER,
              when=lambda o: not _bivariate(o) and o.get("density") == "bins",
              hint="Blank picks a round width automatically"),
        Field("x_dimension", "X dimension", DIMENSION, when=_bivariate,
              page=DATA_PAGE, hint="Plotted against each dimension chosen"),
        Field("grid", "Grid resolution", SELECT, choices=GRID_SIZES,
              default=DEFAULT_GRID, cast=int, when=_bivariate,
              hint="Points per axis; cost grows with the square"),
        Field("x_bandwidth", "X bandwidth", NUMBER, when=_bivariate,
              hint="Blank uses Silverman's rule; ignored for uncertainties "
                   "and categories"),
        Field("y_bandwidth", "Y bandwidth", NUMBER, when=_bivariate,
              hint="Blank uses Silverman's rule; ignored for uncertainties "
                   "and categories"),
    ],
    _run_distribution, _validate_distribution,
    description="Describes how each sample's grains are distributed: a curve "
                "per sample for one dimension, a surface for two. Draw the "
                "result with a Line plot or a Heatmap, or compare samples "
                "with Comparison.")


# ---------------------------------------------------------------------- Points

def _weights_for(points, rows, sample_col, x_dimension, dimension, weight_column, samples):
    """
    Attach each point's weight (an amount) to `points`, in the same order, as meta["weights"].

    The points were made from the rows that have both coordinates, so the weights are read
    from those same rows. A missing weight is NaN, which a weighted fit leaves out.
    """
    from ..table_ops import number_of
    chosen = set(samples) if samples is not None else None
    by_sample = {}
    for row in rows:
        sample = str(row.get(sample_col, "") or "").strip()
        if not sample or (chosen is not None and sample not in chosen):
            continue
        if row.get(x_dimension, "") in ("", None) or row.get(dimension, "") in ("", None):
            continue
        weight = number_of(row.get(weight_column))
        by_sample.setdefault(sample, []).append(float("nan") if weight is None else weight)
    points.meta["weights"] = by_sample
    points.meta["weight_column"] = weight_column
    return points


def _run_points(inputs, opts):
    rows, sample_col = table_of(inputs, "table")
    weight = opts.get("weight") if opts.get("use_weight") else None

    def make(dimension):
        made = points_from_table(rows, sample_col, opts.get("x_dimension"), dimension, opts)
        if weight:
            _weights_for(made, rows, sample_col, opts.get("x_dimension"), dimension, weight,
                         opts.get("samples"))
        return made

    return _each_dimension(opts, make, "Points")


def _validate_points(opts, context):
    if not opts["samples"]:
        return "Select at least one sample."
    if not opts["dimensions"]:
        return "Select at least one dimension."
    if opts.get("use_weight") and not opts.get("weight"):
        return "Choose the weight column."
    return _x_axis_problem(opts)


points = Node(
    "points", "Points", "Describe",
    [Port("table", (TABLE,), "Table")], POINTS,
    [
        Field("samples", "Samples", SAMPLES, page=DATA_PAGE),
        Field("x_dimension", "X dimension", DIMENSION, numeric_only=True,
              page=DATA_PAGE, hint="The horizontal position of each grain"),
        Field("dimensions", "Y dimensions", DIMENSIONS, numeric_only=True,
              page=DATA_PAGE,
              hint="Each becomes its own set of points against the x dimension"),
        Field("use_weight", "Weight each point", CHECKBOX, page=DATA_PAGE,
              hint="Give each point an amount (precipitation depth, say) for a weighted fit "
                   "in Fit a line; the plot itself is unchanged"),
        Field("weight", "Weight column", DIMENSION, numeric_only=True, nth=2, page=DATA_PAGE,
              when=lambda o: bool(o.get("use_weight"))),
    ],
    _run_points, _validate_points,
    description="Lifts two columns into points, one per grain, grouped by "
                "sample. Draw them with a Scatterplot.")


# ------------------------------------------------------------------------ Hull

def _run_hull(inputs, opts):
    batch = []
    for points in inputs["points"][0]:
        shapes = []
        for name, xs, ys in points.groups:
            outline = convex_hull(xs, ys)
            if outline:
                shapes.append((name, outline))
        if not shapes:
            raise NodeProblem(
                "No group has three or more points that enclose an area, so "
                "there is nothing to outline.")
        skipped = len(points.groups) - len(shapes)
        note = (f"Convex hull of each group of {points.name or 'points'}."
                + (f" {skipped} had too few points to outline." if skipped else ""))
        batch.append(Polygons(points.x_title, points.y_title, shapes, note=note,
                              name=points.name))
    return batch, None


hull = Node(
    "hull", "Convex hull", "Describe",
    [Port("points", (POINTS,), "Points")], POLYGON, [], _run_hull,
    description="Outlines each group of points — each sample's grains — with "
                "the smallest convex shape that holds them all. Draw it over "
                "the points by giving a Scatterplot both as inputs, or over a "
                "density with a Heatmap.")


# --------------------------------------------------------------------- Contour

def _run_contour(inputs, opts):
    share = float(opts.get("share", 68)) / 100.0
    batch = []
    for raster in inputs["raster"][0]:
        density_set = raster.density_set
        if density_set.categorical:
            raise NodeProblem("A contour needs two numeric axes; a category has "
                              "no smooth density to outline.")
        shapes = []
        for sample, dist in density_set.entries:
            level = density_level(dist.densities, share)
            for ring in contour_rings(dist.x_values, dist.y_values,
                                      dist.densities, level):
                shapes.append((sample, ring))
        if not shapes:
            raise NodeProblem(f"No outline could be traced for {raster.name}.")
        batch.append(Polygons(
            raster.x_name, raster.y_name, shapes, name=raster.name,
            note=f"The region holding {share:.0%} of each sample's density "
                 f"over {raster.name}."))
    return batch, None


contour = Node(
    "contour", "Density contour", "Describe",
    [Port("raster", (RASTER,), "Raster")], POLYGON,
    [
        Field("share", "Share of density", SELECT,
              choices={"50": "50%", "68": "68%", "90": "90%", "95": "95%"},
              default="68", cast=int,
              hint="The outline encloses the smallest region that holds this "
                   "much of each sample's density"),
    ],
    _run_contour,
    description="Outlines where each sample's bivariate density is concentrated. "
                "Draw it over its own Heatmap, or over Points with a Scatterplot.")


# ------------------------------------------------------------------ Sample PCA

def _run_sample_pca(inputs, opts):
    rows, sample_col = table_of(inputs, "table")
    dimensions = need_dimensions(opts)
    result, samples, labels, categorical, dropped = fit_sample_pca(
        rows, sample_col, dimensions, opts)
    order = {name: i for i, name in enumerate(sample_names(rows, sample_col))}
    note = (f"{len(samples)} samples on {len(dimensions)} "
            f"dimension{'s' if len(dimensions) != 1 else ''}. PC1 explains "
            f"{result.percent(0):.1f}% and PC2 {result.percent(1):.1f}% of the "
            f"variance between samples.")
    if dropped:
        note += " Left out for missing data: " + ", ".join(dropped) + "."
    return [Points(
        f"PC1 ({result.percent(0):.1f}%)", f"PC2 ({result.percent(1):.1f}%)",
        [(s, [float(p.x)], [float(p.y)]) for s, p in zip(samples, result.points)],
        note=note, title="Sample PCA", name="Sample PCA",
        meta={"labeled": True, "order": order,
              "colors": color_groups(rows, sample_col, samples, opts.get("color_by")),
              "sample_pca": {"result": result, "dimensions": dimensions,
                             "labels": labels, "categorical": categorical}})], None


def _validate_sample_pca(opts, context):
    if len(opts["samples"]) < 3:
        return "Sample PCA needs at least three samples."
    return None if opts["dimensions"] else "Select at least one dimension."


sample_pca = Node(
    "sample_pca", "Sample PCA", "Compare",
    [Port("table", (TABLE,), "Table")], POINTS,
    [
        Field("samples", "Samples", SAMPLES, page=DATA_PAGE),
        Field("dimensions", "Dimensions", DIMENSIONS, page=DATA_PAGE,
              hint="The distributions to compare; all go into one fit"),
        Field("color_by", "Colour samples by", SELECT,
              choices=lambda context: {NO_COLOR: NO_COLOR,
                                       **{d: d for d in context.dimensions}},
              hint="A column's mean per sample (numbers) or most common value "
                   "(categories)"),
        Field("clr", "Log-ratio shares (CLR)", CHECKBOX,
              hint="For categorical dimensions: stops abundant categories "
                   "dominating the axes"),
    ],
    _run_sample_pca, _validate_sample_pca,
    description="One point per sample, placed by how its distributions differ. "
                "Draw the map with a Scatterplot and what drives it with a PCA "
                "report.")


# ------------------------------------------------------------------- Grain PCA

def _run_grain_pca(inputs, opts):
    rows, sample_col = table_of(inputs, "table")
    charts = []
    new_rows, body = run_axes(charts, rows, sample_col, need_dimensions(opts),
                              opts, in_workflow=True)
    return [new_rows], StepOutput(opts.get("title") or "Grain PCA",
                                  body, charts, None)


def _validate_pca(opts, context):
    usable = [d for d in opts["dimensions"] if d not in ("PC1", "PC2")]
    if len(usable) < 2:
        return "Choose at least two variables to reduce."
    return None


grain_pca = Node(
    "grain_pca", "Grain PCA", "Transform",
    [Port("table", (TABLE,), "Table")], TABLE,
    [
        Field("samples", "Samples", SAMPLES, page=DATA_PAGE),
        Field("dimensions", "Variables", DIMENSIONS, page=DATA_PAGE,
              hint="The variables to reduce; all go into one fit. A "
                   "categorical variable is one-hot encoded and counts as "
                   "one variable"),
        Field("grain_weighting", "Weighting", SELECT, choices=GRAIN_WEIGHTINGS,
              hint="Stops a sample with many analyses from setting the axis "
                   "for everyone"),
        Field("scree", "Scree plot", CHECKBOX,
              hint="Shows how much is lost by keeping only two axes"),
    ],
    _run_grain_pca, _validate_pca,
    description="Reduces many variables to PC1 and PC2 for every grain and "
                "returns a copy of the table with them added, so the steps "
                "after it can use them as ordinary dimensions. The "
                "spreadsheet itself is not changed.")


# ------------------------------------------------------------------ Comparison

def _metric_choices(context, opts=None):
    """Lines get the 1-D measures and rasters the 2-D ones; a tool that has not
    made its raster yet says which it will by its Analysis choice."""
    bivariate = context.input_type == RASTER or (opts or {}).get("mode") == BI
    return numbered(metrics_for(RASTER if bivariate else LINE))


def _run_comparison(inputs, opts):
    return [compare(combine(group), opts["metric"])
            for group in aligned(inputs["distributions"])], None


comparison = Node(
    "comparison", "Comparison", "Compare",
    [Port("distributions", (LINE, RASTER), "Distributions", multiple=True,
          hint="Add more inputs to compare the samples of several Distribution steps "
               "together; they are put on one shared grid. An NMF can be added too: "
               "its sources are compared as samples")], MATRIX,
    [
        Field("metric", "Comparison metric", SELECT, choices=_metric_choices,
              dynamic=True,
              hint="Statistic computed for every pair of samples; lines use "
                   "the 1D measures, rasters the 2D ones"),
    ],
    _run_comparison,
    description="Scores every pair of samples with a metric, giving a matrix "
                "to read as a table or to map with MDS.")


# ----------------------------------------------------------------------- Match

def _run_match(inputs, opts):
    """Candidates against empirical samples, one pair of items from each port at a time."""
    split = len(inputs["candidates"])
    batch = []
    for group in aligned(inputs["candidates"] + inputs["references"]):
        batch.append(match_sets(combine(group[:split]), combine(group[split:]),
                                opts.get("metric", "r2")))
    return batch, None


match = Node(
    "match_sources", "Match sources", "Compare",
    [Port("candidates", (LINE, RASTER), "Candidate sources", multiple=True,
          hint="The distributions to test: an NMF's Sources, say. Add more inputs to take "
               "them from several steps"),
     Port("references", (LINE, RASTER), "Empirical sources", multiple=True,
          hint="The distributions of the samples you believe are the real sources")],
    MATRIX,
    [
        Field("metric", "Match metric", SELECT, choices=_metric_choices, default="r2",
              dynamic=True,
              hint="How alike two distributions are. Saylor et al. compared factorized and "
                   "known sources by cross-correlation (R²) and the Kuiper V statistic"),
    ],
    _run_match,
    description="Compares each candidate source with each empirical one: a row per candidate, "
                "a column per empirical sample, and the best match for each candidate. Unlike "
                "a Comparison it never compares the candidates with each other or the "
                "empirical samples with each other.")


# ------------------------------------------------------------------------- MDS

def _run_mds(inputs, opts):
    non_metric = opts.get("mds_type", "non_metric") == "non_metric"
    batch = []
    for matrix in inputs["matrix"][0]:
        if matrix.dissimilarity is None:
            raise NodeProblem("This matrix compares two different sets of samples, so "
                              "there is no map to make from it; MDS needs every sample "
                              "compared with every other.")
        if len(matrix.names) < 3:
            raise NodeProblem("Need at least three samples with data for MDS.")
        dissimilarity = matrix.dissimilarity()
        embedding, stress = mds_lib.compute_mds(dissimilarity, non_metric=non_metric)
        found = mds_lib.mds_points([(n, None) for n in matrix.names],
                                   dissimilarity, embedding)
        links = [(p.x, p.y, p.nearest_neighbor[0], p.nearest_neighbor[1])
                 for p in found if p.nearest_neighbor is not None]
        note = (f"{MDS_TYPES[opts.get('mds_type', 'non_metric')]} on "
                f"{matrix.metric_label} dissimilarity of {matrix.name} — "
                f"Kruskal stress-1: {stress:.4f}.")
        batch.append(Points(
            "Dimension 1", "Dimension 2",
            [(p.label, [p.x], [p.y]) for p in found], note=note, links=links,
            title=f"{matrix.name} — MDS", name=matrix.name,
            meta={"labeled": True, "stress": stress, "non_metric": non_metric,
                  "matrix": dissimilarity, "embedding": embedding,
                  "order": {n: i for i, n in enumerate(matrix.names)}}))
    return batch, None


mds = Node(
    "mds", "MDS", "Compare",
    [Port("matrix", (MATRIX,), "Matrix")], POINTS,
    [
        Field("mds_type", "MDS type", SELECT, choices=MDS_TYPES,
              hint="Non-metric preserves rank order; metric preserves "
                   "distances"),
    ],
    _run_mds,
    description="Places samples on a plane so that similar ones sit close "
                "together, from a Comparison matrix. Draw it with a "
                "Scatterplot.")


# --------------------------------------------------------------------- Mixture

def _run_mixture(inputs, opts):
    batch = []
    for group in aligned(inputs["sources"]):
        datum = combine(group)
        batch.append(unmix_raster(datum, opts) if isinstance(datum, Raster)
                     else unmix_lines(datum, opts))
    return batch, None


def _validate_mixture(opts, context):
    if not opts.get("sink"):
        return "Choose a sink sample."
    if len(context.samples) < 3:
        return "Unmixing needs the sink and at least two more samples."
    return None


mixture = Node(
    "mixture", "Mixture model", "Model",
    [Port("sources", (LINE, RASTER), "Distributions", multiple=True,
          hint="Add more inputs to pool samples from several Distribution "
               "steps — the sink can come from one and its sources from another")],
    PROPORTIONS,
    [
        Field("sink", "Sink sample", SAMPLE, page=DATA_PAGE,
              hint="The mixed sample; every other sample in the input is a "
                   "source"),
        Field("metric", "Comparison metric", SELECT,
              choices=numbered(MIXTURE_METRICS),
              hint="Scores each trial's modelled curve against the sink"),
        Field("trials", "Trials", SELECT,
              choices={str(n): f"{n:,}" for n in MIXTURE_TRIALS},
              default=str(MIXTURE_TRIALS[2]), cast=int,
              hint="Random source configurations to try; more is slower but "
                   "steadier"),
    ],
    _run_mixture, _validate_mixture,
    description="Models the sink sample as a mixture of the other samples by "
                "top-down Monte Carlo unmixing. Draw the contributions with "
                "a Bar chart.")


# ------------------------------------------------------------------------- NMF

def _run_nmf(inputs, opts):
    fits = [factorize_lines(combine(group), opts) for group in aligned(inputs["distributions"])]
    return {"": [sources_as_lines(f) for f in fits],
            "weights": [weights_matrix(f) for f in fits],
            "fit": fits}, None


def _validate_nmf(opts, context):
    if opts.get("rank_mode") == "fixed" and not opts.get("sources"):
        return "Say how many sources to factorize into."
    return None


nmf_block = Node(
    "nmf", "NMF sources", "Model",
    [Port("distributions", (LINE,), "Distributions", multiple=True,
          hint="The sink samples' distributions. Add more inputs to pool the samples of "
               "several Distribution steps")], LINE,
    [
        Field("rank_mode", "Number of sources", SELECT,
              choices={"auto": "Automatic — from the residual curve",
                       "fixed": "Fixed — use the number below"},
              default="auto",
              hint="Automatic follows Saylor et al. (2019): the residual is found for each "
                   "rank and the rank is where it stops falling steeply"),
        Field("sources", "Sources", NUMBER, when=lambda o: o.get("rank_mode") == "fixed",
              hint="How many sources to factorize into"),
        Field("max_sources", "Most sources to try", NUMBER,
              when=lambda o: o.get("rank_mode", "auto") == "auto",
              hint="Blank tries up to 8, or as many as there are samples"),
        Field("restarts", "Random starts", SELECT,
              choices={"3": "3 (fast)", "5": "5", "10": "10", "20": "20 (steadier)"},
              default="5", cast=int,
              hint="Each rank is factorized from this many random starts and the best "
                   "kept; more is slower but less likely to land in a poor solution"),
    ],
    _run_nmf, _validate_nmf,
    # One factorization, three things worth having: the sources (as ordinary
    # distributions, the first output, so anything that reads distributions can take
    # them), how much of each every sample holds, and the whole fit for the report.
    extras=[Output("weights", MATRIX, "Weights"), Output("fit", FACTORS, "Fit")],
    output_label="Sources",
    description="Non-negative matrix factorization (Saylor, Sundell & Sharman 2019): "
                "finds the source distributions the sink samples are mixtures of, and "
                "how much of each every sample holds. Works best with more than about "
                "three times as many samples as sources, each well characterized and "
                "different from the others. Feed it KDEs rather than PDPs when the ages are "
                "precise: PDPs are so spiky that the number of sources can come out too low. "
                "The answer is not unique; judge it against what you know of the geology.")


COMPUTE_NODES = [distribution, points, hull, contour, grain_pca, sample_pca, comparison,
                 mds, mixture, nmf_block, match]
