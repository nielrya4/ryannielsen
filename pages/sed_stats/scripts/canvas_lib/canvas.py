"""
The canvas widget: nodes to drag, ports to wire together, and a picker to add more.

Interaction is all pointer events on the root element, which captures the
pointer for the length of a drag so it keeps reporting when the mouse leaves:

    drag a node's header or body    move it
    drag from an output port        draw a wire; compatible input ports light
                                    up, and letting go on one connects it
    drag from a connected input     pick that wire up: drop it on another port
                                    to move it, or on empty canvas to remove it
    drop a new wire on empty canvas offer the blocks that can read it; the one
                                    you pick appears there, already connected
    Ctrl + wheel, or the buttons    zoom
    drag on empty canvas            draw a rectangle: the blocks it touches are selected (hold
      (or double-click and drag)      Ctrl or Shift to add to the selection); drag any selected
                                      block to move them all, Delete to remove them
    Ctrl + click a block            add it to the selection, or take it out
    Shift + click a block           select every block on the way from the one last clicked to
                                    this one (Ctrl + Shift adds that to what is selected)
    click a wire                    select it; its × removes it
    double-click empty canvas, or   open the picker (search, and the tools and blocks by kind): the
      "Add…" in the right-click       one you choose appears where you opened it. The owner can
      menu                            open it elsewhere too (`open_picker`)
    double-click a node             edit it
    click a node's Output button    expand what it made
    right-click a node, a wire or   a menu of what can be done to it, which the owner
      the empty canvas              supplies (`menu_for`), so the boxes stay plain
    Delete / Backspace              remove the selected node or wire
    Escape                          close a menu

Nothing is changed here. Each edit is reported through a callback and the owner
describes the result again with `show`, which redraws everything — except during
a drag, when only the moving node and its wires are updated.
"""
from dataclasses import dataclass, field

import js
from pyodide.ffi import create_proxy

from . import layout as geometry

SVG_NS = "http://www.w3.org/2000/svg"
_CSS_ID = "canvas-lib-css"
_CSS = """
.cv-root { position: relative; display: flex; border: 1px solid #d8dee4; border-radius: 6px;
  background: #fff; height: max(560px, calc(100vh - 250px)); outline: none; user-select: none;
  -webkit-user-select: none; touch-action: none; }
.cv-picker { position: fixed; z-index: 10002; width: 300px; max-height: min(520px, 80vh);
  overflow-y: auto; background: #f7f9fb; border: 1px solid #cfd6dd; border-radius: 6px;
  box-shadow: 0 6px 22px rgba(0,0,0,.25); padding: 10px 10px 14px; box-sizing: border-box;
  display: none; }
.cv-viewport { flex: 1; overflow: auto; position: relative; background: #fbfcfd; }
.cv-surface { position: relative;
  background-image: radial-gradient(#d5dbe1 1px, transparent 1px); background-size: %(grid)spx %(grid)spx; }
/* The outline is a ring drawn outside the box, not a border: nothing inside the node can cover it
   (the output area sits flush with the bottom edge), and it adds no width, so the pins keep their place. */
.cv-node { position: absolute; width: %(w)spx; box-sizing: border-box; background: #fff;
  border-radius: 8px; box-shadow: 0 0 0 2px #8b98a5, 0 2px 8px rgba(0,0,0,.18); }
.cv-node.cv-selected { box-shadow: 0 0 0 3px #3498db, 0 0 0 6px rgba(52,152,219,.28), 0 2px 8px rgba(0,0,0,.18) !important; }
.cv-head { height: %(head)spx; box-sizing: border-box; display: flex; align-items: center;
  gap: 6px; padding: 0 8px 0 10px; cursor: grab; border-radius: 8px 8px 0 0;
  border-bottom: 1px solid #dfe5ea; background: #f3f6f9; }
.cv-title { font-weight: 600; font-size: 13px; flex: 1; overflow: hidden;
  text-overflow: ellipsis; white-space: nowrap; }
.cv-badge { font-size: 10.5px; color: #fff; border-radius: 3px; padding: 1px 6px; flex: none; }
.cv-body { height: %(body)spx; box-sizing: border-box; padding: 6px 10px; cursor: grab; }
.cv-sub { font-size: 11.5px; color: #5d6b78; overflow: hidden; line-height: 1.3;
  max-height: 30px; display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; }
.cv-status { font-size: 11px; margin-top: 2px; overflow: hidden; text-overflow: ellipsis;
  white-space: nowrap; }
.cv-port { position: relative; height: %(port)spx; box-sizing: border-box; padding-left: 14px;
  font-size: 11.5px; line-height: %(port)spx; color: #44505c; }
.cv-pin { position: absolute; width: %(d)spx; height: %(d)spx; border-radius: 50%%;
  box-sizing: border-box; border: 2px solid #fff; box-shadow: 0 0 0 1.5px #8b98a5;
  cursor: crosshair; }
.cv-pin.cv-ok { box-shadow: 0 0 0 3px #2ecc71; transform: scale(1.3); }
.cv-pin.cv-no { opacity: .25; }
.cv-thumb { height: %(thumb)spx; box-sizing: border-box; padding: 5px 8px; border-top: 1px solid #dfe5ea;
  background: #fff; display: flex; align-items: center; justify-content: center;
  cursor: zoom-in; border-radius: 0 0 8px 8px; }
.cv-thumb:hover { background: #f1f7fd; }
.cv-thumb img { max-width: 100%%; max-height: 100%%; object-fit: contain; pointer-events: none; }
.cv-thumb.cv-bare img { width: 30px; height: 30px; opacity: .55; }
.cv-thumb.cv-bare:hover img { opacity: .9; }

.cv-btn { font-size: 11px; padding: 1px 8px; background: #eef1f4; border: 1px solid #cfd6dd;
  border-radius: 3px; cursor: pointer; color: #333; }
.cv-btn:hover { background: #e2e8ee; }

.cv-search { width: 100%%; box-sizing: border-box; padding: 6px 9px; font-size: 13px;
  border: 1px solid #cfd6dd; border-radius: 4px; background: #fff; user-select: text;
  -webkit-user-select: text; }
.cv-tabs { display: flex; gap: 4px; margin: 8px 0 2px; }
.cv-tab { flex: 1; font-size: 12px; padding: 5px 4px; border: 1px solid #cfd6dd;
  background: #fff; border-radius: 4px; cursor: pointer; color: #333; }
.cv-tab.cv-tab-on { background: #34495e; border-color: #34495e; color: #fff; }
.cv-empty { font-size: 12.5px; color: #6c757d; margin: 14px 2px; }
.cv-chip { font-size: 12.5px; padding: 5px 9px; margin: 3px 0; background: #fff;
  border: 1px solid #cfd6dd; border-radius: 4px; cursor: pointer; }
.cv-chip:hover { border-color: #3498db; }
.cv-cat { font-size: 11px; font-weight: 700; text-transform: uppercase; color: #6c757d;
  margin: 12px 0 2px; letter-spacing: .04em; }
.cv-zoom { position: absolute; right: 12px; top: 10px; display: flex; gap: 4px; z-index: 5; }
.cv-zoom button { font-size: 13px; min-width: 28px; padding: 2px 6px; background: #fff;
  border: 1px solid #cfd6dd; border-radius: 3px; cursor: pointer; }
.cv-zoom button:hover { background: #eef1f4; }
.cv-menu { position: fixed; z-index: 10001; background: #fff; border: 1px solid #cfd6dd;
  border-radius: 5px; box-shadow: 0 4px 14px rgba(0,0,0,.2); padding: 4px 0; min-width: 180px; }
.cv-menu-head { font-size: 11px; color: #6c757d; padding: 4px 12px 6px; }
.cv-menu-item { padding: 6px 12px; font-size: 13px; cursor: pointer; }
.cv-menu-item:hover { background: #eaf3fb; }
.cv-menu-item.cv-off { color: #9aa5b0; cursor: default; }
.cv-menu-item.cv-off:hover { background: transparent; }
.cv-menu-sep { height: 1px; background: #e3e8ed; margin: 4px 0; }
.cv-marquee { position: absolute; display: none; z-index: 6; pointer-events: none;
  border: 1.5px dashed #3498db; background: rgba(52,152,219,.12); border-radius: 3px; }
.cv-frame { position: absolute; box-sizing: border-box; border: 2px dashed #9db4cc;
  border-radius: 12px; background: rgba(52,152,219,.05); pointer-events: none; }
.cv-frame-label { position: absolute; left: 14px; top: -10px; background: #fbfcfd; padding: 0 8px;
  font-size: 12px; font-weight: 600; color: #4a6785; }
""" % {"w": geometry.NODE_WIDTH, "head": geometry.HEAD_H, "body": geometry.BODY_H,
       "port": geometry.PORT_H, "thumb": geometry.OUTPUT_H, "grid": geometry.GRID,
       "d": geometry.PORT_RADIUS * 2}

