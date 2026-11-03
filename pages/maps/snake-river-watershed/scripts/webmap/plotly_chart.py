"""Plotly-backed chart macro, as in sed_stats' plot_lib.

Uses the `basic` bundle (bar, pie, scatter): the popups only draw bars. Built lazily
(lazy_init): a popup's content is only attached to the page when it opens, and Plotly needs its
div in the document to lay out, so the map calls ensure_initialized() then.
"""
import js
from antioch.elements import Div
from antioch.macros.js_library import JSLibraryMacro


class PlotlyChart(JSLibraryMacro):
    """
    Usage:
        chart = PlotlyChart(traces=[{"type": "bar", "x": ["a"], "y": [1]}], width=300,
                            height=220)
        parent.add(chart.element)
        chart.ensure_initialized()  # once chart.element is in the document
    """

    def __init__(self, traces=None, layout=None, config=None, width=300, height=220, **kwargs):
        super().__init__(macro_type="plotly_chart", lazy_init=True, **kwargs)
        self._set_state(traces=traces or [], layout=layout or {}, config=config or {},
                        width=width, height=height)
        self._init_macro()

    def _get_library_dependencies(self):
        return {"scripts": ["antioch/lib/vendor/plotly-basic.min.js"], "stylesheets": []}

    def _get_library_global_name(self):
        return "Plotly"

    def _create_elements(self):
        # Sized up front so the popup doesn't change size when the plot draws.
        size = {"width": f"{self._get_state('width')}px",
                "height": f"{self._get_state('height')}px"}
        container = self._register_element("container", self._create_container(
            {**size, "display": "block"}))
        holder = self._register_element("holder", Div(style=size))
        holder.set_attribute("id", f"plotly_{self._id}")
        container.add(holder)
        return container

    def _build_layout(self):
        layout = {
            "width": self._get_state("width"),
            "height": self._get_state("height"),
            "margin": {"l": 40, "r": 8, "t": 8, "b": 60},
            "font": {"size": 11},
            "hovermode": "closest",
            "paper_bgcolor": "rgba(0,0,0,0)",
            "plot_bgcolor": "rgba(0,0,0,0)",
        }
        layout.update(self._get_state("layout"))
        return layout

    def _build_config(self):
        config = {"displaylogo": False, "displayModeBar": False, "responsive": False}
        config.update(self._get_state("config"))
        return config

    def _create_js_instance(self):
        # Plotly's API is keyed on the graph div itself, so that element is the instance.
        graph_div = self._get_element("holder")._dom_element
        js.Plotly.newPlot(graph_div, self._to_js(self._get_state("traces")),
                          self._to_js(self._build_layout()), self._to_js(self._build_config()))
        return graph_div

    def _cleanup_js_instance(self):
        if self.js_instance:
            js.Plotly.purge(self.js_instance)
