"""
The tools that ship with the app, as chains of blocks.

Each is the same `ToolDef` a user's saved tool is, so nothing here is special:
these just happen to be written in Python rather than read from a project. Parameter
names are the option names the toolbar's saved outputs always used, so a project
saved before tools were chains rebuilds unchanged.

Toolboxes:
    Quality control       cleaning a table before analysis
    Distributions         what each sample looks like
    Sample comparison     how samples differ from one another
    Provenance modelling  where a mixed sample came from
    Multivariate          several variables at once
    Hydrology             time, discharge and precipitation; grouping by date and season; hydrograph
                          separation; the local meteoric water line; the Hjulström diagram
    Stable isotopes       δ values: scales, food webs, carbonate temperatures, water lines,
                          isotopic niches and mixing, for the geo- and life sciences
"""
from sed_stats import isotopes
from workflow_lib import ParamSpec, ToolDef, ToolStep

from .table_ops import DATE_PARTS

DATA = "data"
UNI, BI = "uni", "bi"


def step(step_id, node, options=None, expose=(), inputs=None, when=None):
    return ToolStep(step_id, node, dict(options or {}), expose, dict(inputs or {}), when)


def table_in(port="table"):
    return {port: [DATA]}


def distribution_params(uni="uni", bi="bi"):
    """What choosing a distribution asks, for a tool with a univariate and a
    bivariate chain: `uni` and `bi` name the steps the options are taken from."""
    return [
        ParamSpec("samples", source=f"{uni}.samples"),
        ParamSpec("dimensions", source=f"{uni}.dimensions"),
        ParamSpec("mode", source=f"{uni}.mode", default=UNI),
        ParamSpec("x_dimension", source=f"{bi}.x_dimension"),
        ParamSpec("density", source=f"{uni}.density"),
        ParamSpec("sigma_in", source=f"{uni}.sigma_in"),
        ParamSpec("bandwidth", source=f"{uni}.bandwidth"),
        ParamSpec("bin_size", source=f"{uni}.bin_size"),
        ParamSpec("grid", source=f"{bi}.grid"),
        ParamSpec("x_bandwidth", source=f"{bi}.x_bandwidth"),
        ParamSpec("y_bandwidth", source=f"{bi}.y_bandwidth"),
    ]


def distribution_steps(sources=("samples", "dimensions", "density", "sigma_in")):
    """The two ways to describe a table — one line per dimension, or a surface
    per dimension against an x — of which the Analysis choice runs one."""
    return [
        step("uni", "distribution", {"mode": UNI},
             [*sources, "bandwidth", "bin_size"], table_in(), {"mode": UNI}),
        step("bi", "distribution", {"mode": BI},
             [*sources, "x_dimension", "grid", "x_bandwidth", "y_bandwidth"],
             table_in(), {"mode": BI}),
    ]


DISTRIBUTIONS = ToolDef(
    "distributions", "Distributions", "Distributions",
    "A histogram, PDF or CDF for each sample and dimension — or, paired with an "
    "x dimension, a 2-D density.",
    params=[
        ParamSpec("samples", source="uni.samples"),
        ParamSpec("dimensions", source="uni.dimensions"),
        ParamSpec("mode", source="uni.mode", default=UNI),
        ParamSpec("x_dimension", source="bi.x_dimension"),
        ParamSpec("view", default="pdf", when={"mode": UNI}, label="View",
                  hint="Histogram counts, or normalized PDF / CDF",
                  field={"kind": "select", "default": "pdf",
                         "choices": {"histogram": "Histogram", "pdf": "PDF", "cdf": "CDF"}}),
        ParamSpec("layout", source="line.layout", when={"mode": UNI}),
        ParamSpec("density", source="uni.density"),
        ParamSpec("sigma_in", source="uni.sigma_in"),
        ParamSpec("bandwidth", source="uni.bandwidth"),
        ParamSpec("bin_size", source="uni.bin_size", when={"mode": UNI}),
        ParamSpec("grid", source="bi.grid"),
        ParamSpec("x_bandwidth", source="bi.x_bandwidth"),
        ParamSpec("y_bandwidth", source="bi.y_bandwidth"),
        ParamSpec("show_points", label="Overlay grains", when={"mode": BI},
                  hint="Draw the raw measurements over the density; needs numeric axes",
                  field={"kind": "checkbox"}),
    ],
    steps=[
        step("uni", "distribution", {"mode": UNI},
             ["samples", "dimensions", "density", "sigma_in", "bandwidth", "bin_size"],
             table_in(), {"mode": UNI, "view": ["pdf", "cdf"]}),
        step("line", "line_plot", {}, ["view", "layout"], {"lines": ["uni"]},
             {"mode": UNI, "view": ["pdf", "cdf"]}),
        step("hist", "histogram", {}, ["samples", "dimensions", "bin_size", "layout"],
             table_in(), {"mode": UNI, "view": "histogram"}),
        step("bi", "distribution", {"mode": BI},
             ["samples", "dimensions", "density", "sigma_in", "x_dimension", "grid",
              "x_bandwidth", "y_bandwidth"], table_in(), {"mode": BI}),
        step("grains", "points", {}, ["samples", "x_dimension", "dimensions"],
             table_in(), {"mode": BI, "show_points": True}),
        step("heat", "heatmap", {}, [], {"raster": ["bi"], "overlays": ["grains"]},
             {"mode": BI}),
    ])