# A magnifying glass, shown in an output's place when it has no picture of its own.
MAGNIFIER = ("data:image/svg+xml;charset=utf-8,"
             "%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='%232c3e50' "
             "stroke-width='2' stroke-linecap='round'%3E%3Ccircle cx='10' cy='10' r='6.5'/%3E"
             "%3Cline x1='15' y1='15' x2='21' y2='21'/%3E%3Cline x1='10' y1='7' x2='10' y2='13'/%3E"
             "%3Cline x1='7' y1='10' x2='13' y2='10'/%3E%3C/svg%3E")

STATUS_COLORS = {"ok": "#146c2e", "error": "#b00020", "skipped": "#8a6d00"}
BORDER_COLORS = {"ok": "#2e9d57", "error": "#d93a4f", "skipped": "#d9a400"}
DRAG_THRESHOLD = 4


@dataclass
class CanvasNode:
    """
    One box.

    Attributes:
        id: unique within the canvas
        title, subtitle: the header, and a line or two under it
        badge, color: the small tag in the header (a data type) and its colour
        x, y: top-left, in surface pixels
        ports: [(name, label), ...] inputs, top to bottom
        outputs: [(name, label, colour), ...] its output pins, top to bottom; the name
            is "" for the node's first output, which a wire refers to by the node alone
        output: whether it has something to show: it then has an output area below its ports,
            which a click expands (the pointer is a magnifier over it)
        thumb: an image (a data URL) of that output to fill the area; without one it shows a
            magnifier, so there is always something to click
        status, status_text: "", "ok", "error" or "skipped", and what to say
    """
    id: str
    title: str
    x: float
    y: float
    subtitle: str = ""
    badge: str = ""
    color: str = "#6c757d"
    ports: list = field(default_factory=list)
    outputs: list = field(default_factory=list)
    output: bool = False
    thumb: str = ""
    status: str = ""
    status_text: str = ""

    @property
    def height(self):
        return geometry.node_height(len(self.ports), output=bool(self.output))


@dataclass
class CanvasFrame:
    """A dashed outline around some nodes, with a label: what they belong to together."""
    label: str
    node_ids: list


@dataclass
class CanvasEdge:
    """A wire from one of a node's outputs to one of another node's input ports."""
    source: str
    target: str
    port: str
    color: str = "#7f8c8d"
    output: str = ""            # which of the source node's outputs ("" for the first)

    @property
    def ref(self):
        """The source as callbacks name it: the node's id, then ".output" if not the first."""
        return f"{self.source}.{self.output}" if self.output else self.source

    @property
    def key(self):
        return f"{self.ref}>{self.target}:{self.port}"


