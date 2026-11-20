"""
The kinds of data that flow between workflow steps.

A step's output is a *batch*: a list of values of one type. A Distribution over
three dimensions yields a batch of three `Lines`; a plot that reads it draws one
tab for each. Every node maps over a batch element by element, which is what
lets "check several dimensions" keep working once analyses are chained.

The types describe the shape of the data, not how it is drawn:

    TABLE        rows of the spreadsheet, or a table a step derived from it
    LINE         curves on a shared x — a PDF/CDF per sample
    RASTER       a surface on a shared grid — a bivariate density per sample
    POINTS       positions — grains, or samples placed by an ordination
    MATRIX       one number per pair of samples
    POLYGON      closed outlines — a hull or a density contour
    PROPORTIONS  shares that sum to a whole, with their uncertainty
    FACTORS      samples factorized into sources and weights (NMF)

These dataclasses hold plain Python and numpy values and import nothing from
the browser, so the engine and the nodes' computations can be tested without it.
"""
from dataclasses import dataclass, field

TABLE = "table"
LINE = "line"
RASTER = "raster"
POINTS = "points"
MATRIX = "matrix"
POLYGON = "polygon"
PROPORTIONS = "proportions"
FACTORS = "factors"

TYPE_LABELS = {
    TABLE: "Table", LINE: "Line", RASTER: "Raster", POINTS: "Points",
    MATRIX: "Matrix", POLYGON: "Polygon", PROPORTIONS: "Proportions",
    FACTORS: "Factors",
}


@dataclass
class Lines:
    """
    Curves of one dimension for several samples, all on the same x.

    `pdf` and `cdf` hold the same curves in both forms, because the plots want
    one and the comparison metrics another (KS and Kuiper read cumulative
    curves); each consumer takes the form it needs.
    """
    name: str                 # the dimension these curves describe
    x: list                   # grid values, or category names
    pdf: list                 # [(sample, [y, ...]), ...]
    cdf: list
    categorical: bool = False
    note: str = ""            # how the curves were built, for a caption

    def series(self, form):
        return self.cdf if form == "cdf" else self.pdf


@dataclass
class Points:
    """
    Positions in a plane, in named groups.

    Attributes:
        groups: [(name, xs, ys), ...] — a sample's grains, or one named point.
            meta["order"] maps a name to its place in the spreadsheet, so a
            sample keeps its colour whichever selection it is plotted in;
            meta["labeled"] marks groups that are single points to be labelled
            (an ordination map) rather than clouds of grains
        links: [(x0, y0, x1, y1), ...] segments to draw between points
        meta: whatever the producer wants a later step to know (e.g. stress)
    """
    x_title: str
    y_title: str
    groups: list
    note: str = ""
    links: list = field(default_factory=list)
    meta: dict = field(default_factory=dict)
    title: str = ""           # the plot's own title, when "x vs y" would not do
    name: str = ""            # what a batch's tab is called (usually a dimension)


@dataclass
class Raster:
    """Per-sample surfaces on a shared grid (a BivariateSet) and what they plot."""
    x_name: str
    y_name: str
    density_set: object       # dashboard.bivariate.BivariateSet
    note: str = ""            # how it was built, when that is worth saying (pooled inputs)

    @property
    def name(self):
        return f"{self.x_name} vs {self.y_name}"


@dataclass
class Matrix:
    """
    One number per pair of samples — or, when `columns` is given, per pair of one
    set of samples (the rows) and another (the columns), as when NMF sources are
    matched against empirical ones.

    `values` is the metric as the user reads it. `dissimilarity` is a function
    returning the matrix an ordination wants — the metric turned into a
    distance — computed on first use, since most matrices are only displayed.
    """
    name: str
    names: list
    values: list              # n x n, nan where undefined
    metric_label: str = ""
    note: str = ""
    dissimilarity: object = None   # () -> numpy (n, n), or None; none for two different sets
    warning: str = ""
    columns: list = None           # the column labels, when they are not the rows' names


@dataclass
class Polygons:
    """
    Outlines, one per name. Each is a list of (x, y) vertices.

    `open` shapes are lines, not closed outlines (a fitted line); the names in
    `reference` are drawn dashed and on every panel, not just their own (a
    published line the data is compared with); `fill` shades closed outlines
    (the erosion, transport and deposition fields of a Hjulström diagram).
    """
    x_title: str
    y_title: str
    shapes: list              # [(name, [(x, y), ...]), ...]
    note: str = ""
    name: str = ""            # what a batch's tab is called, as for Points
    open: bool = False
    reference: list = field(default_factory=list)
    fill: bool = False        # shade the inside of each closed outline (a field on a diagram)
    bare: bool = False        # the names are legend entries as they are, without "outline" or "line"
    colors: dict = field(default_factory=dict)    # name -> "#rrggbb", where the order carries meaning


@dataclass
class Proportions:
    """Shares of a whole by name, with an uncertainty on each."""
    name: str
    names: list
    values: list              # percent
    errors: list
    label: str = "% contribution"
    note: str = ""
    meta: dict = field(default_factory=dict)


@dataclass
class Factors:
    """
    Sink samples factorized into sources and the weights that mix them.

    Attributes:
        name: the dimension factorized
        x: the grid the curves are on, or category names
        sample_names: the rows of `weights`
        source_names: "Source 1", ... in order of position along the grid
        sources: [[y, ...], ...] one curve per source, each summing to 1
        weights: [[w, ...], ...] one row per sample, each summing to 1
        ranks, residuals: the ranks tried and the final residual of each
        totals: for an automatic choice, the summed squared residuals of the
            two fitted lines at each candidate break (else empty)
        automatic: whether the rank was chosen from the residual curve
        quality: R^2 between each sample and its reconstruction
        warnings: sentences for conditions the method wants and the data lacks
    """
    name: str
    x: list
    sample_names: list
    source_names: list
    sources: list
    weights: list
    ranks: list
    residuals: list
    totals: list = field(default_factory=list)
    automatic: bool = False
    quality: list = field(default_factory=list)
    warnings: list = field(default_factory=list)
    categorical: bool = False

    @property
    def rank(self):
        return len(self.source_names)
