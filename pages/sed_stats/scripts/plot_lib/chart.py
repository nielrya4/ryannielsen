"""Plotly-backed chart macro.

Plotly renders cartesian plots as real SVG in the DOM, so vector export is
native rather than a rasterized canvas snapshot.
"""
import js

from antioch.elements import Div
from antioch.macros.js_library import JSLibraryMacro


class PlotlyChart(JSLibraryMacro):
    """
    Chart backed by plotly.js.

    Usage:
        chart = PlotlyChart(
            traces=[{"type": "bar", "x": ["a", "b"], "y": [1, 2], "name": "S1"}],
            layout={"title": {"text": "Counts"}},
        )
        DOM.add(chart.element)
        chart.download_svg("counts")
    """

    def __init__(self, traces=None, layout=None, config=None,
                 width=760, height=420, **kwargs):
        """
        Args:
            traces: List of plotly trace dicts
            layout: Plotly layout dict, merged over the defaults
            config: Plotly config dict, merged over the defaults
            width/height: Plot size in pixels
        """
        super().__init__(macro_type="plotly_chart", **kwargs)

        self._set_state(
            traces=traces or [],
            layout=layout or {},
            config=config or {},
            width=width,
            height=height,
        )

        self._init_macro()

    def _get_library_dependencies(self):
        return {
            'scripts': ['antioch/lib/vendor/plotly-basic.min.js'],
            'stylesheets': [],
        }

    def _get_library_global_name(self):
        return 'Plotly'

    def _create_elements(self):
        container = self._register_element(
            'container', self._create_container({"width": "100%"})
        )
        holder = self._register_element('holder', Div())
        holder.set_attribute("id", f"plotly_{self._id}")
        container.add(holder)
        return container

    def _build_layout(self):
        layout = {
            'width': self._get_state('width'),
            'height': self._get_state('height'),
            'margin': {'l': 60, 'r': 20, 't': 50, 'b': 50},
            'font': {'size': 12},
            'hovermode': 'closest',
            'showlegend': True,
        }
        layout.update(self._get_state('layout'))
        return layout

    def _build_config(self):
        config = {
            'displaylogo': False,
            'displayModeBar': True,  # always visible; hover-to-reveal is unusable on touch
            'responsive': False,
            # Makes the modebar's camera button emit SVG instead of PNG.
            'toImageButtonOptions': {'format': 'svg', 'filename': 'chart'},
        }
        config.update(self._get_state('config'))
        return config

    def _create_js_instance(self):
        # Plotly's API is keyed on the graph div itself, so that element is the
        # instance. newPlot returns a promise we don't need to await: every
        # later call goes through the same div.
        graph_div = self._get_element('holder')._dom_element
        js.Plotly.newPlot(
            graph_div,
            self._to_js(self._get_state('traces')),
            self._to_js(self._build_layout()),
            self._to_js(self._build_config()),
        )
        return graph_div

    def _cleanup_js_instance(self):
        if self.js_instance:
            js.Plotly.purge(self.js_instance)

    # ========== Public API ==========

    def update(self, traces=None, layout=None):
        """Re-render with new traces/layout via Plotly.react (diffed, not rebuilt)."""
        self.ensure_initialized()
        if traces is not None:
            self._set_state(traces=traces)
        if layout is not None:
            self._set_state(layout=layout)
        js.Plotly.react(
            self.js_instance,
            self._to_js(self._get_state('traces')),
            self._to_js(self._build_layout()),
            self._to_js(self._build_config()),
        )
        return self

    async def to_svg(self):
        """The plot's SVG markup, for callers that want to package it up."""
        self.ensure_initialized()
        data_uri = await js.Plotly.toImage(self.js_instance, self._to_js({
            'format': 'svg',
            'width': self._get_state('width'),
            'height': self._get_state('height'),
        }))
        # Plotly returns "data:image/svg+xml,<percent-encoded markup>"
        return js.decodeURIComponent(data_uri.split(",", 1)[1])

    def download_svg(self, filename="chart"):
        """Trigger a browser download of the plot as SVG."""
        self.ensure_initialized()
        js.Plotly.downloadImage(self.js_instance, self._to_js({
            'format': 'svg',
            'filename': filename,
            'width': self._get_state('width'),
            'height': self._get_state('height'),
        }))
        return self

    def resize(self):
        """Re-fit the plot to its container, after becoming visible again."""
        if self.is_initialized:
            js.Plotly.Plots.resize(self.js_instance)
        return self

    @property
    def is_ready(self):
        return self.is_initialized