DENSITY_CONTOURS = ToolDef(
    "contours", "Density contours", "Distributions",
    "Each sample's 2-D density with the outline of the region holding most of it.",
    params=[
        ParamSpec("samples", source="bi.samples"),
        ParamSpec("dimensions", source="bi.dimensions", label="Y dimensions"),
        # This tool is always bivariate, so what the block shows only in that
        # analysis is shown always.
        ParamSpec("x_dimension", source="bi.x_dimension", when={}),
        ParamSpec("density", source="bi.density"),
        ParamSpec("sigma_in", source="bi.sigma_in"),
        ParamSpec("grid", source="bi.grid", when={}),
        ParamSpec("x_bandwidth", source="bi.x_bandwidth", when={}),
        ParamSpec("y_bandwidth", source="bi.y_bandwidth", when={}),
        ParamSpec("share", source="outline.share", default=68),
    ],
    steps=[
        step("bi", "distribution", {"mode": BI},
             ["samples", "dimensions", "density", "sigma_in", "x_dimension", "grid",
              "x_bandwidth", "y_bandwidth"], table_in()),
        step("outline", "contour", {}, ["share"], {"raster": ["bi"]}),
        step("heat", "heatmap", {}, [], {"raster": ["bi"], "overlays": ["outline"]}),
    ])

COMPARISON_MATRICES = ToolDef(
    "matrix", "Comparison matrices", "Sample comparison",
    "A measure of how alike every pair of samples is.",
    params=[*distribution_params(),
            ParamSpec("metric", source="cmp.metric", default="similarity")],
    steps=[*distribution_steps(),
           step("cmp", "comparison", {}, ["metric"], {"distributions": ["uni", "bi"]}),
           step("show", "matrix_table", {}, [], {"matrix": ["cmp"]})])

MDS = ToolDef(
    "mds", "MDS", "Sample comparison",
    "A map of the samples in which similar ones sit close together.",
    params=[*distribution_params(),
            ParamSpec("metric", source="cmp.metric", default="similarity"),
            ParamSpec("mds_type", source="map.mds_type"),
            ParamSpec("shepard", label="Shepard plot", field={"kind": "checkbox"},
                      hint="Diagnostic comparing dissimilarities to MDS distances")],
    steps=[*distribution_steps(),
           step("cmp", "comparison", {}, ["metric"], {"distributions": ["uni", "bi"]}),
           step("map", "mds", {}, ["mds_type"], {"matrix": ["cmp"]}),
           step("plot", "scatter",
                {"layout": "overlay", "color_by_sample": True, "point_size": 7},
                [], {"series": ["map"]}),
           step("fit", "shepard", {}, [], {"points": ["map"]}, {"shepard": True})])

SAMPLE_PCA = ToolDef(
    "sample_pca", "Sample PCA", "Sample comparison",
    "One point per sample, placed by how its distributions differ, and what "
    "drives the placement.",
    params=[ParamSpec("samples", source="pca.samples"),
            ParamSpec("dimensions", source="pca.dimensions"),
            ParamSpec("color_by", source="pca.color_by"),
            ParamSpec("clr", source="pca.clr"),
            ParamSpec("scree", source="report.scree")],
    steps=[step("pca", "sample_pca", {}, ["samples", "dimensions", "color_by", "clr"],
                table_in()),
           step("plot", "scatter",
                {"layout": "overlay", "color_by_sample": True, "point_size": 7},
                [], {"series": ["pca"]}),
           step("report", "pca_report", {}, ["scree"], {"points": ["pca"]})])

MIXTURE = ToolDef(
    "mixture", "Mixture model", "Provenance modelling",
    "Models a mixed sample as a blend of the others, by top-down Monte Carlo "
    "unmixing.",
    params=[*distribution_params(),
            ParamSpec("sink", source="mix.sink"),
            ParamSpec("metric", source="mix.metric"),
            ParamSpec("trials", source="mix.trials")],
    steps=[*distribution_steps(),
           step("mix", "mixture", {}, ["sink", "metric", "trials"],
                {"sources": ["uni", "bi"]}),
           step("bar", "bar_chart", {"show_fit": True}, [], {"proportions": ["mix"]})])

UNMIX_PC1 = ToolDef(
    "unmix_pc1", "Unmix along PC1", "Provenance modelling",
    "Reduces many variables to their first principal component, then unmixes the "
    "sink along it — the multivariate route when no single variable separates "
    "the sources.",
    params=[ParamSpec("samples", source="pca.samples"),
            ParamSpec("dimensions", source="pca.dimensions", label="Variables to reduce"),
            ParamSpec("grain_weighting", source="pca.grain_weighting"),
            ParamSpec("sink", source="mix.sink"),
            ParamSpec("metric", source="mix.metric"),
            ParamSpec("trials", source="mix.trials")],
    steps=[step("pca", "grain_pca", {"scree": False},
                ["samples", "dimensions", "grain_weighting"], table_in()),
           step("dist", "distribution",
                {"mode": UNI, "dimensions": ["PC1"], "density": "kde", "sigma_in": 1.0,
                 "bandwidth": None, "bin_size": None},
                ["samples"], {"table": ["pca"]}),
           step("mix", "mixture", {}, ["sink", "metric", "trials"],
                {"sources": ["dist"]}),
           step("bar", "bar_chart", {"show_fit": True}, [], {"proportions": ["mix"]})])

