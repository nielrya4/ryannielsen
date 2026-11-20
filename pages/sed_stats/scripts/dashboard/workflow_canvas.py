"""
The workflow as a canvas: the steps drawn as boxes and wires.

This only translates. The canvas (`canvas_lib`) draws what it is told and reports
what the user did; the workflow panel owns the steps and applies every edit, so
dragging a wire here is an edit like any other.
Where each box sits is the one thing the canvas adds, and it is kept with the
workflow (`Workflow.layout`) so it is saved and restored with it.
"""
import asyncio

from canvas_lib import CanvasEdge, CanvasFrame, CanvasNode, GraphCanvas, layout
from workflow_lib import (
    DATA, FACTORS, LINE, MATRIX, POINTS, POLYGON, PROPORTIONS, RASTER, TABLE, TYPE_LABELS,
)
from workflow_lib.engine import OK
from workflow_lib.workflow import source_ref, split_source, step_of

from . import nodes
from .nodes import NODES

# One colour per kind of data, used for a node's tag and for the wires leaving
# it, so what flows where can be read from across the room.
TYPE_COLORS = {
    TABLE: "#5d6d7e", LINE: "#2a78d6", RASTER: "#8e44ad", POINTS: "#16a085",
    MATRIX: "#e67e22", POLYGON: "#c0392b", PROPORTIONS: "#27ae60", FACTORS: "#b8860b",
}
GRAPH_COLOR = "#6c757d"
TOOL_PREFIX = "tool:"
STATUS_TEXT = {OK: "ran", "": "not run yet"}


def _brief(text, limit=220):
    """A description short enough for a tooltip."""
    text = " ".join((text or "").split())
    return text if len(text) <= limit else text[:limit - 1].rstrip() + "…"


