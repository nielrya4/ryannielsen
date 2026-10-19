"""Tools: a wizard in a modal that generates one output on demand."""
import asyncio

from antioch.dom import DOM
from antioch.elements import Div, Input, Option, Select
from antioch.event import when
from antioch.macros import Modal

from ui_lib import (
    CheckboxGroup, TabItem, TabView, Wizard, WizardPanel, labeled,
    set_select_options,
)

from .config import (
    BIVARIATE_METRICS, DEFAULT_GRID, DENSITY_METHODS, GRID_SIZES, LAYOUTS,
    DEFAULT_POINT_SIZE, GRAIN_WEIGHTINGS, METRICS, MDS_TYPES,
    MIXTURE_METRICS, MIXTURE_TRIALS, SCATTER_LAYOUTS, SCATTER_SIZES,
    SIGMA_LEVELS, TERNARY_TOTAL, TOOLS, VIEWS,
)
from .dataset import detect_columns, numeric_columns, sample_names
from .distributions import build_distribution
from .errors import error_box
from .matrices import build_matrix
from .mds_plot import build_mds
from .mixture import build_mixture
from .pca_axes import build_pca_axes
from .scatter import build_scatter
from .ternary_plot import build_ternary
from .bivariate_plot import build_bivariate
from .bivariate_matrix import build_bivariate_matrix
from .bivariate_mds import build_bivariate_mds
from .bivariate_mixture import build_bivariate_mixture

MODAL_STYLE = {"max-width": "840px", "width": "92vw", "min-width": "0"}