NMF_SOURCES = ToolDef(
    "nmf", "NMF sources", "Provenance modelling",
    "Finds the source distributions a set of sink samples are mixtures of, and how much "
    "of each every sample holds (Saylor, Sundell & Sharman 2019). Optionally compares "
    "those sources with samples you believe are the real ones, in a table of how well each "
    "matches each. Needs more than about three times as many sink samples as sources.",
    params=[ParamSpec("samples", source="dist.samples", label="Sink samples",
                      hint="The mixed samples that are factorized"),
            ParamSpec("known", label="Empirical sources to compare with", page="Data",
                      hint="Optional: tick the samples you believe are the real sources. "
                           "Each factorized source is matched against each of them, with the "
                           "best match for each, and the curves are overlaid. Leave all "
                           "unticked to skip the comparison",
                      field={"kind": "samples", "unchecked": True}),
            ParamSpec("dimensions", source="dist.dimensions"),
            # A KDE, not the PDP the other tools start from: PDPs of precisely dated grains
            # are so spiky that their noise keeps the residual falling past the true number
            # of sources, and the automatic rank comes out low.
            ParamSpec("density", source="dist.density", default="kde",
                      hint="PDP spreads each grain by its own uncertainty and is very spiky "
                           "for precise ages, which can make the number of sources come out "
                           "too low; KDE (the default here) smooths it"),
            ParamSpec("sigma_in", source="dist.sigma_in"),
            ParamSpec("bandwidth", source="dist.bandwidth"),
            ParamSpec("bin_size", source="dist.bin_size"),
            ParamSpec("rank_mode", source="fac.rank_mode", default="auto"),
            ParamSpec("sources", source="fac.sources"),
            ParamSpec("max_sources", source="fac.max_sources"),
            ParamSpec("restarts", source="fac.restarts"),
            ParamSpec("match_metric", source="match.metric", when={"known": True},
                      label="Match metric", default="r2",
                      hint="How alike two distributions are. Saylor et al. compared "
                           "factorized and known sources by cross-correlation (R²) and "
                           "the Kuiper V statistic")],
    steps=[step("dist", "distribution", {"mode": UNI},
                ["samples", "dimensions", "density", "sigma_in", "bandwidth", "bin_size"],
                table_in()),
           step("fac", "nmf", {}, ["rank_mode", "sources", "max_sources", "restarts"],
                {"distributions": ["dist"]}),
           step("report", "nmf_report", {}, [], {"factors": ["fac.fit"]}),
           # With empirical sources named, the same curves are made for them, on the
           # same terms, and the factorized sources are matched against them.
           step("ref", "distribution", {"mode": UNI},
                {"samples": "known", "dimensions": "dimensions", "density": "density",
                 "sigma_in": "sigma_in", "bandwidth": "bandwidth", "bin_size": "bin_size"},
                table_in(), {"known": True}),
           step("match", "match_sources", {}, {"metric": "match_metric"},
                {"candidates": ["fac"], "references": ["ref"]}, {"known": True}),
           step("table", "matrix_table", {}, [], {"matrix": ["match"]}, {"known": True}),
           step("overlay", "line_plot", {"view": "pdf", "layout": "overlay"}, [],
                {"lines": ["fac", "ref"]}, {"known": True})])

def _adds_a_column(label, what):
    return ParamSpec("apply", label=label, default=True,
                     hint=f"Untick to see {what} without changing the spreadsheet",
                     field={"kind": "checkbox", "default": True})


FILTER_GRAINS = ToolDef(
    "filter", "Filter grains", "Quality control",
    "Keeps only the samples, or the grains whose value is within a range, one of a list, or "
    "present. Shows what was kept; the spreadsheet is replaced only if you ask.",
    params=[ParamSpec(key, source=f"f.{key}") for key in (
        "samples", "how", "column", "minimum", "maximum", "values")] + [
        ParamSpec("apply", label="Replace the spreadsheet with the kept grains", default=False,
                  hint="Off, you only see what the filter would keep. Grains dropped from "
                       "the spreadsheet can be got back only by reloading the data",
                  field={"kind": "checkbox", "default": False})],
    steps=[step("f", "filter_grains", {}, ["samples", "how", "column", "minimum", "maximum",
                                           "values"], table_in())],
    sheet={"step": "f", "when": {"apply": True}})

TRANSFORM_COLUMN = ToolDef(
    "transform", "Add transformed column", "Quality control",
    "Adds a log, square root, reciprocal or z-score of a column beside the original.",
    params=[ParamSpec("column", source="t.column"), ParamSpec("function", source="t.function"),
            ParamSpec("name", source="t.name"),
            _adds_a_column("Add the column to the spreadsheet", "the result")],
    steps=[step("t", "transform_column", {}, ["column", "function", "name"], table_in())],
    sheet={"step": "t", "when": {"apply": True}})

RATIO_COLUMN = ToolDef(
    "ratio", "Add ratio column", "Quality control",
    "Adds one column divided by another — Th/U, Lu/Hf — as a new column.",
    params=[ParamSpec("numerator", source="r.numerator"),
            ParamSpec("denominator", source="r.denominator"),
            ParamSpec("name", source="r.name"),
            _adds_a_column("Add the column to the spreadsheet", "the result")],
    steps=[step("r", "ratio_column", {}, ["numerator", "denominator", "name"], table_in())],
    sheet={"step": "r", "when": {"apply": True}})

VIEW_TABLE = ToolDef(
    "view_table", "Table view", "Quality control",
    "Shows the spreadsheet — the samples and columns you choose — as a sortable grid you can select "
    "and copy from. Any step that makes a table can also show it from its Show output button.",
    params=[ParamSpec("samples", source="t.samples"),
            ParamSpec("columns", source="t.columns", label="Columns",
                      hint="Leave all unticked to show every column")],
    steps=[step("t", "table_view", {}, ["samples", "columns"], table_in())])

SCATTERPLOT = ToolDef(
    "scatter", "Scatterplot", "Multivariate",
    "The raw grains, one dimension against another, coloured by sample.",
    params=[ParamSpec("samples", source="grains.samples"),
            ParamSpec("x_dimension", source="grains.x_dimension"),
            ParamSpec("dimensions", source="grains.dimensions", label="Y dimensions"),
            ParamSpec("layout", source="plot.layout"),
            ParamSpec("color_by_sample", source="plot.color_by_sample"),
            ParamSpec("point_size", source="plot.point_size")],
    steps=[step("grains", "points", {}, ["samples", "x_dimension", "dimensions"],
                table_in()),
           step("plot", "scatter", {}, ["layout", "color_by_sample", "point_size"],
                {"series": ["grains"]})])

