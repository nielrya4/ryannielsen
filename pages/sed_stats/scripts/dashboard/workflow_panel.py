"""
The Workflow tab: analyses snapped together like building blocks.

A workflow is a list of steps. Each step is a node — a computation or a graph —
whose input ports read the spreadsheet or an earlier step's output. What passes
between them is typed (a Distribution makes Lines, a Comparison turns Lines
into a Matrix, an MDS turns a Matrix into Points, a Scatterplot draws Points),
and a port only offers sources it can read, so whatever can be wired up makes
sense. A graph with several series takes several inputs, added with "+ Add
input".

The tab is a canvas where steps are boxes you drag and wires you connect. You add,
edit, rewire and delete steps and run them in order; results land in the Outputs
tab as cards named after their step.

The structure and execution live in `workflow_lib` and the nodes in `nodes`;
this is only the interface to them.
"""
import asyncio
import copy

from antioch.elements import Button, Div, P, Span
from antioch.event import when

from ui_lib import Toolbar
from workflow_lib import DATA, TABLE, TYPE_LABELS, Workflow, WorkflowEngine
from workflow_lib.engine import OK
from workflow_lib.tools import TABLE_INPUT, instantiate, sheet_step
from workflow_lib.workflow import source_ref, split_source

from canvas_lib import layout

from . import nodes
from .config import LEGACY_TOOLS
from .confirm import ConfirmDialog, MessageDialog
from .node_dialog import NodeDialog
from .nodes import NODES, StepOutput
from .output_viewer import OutputViewer
from .tables import begin_previews, first_preview, result_table
from .thumbnails import MAX_TABLE_ROWS, svg_data_url, table_cells, table_svg
from . import step_menu
from .save_tool_dialog import ManageToolsDialog, SaveToolDialog
from .toolboxes import ToolRegistry
from .workflow_canvas import WorkflowCanvas

TOOLBAR_STYLE = {"background_color": "#34495e"}
MENU_STYLE = {"font_size": "14px", "padding": "10px 18px"}
BUTTON_STYLE = {
    "background-color": "#34495e", "color": "#fff", "border": "none",
    "padding": "6px 14px", "cursor": "pointer", "font-size": "13px",
    "border-radius": "3px",
}
SMALL_BUTTON_STYLE = {
    "background-color": "#eef1f4", "color": "#333", "border": "1px solid #cfd6dd",
    "padding": "3px 9px", "cursor": "pointer", "font-size": "12px",
    "border-radius": "3px",
}
RUN_STYLE = {**BUTTON_STYLE, "background-color": "#146c2e"}
# A switch: a pill with a knob that sits left when off and right when on.
SWITCH_STYLE = {
    "display": "inline-flex", "align-items": "center", "gap": "7px", "background-color": "transparent",
    "border": "none", "padding": "3px 6px", "cursor": "pointer", "font-size": "12px", "color": "#333",
}
SWITCH_TRACK = {
    "position": "relative", "display": "inline-block", "width": "32px", "height": "16px",
    "border-radius": "8px", "background-color": "#b8c2cc", "transition": "background-color .15s",
}
SWITCH_KNOB = {
    "position": "absolute", "top": "2px", "left": "2px", "width": "12px", "height": "12px",
    "border-radius": "50%", "background-color": "#fff", "box-shadow": "0 1px 2px rgba(0,0,0,.3)",
    "transition": "left .15s",
}
MUTED = "#6c757d"