def _el(tag, css="", text=None, **attributes):
    element = js.document.createElement(tag)
    if css:
        element.style.cssText = css
    if text is not None:
        element.textContent = text
    for name, value in attributes.items():
        element.setAttribute(name.replace("_", "-"), str(value))
    return element


def _svg(tag, **attributes):
    element = js.document.createElementNS(SVG_NS, tag)
    for name, value in attributes.items():
        element.setAttribute(name.replace("_", "-"), str(value))
    return element


def _ensure_css():
    if not js.document.getElementById(_CSS_ID):
        style = js.document.createElement("style")
        style.id = _CSS_ID
        style.textContent = _CSS
        js.document.head.appendChild(style)


class GraphCanvas:
    """
    Args:
        palette: {tab: {category: [(key, label, hint), ...]}} what the picker offers, in
            tabs (Tools and Blocks, say) that a search box filters; the hint is the
            tooltip and is searched too
        can_connect: `(source id, target id, port name) -> bool`
        on_move: `(id, x, y)` a node was dragged to a new place
        on_connect: `(source, target, port)` a wire was dropped on a port
        on_disconnect: `(source, target, port)` a wire was removed
        on_edit, on_delete: `(id)` a node was double-clicked, or Delete was pressed on it
        on_delete_many: `([id, ...])` Delete was pressed with several blocks selected
        on_output: `(id)` a node's "Show output" was clicked, or the message of one that failed
        menu_for: `(kind, id) -> [(key, label, enabled) | None, ...]` what a right-click
            offers: kind is "node", "edge" (id is the wire's key) or "canvas" (id is "");
            None is a divider, and an empty list means no menu
        on_action: `(key, kind, id)` an item of that menu was chosen
        on_add: `(key, x, y)` a block was chosen in the picker (x, y None for the next free spot)
        blocks_for: `(source id) -> [(key, label), ...]` blocks that could read a
            wire from that node, offered when a wire is dropped on empty canvas
        on_add_from: `(source id, key, x, y)` one of them was chosen

    Usage:
        canvas = GraphCanvas(palette, can_connect, ...callbacks)
        parent.add(canvas.element)
        canvas.show(nodes, edges)
    """

    def __init__(self, palette, can_connect, on_move=None, on_connect=None,
                 on_disconnect=None, on_edit=None, on_delete=None, on_delete_many=None, on_output=None,
                 menu_for=None, on_action=None, on_add=None, blocks_for=None,
                 on_add_from=None):
        _ensure_css()
        self._blocks_for = blocks_for
        self._zoom = 1.0
        self._snap = 0              # snap dragged blocks to multiples of this many pixels; 0 is off
        self._can_connect = can_connect
        self._callbacks = {
            "move": on_move, "connect": on_connect, "disconnect": on_disconnect,
            "edit": on_edit, "delete": on_delete, "delete_many": on_delete_many,
            "output": on_output, "action": on_action,
            "add": on_add, "add_from": on_add_from}
        self._menu_for = menu_for
        self._menu_calls = []       # what each item of the open menu does, by position
        self._nodes = {}
        self._edges = []
        self._node_els = {}
        self._pin_els = {}          # (node id, input port name) -> element
        self._edge_els = {}         # edge key -> (visible path, hit path)
        self._selected = None       # ("edge", key) when a wire is selected
        self._picked = set()        # the ids of the blocks selected
        self._anchor = None         # the block last clicked, where a Shift + click's path starts
        self._marquee_moved = False  # the last press on empty canvas was a drag, not a click
        self._drag = None
        self._proxies = []

        self._palette = _el("div")
        self._palette.className = "cv-picker"
        self._palette.setAttribute("data-role", "picker")
        self._picker_at = None
        self._palette_tabs = {}
        self._palette_tab = None
        self._palette_query = ""
        self._search = _el("input", type="text", placeholder="Search tools and blocks…")
        self._search.className = "cv-search"
        self._search.setAttribute("data-role", "search")
        self._tabbar = _el("div")
        self._tabbar.className = "cv-tabs"
        self._palette_list = _el("div")
        for part in (self._search, self._tabbar, self._palette_list):
            self._palette.appendChild(part)
        self.set_palette(palette)
        self._surface = _el("div")
        self._surface.className = "cv-surface"
        self._surface.setAttribute("data-role", "surface")
        self._wires = _svg("svg", width="100%", height="100%")
        self._wires.style.cssText = ("position:absolute;left:0;top:0;pointer-events:none;"
                                     "overflow:visible")
        self._edge_layer = _svg("g")
        self._ghost_wire = _svg("path", fill="none", stroke="#3498db", stroke_width="2.5",
                                stroke_dasharray="6 4")
        self._ghost_wire.style.display = "none"
        self._frame_layer = _el("div")
        self._frames = []
        self._frame_els = []
        self._wires.appendChild(self._edge_layer)
        self._wires.appendChild(self._ghost_wire)
        self._node_layer = _el("div")
        self._marquee = _el("div")
        self._marquee.className = "cv-marquee"
        self._surface.appendChild(self._frame_layer)
        self._surface.appendChild(self._wires)
        self._surface.appendChild(self._node_layer)
        self._surface.appendChild(self._marquee)
        # The surface is scaled by zoom; the sizer around it takes the scaled
        # size, so the viewport scrolls over what is actually drawn.
        self._sizer = _el("div", "position:relative;")
        self._surface.style.position = "absolute"
        self._surface.style.left = self._surface.style.top = "0"
        self._surface.style.transformOrigin = "0 0"
        self._sizer.appendChild(self._surface)
        self._viewport = _el("div")
        self._viewport.className = "cv-viewport"
        self._viewport.setAttribute("data-role", "viewport")
        self._viewport.appendChild(self._sizer)
        self._menu = None

        self._root = _el("div")
        self._root.className = "cv-root"
        self._root.setAttribute("tabindex", "0")
        self._root.appendChild(self._viewport)
        self._root.appendChild(self._palette)
        zoom = _el("div")
        zoom.className = "cv-zoom"
        for label, action in (("−", "zoom-out"), ("100%", "zoom-reset"), ("+", "zoom-in")):
            button = _el("button", text=label)
            button.setAttribute("data-role", action)
            zoom.appendChild(button)
        self._zoom_label = zoom.children.item(1)
        self._root.appendChild(zoom)
        for name, handler in (("pointerdown", self._down), ("pointermove", self._move),
                              ("pointerup", self._up), ("pointercancel", self._cancel),
                              ("click", self._click), ("dblclick", self._double),
                              ("contextmenu", self._context), ("keydown", self._key),
                              ("wheel", self._wheel), ("input", self._typed)):
            proxy = create_proxy(handler)
            self._proxies.append(proxy)
            self._root.addEventListener(name, proxy)

        # The widget the caller adds to its page.
        from antioch.elements import Div
        self.element = Div()
        self.element._dom_element.appendChild(self._root)

    # ---------------------------------------------------------------- showing

    def show(self, nodes, edges, frames=()):
        """
        Draw exactly these nodes, wires and frames, keeping the selection if it
        survives.
        """
        self._nodes = {node.id: node for node in nodes}
        self._edges = list(edges)
        self._frames = [f for f in frames if any(i in self._nodes for i in f.node_ids)]
        self._picked &= set(self._nodes)
        if self._selected and self._selected[1] not in {e.key for e in self._edges}:
            self._selected = None
        self._node_layer.innerHTML = ""
        self._edge_layer.innerHTML = ""
        self._node_els, self._pin_els, self._edge_els = {}, {}, {}
        for node in nodes:
            self._node_layer.appendChild(self._build_node(node))
        for edge in self._edges:
            if edge.source in self._nodes and edge.target in self._nodes:
                self._edge_layer.appendChild(self._build_edge(edge))
        self._frame_layer.innerHTML = ""
        self._frame_els = []
        for frame in self._frames:
            box = _el("div")
            box.className = "cv-frame"
            box.appendChild(_el("span", text=frame.label, **{"class": "cv-frame-label"}))
            self._frame_layer.appendChild(box)
            self._frame_els.append(box)
        self._redraw_frames()
        self._fit_surface()
        self._mark_selection()

    def _redraw_frames(self):
        """Fit each frame around its nodes as they are now."""
        for frame, box in zip(self._frames, self._frame_els):
            members = [self._nodes[i] for i in frame.node_ids if i in self._nodes]
            if not members:
                continue
            pad = 16
            left = min(n.x for n in members) - pad
            top = min(n.y for n in members) - pad - 6
            right = max(n.x + geometry.NODE_WIDTH for n in members) + pad
            bottom = max(n.y + n.height for n in members) + pad
            box.style.left, box.style.top = f"{left}px", f"{top}px"
            box.style.width, box.style.height = f"{right - left}px", f"{bottom - top}px"

    def _fit_surface(self):
        width, height = geometry.surface_size(
            [(n.x, n.y, n.height) for n in self._nodes.values()])
        self._surface.style.width = f"{width}px"
        self._surface.style.height = f"{height}px"
        self._surface.style.transform = f"scale({self._zoom})"
        self._sizer.style.width = f"{width * self._zoom}px"
        self._sizer.style.height = f"{height * self._zoom}px"
        self._zoom_label.textContent = f"{round(self._zoom * 100)}%"

    def set_snap(self, grid):
        """Make dragged blocks land on a grid of `grid` pixels (0 for no grid)."""
        self._snap = int(grid or 0)

    def set_zoom(self, zoom):
        """Zoom between 40% and 160%."""
        self._zoom = max(0.4, min(1.6, round(zoom, 2)))
        self._fit_surface()

    def _wheel(self, event):
        if event.ctrlKey:
            event.preventDefault()
            self.set_zoom(self._zoom * (0.9 if event.deltaY > 0 else 1.1))

    def set_palette(self, palette):
        """Replace what can be dropped; the search text and the tab chosen stay."""
        self._palette_tabs = palette
        if self._palette_tab not in palette:
            self._palette_tab = next(iter(palette), None)
        self._render_palette()

    @staticmethod
    def _matches(query, category, label, hint):
        text = f"{label} {hint} {category}".lower()
        return all(word in text for word in query.lower().split())

    def _filtered(self):
        """{tab: {category: [items]}} keeping only what the search matches."""
        found = {}
        for tab, categories in self._palette_tabs.items():
            kept = {}
            for category, items in categories.items():
                hits = [item for item in items
                        if self._matches(self._palette_query, category, item[1], item[2])]
                if hits:
                    kept[category] = hits
            found[tab] = kept
        return found

    def _render_palette(self):
        found = self._filtered()
        counts = {tab: sum(len(items) for items in cats.values()) for tab, cats in found.items()}
        # Searching from a tab with nothing in it, with matches in another: go there.
        if self._palette_query and not counts.get(self._palette_tab):
            self._palette_tab = next((t for t in counts if counts[t]), self._palette_tab)
        self._tabbar.innerHTML = ""
        for tab in self._palette_tabs:
            label = f"{tab} ({counts[tab]})" if self._palette_query else tab
            button = _el("button", text=label)
            button.className = "cv-tab" + (" cv-tab-on" if tab == self._palette_tab else "")
            button.setAttribute("data-role", "palette-tab")
            button.setAttribute("data-tab", tab)
            self._tabbar.appendChild(button)
        self._palette_list.innerHTML = ""
        categories = found.get(self._palette_tab, {})
        if not categories:
            self._palette_list.appendChild(_el(
                "div", text=(f"Nothing matches “{self._palette_query}”." if self._palette_query
                             else "Nothing here yet."), **{"class": "cv-empty"}))
            return
        for category, items in categories.items():
            self._palette_list.appendChild(_el("div", text=category, **{"class": "cv-cat"}))
            for key, label, hint in items:
                chip = _el("div", text=label)
                chip.className = "cv-chip"
                chip.setAttribute("data-role", "palette")
                chip.setAttribute("data-key", key)
                chip.setAttribute("data-label", label)
                if hint:
                    chip.title = hint
                self._palette_list.appendChild(chip)

    # ----------------------------------------------------------------- the picker

    def open_picker(self, client_x, client_y, at=None):
        """
        Show the picker at a point of the window, with the search box ready.

        Args:
            at: where on the canvas (surface pixels) the block chosen should go, or None for
                the next free spot
        """
        self._hide_menu()
        self._picker_at = at
        self._palette_query = ""
        self._search.value = ""
        self._render_palette()
        self._palette.style.display = "block"
        box = self._palette.getBoundingClientRect()
        self._palette.style.left = f"{max(8, min(client_x, js.innerWidth - box.width - 8))}px"
        self._palette.style.top = f"{max(8, min(client_y, js.innerHeight - box.height - 8))}px"
        self._search.focus()

    def _hide_picker(self):
        self._palette.style.display = "none"

    def _typed(self, event):
        _, role = self._role_of(event.target)
        if role == "search":
            self._palette_query = str(self._search.value or "")
            self._render_palette()

    def _build_node(self, node):
        box = _el("div")
        box.className = "cv-node"
        box.setAttribute("data-role", "node")
        box.setAttribute("data-id", node.id)
        box.style.left = f"{node.x}px"
        box.style.top = f"{node.y}px"
        box.style.height = f"{node.height}px"
        if node.status in BORDER_COLORS:
            box.style.boxShadow = f"0 0 0 2px {BORDER_COLORS[node.status]}, 0 2px 8px rgba(0,0,0,.18)"

        head = _el("div")
        head.className = "cv-head"
        head.setAttribute("data-role", "node-head")
        head.appendChild(_el("span", text=node.title, **{"class": "cv-title"}))
        if node.badge:
            badge = _el("span", f"background:{node.color};", node.badge)
            badge.className = "cv-badge"
            head.appendChild(badge)
        box.appendChild(head)

        body = _el("div")
        body.className = "cv-body"
        sub = _el("div", text=node.subtitle)
        sub.className = "cv-sub"
        body.appendChild(sub)
        status = _el("div", f"color:{STATUS_COLORS.get(node.status, '#6c757d')};",
                     node.status_text)
        status.className = "cv-status"
        status.title = node.status_text
        if node.status in ("error", "skipped"):
            # The line is cut off to fit the card: clicking it opens the whole message.
            status.setAttribute("data-role", "status-btn")
            status.setAttribute("data-id", node.id)
            status.style.cursor = "pointer"
            status.style.textDecoration = "underline dotted"
            status.title = "Click to read the whole message"
        body.appendChild(status)
        box.appendChild(body)

        for name, label in node.ports:
            row = _el("div")
            row.className = "cv-port"
            row.textContent = label
            pin = _el("div", f"left:-{geometry.PORT_RADIUS}px;top:"
                             f"{(geometry.PORT_H - geometry.PORT_RADIUS * 2) / 2}px;")
            pin.className = "cv-pin"
            pin.setAttribute("data-role", "in-pin")
            pin.setAttribute("data-id", node.id)
            pin.setAttribute("data-port", name)
            pin.title = "Drop a wire here"
            row.appendChild(pin)
            self._pin_els[(node.id, name)] = pin
            box.appendChild(row)

        for index, (name, label, color) in enumerate(node.outputs):
            out = _el("div", f"right:-{geometry.PORT_RADIUS}px;top:"
                             f"{geometry.HEAD_H / 2 - geometry.PORT_RADIUS + index * geometry.PORT_H}px;"
                             f"background:{color or node.color};")
            out.className = "cv-pin"
            out.setAttribute("data-role", "out-pin")
            out.setAttribute("data-id", node.id)
            out.setAttribute("data-output", name)
            out.title = f"{label}: drag to connect" if label else "Drag to connect"
            box.appendChild(out)

        if node.output:
            frame = _el("div")
            frame.className = "cv-thumb" + ("" if node.thumb else " cv-bare")
            frame.setAttribute("data-role", "output-btn")
            frame.setAttribute("data-id", node.id)
            frame.title = "Click to expand what this step made"
            picture = _el("img")
            picture.setAttribute("src", node.thumb or MAGNIFIER)
            picture.setAttribute("alt", "")
            frame.appendChild(picture)
            box.appendChild(frame)

        self._node_els[node.id] = box
        return box

    def _edge_endpoints(self, edge):
        source, target = self._nodes[edge.source], self._nodes[edge.target]
        return geometry.edge_endpoints(
            (source.x, source.y), [name for name, _, _ in source.outputs], edge.output,
            (target.x, target.y), [name for name, _ in target.ports], edge.port)

    def _build_edge(self, edge):
        group = _svg("g")
        path = geometry.wire_path(*self._edge_endpoints(edge))
        hit = _svg("path", d=path, fill="none", stroke="transparent", stroke_width="14")
        hit.style.pointerEvents = "stroke"
        hit.style.cursor = "pointer"
        hit.setAttribute("data-role", "edge")
        hit.setAttribute("data-key", edge.key)
        visible = _svg("path", d=path, fill="none", stroke=edge.color, stroke_width="2.5")
        visible.style.pointerEvents = "none"
        group.appendChild(visible)
        group.appendChild(hit)
        self._edge_els[edge.key] = (visible, hit)
        return group

    def _redraw_edges_of(self, node_id):
        for edge in self._edges:
            if node_id in (edge.source, edge.target) and edge.key in self._edge_els:
                path = geometry.wire_path(*self._edge_endpoints(edge))
                for element in self._edge_els[edge.key]:
                    element.setAttribute("d", path)
        self._redraw_frames()
        self._place_edge_handle()

    # -------------------------------------------------------------- selection

    def _select(self, kind, key):
        """Select one block ("node") or one wire ("edge"), or nothing (None)."""
        self._picked = {key} if kind == "node" and key else set()
        if kind == "node" and key:
            self._anchor = key
        self._selected = ("edge", key) if kind == "edge" and key else None
        self._mark_selection()

    def selected_ids(self):
        """The ids of the blocks selected, sorted."""
        return sorted(self._picked)

    def _mark_selection(self):
        for node_id, element in self._node_els.items():
            selected = node_id in self._picked
            if selected:
                element.classList.add("cv-selected")
            else:
                element.classList.remove("cv-selected")
        for key, (visible, _) in self._edge_els.items():
            selected = self._selected == ("edge", key)
            visible.setAttribute("stroke-width", "4.5" if selected else "2.5")
        self._place_edge_handle()

    def _place_edge_handle(self):
        """The × that removes the selected wire, at its midpoint."""
        old = self._wires.querySelector("[data-role=edge-x]")
        if old:
            old.remove()
        if not self._selected or self._selected[0] != "edge":
            return
        edge = next((e for e in self._edges if e.key == self._selected[1]), None)
        if edge is None or edge.source not in self._nodes or edge.target not in self._nodes:
            return
        x, y = geometry.wire_midpoint(*self._edge_endpoints(edge))
        group = _svg("g", transform=f"translate({x:.1f},{y:.1f})")
        group.setAttribute("data-role", "edge-x")
        group.setAttribute("data-key", edge.key)
        group.style.pointerEvents = "all"
        group.style.cursor = "pointer"
        group.appendChild(_svg("circle", r="9", fill="#fff", stroke="#b00020", stroke_width="1.5"))
        label = _svg("text", x="0", y="4", text_anchor="middle", fill="#b00020")
        label.style.fontSize = "13px"
        label.style.fontWeight = "700"
        label.textContent = "×"
        group.appendChild(label)
        self._wires.appendChild(group)

    # ----------------------------------------------------------------- events

    @staticmethod
    def _role_of(element):
        """(element, role) of the nearest thing at or above `element` with a role."""
        while element:
            role = element.getAttribute("data-role")
            if role:
                return element, str(role)
            element = element.parentElement
        return None, ""

    def _surface_point(self, event):
        rect = self._surface.getBoundingClientRect()
        return (event.clientX - rect.left) / self._zoom, (event.clientY - rect.top) / self._zoom

    def _call(self, name, *args):
        callback = self._callbacks.get(name)
        if callback:
            callback(*args)

    def _down(self, event):
        if event.button != 0:
            return
        element, role = self._role_of(event.target)
        if role != "menu-item":
            self._hide_menu()
        if role not in ("palette", "palette-tab", "search", "picker"):
            self._hide_picker()
        if role in ("output-btn", "status-btn", "edge-x", "menu-item", "zoom-in", "zoom-out",
                    "zoom-reset", "palette-tab", "search", "palette", "picker"):
            return                      # handled on click, or by the browser itself
        self._root.focus()
        self._marquee_moved = False
        x, y = self._surface_point(event)
        ctrl = bool(event.ctrlKey or event.metaKey)
        shift = bool(event.shiftKey)
        extend = ctrl or shift                  # for the rectangle: add to what is selected
        if role in ("node-head", "node"):
            box = element if role == "node" else element.parentElement
            node_id = str(box.getAttribute("data-id"))
            if node_id in self._nodes:
                collapse = None         # a plain click on one of several selected blocks narrows to it, on release
                if shift and self._anchor in self._nodes and self._anchor != node_id:
                    # Everything on the way from the block last clicked to this one.
                    path = geometry.path_between([(e.source, e.target) for e in self._edges],
                                                 self._anchor, node_id)
                    self._picked = (self._picked | path) if ctrl else set(path)
                    self._selected = None
                    self._mark_selection()
                elif extend:
                    self._picked ^= {node_id}              # add it to the selection, or take it out
                    if node_id in self._picked:
                        self._anchor = node_id
                    self._selected = None
                    self._mark_selection()
                elif node_id not in self._picked:
                    self._select("node", node_id)
                else:
                    self._anchor = node_id
                    collapse = node_id if len(self._picked) > 1 and not extend else None
                if node_id in self._picked:                # drag them all, or just this one
                    starts = {i: (self._nodes[i].x, self._nodes[i].y) for i in self._picked}
                    self._start(event, {"kind": "node", "starts": starts, "px": x, "py": y,
                                        "collapse": collapse})
        elif role == "out-pin":
            self._begin_wire(event, str(element.getAttribute("data-id")),
                             str(element.getAttribute("data-output") or ""), None)
        elif role == "in-pin":
            target, port = str(element.getAttribute("data-id")), str(element.getAttribute("data-port"))
            wires = [e for e in self._edges if e.target == target and e.port == port]
            if wires:
                self._begin_wire(event, wires[-1].source, wires[-1].output, wires[-1])
        elif role == "edge":
            self._select("edge", str(element.getAttribute("data-key")))
        elif role in ("surface", "viewport"):
            base = set(self._picked) if extend else set()
            if not extend:
                self._select(None, None)
            self._start(event, {"kind": "marquee", "sx": x, "sy": y, "base": base})
        else:
            self._select(None, None)

    def _start(self, event, drag):
        drag.update({"moved": False, "x0": event.clientX, "y0": event.clientY})
        self._drag = drag
        self._root.setPointerCapture(event.pointerId)

    def _begin_wire(self, event, node_id, output, picked_up):
        """Start drawing a wire from an output of a node, lighting every port it could reach."""
        source = f"{node_id}.{output}" if output else node_id
        self._start(event, {"kind": "wire", "source": source, "node": node_id,
                            "output": output, "picked": picked_up})
        if picked_up is not None:
            for element in self._edge_els.get(picked_up.key, ()):
                element.style.display = "none"
        for (node_id, port), pin in self._pin_els.items():
            fits = bool(self._can_connect(source, node_id, port))
            pin.classList.add("cv-ok" if fits else "cv-no")
        self._ghost_wire.style.display = "block"
        self._ghost_to(event)

    def _ghost_to(self, event):
        drag = self._drag
        node = self._nodes[drag["node"]]
        names = [name for name, _, _ in node.outputs]
        x1, y1 = geometry.output_anchor(
            node.x, node.y, names.index(drag["output"]) if drag["output"] in names else 0)
        x2, y2 = self._surface_point(event)
        snap = self._pin_under(event)
        if snap is not None:
            target = self._nodes[snap[0]]
            names = [name for name, _ in target.ports]
            x2, y2 = geometry.input_anchor(target.x, target.y, names.index(snap[1]))
        self._ghost_wire.setAttribute("d", geometry.wire_path(x1, y1, x2, y2))

    def _pin_under(self, event):
        """(node id, port) of the lit input port under the pointer, if any."""
        element = js.document.elementFromPoint(event.clientX, event.clientY)
        found, role = self._role_of(element)
        if role == "in-pin" and found.classList.contains("cv-ok"):
            return str(found.getAttribute("data-id")), str(found.getAttribute("data-port"))
        return None

    def _move(self, event):
        drag = self._drag
        if drag is None:
            return
        if not drag["moved"]:
            if (abs(event.clientX - drag["x0"]) + abs(event.clientY - drag["y0"])
                    < DRAG_THRESHOLD):
                return
            drag["moved"] = True
        if drag["kind"] == "node":
            x, y = self._surface_point(event)
            starts = drag["starts"]
            dx, dy = geometry.clamp_shift(starts, x - drag["px"], y - drag["py"])
            for node_id, (sx, sy) in starts.items():
                node = self._nodes[node_id]
                node.x, node.y = max(0.0, sx + dx), max(0.0, sy + dy)
                if self._snap:
                    node.x = float(geometry.snap(node.x, self._snap))
                    node.y = float(geometry.snap(node.y, self._snap))
                box = self._node_els[node_id]
                box.style.left, box.style.top = f"{node.x}px", f"{node.y}px"
                self._redraw_edges_of(node_id)
        elif drag["kind"] == "marquee":
            x, y = self._surface_point(event)
            left, top = min(drag["sx"], x), min(drag["sy"], y)
            self._marquee.style.left, self._marquee.style.top = f"{left}px", f"{top}px"
            self._marquee.style.width, self._marquee.style.height = f"{abs(x - drag['sx'])}px", f"{abs(y - drag['sy'])}px"
            self._marquee.style.display = "block"
            boxes = {i: (n.x, n.y, geometry.NODE_WIDTH, n.height) for i, n in self._nodes.items()}
            self._picked = drag["base"] | set(geometry.boxes_in_rect(boxes, drag["sx"], drag["sy"], x, y))
            self._mark_selection()
        elif drag["kind"] == "wire":
            self._ghost_to(event)


    def _up(self, event):
        drag, self._drag = self._drag, None
        if drag is None:
            return
        try:
            self._root.releasePointerCapture(event.pointerId)
        except Exception:
            pass
        kind = drag["kind"]
        if kind == "node":
            if drag["moved"]:
                self._fit_surface()
                for node_id in drag["starts"]:
                    node = self._nodes[node_id]
                    self._call("move", node.id, node.x, node.y)
            elif drag.get("collapse"):
                self._select("node", drag["collapse"])
        elif kind == "marquee":
            self._marquee.style.display = "none"
            self._marquee_moved = bool(drag["moved"])
        elif kind == "wire":
            self._finish_wire(event, drag)

    def _finish_wire(self, event, drag):
        snap = self._pin_under(event)
        self._ghost_wire.style.display = "none"
        for pin in self._pin_els.values():
            pin.classList.remove("cv-ok")
            pin.classList.remove("cv-no")
        picked = drag["picked"]
        if picked is not None:
            for element in self._edge_els.get(picked.key, ()):
                element.style.display = ""
        if not drag["moved"]:
            return
        if snap is not None:
            target, port = snap
            if picked is not None and (picked.target, picked.port) == (target, port):
                return                          # put back where it was
            if picked is not None:
                self._call("disconnect", picked.ref, picked.target, picked.port)
            self._call("connect", drag["source"], target, port)
        elif picked is not None:
            self._call("disconnect", picked.ref, picked.target, picked.port)
        else:
            _, role = self._role_of(js.document.elementFromPoint(event.clientX, event.clientY))
            if role in ("surface", "viewport"):
                self._offer_blocks(event, drag["source"])

    def _offer_blocks(self, event, source):
        """A new wire was dropped on empty canvas: list what could read it."""
        choices = self._blocks_for(source) if self._blocks_for else []
        if not choices:
            return
        x, y = self._surface_point(event)
        entries = [(label, lambda key=key: self._call("add_from", source, key, max(0.0, x), max(0.0, y)))
                   for key, label in choices]
        self._show_menu(event.clientX, event.clientY, entries, "Add a block that reads this")

    def _show_menu(self, client_x, client_y, entries, head=""):
        """
        Open a menu at a point of the window.

        Args:
            entries: [(label, callable, enabled=True) | None]; None is a divider, and an
                item that is not enabled is shown greyed and does nothing
        """
        self._hide_menu()
        menu = _el("div", f"left:{client_x}px;top:{client_y}px;")
        menu.className = "cv-menu"
        menu.setAttribute("data-role", "menu")
        if head:
            menu.appendChild(_el("div", text=head, **{"class": "cv-menu-head"}))
        self._menu_calls = []
        for entry in entries:
            if entry is None:
                menu.appendChild(_el("div", **{"class": "cv-menu-sep"}))
                continue
            label, call, *rest = entry
            enabled = rest[0] if rest else True
            item = _el("div", text=label)
            item.className = "cv-menu-item" + ("" if enabled else " cv-off")
            item.setAttribute("data-role", "menu-item")
            item.setAttribute("data-index", str(len(self._menu_calls)))
            self._menu_calls.append(call if enabled else None)
            menu.appendChild(item)
        self._root.appendChild(menu)
        self._menu = menu
        # A tall menu opened near an edge would run off the window; slide it back.
        box = menu.getBoundingClientRect()
        menu.style.left = f"{max(8, min(client_x, js.innerWidth - box.width - 8))}px"
        menu.style.top = f"{max(8, min(client_y, js.innerHeight - box.height - 8))}px"

    def _hide_menu(self):
        if self._menu is not None:
            self._menu.remove()
            self._menu = None
        self._menu_calls = []

    def _context(self, event):
        """A right-click: a node, a wire or the empty canvas offers its menu."""
        if not self._menu_for:
            return
        element, role = self._role_of(event.target)
        if role in ("node", "node-head", "in-pin", "out-pin", "output-btn", "status-btn"):
            owner = element
            while owner is not None and str(owner.getAttribute("data-role")) != "node":
                owner = owner.parentElement
            if owner is None:
                return
            kind, key = "node", str(owner.getAttribute("data-id"))
            if key not in self._nodes:
                return
            if key in self._picked and len(self._picked) > 1:
                kind, key = "selection", ",".join(sorted(self._picked))     # several selected: the menu is for all
            else:
                self._select("node", key)
        elif role == "edge":
            kind, key = "edge", str(element.getAttribute("data-key"))
            self._select("edge", key)
        elif role in ("surface", "viewport"):
            kind, key = "canvas", ""
            self._select(None, None)
        else:
            return                      # the palette, the zoom buttons: the browser's own menu
        offered = self._menu_for(kind, key)
        if kind == "canvas":
            x, y = self._surface_point(event)
            here = (max(0.0, x - geometry.NODE_WIDTH / 2), max(0.0, y - geometry.HEAD_H / 2))
            offered = [("__add__", "Add a tool or block here…"), None] + list(offered or [])
        if not offered:
            return
        event.preventDefault()
        entries = []
        for item in offered:
            if item is None:
                entries.append(None)
                continue
            action, label, *rest = item
            if action == "__add__":
                at_x, at_y = event.clientX, event.clientY
                entries.append((label, lambda: self.open_picker(at_x, at_y, here)))
                continue
            entries.append((label, lambda a=action: self._call("action", a, kind, key),
                            rest[0] if rest else True))
        self._show_menu(event.clientX, event.clientY, entries)

    def _cancel(self, event):
        drag, self._drag = self._drag, None
        if drag is None:
            return
        if drag["kind"] == "wire":
            self._finish_wire(event, {**drag, "moved": False})

    def _click(self, event):
        element, role = self._role_of(event.target)
        if role == "palette-tab":
            self._palette_tab = str(element.getAttribute("data-tab"))
            self._render_palette()
        elif role == "palette":
            at, self._picker_at = self._picker_at, None
            self._hide_picker()
            self._call("add", str(element.getAttribute("data-key")),
                       None if at is None else at[0], None if at is None else at[1])
        elif role in ("zoom-in", "zoom-out", "zoom-reset"):
            self.set_zoom(1.0 if role == "zoom-reset"
                          else self._zoom + (0.1 if role == "zoom-in" else -0.1))
        elif role == "menu-item":
            call = self._menu_calls[int(element.getAttribute("data-index"))]
            self._hide_menu()
            if call is not None:
                call()
        elif role in ("output-btn", "status-btn"):
            self._call("output", str(element.getAttribute("data-id")))
        elif role == "edge-x":
            source_target, _, port = str(element.getAttribute("data-key")).rpartition(":")
            source, _, target = source_target.partition(">")
            self._selected = None
            self._call("disconnect", source, target, port)

    def _double(self, event):
        # Not event.target: a press on empty canvas captures the pointer (for the rectangle), so
        # the browser reports the double-click on the whole canvas; ask what is under the pointer.
        element, role = self._role_of(js.document.elementFromPoint(event.clientX, event.clientY))
        if self._marquee_moved:
            self._marquee_moved = False         # that press was dragging out a rectangle
            return
        if role in ("surface", "viewport"):
            x, y = self._surface_point(event)
            self.open_picker(event.clientX, event.clientY,
                             (max(0.0, x - geometry.NODE_WIDTH / 2), max(0.0, y - geometry.HEAD_H / 2)))
        elif role in ("node", "node-head"):
            owner = element if role == "node" else element.parentElement
            self._call("edit", str(owner.getAttribute("data-id")))

    def _key(self, event):
        if event.key == "Escape":
            self._hide_menu()
            self._hide_picker()
            return
        if event.key == "Enter" and event.target == self._search:
            first = self._palette_list.querySelector("[data-role=palette]")
            if first:
                first.click()
            return
        if event.key not in ("Delete", "Backspace") or not (self._selected or self._picked):
            return
        if str(event.target.tagName).lower() in ("input", "textarea"):
            return                      # typing in the search box is not deleting a node
        event.preventDefault()
        if self._picked:
            ids = sorted(self._picked)
            if len(ids) == 1:
                self._call("delete", ids[0])
            else:
                self._call("delete_many", ids)
        else:
            kind, key = self._selected
            source_target, _, port = key.rpartition(":")
            source, _, target = source_target.partition(">")
            self._selected = None
            self._call("disconnect", source, target, port)