TERNARY = ToolDef(
    "ternary", "Ternary", "Multivariate",
    "Three parts of a whole, one point per grain.",
    params=[ParamSpec(key, source=f"plot.{key}") for key in (
        "samples", "apex_a", "apex_b", "apex_c", "color_by_sample",
        "show_centroids", "point_size")],
    steps=[step("plot", "ternary", {}, ["samples", "apex_a", "apex_b", "apex_c",
                                        "color_by_sample", "show_centroids",
                                        "point_size"], table_in())])

GRAIN_PCA = ToolDef(
    "pca", "Grain PCA", "Multivariate",
    "Reduces many variables to PC1 and PC2 for every grain, and adds them to the "
    "spreadsheet as columns for the other tools to use.",
    params=[ParamSpec("samples", source="pca.samples"),
            ParamSpec("dimensions", source="pca.dimensions", label="Variables"),
            ParamSpec("grain_weighting", source="pca.grain_weighting"),
            ParamSpec("scree", source="pca.scree"),
            ParamSpec("apply", label="Add PC1 and PC2 to the spreadsheet", default=True,
                      hint="So the other tools offer them as dimensions; untick to "
                           "see the fit without changing the sheet",
                      field={"kind": "checkbox", "default": True})],
    steps=[step("pca", "grain_pca", {}, ["samples", "dimensions", "grain_weighting",
                                         "scree"], table_in())],
    sheet={"step": "pca", "when": {"apply": True}})


# ------------------------------------------------------------- stable isotopes
# Chains over the blocks in nodes/isotope.py and nodes/tablework.py. Each that adds a
# column offers to write it into the spreadsheet, as the Quality control tools do.

ISO = "Stable isotopes"


def _column_tool(key, label, description, node, options, extra=()):
    """A tool that adds one column to the table with a single block."""
    return ToolDef(
        key, label, ISO, description,
        params=[*extra, ParamSpec("apply", label="Add the column to the spreadsheet",
                                  default=True,
                                  hint="Untick to see the result without changing the spreadsheet",
                                  field={"kind": "checkbox", "default": True})],
        steps=[step("c", node, options, [p.key for p in extra], table_in())],
        sheet={"step": "c", "when": {"apply": True}})


def _from(step_id, *keys, **labels):
    return [ParamSpec(k, source=f"{step_id}.{k}", label=labels.get(k, "")) for k in keys]


CONVERT_OXYGEN = _column_tool(
    "iso_scale", "Convert δ¹⁸O scale",
    "Adds δ¹⁸O on the other of the VPDB and VSMOW scales — carbonates are usually reported "
    "against VPDB, waters and phosphates against VSMOW — so that carbonates and waters can "
    "be compared.", "convert_scale", {}, _from("c", "column", "conversion", "name"))

DEUTERIUM_EXCESS = _column_tool(
    "iso_difference", "Deuterium excess and Δ",
    "Adds the difference of two delta columns, or a fractionation 1000 ln α. With a factor "
    "of 8 on δ¹⁸O, the difference is deuterium excess, d = δ²H − 8·δ¹⁸O, which records "
    "the conditions where the water evaporated from.",
    "isotope_difference", {}, _from("c", "first", "second", "form", "factor", "name"))

ATOMIC_CN = ToolDef(
    "iso_cn", "Atomic C:N", ISO,
    "Adds atomic C:N from weight percent carbon and nitrogen (the weight ratio times "
    "14.007 / 12.011). Atomic C:N screens collagen for diagenesis — well preserved bone "
    "collagen has 2.9–3.6 (DeNiro 1985) — and measures lipid content in animal tissue; "
    "follow it with 'Filter grains' to drop the samples outside the range.",
    params=[ParamSpec("numerator", source="c.numerator", label="Carbon (wt %)"),
            ParamSpec("denominator", source="c.denominator", label="Nitrogen (wt %)"),
            ParamSpec("name", source="c.name", default="C:N atomic"),
            ParamSpec("apply", label="Add the column to the spreadsheet", default=True,
                      hint="Untick to see the result without changing the spreadsheet",
                      field={"kind": "checkbox", "default": True})],
    steps=[step("c", "ratio_column",
                {"factor": isotopes.ATOMIC_WEIGHT_N / isotopes.ATOMIC_WEIGHT_C},
                ["numerator", "denominator", "name"], table_in())],
    sheet={"step": "c", "when": {"apply": True}})

LIPID_CORRECTION = _column_tool(
    "iso_lipid", "Lipid-normalise δ¹³C",
    "Corrects δ¹³C of animal tissue for the lipids in it, which are depleted in ¹³C, from the "
    "sample's C:N: δ¹³C − 3.32 + 0.99 · C:N (Post et al. 2007, for aquatic animals, "
    "fitted on C:N up to 6.9). Do it before comparing tissues with different fat content.",
    "lipid_normalise", {}, _from("c", "d13c", "cn", "name"))

TROPHIC_POSITION = _column_tool(
    "iso_trophic", "Trophic position",
    "Estimates how many trophic levels above the baseline each consumer sits from δ¹⁵N: "
    "λ + (δ¹⁵N − baseline) / 3.4 (Post 2002). The baseline should be a long-lived primary "
    "consumer, such as mussels or snails, that integrates the same web.",
    "trophic_position", {}, _from("c", "d15n", "baseline_from", "baseline", "baseline_sample",
                                  "position", "enrichment", "name"))

CARBONATE_TEMPERATURE = _column_tool(
    "iso_temperature", "Carbonate temperature",
    "Estimates the temperature a carbonate grew at from its δ¹⁸O and the water's (Shackleton "
    "1974; Kim & O'Neil 1997; or a calibration you give). The water's δ¹⁸O is the biggest "
    "unknown — about 4–5 °C per ‰ — so state the assumption with the answer.",
    "carbonate_temperature", {}, _from("c", "calcite", "scale", "water_from", "water",
                                       "water_column", "equation", "a", "b", "c", "name"))

