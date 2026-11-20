"""
The workflow data model: steps and the edits that keep them consistent.

Each step and the spreadsheet can also have a position on the canvas (`layout`);
it is only where a node is drawn and has no effect on what runs. Steps that came
from one tool share a `group`, which the canvas draws as a frame around them; it
too changes nothing about what runs.

A step reads from one or more *sources* — DATA (the spreadsheet) or an earlier
step — through the named input ports of its node. The list order is always a
valid run order: every step comes after each step it reads. All the editing
methods preserve that, which is what lets the engine run the list top to bottom
without sorting it.
"""
from dataclasses import dataclass, field

from .types import TABLE

DATA = "data"


def snap_to_grid(value, grid):
    """`value` moved to the nearest multiple of `grid` (a whole number of pixels)."""
    return round(float(value) / grid) * grid
FORMAT_VERSION = 2


def split_source(source):
    """
    ("step id", "output name") of a source. A step's first output is addressed by
    the step alone ("s3"); another is addressed "s3.weights".
    """
    step_id, _, name = source.partition(".")
    return step_id, name


def step_of(source):
    """The id of the step (or DATA) that a source comes from."""
    return source.partition(".")[0]


def source_ref(step_id, name=""):
    return f"{step_id}.{name}" if name else step_id


class WorkflowError(ValueError):
    """An edit or a document that would break the workflow's structure."""


@dataclass
class Step:
    id: str
    tool: str
    options: dict
    inputs: dict = field(default_factory=dict)   # port name -> [source ids]
    title: str = ""
    group: str = ""                              # the tool it was added with, if any

    @property
    def sources(self):
        """Every source this step reads, in port order, without repeats."""
        found = []
        for ids in self.inputs.values():
            for source in ids:
                if source not in found:
                    found.append(source)
        return found

    @property
    def source_steps(self):
        """The steps (or DATA) those sources come from, without repeats."""
        found = []
        for source in self.sources:
            if step_of(source) not in found:
                found.append(step_of(source))
        return found

    def to_dict(self):
        document = {"id": self.id, "tool": self.tool, "title": self.title,
                    "inputs": {port: list(ids) for port, ids in self.inputs.items()},
                    "options": self.options}
        if self.group:
            document["group"] = self.group
        return document


def _clean_inputs(inputs):
    """A port -> [ids] dict, whatever sloppy shape it was given in."""
    if inputs is None:
        return {}
    cleaned = {}
    for port, ids in dict(inputs).items():
        if isinstance(ids, str):
            ids = [ids]
        cleaned[str(port)] = [str(i) for i in ids]
    return cleaned


