"""
Saving the workflow, or one tool's steps, as a tool of the user's own, and
managing the tools saved that way.

The dialog says what the tool is called and which toolbox it lives in, which steps
to take (the whole workflow, or just a group a tool added), and which of their
options the tool should ask about each time it is run. The rest stay as they are
now. Making the tool is `tool_builder`'s job; this is the form.
"""
from antioch.dom import DOM
from antioch.elements import Button, Div, Input, Option, P, Select, Span
from antioch.event import when
from antioch.macros import Modal

from ui_lib import CheckboxGroup, labeled
from workflow_lib import ToolError

from . import nodes
from .node_dialog import _check_only
from .tool_builder import build_tool, candidates, option_label

NEW_TOOLBOX = "(a new toolbox…)"
WHOLE = "whole"
SELECTED = "selected"
BUTTON = {"background-color": "#34495e", "color": "#fff", "border": "none",
          "padding": "7px 16px", "cursor": "pointer", "font-size": "13px",
          "border-radius": "3px"}
SMALL = {"background-color": "#eef1f4", "color": "#333", "border": "1px solid #cfd6dd",
         "padding": "3px 9px", "cursor": "pointer", "font-size": "12px",
         "border-radius": "3px"}
MODAL_STYLE = {"max-width": "640px", "width": "92vw", "min-width": "0"}


class SaveToolDialog:
    """
    Usage:
        dialog = SaveToolDialog(panel)      # the WorkflowPanel
        dialog.open()
    """

    def __init__(self, panel):
        self._panel = panel
        self._selected = []         # the blocks selected when the dialog opened, in workflow order
        self._options = {}          # parameter label -> (step id, option)
        self._name = Input("text", placeholder="e.g. My provenance check",
                           style={"width": "280px"})
        self._toolbox = Select()
        self._new_toolbox = Input("text", placeholder="Toolbox name",
                                  style={"width": "200px", "margin-top": "6px"})
        self._description = Input("text", placeholder="What it is for (optional)",
                                  style={"width": "100%"})
        self._steps = Select()
        self._exposed = CheckboxGroup(all_checked=False, height="190px",
                                      empty_text="This selection has no options")
        self._status = Span("", style={"color": "#b00020", "font-size": "13px"})
        self._toolbox.on('change', lambda e: self._toolbox_changed())
        self._steps.on('change', lambda e: self._list_options())

        save = Button("Save tool", style=dict(BUTTON))

        @when(save.events.click)
        def on_save(sender, *args):
            self._save()

        form = Div(
            P("Turns steps you have wired up into a tool you can run again from the "
              "menus, with a short dialog of its own.",
              style={"color": "#555", "font-size": "13px", "margin": "0 0 14px 0"}),
            labeled("Name", self._name),
            labeled("Toolbox", Div(self._toolbox, self._new_toolbox),
                    "Tools are grouped into toolboxes, like the built-in ones"),
            labeled("Description", self._description),
            labeled("Steps to include", self._steps,
                    "The whole workflow, or just the steps one tool added"),
            labeled("Ask for these each time", self._exposed.element,
                    "Everything not ticked stays as it is now"),
            Div(save, self._status, style={"display": "flex", "gap": "12px",
                                            "align-items": "center"}),
            style={"padding": "16px 18px"})
        self.modal = Modal(title="Save as tool", modal_style=MODAL_STYLE)
        self.modal.set_content(form)
        DOM.add(self.modal.element)

    def open(self):
        panel = self._panel
        self._status.set_text("")
        self._name.value = ""
        self._description.value = ""
        self._fill_toolboxes()
        self._steps.clear()
        # What is selected on the canvas is what the tool is made from, if anything is.
        self._selected = panel.selected_steps()
        if self._selected:
            count = len(self._selected)
            self._steps.add(Option(f"The {count} selected block{'s' if count != 1 else ''}",
                                   value=SELECTED))
        self._steps.add(Option(f"The whole workflow ({len(panel.workflow.steps)} steps)",
                               value=WHOLE))
        for group, info in panel.workflow.groups.items():
            count = len(panel.workflow.members(group))
            self._steps.add(Option(f"{info['title'] or info['tool']} ({count} steps)",
                                   value=group))
        if self._selected:
            self._steps.value = SELECTED
        self._list_options()
        self.modal.open()

    def _fill_toolboxes(self):
        registry = self._panel.registry
        names = [n for n in registry.toolboxes()] or []
        if "My tools" not in names:
            names.append("My tools")
        self._toolbox.clear()
        for name in names:
            self._toolbox.add(Option(name, value=name))
        self._toolbox.add(Option(NEW_TOOLBOX, value=NEW_TOOLBOX))
        self._toolbox.value = "My tools"
        self._new_toolbox.value = ""
        self._toolbox_changed()

    def _toolbox_changed(self):
        self._new_toolbox.style.display = (
            "block" if self._toolbox.value == NEW_TOOLBOX else "none")

    def _chosen_steps(self):
        workflow = self._panel.workflow
        if self._steps.value == SELECTED:
            return [i for i in self._selected if any(s.id == i for s in workflow.steps)]
        if self._steps.value == WHOLE:
            return [s.id for s in workflow.steps]
        return workflow.members(self._steps.value)

    def _list_options(self):
        """Offer every option of the chosen steps; the data choices start ticked."""
        workflow = self._panel.workflow
        ids = self._chosen_steps()
        self._options, labels, ticked = {}, [], []
        for c in candidates(workflow, ids):
            label = option_label(workflow, c)       # numbered as the blocks are on the canvas
            self._options[label] = (c.step_id, c.option)
            labels.append(label)
            if c.exposed_by_default:
                ticked.append(label)
        self._exposed.set_options(labels)
        _check_only(self._exposed, ticked)

    def _save(self):
        panel = self._panel
        toolbox = (self._new_toolbox.value if self._toolbox.value == NEW_TOOLBOX
                   else self._toolbox.value)
        exposed = {self._options[label] for label in self._exposed.values()}
        try:
            tool = build_tool(
                panel.workflow, nodes.specs(), self._chosen_steps(),
                self._name.value, toolbox, self._description.value,
                exposed=exposed, taken=set(panel.registry.tools))
            panel.registry.add(tool)
        except ToolError as error:
            self._status.set_text(str(error))
            return
        self.modal.close()
        panel.say(f"Saved '{tool.label}' in the {tool.toolbox} toolbox. It is in the "
                  "menus now, and saved with the project.")