class Tool:
    """
    One entry in the toolbar.

    Owns its modal + wizard, reads the current spreadsheet when submitted, and
    hands each selected dimension to `build`. Several dimensions produce one
    tabbed output with a tab each.
    """

    # Shared numeric option rows, in display order. A tool can take a subset;
    # the bivariate tools drop bin size (they have a grid, not bins) and the
    # single bandwidth (they need one per axis).
    ALL_NUMERIC_ROWS = ("bin_size", "density", "sigma", "bandwidth")

    def __init__(self, key, label, submit_text, option_rows, min_samples,
                 build, read_extra, get_rows, gallery, overlay, on_close=None,
                 sync_extra=None, validate_extra=None,
                 numeric_rows=ALL_NUMERIC_ROWS,
                 dimension_hint="Several dimensions produce one tabbed output, "
                                "a tab each",
                 numeric_dimensions_only=False,
                 use_dimensions=True):
        self.key = key
        self.label = label
        self._min_samples = min_samples
        self._build = build
        self._read_extra = read_extra
        self._get_rows = get_rows
        self._gallery = gallery
        self._overlay = overlay
        self._on_close = on_close
        # Tools whose options depend on the data (a sink picker, say) refresh
        # them here; validate_extra reports a problem the wizard should show.
        self._sync_extra = sync_extra
        self._validate_extra = validate_extra
        self._numeric_rows = numeric_rows
        self._dimension_hint = dimension_hint
        # Density grids need two numeric axes, so those tools never offer a
        # categorical dimension rather than failing once it is submitted.
        self._numeric_dimensions_only = numeric_dimensions_only
        # A tool that names its dimensions some other way — a ternary plot
        # assigns three of them to named apexes — drops the panel entirely
        # rather than showing a checklist that means nothing.
        self._use_dimensions = use_dimensions

        self._title_input = Input("text", placeholder=f"e.g. {label} of size",
                                  style={"width": "260px"})
        self._samples = CheckboxGroup(empty_text="No samples in the spreadsheet")
        self._dimensions = CheckboxGroup(
            empty_text=("No numeric dimensions in the spreadsheet"
                        if numeric_dimensions_only
                        else "No dimensions in the spreadsheet"),
            on_change=lambda values: self._update_option_visibility(),
        )
        # Dimensions holding numbers. Binning, PDPs and KDEs mean nothing for
        # a categorical dimension, so their options are hidden for one.
        self._numeric_columns = set()
        self._bin_size = Input("number", placeholder="auto", style={"width": "90px"})
        self._density = _select(DENSITY_METHODS)
        self._sigma_in = _select(SIGMA_LEVELS)
        self._bandwidth = Input("number", placeholder="auto", style={"width": "90px"})

        self.wizard = self._make_wizard(submit_text, option_rows)
        self.modal = self._make_modal()

    # ------------------------------------------------------------- construction

    def _numeric_option_rows(self):
        """
        Option rows that only make sense for numeric dimensions.

        Kept as attributes so _update_option_visibility can show and hide them;
        a bin width or a KDE bandwidth over "quartz, feldspar, mica" is
        meaningless, and offering it invites a nonsense setting.
        """
        available = {
            "bin_size": labeled(
                "Bin size", self._bin_size,
                "Blank picks a round width automatically"),
            "density": labeled(
                "Density method", self._density,
                "How PDF and CDF curves are built; histograms always bin"),
            "sigma": labeled(
                "Uncertainty level", self._sigma_in,
                "For uncertainty columns that don't say; a '1s' or '2s' header "
                "overrides it"),
            "bandwidth": labeled(
                "KDE bandwidth", self._bandwidth,
                "Blank uses Silverman's rule on the pooled samples"),
        }
        self._rows = {key: available[key] for key in self._numeric_rows}
        self._density.on('change', lambda e: self._update_option_visibility())

        rows = list(self._rows.values())
        self._update_option_visibility()
        return rows

    def _update_option_visibility(self):
        """Show the numeric-only rows only when they apply to what's selected."""
        if not hasattr(self, '_rows'):
            return  # rows not built yet

        selected = self._dimensions.values()
        if selected:
            numeric = any(d in self._numeric_columns for d in selected)
        else:
            # Nothing chosen yet: go by whether the spreadsheet has any numbers.
            numeric = bool(self._numeric_columns)

        is_kde = self._density.value == "kde"
        visibility = {
            "bin_size": numeric,
            "density": numeric,
            "sigma": numeric and not is_kde,
            "bandwidth": numeric and is_kde,
        }
        for key, row in self._rows.items():
            row.style.display = "block" if visibility[key] else "none"

    def _make_wizard(self, submit_text, option_rows):
        plural = "s" if self._min_samples != 1 else ""
        dimension_panel = WizardPanel("Dimensions", Div(
            labeled("Dimensions", self._dimensions.element,
                    self._dimension_hint),
        ), "Choose which dimensions of the sample set to graph.")

        panels = [
            WizardPanel("Samples", Div(
                labeled("Output title", self._title_input,
                        "Optional; names the entry and its SVG file"),
                labeled("Samples", self._samples.element,
                        f"Choose at least {self._min_samples} sample{plural}"),
            ), f"Choose the samples to include in the {self.label.lower()}."),
            WizardPanel("Options", Div(
                *option_rows,
                *self._numeric_option_rows(),
            ), "Configure how the distributions are computed."),
        ]
        if self._use_dimensions:
            panels.insert(1, dimension_panel)

        # The modal supplies the title bar and the curtain, so the wizard is
        # built without its own header.
        wizard = Wizard(submit_text=submit_text, panels=panels)
        wizard.element.style.update({
            "margin-top": "0", "border": "none", "border-radius": "0",
        })

        @when(wizard.events.submit)
        def on_submit(sender, *args):
            self._submit()

        return wizard

    def _make_modal(self):
        modal = Modal(title=self.label, modal_style=MODAL_STYLE)
        modal.set_content(self.wizard.element)
        DOM.add(modal.element)

        @when(modal.events.close)
        def on_close(sender, *args):
            if self._on_close:
                self._on_close(self)

        return modal

    # ------------------------------------------------------------------- state

    def open(self):
        self.modal.open()
        return self

    def sync_options(self, rows):
        """Keep the sample/dimension choices in step with the spreadsheet."""
        sample_col, _, dimensions = detect_columns(rows)
        names = sample_names(rows, sample_col)
        self._numeric_columns = numeric_columns(rows, dimensions)
        if self._numeric_dimensions_only:
            dimensions = [d for d in dimensions if d in self._numeric_columns]
        self._samples.set_options(names)
        self._dimensions.set_options(dimensions)
        self._update_option_visibility()
        if self._sync_extra:
            self._sync_extra(names, dimensions, self._numeric_columns)
        return self

    def _current_bin_size(self):
        try:
            size = float(self._bin_size.value)
            return size if size > 0 else None
        except ValueError:
            return None

    def _current_bandwidth(self):
        try:
            width = float(self._bandwidth.value)
            return width if width > 0 else None
        except ValueError:
            return None

    def read_options(self):
        opts = {
            "title": self._title_input.value.strip(),
            "samples": self._samples.values(),
            "dimensions": self._dimensions.values() if self._use_dimensions else [],
            "bin_size": self._current_bin_size(),
            "density": self._density.value,
            "sigma_in": float(self._sigma_in.value or 1),
            "bandwidth": self._current_bandwidth(),
        }
        opts.update(self._read_extra())
        return opts

    def _validation_error(self, opts):
        if len(opts["samples"]) < self._min_samples:
            plural = "s" if self._min_samples != 1 else ""
            return (f"{self.label} needs at least {self._min_samples} sample{plural}; "
                    f"{len(opts['samples'])} selected.")
        if self._use_dimensions and not opts["dimensions"]:
            return "Select at least one dimension."
        if self._validate_extra:
            return self._validate_extra(opts)
        return None

    # ---------------------------------------------------------------- generation

    def _submit(self):
        opts = self.read_options()
        problem = self._validation_error(opts)
        if problem:
            self.wizard.set_status(problem)
            return

        self.wizard.set_status("")
        self.modal.close()
        asyncio.ensure_future(self._run(opts))

    async def _run(self, opts):
        # Building is synchronous and can take seconds (MDS especially), which
        # freezes the UI thread — so the curtain goes up first and
        # LoadingOverlay.run waits for it to paint before starting.
        try:
            charts = await self._overlay.run(
                lambda: self._generate(opts), f"Building {self.label.lower()}…"
            )
        except Exception as e:
            # ensure_future would otherwise swallow this into a console the
            # user can't reach on a phone.
            self._gallery.add(opts["title"] or self.label,
                              error_box(f"{self.label} failed", e), [])
            return
        # Sized while the gallery was behind the curtain; re-fit now.
        for _, chart in charts:
            chart.resize()

    def _generate(self, opts):
        rows = self._get_rows()
        sample_col, _, _ = detect_columns(rows)
        charts = []
        contents = []

        # Three shapes of output. A tool that names its dimensions elsewhere
        # (ternary picks three apexes) builds once and ignores the target; a
        # combining tool takes the whole list at once; everything else gets one
        # build, and so one tab, per dimension.
        if not self._use_dimensions:
            targets, titles = [None], []
        elif opts.get("combine_dimensions"):
            targets, titles = [opts["dimensions"]], []
        else:
            targets, titles = list(opts["dimensions"]), list(opts["dimensions"])

        for target in targets:
            label = f"'{target}'" if titles else f"the {self.label.lower()}"
            try:
                contents.append(self._build(charts, rows, sample_col, target, opts))
            except Exception as e:
                contents.append(error_box(f"Could not build {label}", e))

        tabview = None
        if len(contents) == 1:
            body = contents[0]
        else:
            tabview = TabView(tabs=[
                TabItem(title, content)
                for title, content in zip(titles, contents)
            ])
            body = tabview.element

            @when(tabview.events.change)
            def on_dimension_tab(sender, *args):
                # Plots sized while their tab was hidden need a re-fit
                for _, chart in charts:
                    chart.resize()

        self._gallery.add(opts["title"] or self.label, body, charts, tabview)
        return charts


