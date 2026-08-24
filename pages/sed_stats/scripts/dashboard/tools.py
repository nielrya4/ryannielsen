"""Ribbon tools: a wizard in a modal that generates one output on demand."""
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
    LAYOUTS, METRICS, MDS_TYPES, MIXTURE_METRICS, MIXTURE_TRIALS, TOOLS, VIEWS,
)
from .dataset import detect_columns, sample_names
from .distributions import build_distribution
from .errors import error_box
from .matrices import build_matrix
from .mds_plot import build_mds
from .mixture import build_mixture

MODAL_STYLE = {"max-width": "840px", "width": "92vw", "min-width": "0"}


class Tool:
    """
    One ribbon entry.

    Owns its modal + wizard, reads the current spreadsheet when submitted, and
    hands each selected dimension to `build`. Several dimensions produce one
    tabbed output with a tab each.
    """

    def __init__(self, key, label, submit_text, option_rows, min_samples,
                 build, read_extra, get_rows, gallery, overlay, on_close=None,
                 sync_extra=None, validate_extra=None):
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

        self._title_input = Input("text", placeholder=f"e.g. {label} of size",
                                  style={"width": "260px"})
        self._samples = CheckboxGroup(empty_text="No samples in the spreadsheet")
        self._dimensions = CheckboxGroup(empty_text="No dimensions in the spreadsheet")
        self._bin_size = Input("number", placeholder="auto", style={"width": "90px"})

        self.wizard = self._make_wizard(submit_text, option_rows)
        self.modal = self._make_modal()

    # ------------------------------------------------------------- construction

    def _make_wizard(self, submit_text, option_rows):
        plural = "s" if self._min_samples != 1 else ""
        panels = [
            WizardPanel("Samples", Div(
                labeled("Output title", self._title_input,
                        "Optional; names the entry and its SVG file"),
                labeled("Samples", self._samples.element,
                        f"Choose at least {self._min_samples} sample{plural}"),
            ), f"Choose the samples to include in the {self.label.lower()}."),
            WizardPanel("Dimensions", Div(
                labeled("Dimensions", self._dimensions.element,
                        "Several dimensions produce one tabbed output, a tab each"),
            ), "Choose which dimensions of the sample set to graph."),
            WizardPanel("Options", Div(
                *option_rows,
                labeled("Bin size", self._bin_size,
                        "Numeric dimensions only; blank picks a round width automatically"),
            ), "Configure how the distributions are computed."),
        ]

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
        self._samples.set_options(names)
        self._dimensions.set_options(dimensions)
        if self._sync_extra:
            self._sync_extra(names)
        return self

    def _current_bin_size(self):
        try:
            size = float(self._bin_size.value)
            return size if size > 0 else None
        except ValueError:
            return None

    def read_options(self):
        opts = {
            "title": self._title_input.value.strip(),
            "samples": self._samples.values(),
            "dimensions": self._dimensions.values(),
            "bin_size": self._current_bin_size(),
        }
        opts.update(self._read_extra())
        return opts

    def _validation_error(self, opts):
        if len(opts["samples"]) < self._min_samples:
            plural = "s" if self._min_samples != 1 else ""
            return (f"{self.label} needs at least {self._min_samples} sample{plural}; "
                    f"{len(opts['samples'])} selected.")
        if not opts["dimensions"]:
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

        for dimension in opts["dimensions"]:
            try:
                contents.append(self._build(charts, rows, sample_col, dimension, opts))
            except Exception as e:
                contents.append(error_box(f"Could not build '{dimension}'", e))

        tabview = None
        if len(contents) == 1:
            body = contents[0]
        else:
            tabview = TabView(tabs=[
                TabItem(dimension, content)
                for dimension, content in zip(opts["dimensions"], contents)
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


def build_tools(get_rows, gallery, overlay, on_close=None):
    """Every ribbon tool, keyed the same way as the ribbon's buttons."""
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
        sync_extra=lambda names: set_select_options(sink, names,
                                                    empty_text="No samples"),
        validate_extra=validate_mixture,
        **shared,
    )
    return tools