class WorkflowPanel:
    """
    Usage:
        panel = WorkflowPanel(get_rows, on_change=tracker.changed, on_save=drive.save_bytes,
                              set_rows=table.set_data)
        DOM.add(panel.element)
        panel.attach(overlay, registry)
    """

    def __init__(self, get_rows, on_change=None, on_save=None, set_rows=None, on_view_spreadsheet=None,
                 on_view_map=None):
        self._get_rows = get_rows
        self._on_view_spreadsheet = on_view_spreadsheet   # switches to the spreadsheet tab
        self._on_view_map = on_view_map                   # `(step id)` shows a block on the Maps tab
        self._set_rows = set_rows       # replaces the spreadsheet, for a step that writes to it
        self._on_change = on_change
        self._on_save = on_save         # `async (filename, data, mime)` to Drive, or None
        self._outputs = {}              # step id -> the StepOutput its block shows
        self._thumbs = {}               # step id -> a data URL picture of that output
        self._table_views = {}          # step id -> its table, built when first opened
        self._viewer = None             # the window an output expands in, built on first use
        self._message_dialog = None     # shows a failed step's whole message, built on first use
        self._viewing = None            # the step whose output it shows
        self._overlay = None
        self._specs = nodes.specs()
        self._dialogs = {}          # block key -> its NodeDialog, built on first use
        self._tool_dialogs = {}     # tool key -> its NodeDialog (tools and blocks share keys)
        self.registry = ToolRegistry()
        self.workflow = Workflow()
        self.engine = None
        self._status = {}           # step id -> (status, message)
        self._unplaced = set()      # compute steps run quietly, card not yet shown
        self._quiet = False
        self._confirm = None
        self._sheet_confirm = None
        self._canvas = None
        self._save_tool = None
        self._manage_tools = None
        self._pending_pos = None    # where a block dropped on the canvas should land

        self._toolbar = Toolbar(toolbar_style=dict(TOOLBAR_STYLE),
                                menu_item_style=dict(MENU_STYLE))
        self._add_button = Button("＋ Add…", style=dict(BUTTON_STYLE))
        self._add_button.set_attribute("title", "Search every tool and block, or browse them by kind")
        self._snap_track = Span(style=dict(SWITCH_TRACK))
        self._snap_knob = Span(style=dict(SWITCH_KNOB))
        self._snap_track.add(self._snap_knob)
        self._snap_switch = Button(self._snap_track, Span("Snap to grid"), style=dict(SWITCH_STYLE))
        self._snap_switch.set_attribute("title", "Blocks land on the canvas grid when you drag them or add them, "
                                                 "and the ones already there move onto it")
        run_all = Button("Run workflow", style=dict(RUN_STYLE))
        clear = Button("Clear", style=dict(SMALL_BUTTON_STYLE))
        save_tool = Button("Save as tool…", style=dict(SMALL_BUTTON_STYLE))
        my_tools = Button("My tools…", style=dict(SMALL_BUTTON_STYLE))
        self._tidy = Button("Tidy up", style=dict(SMALL_BUTTON_STYLE))
        self._summary = Span("", style={"font-size": "13px", "color": MUTED})
        self._empty = P(
            "No steps yet. Add a tool or block from the menus above, with ＋ Add…, or by "
            "double-clicking the canvas. Describe turns the spreadsheet into "
            "distributions or points, Compare and Model work on those, and Graph "
            "draws any of them; each step reads the spreadsheet or an earlier "
            "step, so Distribution → Comparison → MDS → Scatterplot is four blocks "
            "snapped together.",
            style={"color": MUTED, "margin": "0"})

        @when(self._snap_switch.events.click)
        def on_snap(sender, *args):
            self.workflow.set_snap(0 if self.workflow.snap_grid else layout.GRID)
            self._changed()

        @when(self._add_button.events.click)
        def on_add(sender, *args):
            box = self._add_button._dom_element.getBoundingClientRect()
            self._canvas.open_picker(box.left, box.bottom + 4)

        @when(run_all.events.click)
        def on_run(sender, *args):
            asyncio.ensure_future(self._run(None))

        @when(clear.events.click)
        def on_clear(sender, *args):
            asyncio.ensure_future(self._clear())

        @when(save_tool.events.click)
        def on_save_tool(sender, *args):
            self.open_save_tool()

        @when(my_tools.events.click)
        def on_my_tools(sender, *args):
            if self._manage_tools is None:
                self._manage_tools = ManageToolsDialog(self)
            self._manage_tools.open()

        @when(self._tidy.events.click)
        def on_tidy(sender, *args):
            self.workflow.layout.clear()
            self._changed()

        self.element = Div(
            Div(self._toolbar.element, style={"margin-bottom": "12px"}),
            Div(self._add_button, run_all, clear, self._summary, Div(style={"flex": "1"}),
                self._snap_switch, save_tool, my_tools, self._tidy,
                style={"display": "flex", "align-items": "center", "gap": "10px",
                       "margin-bottom": "14px", "flex-wrap": "wrap"}),
            self._empty,
        )
        self._canvas_host = Div()
        self.element.add(self._canvas_host)

    # ------------------------------------------------------------------- setup

    def attach(self, overlay, registry):
        """
        Connect the loading overlay and the tools, and build the Add menu: a
        menu per toolbox of pre-wired tools, then every block on its own.
        """
        self._overlay = overlay
        self.registry = registry
        self.engine = WorkflowEngine(
            self.workflow, self._get_rows, self._specs,
            self._compute, self._render_graph)

        self._canvas = WorkflowCanvas(self)
        self._canvas_host.add(self._canvas.element)
        self.refresh_tool_menu()
        self._rebuild()
        return self

    def refresh_tool_menu(self):
        """Rebuild the Add menu and the canvas palette, after tools were added or removed."""
        def block_opener(key):
            return lambda: self.open_node(key)

        def tool_opener(key):
            return lambda: self.open_tool(key)

        registry = self.registry
        menu = {toolbox: {registry.get(key).label: tool_opener(key) for key in keys}
                for toolbox, keys in registry.toolboxes().items()}
        menu["Building blocks"] = {
            category: {NODES[key].label: block_opener(key) for key in keys}
            for category, keys in nodes.menu().items()}
        self._toolbar.update_menu(menu)
        # A removed tool's dialog should not outlive it, nor a new tool's dialog
        # be built from an old definition.
        self._tool_dialogs = {k: d for k, d in self._tool_dialogs.items()
                              if registry.get(k) is not None
                              and d.node is registry.node(k)}
        if self._canvas is not None:
            self._canvas.refresh_palette()

    def say(self, text):
        """Put a message beside the Run button."""
        self._summary.set_text(text)

    def append_note(self, text):
        """Add a sentence to the message beside the Run button, keeping what it says."""
        current = str(self._summary._dom_element.textContent or "").strip()
        self._summary.set_text(f"{current} {text}".strip())

    def open_node(self, key, step=None, at=None, preset=None):
        """
        Open the dialog to add a `key` step, or to edit `step`.

        `at` is where on the canvas the new step should be drawn, when it was
        dropped there; `preset` is a source to wire into the new step's first
        port that can read it, when the step was made by dragging a wire out.
        """
        self._pending_pos = at
        if key not in self._dialogs:
            self._dialogs[key] = NodeDialog(NODES[key])
        self._dialogs[key].open(_DialogContext(self), step=step, preset=preset)

    def open_tool(self, key, at=None):
        """
        Open a tool's dialog; confirming adds its chain of blocks to the
        workflow as steps, which can then be edited like any others. `at` is where
        on the canvas the chain should start, when it was dropped there.
        """
        self._pending_pos = at
        if key not in self._tool_dialogs:
            self._tool_dialogs[key] = NodeDialog(self.registry.node(key))
        self._tool_dialogs[key].open(_ToolContext(self))

    def _add_tool(self, key, opts, inputs, run=False):
        """
        Lay a tool's chain into the workflow as one group of steps.

        With `run`, the chain is run at once, as the toolbar's tools always were, and a tool
        that adds columns to the spreadsheet does so if its box was ticked.
        """
        tool = self.registry.get(key)
        planned = instantiate(tool, opts)
        source = inputs.get("table", [None])[0]       # None for a tool that takes no table
        group = self.workflow.new_group(key, opts.get("title") or tool.label)
        made, depth = {}, {}
        def actual(s):
            if s == TABLE_INPUT:
                return source
            local, _, output = s.partition(".")
            return source_ref(made[local], output)

        for step in planned:
            wired = {port: [actual(s) for s in sources]
                     for port, sources in step.inputs.items()}
            added = self.workflow.add(step.node, step.options, wired,
                                      NODES[step.node].label, group=group)
            made[step.id] = added.id
            depth[step.id] = 1 + max(
                (depth[s.partition(".")[0]] for sources in step.inputs.values()
                 for s in sources if s.partition(".")[0] in depth), default=-1)
        if self._pending_pos:
            items = [(made[step.id], depth[step.id],
                      layout.node_height(len(NODES[step.node].spec.ports), output=True))
                     for step in planned]
            for node_id, (x, y) in layout.arrange_group(items, self._pending_pos).items():
                self.workflow.set_position(node_id, x, y)
        self._pending_pos = None
        self._changed()
        if run:
            target = sheet_step(tool, opts)
            asyncio.ensure_future(self._run_added([made[step.id] for step in planned],
                                                  made.get(target) if target else None))
        return made

    async def _run_added(self, step_ids, sheet_id):
        """Run the steps of a tool just added, then write its table to the spreadsheet if asked."""
        await self._run(step_ids)
        if sheet_id and self._set_rows and self._status.get(sheet_id, ("",))[0] == OK:
            self._set_rows(self.engine.batch_for(sheet_id)[0])

    def import_legacy(self, records):
        """
        Add the outputs an older project kept on its Outputs tab to the workflow, each as the
        tool that made it, reading the spreadsheet. Nothing is run.

        Args:
            records: [{"tool", "title", "options"}] as the project file lists them

        Returns:
            (added, skipped): skipped are those of a tool this version lacks
        """
        added = skipped = 0
        for record in records:
            key, options = record.get("tool"), dict(record.get("options") or {})
            if key in LEGACY_TOOLS:
                # Saved when bivariate tools were separate; the same tool now.
                key, options["mode"] = LEGACY_TOOLS[key][0], LEGACY_TOOLS[key][1]
            if self.registry.get(key) is None:
                skipped += 1
                continue
            if record.get("title") and not options.get("title"):
                options["title"] = record["title"]
            self._pending_pos = None
            self._add_tool(key, options, {"table": [DATA]})
            added += 1
        return added, skipped

    async def run_workflow(self):
        """Run every step (for a restored session, which should show what it had)."""
        await self._run(None)

    # ---------------------------------------------------------- engine callbacks

    @staticmethod
    def _with_preview(report):
        """A step that showed a table but no plot gets a few rows of it for its thumbnail."""
        if isinstance(report, StepOutput) and not report.charts and report.preview is None:
            preview = first_preview()
            if preview is not None:
                return report._replace(preview=preview)
        return report

    def _compute(self, step, inputs):
        begin_previews()
        batch, report = nodes.compute(step, inputs)
        report = self._with_preview(report)
        if self._quiet and report is not None:
            self._unplaced.add(step.id)
        return batch, report

    def _render_graph(self, step, inputs):
        begin_previews()
        return self._with_preview(nodes.render(step, inputs))

    # ------------------------------------------------------------------ editing

    def _changed(self):
        self._rebuild()
        self.notify_changed()

    def notify_changed(self):
        """Tell the owner the workflow differs from what was last saved."""
        if self._on_change:
            self._on_change()

    # ------------------------------------------------------------------- outputs
    # A step's output belongs to its block: it is kept here, shown in a viewer the block opens,
    # and thrown away when the step changes, as the Outputs tab's cards used to be.

    # A step that made a table can always show it, whatever else it reports.
    TABLE_ROWS_SHOWN = MAX_TABLE_ROWS

    def _made_table(self, step_id):
        return (self._status.get(step_id, ("",))[0] == OK
                and self.workflow.type_of(step_id, self._specs) == TABLE)

    def has_output(self, step_id):
        return step_id in self._outputs or self._made_table(step_id)

    def thumbnail(self, step_id):
        """The data URL of a step's thumbnail, or "" while it has none."""
        return self._thumbs.get(step_id, "")

    def _output_of(self, step_id):
        """What a step shows: its own output, and its table too when it made one."""
        output = self._outputs.get(step_id)
        if not self._made_table(step_id):
            return output
        if step_id not in self._table_views:
            rows = self.engine.batch_for(step_id)[0]
            titles, cells, total = table_cells(rows, limit=self.TABLE_ROWS_SHOWN)
            note = (f"{total:,} row{'s' if total != 1 else ''} × {len(titles)} column"
                    f"{'s' if len(titles) != 1 else ''}"
                    + (f"; the first {self.TABLE_ROWS_SHOWN:,} are shown" if total > len(cells) else "")
                    + ". Click a column's arrow to sort.")
            table = Div(P(note, style={"font-size": "13px", "color": "#555", "margin": "12px 0 6px 0"}),
                        result_table(titles, cells, sortable=True))
            body = Div(output.body, table) if output is not None else table
            self._table_views[step_id] = StepOutput(
                output.title if output is not None else self._numbered(self.workflow.get(step_id)),
                body, output.charts if output is not None else [],
                output.tabview if output is not None else None)
        return self._table_views[step_id]

    def _output_viewer(self):
        if self._viewer is None:
            self._viewer = OutputViewer(self._on_save)
        return self._viewer

    def has_message(self, step_id):
        """Did this step fail, or get skipped, with something to read?"""
        status, message = self._status.get(step_id, ("", ""))
        return status != OK and bool(message)

    def show_message(self, step_id):
        """Show in full why a step failed or was skipped — the block's line is cut to fit."""
        if not self.has_message(step_id):
            return
        if self._message_dialog is None:
            self._message_dialog = MessageDialog()
        self._message_dialog.show(self._numbered(self.workflow.get(step_id)),
                                  self._status[step_id][1])

    def show_output(self, step_id):
        """Expand a step's output; for a step that failed, its message."""
        output = self._output_of(step_id)
        if output is None:
            self.show_message(step_id)
            return
        self._viewing = step_id
        self._output_viewer().show(self._numbered(self.workflow.get(step_id)), output)

    def _discard_output(self, step_id):
        self._thumbs.pop(step_id, None)
        self._table_views.pop(step_id, None)
        output = self._outputs.pop(step_id, None)
        if output is None:
            return
        if self._viewing == step_id and self._viewer is not None:
            self._viewer.close()
            self._viewing = None
        for _, chart in output.charts:
            try:
                chart.destroy()
            except Exception:
                pass                    # a plot that never started has nothing to tear down

    async def _write_to_sheet(self, step_id):
        """Replace the spreadsheet with the table a step made, after asking."""
        step = self.workflow.get(step_id)
        if self._sheet_confirm is None:
            self._sheet_confirm = ConfirmDialog("Replace the spreadsheet")
        if not await self._sheet_confirm.ask(
                f"Replace the spreadsheet with the table from {self._numbered(step)}?\n\n"
                "The rows now in it are lost unless you have them saved or loaded again.",
                "Replace", "Keep"):
            return
        self._set_rows(self.engine.batch_for(step_id)[0])
        self._summary.set_text(f"The spreadsheet now holds the table from {self._numbered(step)}.")

    async def _make_thumbnail(self, step_id):
        """Draw the small picture of a step's output: its first plot, or a few rows of its table."""
        await asyncio.sleep(0.4)            # a plot has to have drawn before it can be exported
        output = self._outputs.get(step_id)
        url = ""
        try:
            if output is not None and output.charts:
                url = svg_data_url(await output.charts[0][1].to_svg())
            elif self._made_table(step_id):
                # The table the step made, not a table in its report (a filter's report counts grains).
                titles, cells, _ = table_cells(self.engine.batch_for(step_id)[0], limit=8)
                url = svg_data_url(table_svg(titles, cells))
            elif output is not None and output.preview:
                url = svg_data_url(table_svg(*output.preview))
        except Exception:
            url = ""                        # no picture is better than an error over a block
        still_there = any(step.id == step_id for step in self.workflow.steps)
        if url and still_there and self._outputs.get(step_id) is output:
            self._thumbs[step_id] = url
            self._rebuild()

    def duplicate_step(self, step_id):
        """A copy of a step, wired to the same inputs, a little below it."""
        step = self.workflow.get(step_id)
        made = self.workflow.add(step.tool, copy.deepcopy(step.options),
                                 {port: list(sources) for port, sources in step.inputs.items()},
                                 step.title)
        x, y = self.workflow.position(step_id) or (0.0, 0.0)
        self.workflow.set_position(made.id, x + 36, y + 72)
        self._changed()

    # --------------------------------------------------------------- right-click

    def menu_for(self, kind, key):
        """What a right-click on a block (`node`), a wire (`edge`) or the canvas offers."""
        if kind == "node":
            if key == DATA:
                return step_menu.data_menu() if self._on_view_spreadsheet else []
            output = self._output_of(key) if self.has_output(key) else None
            writes = (self._set_rows is not None
                      and self.workflow.type_of(key, self._specs) == TABLE
                      and self._status.get(key, ("",))[0] == OK)
            return step_menu.node_menu(
                output is not None, bool(output and output.charts), self._on_save is not None,
                bool(output and len(output.charts) > 1), writes,
                can_view_map=self._on_view_map is not None and self.is_on_map(key),
                has_message=self.has_message(key))
        if kind == "selection":
            ids = self._chosen_steps(key.split(","))
            return step_menu.selection_menu(len(ids)) if ids else []
        if kind == "edge":
            return step_menu.edge_menu()
        return step_menu.canvas_menu(bool(self.workflow.steps))

    def menu_action(self, action, kind, key):
        """Do what a right-click menu item said."""
        if kind == "selection":
            ids = self._chosen_steps(key.split(","))
            if action == "run_selected" and ids:
                asyncio.ensure_future(self._run(ids))
            elif action == "delete_selected" and ids:
                asyncio.ensure_future(self._delete_many(ids))
            elif action == "save_tool" and ids:
                self.open_save_tool()
        elif kind == "edge":
            source_target, _, port = key.rpartition(":")
            source, _, target = source_target.partition(">")
            self.disconnect_wire(source, target, port)
        elif kind == "canvas":
            if action == "run_all":
                asyncio.ensure_future(self._run(None))
            elif action == "tidy":
                self.workflow.layout.clear()
                self._changed()
            elif action == "zoom_reset":
                self._canvas.reset_zoom()
            elif action == "clear":
                asyncio.ensure_future(self._clear())
        elif key == DATA:
            if action == "view_sheet" and self._on_view_spreadsheet:
                self._on_view_spreadsheet()
        else:
            step = self.workflow.get(key)
            output = self._output_of(key) if self.has_output(key) else None
            title = self._numbered(step)
            if action == "edit":
                self.open_node(step.tool, step)
            elif action == "run":
                asyncio.ensure_future(self._run(key))
            elif action == "output":
                self.show_output(key)
            elif action == "message":
                self.show_message(key)
            elif action == "download" and output is not None:
                asyncio.ensure_future(self._output_viewer().download(output, title))
            elif action == "save" and output is not None:
                asyncio.ensure_future(self._output_viewer().save(output, title))
            elif action == "to_sheet":
                asyncio.ensure_future(self._write_to_sheet(key))
            elif action == "view_map" and self._on_view_map:
                self._on_view_map(key)
            elif action == "duplicate":
                self.duplicate_step(key)
            elif action == "delete":
                asyncio.ensure_future(self._delete(key))

    # ------------------------------------------------------------------- the map
    # The Maps tab makes watersheds and fetches tables; they live on the canvas as source blocks
    # holding what the map made, so the rest of the workflow reads them like any other step.

    def is_on_map(self, step_id):
        """Does this block hold something the Maps tab can show?"""
        step = self.workflow.get(step_id)
        return step.tool == "watershed" and bool(step.options.get("watershed"))

    def watershed_blocks(self):
        """[(step id, name, the stored watershed)] for the watersheds on the canvas."""
        found = []
        for step in self.workflow.steps:
            held = step.options.get("watershed") if step.tool == "watershed" else None
            if held:
                found.append((step.id, step.title or held.get("name") or "Watershed", held))
        return found

    def add_from_map(self, tool_key, options, title="", inputs=None, run=True):
        """
        Put a block the Maps tab made onto the canvas, and run it so its output is ready.

        Args:
            inputs: {port: [source ids]} for a block that reads others (a hydrograph of a fetched
                table)
            run: run it now; False when the caller runs several steps together (`run_steps`)

        Returns:
            the step's id
        """
        self._pending_pos = None
        step = self.workflow.add(tool_key, options, inputs or {}, title or NODES[tool_key].label)
        if title:
            step.options["title"] = title
        self._status.pop(step.id, None)
        self._changed()
        if run:
            self.run_steps([step.id])
        return step.id

    def run_steps(self, step_ids):
        """Run these steps (and what they read) in the background."""
        asyncio.ensure_future(self._run(list(step_ids)))

    # ---------------------------------------------------------- canvas wiring

    def connect_wire(self, source, step_id, port):
        """A wire was dropped on a port of the canvas."""
        try:
            self.workflow.connect(self._specs, source, step_id, port)
        except ValueError as error:
            self._summary.set_text(str(error))
            self._rebuild()
            return
        self._stale([step_id] + self.workflow.dependents(step_id))
        self._changed()

    def disconnect_wire(self, source, step_id, port):
        """A wire was taken off a port of the canvas."""
        self.workflow.disconnect(step_id, port, source)
        self._stale([step_id] + self.workflow.dependents(step_id))
        self._changed()

    def _step_name(self, step):
        return step.title or NODES[step.tool].label if step.tool in NODES else step.tool

    def selected_steps(self):
        """The steps selected on the canvas (not the spreadsheet block), in workflow order."""
        return self._chosen_steps(self._canvas.selected_ids()) if self._canvas is not None else []

    def open_save_tool(self):
        """Open Save as tool, which makes the tool from what is selected, else from what you choose."""
        if not self.workflow.steps:
            self.say("Add some steps first; a tool is made from steps.")
            return
        if self._save_tool is None:
            self._save_tool = SaveToolDialog(self)
        self._save_tool.open()

    def number_of(self, step):
        """A step's number: 1, 2 for what reads the spreadsheet, 1.1 for the first step off 1, ..."""
        return self.workflow.numbers().get(step.id, "?")

    def _numbered(self, step):
        return f"Step {self.number_of(step)}: {self._step_name(step)}"

    def _add_step(self, tool_key, opts, inputs):
        title = opts.get("title") or NODES[tool_key].label
        step = self.workflow.add(tool_key, opts, inputs, title)
        if self._pending_pos:
            self.workflow.set_position(step.id, *self._pending_pos)
        self._pending_pos = None
        self._status.pop(step.id, None)
        self._changed()
        return step

    def _replace_step(self, step_id, opts, inputs):
        """Apply an edit from the dialog; what depended on the step is stale."""
        step = self.workflow.get(step_id)
        spec = self._specs[step.tool]
        was = self.workflow.type_of(step_id, self._specs)
        becomes = spec.output_type(opts)
        dependents = self.workflow.dependents(step_id)
        if was != becomes and dependents:
            self._summary.set_text(
                f"Not changed: this step would make {TYPE_LABELS[becomes].lower()} "
                f"instead of {TYPE_LABELS[was].lower()}, and other steps read it. "
                "Delete them first.")
            return
        # What the dialog does not edit (a stored watershed) is the block's content, not a choice.
        for key in getattr(NODES[step.tool], "keep", ()):
            if key in step.options and key not in opts:
                opts[key] = step.options[key]
        try:
            self.workflow.replace(step_id, options=opts, inputs=inputs,
                                  title=opts.get("title") or NODES[step.tool].label)
        except ValueError as error:
            self._summary.set_text(str(error))
            return
        self._stale([step_id] + dependents)
        self._changed()

    def _stale(self, step_ids):
        """Drop what a changed step and its dependents showed: they no longer say true."""
        for step_id in step_ids:
            self._status.pop(step_id, None)
            self._unplaced.discard(step_id)
            self._discard_output(step_id)

    def _remove(self, step_id):
        removed = self.workflow.remove(step_id)
        self._stale(removed)
        for gone in removed:
            self.engine.invalidate(gone)
        self._changed()

    def _chosen_steps(self, ids):
        """The ids that are steps (the spreadsheet block is not one), in workflow order, without repeats."""
        wanted = set(ids)
        return [s.id for s in self.workflow.steps if s.id in wanted]

    async def _delete_many(self, ids):
        """Delete several blocks at once, asking once about all that would go."""
        chosen = self._chosen_steps(ids)
        if not chosen:
            return
        doomed = set(chosen)
        for step_id in chosen:
            doomed |= set(self.workflow.dependents(step_id))
        extra = len(doomed) - len(chosen)
        if len(chosen) > 1 or extra:
            if self._confirm is None:
                self._confirm = ConfirmDialog("Delete step")
            message = f"Delete {len(chosen)} step{'s' if len(chosen) != 1 else ''}"
            if extra:
                message += (f", and the {extra} other step{'s' if extra != 1 else ''} "
                            f"that read{'' if extra != 1 else 's'} {'them' if len(chosen) > 1 else 'it'}")
            if not await self._confirm.ask(message + "?", "Delete", "Keep"):
                return
        for step_id in chosen:
            if any(s.id == step_id for s in self.workflow.steps):      # an earlier one may have taken it
                self._remove(step_id)

    async def _delete(self, step_id):
        if step_id == DATA:
            return                          # the spreadsheet block stays
        dependents = self.workflow.dependents(step_id)
        if dependents:
            if self._confirm is None:
                self._confirm = ConfirmDialog("Delete step")
            plural = "s" if len(dependents) != 1 else ""
            if not await self._confirm.ask(
                    f"Other steps read this one. Deleting it also deletes "
                    f"{len(dependents)} step{plural} that depend on it.",
                    "Delete", "Keep"):
                return
        self._remove(step_id)

    async def _clear(self):
        if not self.workflow.steps:
            return
        if self._confirm is None:
            self._confirm = ConfirmDialog("Delete step")
        if await self._confirm.ask("Remove every step from the workflow?",
                                   "Remove all", "Keep"):
            for step in list(self.workflow.steps):
                if step.id in {s.id for s in self.workflow.steps}:
                    self._remove(step.id)

    # ---------------------------------------------------------------------- run

    async def _run(self, step_id):
        """Run the whole workflow (None), one step and what it needs, or a list of steps."""
        if not self.workflow.steps:
            self._summary.set_text("Nothing to run — add a step first.")
            return

        def work():
            if step_id is None:
                results = self.engine.run_all()
            elif isinstance(step_id, (list, tuple)):
                results = [self.engine.run_step(i) for i in step_id]
            else:
                results = [self.engine.run_step(step_id)]
            self._place_cards(results)
            return results

        try:
            results = await self._overlay.run(work, "Running workflow…")
        except Exception as error:
            self._summary.set_text(f"The workflow stopped: {error}")
            return

        for result in results:
            self._status[result.step_id] = (result.status, result.message)
        ok = sum(1 for r in results if r.status == OK)
        self._summary.set_text(
            f"{ok} of {len(results)} step{'s' if len(results) != 1 else ''} ran.")
        self._rebuild()

    def _place_cards(self, results):
        """Keep each step's result with its block, replacing its old output."""
        for result in results:
            step = self.workflow.get(result.step_id)
            computes = not self._specs[step.tool].is_graph
            show = (result.fresh or step.id in self._unplaced) if computes else True
            if result.status == OK and computes and result.fresh:
                # A table made again is a different table: forget the one shown before.
                self._table_views.pop(step.id, None)
                self._thumbs.pop(step.id, None)
                asyncio.ensure_future(self._make_thumbnail(step.id))
            if result.status != OK or not show or not isinstance(result.report, StepOutput):
                continue
            self._unplaced.discard(step.id)
            self._discard_output(step.id)
            self._outputs[step.id] = result.report
            asyncio.ensure_future(self._make_thumbnail(step.id))

    # ------------------------------------------------------------- persistence

    def to_dict(self):
        """The tab's state for the project file: the steps, and the user's tools."""
        document = self.workflow.to_dict()
        tools = self.registry.user_tools()
        if tools:
            document["tools"] = tools
        return document

    def load(self, document):
        """
        Replace the workflow with a saved one. Nothing runs; its cards, status
        and cached results belong to the workflow it replaces, so they go.

        Raises:
            ValueError: if the document is not a well-formed workflow
        """
        loaded = Workflow.from_dict(document)
        for step in list(self.workflow.steps):
            self._discard_output(step.id)
        self.workflow.steps = loaded.steps
        self.workflow.layout = loaded.layout
        self.workflow.groups = loaded.groups
        self.workflow.snap_grid = loaded.snap_grid
        skipped = self.registry.load_user_tools(document.get("tools"))
        self._status.clear()
        self._unplaced.clear()
        if self.engine:
            self.engine.invalidate()
        self._summary.set_text(
            "Not loaded, because a block they need is missing: " + ", ".join(skipped) + "."
            if skipped else "")
        self._changed()

    def load_or_clear(self, document):
        """`load`, but an unusable workflow leaves an empty one and says why."""
        try:
            self.load(document or {"version": 2, "steps": []})
        except ValueError as error:
            self.load({"version": 2, "steps": []})
            self._summary.set_text(f"The saved workflow was not loaded: {error}")

    # ----------------------------------------------------------------- display

    def _rebuild(self):
        if self.engine is None:
            return
        self._empty.style.display = "none" if self.workflow.steps else "block"
        self._show_snap_switch()
        self._canvas.refresh()

    def _show_snap_switch(self):
        """Draw the Snap to grid switch as the workflow has it."""
        on = bool(self.workflow.snap_grid)
        self._snap_track.style.update({"background-color": "#2e9d57" if on else "#b8c2cc"})
        self._snap_knob.style.update({"left": "16px" if on else "2px"})
        self._snap_switch.set_attribute("aria-pressed", "true" if on else "false")

    def _source_label(self, source_id):
        """What a source is called in a picker: the step, which of its outputs when it
        has several, and the kind of data."""
        if source_id == DATA:
            return "Spreadsheet"
        step_id, name = split_source(source_id)
        step = self.workflow.get(step_id)
        spec = self._specs.get(step.tool)
        produced = self.workflow.type_of(source_id, self._specs)
        which = (spec.output_label_of(name)
                 if spec is not None and len(spec.output_names()) > 1 else "")
        return (f"{self._numbered(step)}{' → ' + which if which else ''} "
                f"({TYPE_LABELS.get(produced, '?').lower()})")


