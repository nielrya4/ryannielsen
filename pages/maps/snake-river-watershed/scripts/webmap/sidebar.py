"""The sidebar: title, the coloring choices, and the chosen coloring's description and legend."""
from antioch.elements import Div, H1, H2, Input, Label, P, Span
from antioch.event import when

from . import config as c
from .data import CONFIG, LAYERS, MODEL
from .ternary_key import ternary_key
from .wheel_key import wheel_key


class Sidebar:
    """
    Attributes:
        element   - the sidebar's root Div
        on_select - called with a layer id when the viewer picks a coloring
    """

    def __init__(self, initial):
        self.on_select = None
        self._current = initial
        self._choices = {}
        self._description = P("", style=c.DESCRIPTION_STYLE)
        self._legend = Div()
        for layer in CONFIG["layers"]:
            self._choices[layer["id"]] = self._choice(layer)
        self.element = Div(
            H1("Microplastics in the Snake River Watershed", style=c.TITLE_STYLE),
            P("I sampled 6 watersheds and the area downstream of them "
              "to determine which watersheds contributed the most microplastics "
              "to the main stem of the Snake.", style=c.LEDE_STYLE),
            H2("Watershed Attributes:", style=c.HEADING_STYLE),
            *self._choices.values(),
            self._description,
            self._legend,
            H2("Information and References:", style=c.HEADING_STYLE),
            P(f"Mixture model: polymer-type unmixing, {MODEL['metric']} "
              f"{MODEL['best_score']:.3f}, optimised best fit with bootstrap ranges. Land cover: "
              "ESA WorldCover 2021. Streams: NHDPlus V2 and high-resolution NHD canals; flow "
              "permanence: USGS PROSPER. Watersheds: MERIT-Hydro.", style=c.FOOTNOTE_STYLE),
            style=c.SIDEBAR_STYLE,
        )
        self.show(initial)

    def _choice(self, layer):
        radio = Input("radio", name="coloring", value=layer["id"], style=c.RADIO_STYLE)
        if layer["id"] == self._current:
            radio.set_attribute("checked", "checked")
        label = Label(radio, Span(layer["title"]), style=c.CHOICE_STYLE)

        @when(radio.events.change)
        def on_change(sender, *args):
            self.show(layer["id"])
            if self.on_select:
                self.on_select(layer["id"])

        @when(label.events.mouseenter)
        def on_enter(sender, *args):
            if layer["id"] != self._current:
                label.style.update({"background-color": c.HOVER})

        @when(label.events.mouseleave)
        def on_leave(sender, *args):
            if layer["id"] != self._current:
                label.style.update(c.CHOICE_IDLE)

        return label

    def show(self, layer_id):
        """Mark layer_id as chosen and show its description and legend."""
        self._current = layer_id
        for lid, label in self._choices.items():
            label.style.update(c.CHOICE_ACTIVE if lid == layer_id else c.CHOICE_IDLE)
        layer = LAYERS[layer_id]
        self._description.set_text(layer["description"])
        self._legend.clear()
        if "gradient" in layer:
            self._legend.add(*_gradient(layer["gradient"]))
        if "ternary" in layer:
            self._legend.add(ternary_key(layer["ternary"]))
        if "wheel" in layer:
            self._legend.add(wheel_key(layer["wheel"]))
        self._legend.add(*[
            Div(Span(style={**c.SWATCH_STYLE, **(c.DOT_SWATCH if item.get("marker") == "dot"
                                                 else {}),
                            "background-color": item["color"]}),
                Span(item["label"]), style=c.LEGEND_ROW_STYLE)
            for item in layer["legend"]])

    def set_narrow(self, narrow):
        self.element.style.update(c.SIDEBAR_NARROW if narrow else c.SIDEBAR_WIDE)


def _gradient(spec):
    """A horizontal color bar with labelled ticks underneath (at: 0-1 along the bar)."""
    bar = Div(style={**c.GRADIENT_STYLE,
                     "background": f"linear-gradient(to right, {', '.join(spec['stops'])})"})
    ticks = Div(style=c.TICKS_STYLE)
    for tick in spec["ticks"]:
        left = f"{100 * tick['at']:.1f}%"
        ticks.add(Div(style={**c.TICK_STYLE, "left": left}),
                  Span(tick["label"], style={**c.TICK_LABEL_STYLE, "left": left}))
    return [bar, ticks]