ISOTOPIC_NICHE = ToolDef(
    "iso_niche", "Isotopic niche", ISO,
    "Plots each sample's points in two isotope dimensions — δ¹³C against δ¹⁵N for a food "
    "web — with each one's standard ellipse, and tabulates the ellipse areas (SEA, SEAc), "
    "the convex hull area and how much the niches overlap (after SIBER, Jackson et al. 2011). "
    "Ellipse areas need more than about ten points per sample to be steady.",
    params=[ParamSpec("samples", source="grains.samples", label="Species or groups"),
            ParamSpec("x_dimension", source="grains.x_dimension", label="x (δ¹³C)"),
            ParamSpec("dimensions", source="grains.dimensions", label="y (δ¹⁵N)"),
            ParamSpec("shape", source="niche.shape"),
            ParamSpec("level", source="niche.level"),
            ParamSpec("layout", source="plot.layout"),
            ParamSpec("point_size", source="plot.point_size")],
    steps=[step("grains", "points", {}, ["samples", "x_dimension", "dimensions"], table_in()),
           step("niche", "niche", {}, ["shape", "level"], {"points": ["grains"]}),
           step("plot", "scatter", {"color_by_sample": True}, ["layout", "point_size"],
                {"series": ["grains", "niche"]})])

WATER_LINE = ToolDef(
    "iso_water_line", "Local meteoric water line", "Hydrology",
    "Plots δ²H against δ¹⁸O for water samples with a fitted line — a local meteoric water "
    "line — and the global one (δ²H = 8·δ¹⁸O + 10, Craig 1961) dashed for comparison. Weight each "
    "point by its precipitation amount (Hughes & Crawford 2012) so that large events count for "
    "more and the many small, often evaporated ones for less. Waters that have evaporated fall on "
    "lines with a slope below 8, below the global line.",
    params=[ParamSpec("samples", source="grains.samples"),
            ParamSpec("x_dimension", source="grains.x_dimension", label="x (δ¹⁸O)"),
            ParamSpec("dimensions", source="grains.dimensions", label="y (δ²H)"),
            ParamSpec("use_weight", source="grains.use_weight", label="Weight by precipitation amount"),
            ParamSpec("weight", source="grains.weight", label="Precipitation amount column"),
            ParamSpec("scope", source="fit.scope"),
            ParamSpec("method", source="fit.method"),
            ParamSpec("reference", source="fit.reference", default="gmwl"),
            ParamSpec("ref_slope", source="fit.ref_slope"),
            ParamSpec("ref_intercept", source="fit.ref_intercept"),
            ParamSpec("layout", source="plot.layout"),
            ParamSpec("point_size", source="plot.point_size")],
    steps=[step("grains", "points", {}, ["samples", "x_dimension", "dimensions", "use_weight", "weight"],
                table_in()),
           step("fit", "fit_line", {}, ["scope", "method", "reference", "ref_slope",
                                       "ref_intercept"], {"points": ["grains"]}),
           step("plot", "scatter", {"color_by_sample": True}, ["layout", "point_size"],
                {"series": ["grains", "fit"]})])

ISOTOPE_MIXING = ToolDef(
    "iso_mixing", "Isotope mixing solutions", ISO,
    "Finds every combination of source shares that reproduces a mixture's isotope values "
    "(IsoSource, Phillips & Gregg 2003) and shows each source's share as a distribution. "
    "Pick the mixture (a consumer, sediment, water) and its end members. With more sources than "
    "isotopes + 1 the answer is a range, which is the honest result.",
    params=_from("mix", "tracers", "mixture", "sources", "increment", "tolerance"),
    steps=[step("mix", "isosource", {}, ["tracers", "mixture", "sources", "increment",
                                         "tolerance"], table_in()),
           step("bar", "bar_chart", {}, [], {"proportions": ["mix"]})])

END_MEMBER_MIXING = ToolDef(
    "iso_emma", "End-member mixing", ISO,
    "Solves what share of a mixture — a stream, a consumer — came from each end member, from the "
    "mass balance of its tracers (EMMA). Exact when there is one more end member than tracers, "
    "a least-squares fit when there are fewer, with an uncertainty from Monte Carlo draws of the "
    "end members' means. A share well below 0 or above 100% means the mixture lies outside the "
    "end members. With more end members than tracers + 1, use Isotope mixing solutions.",
    params=_from("mix", "tracers", "mixture", "sources", "constraint", "spread", "trials"),
    steps=[step("mix", "emma", {}, ["tracers", "mixture", "sources", "constraint", "spread",
                                    "trials"], table_in()),
           step("bar", "bar_chart", {}, [], {"proportions": ["mix"]})])

END_MEMBER_SPLITTING = ToolDef(
    "iso_emsa", "End-member splitting", ISO,
    "End-member splitting analysis (Kirchner & Allen 2020): from a tracer and the fluxes, what "
    "share of each streamflow came from each of two precipitation end members (mixing), and "
    "what share of each precipitation end member left as each streamflow or as "
    "evapotranspiration (splitting). Each sample is a category: name your samples by season or "
    "type, one row per sample interval, with its tracer value and its flux.",
    params=_from("split", "tracer", "precipitation", "streamflow", "use_flux", "flux", "years",
                 "bounded"),
    steps=[step("split", "emsa", {}, ["tracer", "precipitation", "streamflow", "use_flux", "flux",
                                      "years", "bounded"], table_in()),
           step("mixing", "bar_chart", {}, [], {"proportions": ["split"]}),
           step("splitting", "bar_chart", {}, [], {"proportions": ["split.splitting"]})])


# ------------------------------------------------------------------- hydrology
# Time, discharge and precipitation, and the grouping that hydrology's methods need.