@dataclass
class Workflow:
    steps: list = field(default_factory=list)
    layout: dict = field(default_factory=dict)    # id (or DATA) -> [x, y]
    groups: dict = field(default_factory=dict)    # group id -> {"tool": key, "title": text}
    snap_grid: int = 0                            # blocks snap to multiples of this many pixels; 0 is off

    # ---------------------------------------------------------------- queries

    def get(self, step_id):
        for step in self.steps:
            if step.id == step_id:
                return step
        raise WorkflowError(f"No step '{step_id}'.")

    def index_of(self, step_id):
        return self.steps.index(self.get(step_id))

    def numbers(self):
        """
        The number each step goes by, from how the steps fork: those reading the spreadsheet are
        1, 2, 3 in the order they were made; the first step reading step 1 is 1.1, the second 1.2;
        the first reading 1.1 is 1.1.1; and so on. A step that reads several others is numbered
        under the first of them (the first input port), so every step has one place in the tree.

        Derived from the wiring each time, so rewiring or deleting a step renumbers what follows
        it rather than leaving gaps.

        Returns:
            {step id: "1", "1.1", ...}
        """
        label = {DATA: ""}
        children = {}
        for step in self.steps:
            parent = step_of(step.sources[0]) if step.sources else DATA
            if parent not in label:           # reads a step that is not (or not yet) there
                parent = DATA
            children[parent] = children.get(parent, 0) + 1
            label[step.id] = (f"{label[parent]}." if label[parent] else "") + str(children[parent])
        del label[DATA]
        return label

    def dependents(self, step_id):
        """Ids of every step that reads this one, directly or through others."""
        found = []
        frontier = {step_id}
        for step in self.steps:           # list order is run order
            if frontier.intersection(step.source_steps):
                found.append(step.id)
                frontier.add(step.id)
        return found

    def type_of(self, source_id, specs):
        """The data type a source delivers: a table for DATA, else that output of its node."""
        if source_id == DATA:
            return TABLE
        step_id, name = split_source(source_id)
        step = self.get(step_id)
        spec = specs.get(step.tool)
        return spec.type_of_output(name, step.options) if spec else None

    def sources_for(self, specs, port, before=None):
        """
        Sources that `port` could read: DATA, and each output of an earlier step
        whose type the port accepts (a step with several outputs may offer more
        than one, the first as the step's id and the others as "id.name").

        Args:
            specs: {tool key: NodeSpec}
            before: only steps ahead of this step id (for re-pointing a step)
        """
        limit = self.index_of(before) if before else len(self.steps)
        found = [DATA] if port.accepts(TABLE) else []
        for step in self.steps[:limit]:
            spec = specs.get(step.tool)
            for name in (spec.output_names() if spec else []):
                if port.accepts(spec.type_of_output(name, step.options)):
                    found.append(source_ref(step.id, name))
        return found

    # ------------------------------------------------------------------ edits

    def new_group(self, tool, title):
        """Start a group for the steps one tool is about to add; returns its id."""
        numbers = [int(g[1:]) for g in self.groups if g[1:].isdigit()]
        group = f"g{max(numbers, default=0) + 1}"
        self.groups[group] = {"tool": tool, "title": title}
        return group

    def members(self, group):
        """Ids of the steps in a group, in run order."""
        return [step.id for step in self.steps if step.group == group]

    def add(self, tool, options, inputs=None, title="", group=""):
        """Append a step. Each source must be DATA or an existing step."""
        inputs = _clean_inputs(inputs)
        for source in (s for ids in inputs.values() for s in ids):
            if source != DATA:
                self.get(step_of(source))     # raises if it does not exist
        if group and group not in self.groups:
            raise WorkflowError(f"No group '{group}'.")
        step = Step(self._next_id(), tool, dict(options), inputs, title, group)
        self.steps.append(step)
        return step

    def position(self, node_id):
        """Where a node is drawn on the canvas, as (x, y), or None if unplaced."""
        spot = self.layout.get(node_id)
        return (spot[0], spot[1]) if spot else None

    def set_position(self, node_id, x, y):
        """Where a node is drawn; on the grid when snapping is on."""
        if node_id != DATA:
            self.get(node_id)
        if self.snap_grid:
            x, y = snap_to_grid(x, self.snap_grid), snap_to_grid(y, self.snap_grid)
        self.layout[node_id] = [float(x), float(y)]

    def set_snap(self, grid):
        """
        Turn grid snapping on (`grid` pixels, a positive whole number) or off (0). Turning it on
        moves every block placed so far onto the grid.
        """
        self.snap_grid = max(0, int(grid or 0))
        if self.snap_grid:
            for node_id, (x, y) in list(self.layout.items()):
                self.layout[node_id] = [float(snap_to_grid(x, self.snap_grid)),
                                        float(snap_to_grid(y, self.snap_grid))]

    def ancestors(self, step_id):
        """Ids this step reads, directly or through others (DATA excluded)."""
        found = []
        frontier = [step_id]
        while frontier:
            step = self.get(frontier.pop())
            for source in step.source_steps:
                if source != DATA and source not in found:
                    found.append(source)
                    frontier.append(source)
        return found

    def depth_of(self, node_id):
        """How many steps lie between the spreadsheet and this node (DATA is 0)."""
        if node_id == DATA:
            return 0
        step = self.get(node_id)
        return 1 + max((self.depth_of(s) for s in step.source_steps), default=0)

    def remove(self, step_id):
        """
        Remove a step and everything that reads it, since a step without its
        input has nothing to run on.

        Returns the ids removed, the step itself first.
        """
        self.get(step_id)
        removed = [step_id] + self.dependents(step_id)
        self.steps = [s for s in self.steps if s.id not in removed]
        for gone in removed:
            self.layout.pop(gone, None)
        for group in [g for g in self.groups if not self.members(g)]:
            del self.groups[group]          # a frame with nothing in it
        return removed

    def replace(self, step_id, options=None, inputs=None, title=None):
        """Change a step's options, inputs or title in place."""
        step = self.get(step_id)
        if inputs is not None:
            inputs = _clean_inputs(inputs)
            for source in (s for ids in inputs.values() for s in ids):
                self._check_source(step, source)
            step.inputs = inputs
        if options is not None:
            step.options = dict(options)
        if title is not None:
            step.title = title
        return step

    # ----------------------------------------------------------- canvas wiring
    # The canvas lets a wire go to any step that would not make a loop, wherever
    # it sits in the list; the list is put back into run order afterwards.

    def can_connect(self, specs, source_id, step_id, port_name):
        """May `source_id` feed `port_name` of `step_id` — right type, no loop?"""
        step = self.get(step_id)
        spec = specs.get(step.tool)
        if spec is None or step_of(source_id) == step_id:
            return False
        try:
            port = spec.port(port_name)
        except KeyError:
            return False
        if source_id != DATA:
            self.get(step_of(source_id))
            if step_of(source_id) in self.dependents(step_id):
                return False
        return port.accepts(self.type_of(source_id, specs))

    def connect(self, specs, source_id, step_id, port_name):
        """
        Wire a source into a port: a port that takes one source switches to it,
        one that takes several adds it. Returns the inputs the step now has.

        Raises:
            WorkflowError: if the type does not fit or the wire would make a loop
        """
        if not self.can_connect(specs, source_id, step_id, port_name):
            raise WorkflowError(
                f"'{source_id}' cannot feed '{port_name}' of '{step_id}': "
                "wrong kind of data, or it would make a loop.")
        step = self.get(step_id)
        port = specs[step.tool].port(port_name)
        current = list(step.inputs.get(port_name, []))
        if port.multiple:
            if source_id not in current:
                current.append(source_id)
        else:
            current = [source_id]
        self.rewire(step_id, {**step.inputs, port_name: current})
        return self.get(step_id).inputs

    def disconnect(self, step_id, port_name, source_id):
        """Take one wire off a port; the port may be left empty."""
        step = self.get(step_id)
        remaining = [s for s in step.inputs.get(port_name, []) if s != source_id]
        self.rewire(step_id, {**step.inputs, port_name: remaining})

    def rewire(self, step_id, inputs):
        """
        Replace a step's inputs, allowing sources that come later in the list.

        The list is then reordered so every step still follows what it reads,
        changing as little as it can.

        Raises:
            WorkflowError: for an unknown source or one that would make a loop
        """
        step = self.get(step_id)
        inputs = _clean_inputs(inputs)
        for source in (s for ids in inputs.values() for s in ids):
            if source == DATA:
                continue
            self.get(step_of(source))
            if step_of(source) == step_id or step_of(source) in self.dependents(step_id):
                raise WorkflowError(f"A step cannot read '{source}': that would make a loop.")
        step.inputs = inputs
        self._resort()

    def _resort(self):
        """
        Put the list back in run order, disturbing it as little as possible: walk
        it as it stands, and where a step reads one that comes later, bring that
        one (and what it needs) forward just ahead of it.
        """
        by_id = {step.id: step for step in self.steps}
        ordered, done, visiting = [], set(), set()

        def place(step):
            if step.id in done:
                return
            if step.id in visiting:
                raise WorkflowError("The steps contain a loop.")
            visiting.add(step.id)
            for source in step.source_steps:
                if source != DATA:
                    place(by_id[source])
            visiting.discard(step.id)
            done.add(step.id)
            ordered.append(step)

        for step in self.steps:
            place(step)
        self.steps = ordered

    def move(self, step_id, delta):
        """
        Shift a step up (negative) or down (positive) the list.

        Refused, returning False, if that would put a step ahead of one it
        reads or behind one that reads it.
        """
        index = self.index_of(step_id)
        target = index + delta
        if target < 0 or target >= len(self.steps):
            return False
        proposed = list(self.steps)
        proposed.insert(target, proposed.pop(index))
        if not self._ordered(proposed):
            return False
        self.steps = proposed
        return True

    def _check_source(self, step, new_source):
        """Raise unless `step` may read `new_source` without a cycle or a gap."""
        if new_source == DATA:
            return
        source = self.get(step_of(new_source))
        if source.id == step.id or step.id in self.dependents(source.id) \
                or self.index_of(source.id) > self.index_of(step.id):
            raise WorkflowError(
                f"A step cannot read '{new_source}': it comes later or reads this step.")

    @staticmethod
    def _ordered(steps):
        seen = {DATA}
        for step in steps:
            if any(source not in seen for source in step.source_steps):
                return False
            seen.add(step.id)
        return True

    def _next_id(self):
        numbers = [int(s.id[1:]) for s in self.steps
                   if s.id.startswith("s") and s.id[1:].isdigit()]
        return f"s{max(numbers, default=0) + 1}"

    # ------------------------------------------------------------ persistence

    def to_dict(self):
        document = {"version": FORMAT_VERSION,
                    "steps": [step.to_dict() for step in self.steps]}
        known = {DATA} | {step.id for step in self.steps}
        layout = {key: list(spot) for key, spot in self.layout.items() if key in known}
        if layout:
            document["layout"] = layout
        groups = {g: dict(info) for g, info in self.groups.items() if self.members(g)}
        if groups:
            document["groups"] = groups
        if self.snap_grid:
            document["snap"] = self.snap_grid
        return document

    @classmethod
    def from_dict(cls, document):
        """
        Rebuild from `to_dict` output.

        Raises:
            WorkflowError: for anything that is not a well-formed, correctly
                ordered workflow, including one saved before steps had typed
                inputs
        """
        if not isinstance(document, dict) or not isinstance(document.get("steps"), list):
            raise WorkflowError("A workflow needs a list of steps.")
        if document.get("version") != FORMAT_VERSION:
            raise WorkflowError(
                "This workflow was saved by an older version, before analyses "
                "could be chained by data type, and cannot be loaded.")
        steps = []
        for raw in document["steps"]:
            if (not isinstance(raw, dict) or not isinstance(raw.get("id"), str)
                    or not isinstance(raw.get("tool"), str)
                    or not isinstance(raw.get("options"), dict)
                    or not isinstance(raw.get("inputs", {}), dict)):
                raise WorkflowError("A step needs an id, a tool, inputs and options.")
            steps.append(Step(raw["id"], raw["tool"], dict(raw["options"]),
                              _clean_inputs(raw.get("inputs")),
                              str(raw.get("title") or ""), str(raw.get("group") or "")))
        if len({s.id for s in steps}) != len(steps):
            raise WorkflowError("Step ids must be unique.")
        if not cls._ordered(steps):
            raise WorkflowError("A step reads a step that does not come before it.")
        layout = {}
        raw_layout = document.get("layout")
        if isinstance(raw_layout, dict):
            known = {DATA} | {step.id for step in steps}
            for key, spot in raw_layout.items():
                if (key in known and isinstance(spot, (list, tuple)) and len(spot) == 2
                        and all(isinstance(v, (int, float)) and not isinstance(v, bool)
                                for v in spot)):
                    layout[key] = [float(spot[0]), float(spot[1])]
        groups = {}
        raw_groups = document.get("groups")
        if isinstance(raw_groups, dict):
            for key, info in raw_groups.items():
                if isinstance(info, dict) and any(s.group == key for s in steps):
                    groups[str(key)] = {"tool": str(info.get("tool", "")),
                                        "title": str(info.get("title", ""))}
        for step in steps:
            if step.group not in groups:
                step.group = ""
        snap = document.get("snap")
        grid = snap if isinstance(snap, int) and not isinstance(snap, bool) and snap > 0 else 0
        return cls(steps, layout, groups, grid)
