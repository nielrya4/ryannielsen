"""
Snake River watershed web map.

The six sampled source catchments above the Weiser confluence, colored by one of several
results, with the rivers and sample sites as overlays. Clicking a watershed opens its stats:
modelled contribution to the sink, polymer mix (against the sink's), land cover and stream
connectivity. The data come from export_web_map.py in the main project; the pieces live in the
`webmap` package and this module only assembles them.
"""
import js
from pyodide.ffi import create_proxy

from antioch import DOM
from antioch.elements import Div
from webmap import Sidebar, WatershedMap
from webmap import config as c

INITIAL = "basin"


def main():
    DOM.clear()
    DOM.title = "Snake River Microplastics"
    DOM.body.style.update(c.BODY_STYLE)

    sidebar = Sidebar(INITIAL)
    world = WatershedMap(INITIAL)
    sidebar.on_select = world.color_by
    app = Div(sidebar.element, Div(world.element, style=c.MAP_PANE_STYLE), style=c.APP_STYLE)
    DOM.add(app)

    # Inline styles have no media queries, so the layout follows the window width here.
    narrow = js.window.matchMedia(c.NARROW)

    def layout(*args):
        app.style.update(c.APP_NARROW if narrow.matches else c.APP_WIDE)
        sidebar.set_narrow(narrow.matches)

    layout()
    narrow.addEventListener("change", create_proxy(layout))


main()