HYDRO = "Hydrology"

GROUP_BY_DATE = _column_tool(
    "hy_dates", "Group by date", "Adds one part of each row's date as a column: the year, month, "
    "water year, day of the water year, season, or a split of the year in two by months you "
    "give (snow and warm, say). Follow it with Regroup samples to analyse by that grouping.",
    "date_part", {}, _from("c", "column", "part", "season_months", "first_name", "second_name",
                           "hemisphere", "water_year_start", "day_first", "name"))
GROUP_BY_DATE.toolbox = HYDRO

REGROUP_SAMPLES = ToolDef(
    "hy_regroup", "Regroup samples", HYDRO,
    "Renames every row's sample from another column — a season from Group by date, a year, a "
    "site — so tools that compare or split by sample work on that grouping, as end-member "
    "splitting wants one sample per season. The old names are kept in a column of their own.",
    params=[ParamSpec("column", source="g.column"), ParamSpec("mode", source="g.mode"),
            ParamSpec("apply", label="Replace the spreadsheet with the regrouped rows", default=False,
                      hint="Off, you only see how the samples would fall. On, the spreadsheet's "
                           "sample names are changed (the old names are kept in a new column)",
                      field={"kind": "checkbox", "default": False})],
    steps=[step("g", "regroup", {}, ["column", "mode"], table_in())],
    sheet={"step": "g", "when": {"apply": True}})

SAMPLE_SUMMARY = ToolDef(
    "hy_summary", "Sample summary", HYDRO,
    "One row per sample: how many values, and for each column the mean, standard deviation and "
    "standard error. With a precipitation amount column, also the amount-weighted mean and its "
    "standard error (Kirchner & Allen 2020): the amount-weighted δ¹⁸O of precipitation.",
    params=_from("s", "columns", "use_weight", "weight"),
    steps=[step("s", "sample_summary", {}, ["columns", "use_weight", "weight"], table_in())])

ISOTOPE_TIME_SERIES = ToolDef(
    "hy_time_series", "Time series", HYDRO,
    "Plots any measurement against its date, a line per sample, optionally with error bars: a "
    "δ¹⁸O record through the years. As a typical year, the years are laid over one another by day "
    "of the water year to show the seasonal cycle.",
    params=_from("ts", "date", "dimensions", "samples", "use_error", "error", "view", "lines",
                 "day_first", "water_year_start"),
    steps=[step("ts", "time_series", {}, ["date", "dimensions", "samples", "use_error", "error",
                                          "view", "lines", "day_first", "water_year_start"], table_in())])

HYDROGRAPH = ToolDef(
    "hy_hydrograph", "Hydrograph and hyetograph", HYDRO,
    "Discharge through time with precipitation hanging from the top of the same chart in its own "
    "band, so rain and the flow it feeds read together. As the typical year it averages discharge by "
    "day of the water year and precipitation by month. Discharge and precipitation can be at "
    "different spacings (daily flow, monthly rain): put each in its own column and leave the other blank.",
    params=_from("h", "date", "samples", "use_flow", "flow", "use_rain", "rain", "view", "smooth",
                 "rain_at", "flow_units", "rain_units", "day_first", "water_year_start"),
    steps=[step("h", "hydrograph", {}, ["date", "samples", "use_flow", "flow", "use_rain", "rain",
                                        "view", "smooth", "rain_at", "flow_units", "rain_units",
                                        "day_first", "water_year_start"], table_in())])

HYDROGRAPH_SEPARATION = ToolDef(
    "hy_separation", "Hydrograph separation", HYDRO,
    "Solves each stream sample for the share of its water from each end member (snow, rain, "
    "groundwater) by its tracers, with a Monte Carlo uncertainty, and draws the fractions through "
    "time. The same mass balance as End-member mixing, for every sample. Conservative tracers and "
    "constant end members are assumed; δ¹⁸O and δ²H alone support two end members, not three, as "
    "they lie close to one line.",
    params=_from("sep", "tracers", "mixture", "sources", "date", "constraint", "spread", "trials"),
    steps=[step("sep", "hydrograph_separation", {}, ["tracers", "mixture", "sources", "date", "constraint",
                                                     "spread", "trials"], table_in()),
           step("plot", "time_series", {"dimensions": ["fraction_pct"], "use_error": True,
                                        "error": "sd_pct", "lines": True}, {"date": "date"},
                {"table": ["sep"]}, {"spread": ["se", "sd"]}),
           step("plot_plain", "time_series", {"dimensions": ["fraction_pct"], "lines": True},
                {"date": "date"}, {"table": ["sep"]}, {"spread": "none"})])

HJULSTROM = ToolDef(
    "hy_hjulstrom", "Hjulström diagram", HYDRO,
    "Draws grain size against flow velocity on log axes with the three fields of the Hjulström "
    "diagram — erosion, transport and deposition — shaded behind your own points, to see in which "
    "field each falls. The fields are rows of the spreadsheet (see hjulstrom_diagram.csv): a sample "
    "for each field, its corners as rows in order, with grain size in mm and velocity in cm/s; add "
    "your own samples to the same sheet, with their own names. Tick the same velocity column for the "
    "diagram and for your data. The diagram has no flow depth in it and is a historical, "
    "illustrative reference, not a design threshold.",
    params=[ParamSpec("diagram", source="fields.samples", label="Samples that are the fields"),
            ParamSpec("samples", label="Your samples", page="Data",
                      field={"kind": "samples", "unchecked": True}),
            ParamSpec("x_dimension", source="grains.x_dimension", label="Grain size column"),
            ParamSpec("y_dimension", source="fields.y_dimension", label="Velocity column (the fields)"),
            ParamSpec("dimensions", source="grains.dimensions", label="Velocity column (your samples)"),
            ParamSpec("point_size", source="plot.point_size")],
    steps=[step("fields", "table_outlines", {"shape": "closed", "fill": True},
                {"samples": "diagram", "x_dimension": "x_dimension", "y_dimension": "y_dimension"},
                table_in()),
           step("grains", "points", {}, ["samples", "x_dimension", "dimensions"], table_in()),
           step("plot", "scatter", {"layout": "overlay", "color_by_sample": True,
                                    "x_scale": "log", "y_scale": "log"}, ["point_size"],
                {"series": ["fields", "grains"]})])