def _select(choices, label_of=lambda v: v):
    return Select(*[Option(label_of(v), value=k) for k, v in choices.items()])


def build_tools(get_rows, gallery, overlay, on_close=None, set_rows=None):
    """Every tool, keyed the way dashboard.config.TOOL_MENU refers to them."""
    shared = {"get_rows": get_rows, "gallery": gallery,
              "overlay": overlay, "on_close": on_close}
    tools = {}

    # Distributions
    view = _select(VIEWS, lambda v: v["label"])
    layout = _select(LAYOUTS)
    tools["distributions"] = Tool(
        "distributions", TOOLS["distributions"], "Create distribution plots",
        option_rows=[
            labeled("View", view, "Histogram counts, or normalized PDF / CDF"),
            labeled("Layout", layout,
                    "Overlay samples on one plot, or stack one per sample"),
        ],
        min_samples=1,
        build=build_distribution,
        read_extra=lambda: {"view": view.value, "layout": layout.value},
        **shared,
    )

    # Comparison matrices
    matrix_metric = _select(METRICS, lambda m: m["label"])
    tools["matrix"] = Tool(
        "matrix", TOOLS["matrix"], "Create comparison matrices",
        option_rows=[
            labeled("Comparison metric", matrix_metric,
                    "Statistic computed for every pair of samples"),
        ],
        min_samples=2,
        build=build_matrix,
        read_extra=lambda: {"metric": matrix_metric.value},
        **shared,
    )

    # MDS
    mds_metric = _select(METRICS, lambda m: m["label"])
    mds_type = _select(MDS_TYPES)
    shepard = Input("checkbox")
    tools["mds"] = Tool(
        "mds", TOOLS["mds"], "Create MDS plots",
        option_rows=[
            labeled("Comparison metric", mds_metric,
                    "Used to build the dissimilarity matrix"),
            labeled("MDS type", mds_type,
                    "Non-metric preserves rank order; metric preserves distances"),
            labeled("Shepard plot", shepard,
                    "Diagnostic comparing dissimilarities to MDS distances"),
        ],
        min_samples=3,
        build=build_mds,
        read_extra=lambda: {
            "metric": mds_metric.value,
            "mds_type": mds_type.value,
            "shepard": shepard._dom_element.checked,
        },
        **shared,
    )

    # Mixture model
    sink = Select()
    mixture_metric = _select(MIXTURE_METRICS, lambda m: m["label"])
    trials = Select(*[Option(f"{n:,}", value=str(n)) for n in MIXTURE_TRIALS])
    trials.value = str(MIXTURE_TRIALS[2])

    def validate_mixture(opts):
        if not opts["sink"]:
            return "Choose a sink sample."
        if opts["sink"] not in opts["samples"]:
            return f"The sink '{opts['sink']}' is not among the selected samples."
        # The sink is one of the selected samples, so unmixing it needs two
        # more alongside it.
        if len(opts["samples"]) < 3:
            return "Select the sink plus at least two source samples."
        return None

    tools["mixture"] = Tool(
        "mixture", TOOLS["mixture"], "Create mixture model",
        option_rows=[
            labeled("Sink sample", sink,
                    "The mixed sample; every other selected sample is a source"),
            labeled("Comparison metric", mixture_metric,
                    "Scores each trial's modelled curve against the sink"),
            labeled("Trials", trials,
                    "Random source configurations to try; more is slower but steadier"),
        ],
        min_samples=3,
        build=build_mixture,
        read_extra=lambda: {
            "sink": sink.value,
            "metric": mixture_metric.value,
            "trials": int(trials.value),
        },
        sync_extra=lambda names, dimensions, numeric: set_select_options(
            sink, names, empty_text="No samples"),
        validate_extra=validate_mixture,
        **shared,
    )

    # Scatterplot — the raw grains, not a distribution of them.
    scatter_x = Select()
    scatter_layout = _select(SCATTER_LAYOUTS)
    scatter_color = Input("checkbox")
    scatter_color._dom_element.checked = True
    scatter_size = _select(SCATTER_SIZES)
    scatter_size.value = DEFAULT_POINT_SIZE

    def validate_scatter(opts):
        if not opts.get("x_dimension"):
            return "Choose an x dimension."
        if all(d == opts["x_dimension"] for d in opts["dimensions"]):
            return ("The x dimension is the only one checked; choose a "
                    "different y dimension.")
        return None

    tools["scatter"] = Tool(
        "scatter", TOOLS["scatter"], "Create scatterplots",
        option_rows=[
            labeled("X dimension", scatter_x,
                    "Plotted against each dimension checked on the previous step"),
            labeled("Colour by sample", scatter_color,
                    "Each sample gets its own colour and marker shape"),
            labeled("Layout", scatter_layout,
                    "Overlay every sample, or give each its own panel on "
                    "shared axes"),
            labeled("Point size", scatter_size,
                    "Smaller reads better where grains pile up"),
        ],
        min_samples=1,
        build=build_scatter,
        read_extra=lambda: {
            "x_dimension": scatter_x.value,
            "layout": scatter_layout.value,
            "color_by_sample": scatter_color._dom_element.checked,
            "point_size": int(scatter_size.value or DEFAULT_POINT_SIZE),
        },
        sync_extra=lambda names, dimensions, numeric: set_select_options(
            scatter_x, [d for d in dimensions if d in numeric],
            empty_text="No numeric dimensions"),
        validate_extra=validate_scatter,
        # A scatter draws the measurements themselves; there is nothing to bin,
        # smooth or assign an uncertainty to.
        numeric_rows=(),
        numeric_dimensions_only=True,
        dimension_hint="Each becomes the y axis against the x dimension below",
        **shared,
    )

    # Ternary — three parts of a whole, one point per grain.
    apex_a, apex_b, apex_c = Select(), Select(), Select()
    ternary_color = Input("checkbox")
    ternary_color._dom_element.checked = True
    ternary_centroids = Input("checkbox")
    ternary_size = _select(SCATTER_SIZES)
    ternary_size.value = DEFAULT_POINT_SIZE

    def validate_ternary(opts):
        apexes = [opts.get("apex_a"), opts.get("apex_b"), opts.get("apex_c")]
        if not all(apexes):
            return "Choose all three apex dimensions."
        if len(set(apexes)) < 3:
            return "The three apexes must be different dimensions."
        return None

    def sync_ternary(names, dimensions, numeric):
        # Only numeric columns can be a part of a whole.
        usable = [d for d in dimensions if d in numeric]
        for select in (apex_a, apex_b, apex_c):
            set_select_options(select, usable, empty_text="No numeric dimensions")
        # Open on three different columns rather than three copies of the
        # first, so the plot is valid before anything is touched.
        for select, value in zip((apex_a, apex_b, apex_c), usable[:3]):
            if not select.value or select.value not in usable:
                select.value = value

    tools["ternary"] = Tool(
        "ternary", TOOLS["ternary"], "Create ternary plot",
        option_rows=[
            labeled("Top apex", apex_a, "The component plotted at the peak"),
            labeled("Lower-left apex", apex_b, ""),
            labeled("Lower-right apex", apex_c, ""),
            labeled("Colour by sample", ternary_color,
                    "Each sample gets its own colour and marker shape"),
            labeled("Mark sample means", ternary_centroids,
                    "A star at each sample's mean composition, with a table"),
            labeled("Point size", ternary_size,
                    "Smaller reads better where grains pile up"),
        ],
        min_samples=1,
        build=build_ternary,
        read_extra=lambda: {
            "apex_a": apex_a.value,
            "apex_b": apex_b.value,
            "apex_c": apex_c.value,
            "color_by_sample": ternary_color._dom_element.checked,
            "show_centroids": ternary_centroids._dom_element.checked,
            "point_size": int(ternary_size.value or DEFAULT_POINT_SIZE),
        },
        sync_extra=sync_ternary,
        validate_extra=validate_ternary,
        # Each grain is closed to a constant sum; there is nothing to bin or
        # smooth, and the three apexes replace the dimension checklist.
        numeric_rows=(),
        use_dimensions=False,
        **shared,
    )

    # PCA axes — reduces many variables to PC1/PC2 per grain and writes them
    # back as spreadsheet columns for the other tools to consume.
    axes_weighting = _select(GRAIN_WEIGHTINGS)
    axes_scree = Input("checkbox")

    def validate_axes(opts):
        usable = [d for d in opts["dimensions"] if d not in ("PC1", "PC2")]
        if len(usable) < 2:
            return "Choose at least two variables to reduce."
        return None

    tools["pca"] = Tool(
        "pca", TOOLS["pca"], "Add PC1 and PC2 columns",
        option_rows=[
            labeled("Weighting", axes_weighting,
                    "Stops a sample with many analyses from setting the axis "
                    "for everyone"),
            labeled("Scree plot", axes_scree,
                    "Shows how much is lost by keeping only two axes"),
        ],
        min_samples=1,
        build=lambda charts, rows, sample_col, dims, opts: build_pca_axes(
            charts, rows, sample_col, dims, opts, set_rows=set_rows),
        read_extra=lambda: {
            "grain_weighting": axes_weighting.value,
            "scree": axes_scree._dom_element.checked,
            # Every chosen variable goes into one fit, so there is one output.
            "combine_dimensions": True,
        },
        validate_extra=validate_axes,
        numeric_rows=(),
        numeric_dimensions_only=True,
        dimension_hint="The variables to reduce; all go into one fit",
        **shared,
    )

    _add_bivariate_tools(tools, shared)
    return tools