class _ToolContext:
    """What a tool's dialog needs here: the same sources a block could read, and an
    Add button that lays the whole chain in."""

    submit_label = "Add and run"

    def __init__(self, panel):
        self._panel = panel
        self._blocks = _DialogContext(panel)

    def choices(self, node, port, before=None):
        return self._blocks.choices(node, port, before)

    def type_of(self, source_id):
        return self._blocks.type_of(source_id)

    def batch(self, source_id):
        return self._blocks.batch(source_id)

    def submit(self, key, opts, inputs, step_id=None):
        self._panel._add_tool(key, opts, inputs, run=True)


class _DialogContext:
    """What a node's dialog needs from this panel's workflow."""

    def __init__(self, panel):
        self._panel = panel

    def choices(self, node, port, before=None):
        panel = self._panel
        return [(i, panel._source_label(i))
                for i in panel.workflow.sources_for(panel._specs, port, before=before)]

    def type_of(self, source_id):
        return self._panel.workflow.type_of(source_id, self._panel._specs)

    def batch(self, source_id):
        panel = self._panel
        # Preparing a dialog should not draw anything; if it has to compute an
        # upstream step that makes a card, that card is shown the next time it
        # runs.
        panel._quiet = True
        try:
            return panel.engine.batch_for(source_id)
        finally:
            panel._quiet = False

    def submit(self, tool_key, opts, inputs, step_id=None):
        if step_id:
            self._panel._replace_step(step_id, opts, inputs)
        else:
            self._panel._add_step(tool_key, opts, inputs)