JULIAN_DATE = ToolDef(
    "date_julian", "Add Julian date column", "Quality control",
    "Adds a number for each row's date, so dates can be used as a position or an axis (in a scatterplot, "
    "a fit, a profile): the Julian date, JD (days, with the fraction, from noon 1 January 4713 BC, so "
    "midnight is a half: 1 January 2021 is 2459215.5), the Modified Julian date (JD − 2400000.5, 59215.0), "
    "the whole Julian day number (2459216), the day of the year (1–366, what hydrology often calls the "
    "“Julian day”) or the decimal year (2021.0). Dates are read as written, in the proleptic Gregorian "
    "calendar, with no time zone applied; a row whose date cannot be read is left blank.",
    params=[ParamSpec("column", source="c.column", label="Date column"),
            ParamSpec("part", label="Add", page="Data",
                      field={"kind": "select", "default": "julian_date",
                             "choices": {k: DATE_PARTS[k] for k in (
                                 "julian_date", "modified_julian_date", "julian_day_number",
                                 "day_of_year", "decimal_year")}}),
            ParamSpec("day_first", source="c.day_first"),
            ParamSpec("name", source="c.name"),
            ParamSpec("apply", label="Add the column to the spreadsheet", default=True,
                      hint="Untick to see the result without changing the spreadsheet",
                      field={"kind": "checkbox", "default": True})],
    steps=[step("c", "date_part", {}, ["column", "part", "day_first", "name"], table_in())],
    sheet={"step": "c", "when": {"apply": True}})

GROUNDWATER = "Groundwater"

# ----------------------------------------------------------------- the isotope tools offered

DUAL_ISOTOPE = ToolDef(
    "iso_dual", "Dual isotope plot", ISO,
    "δ²H against δ¹⁸O for each sample, with the global meteoric water line (Craig 1961: "
    "δ²H = 8·δ¹⁸O + 10) or a line of your own beside it, to see how the samples sit against it: evaporated "
    "water falls to the right and below the line, with a slope under 8. To fit a line through your own "
    "samples, use the meteoric water line tool.",
    params=[ParamSpec("samples", source="grains.samples"),
            ParamSpec("x_dimension", source="grains.x_dimension", label="x (δ¹⁸O)"),
            ParamSpec("dimensions", source="grains.dimensions", label="y (δ²H)"),
            ParamSpec("reference", source="line.reference", default="gmwl", label="Reference line",
                      hint="Choose None for the points alone"),
            ParamSpec("ref_slope", source="line.ref_slope"),
            ParamSpec("ref_intercept", source="line.ref_intercept"),
            ParamSpec("layout", source="plot.layout"),
            ParamSpec("point_size", source="plot.point_size")],
    steps=[step("grains", "points", {}, ["samples", "x_dimension", "dimensions"], table_in()),
           step("line", "fit_line", {"scope": "none"}, ["reference", "ref_slope", "ref_intercept"],
                {"points": ["grains"]}, when={"reference": ["gmwl", "custom"]}),
           step("plot", "scatter", {"color_by_sample": True}, ["layout", "point_size"],
                {"series": ["grains", "line"]})])

ISOTOPE_BOXPLOT = ToolDef(
    "iso_boxplot", "Isotope boxplots by period", ISO,
    "A boxplot of an isotope (or any measurement) for each month, season, year or water year of a "
    "dated record, with a box per sample in each. Month of the year pools every January, every "
    "February…, which shows the seasonal cycle; each month keeps the years apart. Dates are read from "
    "the date column (2021-01-16, 1/16/2021, 16-Jan-2021…).",
    params=_from("box", "date", "dimensions", "samples", "period", "show_points", "show_mean",
                 "day_first", "water_year_start"),
    steps=[step("box", "period_boxplot", {}, ["date", "dimensions", "samples", "period", "show_points",
                                              "show_mean", "day_first", "water_year_start"], table_in())])

ISOTOPE_EXCURSIONS = ToolDef(
    "iso_excursions", "Isotope excursions", ISO,
    "An isotope record against depth, age or year with its baseline and a band about it, the points "
    "beyond the band marked, and a table of each excursion — a stretch of consecutive points on one side "
    "of the baseline — with where it starts, ends and peaks. The baseline is the whole record's median "
    "or mean, or a running median for a record that drifts; the scatter is a robust standard "
    "deviation. It assumes the background is most of the record.",
    params=_from("prof", "position", "dimensions", "samples", "orientation", "baseline", "window",
                 "threshold", "min_run", "day_first"),
    steps=[step("prof", "isotope_profile", {}, ["position", "dimensions", "samples", "orientation",
                                                "baseline", "window", "threshold", "min_run", "day_first"],
                table_in())])

# ------------------------------------------------------ the hydrology tools: flow, rain, both

_HYDROGRAPH_OPTIONS = ["date", "samples", "view", "smooth", "rain_at", "flow_units", "rain_units",
                       "day_first", "water_year_start"]

HYDROGRAPH_ONLY = ToolDef(
    "hy_flow", "Hydrograph", HYDRO,
    "Discharge through time, one chart per site. As the typical year it averages discharge by day of "
    "the water year and smooths it over the days you choose.",
    params=_from("h", "date", "samples", "flow", "view", "smooth", "flow_units", "day_first",
                 "water_year_start"),
    steps=[step("h", "hydrograph", {"use_flow": True, "use_rain": False},
                ["date", "samples", "flow", "view", "smooth", "flow_units", "day_first",
                 "water_year_start"], table_in())])