def _add_bivariate_tools(tools, shared):
    """
    The three tools built on 2-D density grids.

    Each pairs one x dimension against every checked dimension, so the
    per-dimension tab loop still applies: a tab per y variable, all against the
    same x. That matches how paired data is actually read — age against Hf,
    against Ti, against Th/U.
    """
    # Bin size means nothing on a grid, and one bandwidth cannot cover two axes.
    numeric_rows = ("density", "sigma")
    dimension_hint = "Each becomes the y axis against the x dimension below"

    def axis_controls():
        """An x-dimension picker plus its own per-axis bandwidths and grid."""
        x_dimension = Select()
        grid = _select(GRID_SIZES)
        grid.value = DEFAULT_GRID
        x_bandwidth = Input("number", placeholder="auto", style={"width": "90px"})
        y_bandwidth = Input("number", placeholder="auto", style={"width": "90px"})
        return x_dimension, grid, x_bandwidth, y_bandwidth

    def axis_rows(x_dimension, grid, x_bandwidth, y_bandwidth):
        return [
            labeled("X dimension", x_dimension,
                    "Plotted against each dimension checked on the previous step"),
            labeled("Grid resolution", grid,
                    "Points per axis; cost grows with the square"),
            labeled("X bandwidth", x_bandwidth,
                    "Blank uses Silverman's rule; ignored when uncertainties are used"),
            labeled("Y bandwidth", y_bandwidth,
                    "Blank uses Silverman's rule; ignored when uncertainties are used"),
        ]

    def axis_options(x_dimension, grid, x_bandwidth, y_bandwidth):
        return {
            "x_dimension": x_dimension.value,
            "grid": int(grid.value or DEFAULT_GRID),
            "x_bandwidth": _positive(x_bandwidth.value),
            "y_bandwidth": _positive(y_bandwidth.value),
        }

    def sync_axis(x_dimension):
        def sync(names, dimensions, numeric):
            # A density grid needs two numeric axes, so a categorical column is
            # not a candidate for x.
            set_select_options(x_dimension, [d for d in dimensions if d in numeric],
                               empty_text="No numeric dimensions")
        return sync

    def validate_axis(x_dimension):
        def validate(opts):
            if not opts.get("x_dimension"):
                return "Choose an x dimension."
            if all(d == opts["x_dimension"] for d in opts["dimensions"]):
                return ("The x dimension is the only one checked; choose a "
                        "different y dimension.")
            return None
        return validate

    # Bivariate density
    x_dim, grid, x_bw, y_bw = axis_controls()
    show_points = Input("checkbox")
    tools["bivariate"] = Tool(
        "bivariate", TOOLS["bivariate"], "Create density plots",
        option_rows=axis_rows(x_dim, grid, x_bw, y_bw) + [
            labeled("Overlay grains", show_points,
                    "Draw the raw measurements over the density"),
        ],
        min_samples=1,
        build=build_bivariate,
        read_extra=lambda: {
            **axis_options(x_dim, grid, x_bw, y_bw),
            "show_points": show_points._dom_element.checked,
        },
        sync_extra=sync_axis(x_dim),
        validate_extra=validate_axis(x_dim),
        numeric_rows=numeric_rows,
        dimension_hint=dimension_hint,
        numeric_dimensions_only=True,
        **shared,
    )

    # Bivariate comparison matrices
    matrix_x, matrix_grid, matrix_x_bw, matrix_y_bw = axis_controls()
    matrix_metric = _select(BIVARIATE_METRICS, lambda m: m["label"])
    tools["bivariate_matrix"] = Tool(
        "bivariate_matrix", TOOLS["bivariate_matrix"], "Create comparison matrices",
        option_rows=axis_rows(matrix_x, matrix_grid, matrix_x_bw, matrix_y_bw) + [
            labeled("Comparison metric", matrix_metric,
                    "Two-dimensional measure computed for every pair of samples"),
        ],
        min_samples=2,
        build=build_bivariate_matrix,
        read_extra=lambda: {
            **axis_options(matrix_x, matrix_grid, matrix_x_bw, matrix_y_bw),
            "metric": matrix_metric.value,
        },
        sync_extra=sync_axis(matrix_x),
        validate_extra=validate_axis(matrix_x),
        numeric_rows=numeric_rows,
        dimension_hint=dimension_hint,
        numeric_dimensions_only=True,
        **shared,
    )

    # Bivariate MDS
    mds_x, mds_grid, mds_x_bw, mds_y_bw = axis_controls()
    mds_metric = _select(BIVARIATE_METRICS, lambda m: m["label"])
    mds_type = _select(MDS_TYPES)
    shepard = Input("checkbox")
    tools["bivariate_mds"] = Tool(
        "bivariate_mds", TOOLS["bivariate_mds"], "Create MDS plots",
        option_rows=axis_rows(mds_x, mds_grid, mds_x_bw, mds_y_bw) + [
            labeled("Comparison metric", mds_metric,
                    "Used to build the 2D dissimilarity matrix"),
            labeled("MDS type", mds_type,
                    "Non-metric preserves rank order; metric preserves distances"),
            labeled("Shepard plot", shepard,
                    "Diagnostic comparing dissimilarities to MDS distances"),
        ],
        min_samples=3,
        build=build_bivariate_mds,
        read_extra=lambda: {
            **axis_options(mds_x, mds_grid, mds_x_bw, mds_y_bw),
            "metric": mds_metric.value,
            "mds_type": mds_type.value,
            "shepard": shepard._dom_element.checked,
        },
        sync_extra=sync_axis(mds_x),
        validate_extra=validate_axis(mds_x),
        numeric_rows=numeric_rows,
        dimension_hint=dimension_hint,
        numeric_dimensions_only=True,
        **shared,
    )

    # Bivariate mixture model
    mix_x, mix_grid, mix_x_bw, mix_y_bw = axis_controls()
    mix_sink = Select()
    mix_metric = _select(MIXTURE_METRICS, lambda m: m["label"])
    mix_trials = Select(*[Option(f"{n:,}", value=str(n)) for n in MIXTURE_TRIALS])
    mix_trials.value = str(MIXTURE_TRIALS[2])

    def sync_mixture(names, dimensions, numeric):
        set_select_options(mix_x, [d for d in dimensions if d in numeric],
                           empty_text="No numeric dimensions")
        set_select_options(mix_sink, names, empty_text="No samples")

    def validate_mixture_2d(opts):
        problem = validate_axis(mix_x)(opts)
        if problem:
            return problem
        if not opts.get("sink"):
            return "Choose a sink sample."
        if opts["sink"] not in opts["samples"]:
            return f"The sink '{opts['sink']}' is not among the selected samples."
        if len(opts["samples"]) < 3:
            return "Select the sink plus at least two source samples."
        return None

    tools["bivariate_mixture"] = Tool(
        "bivariate_mixture", TOOLS["bivariate_mixture"], "Create mixture model",
        option_rows=axis_rows(mix_x, mix_grid, mix_x_bw, mix_y_bw) + [
            labeled("Sink sample", mix_sink,
                    "The mixed sample; every other selected sample is a source"),
            labeled("Comparison metric", mix_metric,
                    "Scores each trial's modelled density against the sink"),
            labeled("Trials", mix_trials,
                    "Random source configurations to try"),
        ],
        min_samples=3,
        build=build_bivariate_mixture,
        read_extra=lambda: {
            **axis_options(mix_x, mix_grid, mix_x_bw, mix_y_bw),
            "sink": mix_sink.value,
            "metric": mix_metric.value,
            "trials": int(mix_trials.value),
        },
        sync_extra=sync_mixture,
        validate_extra=validate_mixture_2d,
        numeric_rows=numeric_rows,
        dimension_hint=dimension_hint,
        numeric_dimensions_only=True,
        **shared,
    )


def _positive(value):
    """A positive float from a number input, or None when blank or invalid."""
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if number > 0 else None