class WorkflowCanvas:
    """
    Usage:
        canvas = WorkflowCanvas(panel)
        parent.add(canvas.element)
        canvas.refresh()            # whenever the workflow or its status changes
    """

    def __init__(self, panel):
        self._panel = panel
        self._canvas = GraphCanvas(
            self._palette(),
            can_connect=self._can_connect,
            on_move=self._moved,
            on_connect=lambda s, t, p: panel.connect_wire(s, t, p),
            on_disconnect=lambda s, t, p: panel.disconnect_wire(s, t, p),
            on_edit=self._edit,
            on_delete=lambda i: asyncio.ensure_future(panel._delete(i)),
            on_delete_many=lambda ids: asyncio.ensure_future(panel._delete_many(ids)),
            on_output=panel.show_output,
            menu_for=panel.menu_for,
            on_action=panel.menu_action,
            on_add=self._add,
            blocks_for=self._blocks_for,
            on_add_from=lambda source, key, x, y: panel.open_node(
                key, at=(x, y), preset=source))
        self.element = self._canvas.element

    # -------------------------------------------------------------- callbacks

    def _can_connect(self, source, target, port):
        panel = self._panel
        return panel.workflow.can_connect(panel._specs, source, target, port)

    def _palette(self):
        """
        What can be dropped, in two tabs: the tools, by toolbox, and the blocks they
        are made of, by kind. A tool's key is told apart from a block's by a prefix,
        since a few names are both. Each carries its description as a tooltip, which
        the search looks in too.
        """
        panel = self._panel
        registry = panel.registry
        return {
            "Tools": {toolbox: [(f"{TOOL_PREFIX}{key}", registry.get(key).label,
                                 _brief(registry.get(key).description)) for key in keys]
                      for toolbox, keys in registry.toolboxes().items()},
            "Blocks": {category: [(key, NODES[key].label, _brief(NODES[key].description))
                                  for key in keys]
                       for category, keys in nodes.menu().items()},
        }

    def selected_ids(self):
        """The ids of the blocks selected on the canvas."""
        return self._canvas.selected_ids()

    def reset_zoom(self):
        self._canvas.set_zoom(1.0)

    def open_picker(self, client_x, client_y):
        """Open the tool and block picker at a point of the window; the choice goes to the next free spot."""
        self._canvas.open_picker(client_x, client_y)

    def refresh_palette(self):
        self._canvas.set_palette(self._palette())

    def _add(self, key, x, y):
        at = None if x is None else (x, y)
        if key.startswith(TOOL_PREFIX):
            self._panel.open_tool(key[len(TOOL_PREFIX):], at=at)
        else:
            self._panel.open_node(key, at=at)

    def _blocks_for(self, source):
        """The blocks with an input that could read what `source` produces."""
        panel = self._panel
        kind = panel.workflow.type_of(source, panel._specs)
        return [(key, node.label) for category, keys in nodes.menu().items()
                for key in keys for node in (NODES[key],)
                if any(port.accepts(kind) for port in node.spec.ports)]

    def _moved(self, node_id, x, y):
        self._panel.workflow.set_position(node_id, x, y)
        self._panel.notify_changed()

    def _edit(self, node_id):
        if node_id == DATA:
            return
        step = self._panel.workflow.get(node_id)
        self._panel.open_node(step.tool, step)

    # ---------------------------------------------------------------- drawing

    def refresh(self):
        panel = self._panel
        workflow = panel.workflow
        self._canvas.set_snap(workflow.snap_grid)
        self._place_new()
        canvas_nodes = [self._data_node()]
        edges = []
        numbers = workflow.numbers()
        for step in workflow.steps:
            node = NODES.get(step.tool)
            if node is None:
                continue
            outputs = []
            for name in node.spec.output_names():
                kind = workflow.type_of(source_ref(step.id, name), panel._specs)
                if kind:
                    outputs.append((name, node.spec.output_label_of(name) or TYPE_LABELS[kind],
                                    TYPE_COLORS.get(kind, GRAPH_COLOR)))
            produces = workflow.type_of(step.id, panel._specs)
            badge = (TYPE_LABELS[produces] + (f" +{len(outputs) - 1}" if len(outputs) > 1 else "")
                     if outputs else "graph")
            status, message = panel._status.get(step.id, ("", ""))
            text = STATUS_TEXT.get(status) or f"{status} — {message}"
            x, y = workflow.position(step.id)
            canvas_nodes.append(CanvasNode(
                id=step.id, title=f"{numbers[step.id]} · {panel._step_name(step)}",
                subtitle=node.describe(step.options),
                badge=badge, color=TYPE_COLORS.get(produces, GRAPH_COLOR),
                x=x, y=y, ports=[(p.name, p.label or p.name) for p in node.spec.ports],
                outputs=outputs,
                output=panel.has_output(step.id), thumb=panel.thumbnail(step.id),
                status=status, status_text=text))
            for port in node.spec.ports:
                for source in step.inputs.get(port.name, []):
                    kind = workflow.type_of(source, panel._specs)
                    edges.append(CanvasEdge(step_of(source), step.id, port.name,
                                            TYPE_COLORS.get(kind, GRAPH_COLOR),
                                            split_source(source)[1]))
        frames = [CanvasFrame(info["title"] or info["tool"], workflow.members(group))
                  for group, info in workflow.groups.items()]
        self._canvas.show(canvas_nodes, edges, frames)

    def _data_node(self):
        panel = self._panel
        rows = panel._get_rows()
        columns = len(rows[0]) if rows else 0
        x, y = panel.workflow.position(DATA)
        return CanvasNode(
            id=DATA, title="Spreadsheet", x=x, y=y,
            subtitle=f"{len(rows):,} rows × {columns} columns",
            badge=TYPE_LABELS[TABLE], color=TYPE_COLORS[TABLE],
            outputs=[("", TYPE_LABELS[TABLE], TYPE_COLORS[TABLE])])

    def _place_new(self):
        """Give every node without a position one, in columns by how far it is from the data."""
        workflow = self._panel.workflow
        occupied, wanted = {}, []
        entries = [(DATA, layout.node_height(0))]
        for step in workflow.steps:
            node = NODES.get(step.tool)
            if node is not None:
                # Room for the output area, which a step gets once it has run.
                entries.append((step.id, layout.node_height(len(node.spec.ports), output=True)))
        for node_id, height in entries:
            spot = workflow.position(node_id)
            if spot:
                occupied[node_id] = (spot[0], spot[1], height)
            else:
                wanted.append((node_id, workflow.depth_of(node_id), height))
        for node_id, (x, y) in layout.auto_place(wanted, occupied).items():
            workflow.set_position(node_id, x, y)