class ManageToolsDialog:
    """The tools the user has made, with a way to delete each."""

    def __init__(self, panel):
        self._panel = panel
        self._list = Div()
        self.modal = Modal(title="My tools", modal_style=MODAL_STYLE)
        self.modal.set_content(Div(self._list, style={"padding": "16px 18px"}))
        DOM.add(self.modal.element)

    def open(self):
        self._rebuild()
        self.modal.open()

    def _rebuild(self):
        registry = self._panel.registry
        self._list._dom_element.innerHTML = ""
        mine = [(k, t) for k, t in registry.tools.items() if not registry.is_builtin(k)]
        if not mine:
            self._list.add(P("No tools of your own yet. Wire up some steps and use "
                             "\"Save as tool…\".", style={"color": "#6c757d"}))
            return
        for key, tool in mine:
            remove = Button("Delete", style=dict(SMALL))

            @when(remove.events.click)
            def on_remove(sender, *args, key=key):
                registry.remove(key)
                self._rebuild()

            self._list.add(Div(
                Div(Span(tool.label, style={"font-weight": "600"}),
                    Span(f"  in {tool.toolbox}", style={"color": "#6c757d", "font-size": "12px"}),
                    P(tool.description or f"{len(tool.steps)} steps",
                      style={"margin": "2px 0 0 0", "font-size": "12px", "color": "#555"}),
                    style={"flex": "1"}),
                remove,
                style={"display": "flex", "align-items": "center", "gap": "10px",
                       "padding": "8px 0", "border-bottom": "1px solid #edf0f3"}))