HYETOGRAPH_ONLY = ToolDef(
    "hy_rain", "Hyetograph", HYDRO,
    "Precipitation through time, hanging from the top of the chart as bars, one chart per site. As "
    "the typical year it totals precipitation by month and averages over the years. The column is an "
    "amount in each interval (mm per hour, per day, per month).",
    params=_from("h", "date", "samples", "rain", "view", "rain_at", "rain_units", "day_first",
                 "water_year_start"),
    steps=[step("h", "hydrograph", {"use_flow": False, "use_rain": True},
                ["date", "samples", "rain", "view", "rain_at", "rain_units", "day_first",
                 "water_year_start"], table_in())])

# ------------------------------------------------------------------------- groundwater

THIEM_DRAWDOWN = ToolDef(
    "gw_thiem", "Thiem drawdown (cone of depression and map)", GROUNDWATER,
    "Drawdown round a pumping well in a confined aquifer, steady flow (the Thiem equation). From the "
    "pumping rate, the aquifer's thickness, the radius its cone of depression reaches and either K or "
    "the drawdown measured in the well, it finds K and the transmissivity, the drawdown in any "
    "monitoring wells you list, a semilog plot of the cone of depression and a plan-view map of drawdown "
    "contours. Use the units chosen throughout. It reads no table. For a confined, homogeneous aquifer "
    "and a fully penetrating well; not for an unconfined aquifer with large drawdown, nor for flow that "
    "is still changing.",
    needs_table=False,
    params=_from("thiem", "units", "flow", "thickness", "radius", "well_radius", "solve", "drawdown_well",
                 "conductivity", "monitors", "interval"),
    steps=[step("thiem", "thiem", {}, ["units", "flow", "thickness", "radius", "well_radius", "solve",
                                       "drawdown_well", "conductivity", "monitors", "interval"], {}),
           step("cone", "scatter", {"layout": "overlay", "color_by_sample": True, "point_size": 10,
                                    "x_scale": "log", "y_reverse": True},
                [], {"series": ["thiem.cone", "thiem.profile_wells"]}),
           step("map", "scatter", {"layout": "overlay", "color_by_sample": True, "point_size": 10,
                                   "equal_scale": True},
                [], {"series": ["thiem.contours", "thiem.plan_wells"]}),
           step("summary", "table_view", {}, [], {"table": ["thiem.summary"]})])

BUILTIN_TOOLS = [FILTER_GRAINS, TRANSFORM_COLUMN, RATIO_COLUMN, JULIAN_DATE, VIEW_TABLE, DISTRIBUTIONS, DENSITY_CONTOURS, COMPARISON_MATRICES, MDS, SAMPLE_PCA,
                 MIXTURE, UNMIX_PC1, NMF_SOURCES, SCATTERPLOT, TERNARY, GRAIN_PCA,
                 CONVERT_OXYGEN, DEUTERIUM_EXCESS, ATOMIC_CN, LIPID_CORRECTION, TROPHIC_POSITION,
                 CARBONATE_TEMPERATURE, ISOTOPIC_NICHE, WATER_LINE, ISOTOPE_MIXING,
                 END_MEMBER_MIXING, END_MEMBER_SPLITTING,
                 GROUP_BY_DATE, REGROUP_SAMPLES, SAMPLE_SUMMARY, ISOTOPE_TIME_SERIES, HYDROGRAPH,
                 HYDROGRAPH_SEPARATION, HJULSTROM,
                 DUAL_ISOTOPE, ISOTOPE_BOXPLOT, ISOTOPE_EXCURSIONS, HYDROGRAPH_ONLY, HYETOGRAPH_ONLY,
                 THIEM_DRAWDOWN]

# What the menus offer is narrowed to what is used. Isotopes: the dual isotope plot, boxplots by
# period, a water line (local fit, global reference) and excursions by depth or time. Hydrology: the
# hydrograph, the hyetograph, both together, and the two end-member methods. Groundwater: the Thiem
# drawdown. The rest are kept, so that work saved with them still opens, and are simply not listed;
# remove a key from HIDDEN_TOOLS to offer it again. (The sediment toolboxes are not narrowed, and
# every block is still in the Add menu's building blocks.)
WATER_LINE.label = "Meteoric water line (local fit, global reference)"
for _tool in (WATER_LINE,):
    _tool.toolbox = ISO
for _tool in (END_MEMBER_MIXING, END_MEMBER_SPLITTING):
    _tool.toolbox = HYDRO          # the end-member methods are used for hydrology
END_MEMBER_MIXING.label = "End-member mixing (EMMA)"
END_MEMBER_SPLITTING.label = "End-member splitting (EMSA)"

HIDDEN_TOOLS = {
    # stable isotopes beyond the four wanted
    "iso_scale", "iso_difference", "iso_cn", "iso_lipid", "iso_trophic", "iso_temperature",
    "iso_niche", "iso_mixing",
    # hydrology beyond the hydrograph, hyetograph and end-member methods
    "hy_dates", "hy_regroup", "hy_summary", "hy_time_series", "hy_separation", "hy_hjulstrom",
}

# The order the offered tools are listed in within their toolboxes (any others follow, as written).
MENU_ORDER = ["iso_dual", "iso_boxplot", "iso_water_line", "iso_excursions",
              "hy_flow", "hy_rain", "hy_hydrograph", "iso_emma", "iso_emsa", "gw_thiem"]

# The order toolboxes are listed in; any others (a user's own) follow.
TOOLBOX_ORDER = ["Quality control", "Distributions", "Sample comparison",
                 "Provenance modelling", "Multivariate", "Stable isotopes", "Hydrology", "Groundwater"]
