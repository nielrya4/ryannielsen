"""
Running a workflow.

Compute steps are pure — typed batches in, a typed batch out — so their results
are cached and a rerun only redoes what changed. Graph steps draw something, so
they run every time they are asked to.

A cache entry is keyed on the step's tool and options together with the keys of
everything it reads, back to the spreadsheet's own fingerprint. Change a step's
options, or the data, and exactly the steps downstream of the change are stale.

The engine knows nothing about plots or dialogs. It is given two callbacks, so
it can be tested without a browser:

    compute(step, inputs) -> (batch, report)
    render(step, inputs)  -> report

A node that makes several things returns `{"": first_batch, "name": batch, ...}` in
place of a batch; a wire then picks one of them by name (see `workflow.split_source`).

`inputs` maps each port name to a list of batches, one per source wired to it.
A batch is a list of values of one type (see `types`); the spreadsheet is the
batch `[rows]`. A `report` is whatever the caller wants to show for the step
(an element, a message); the engine just hands it back.
"""
import hashlib
import json
from dataclasses import dataclass

from .workflow import DATA, split_source

OK = "ok"
ERROR = "error"
SKIPPED = "skipped"


@dataclass
class StepResult:
    step_id: str
    status: str            # OK, ERROR or SKIPPED
    message: str = ""
    report: object = None
    # False when a compute step's cached result was reused, so there is
    # nothing new to show for it.
    fresh: bool = True


def table_signature(rows):
    """A fingerprint of a table, for deciding whether a cached result is stale."""
    payload = json.dumps(rows, sort_keys=True, default=str)
    return hashlib.md5(payload.encode("utf-8")).hexdigest()


class WorkflowEngine:
    def __init__(self, workflow, get_data, specs, compute, render):
        """
        Args:
            workflow: the Workflow to run
            get_data: `() -> rows`, the spreadsheet as it is now
            specs: {tool key: NodeSpec}
            compute, render: see the module docstring
        """
        self.workflow = workflow
        self._get_data = get_data
        self._specs = specs
        self._compute = compute
        self._render = render
        self._cache = {}      # step id -> (key, {output name: batch}, report)
        self.computed = []    # ids of compute steps actually computed, in order
        self._data = None     # (rows, signature) for the run in progress

    # ------------------------------------------------------------------ values

    def _begin(self):
        """Take the spreadsheet as it is now; one run sees one version of it."""
        rows = self._get_data()
        self._data = (rows, table_signature(rows))

    def batch_for(self, source_id):
        """
        What a step reading `source_id` would receive, computing upstream
        steps as needed.

        Raises:
            RuntimeError: if an upstream step fails; its message says why
        """
        self._begin()
        return self._batch(source_id)[0]

    def _batch(self, source_id):
        """(batch, key) of one source: a whole step, or one named output of it."""
        if source_id == DATA:
            rows, signature = self._data
            return [rows], f"data:{signature}"
        step_id, name = split_source(source_id)
        outputs, _, _, key = self._result(self.workflow.get(step_id))
        if name not in outputs:
            raise RuntimeError(f"'{step_id}' has no output '{name}'.")
        return outputs[name], f"{key}#{name}"

    def _spec(self, step):
        spec = self._specs.get(step.tool)
        if spec is None:
            raise RuntimeError(f"Unknown tool '{step.tool}'.")
        return spec

    def _gather(self, step):
        """
        The inputs for a step, checked against its node's ports.

        Returns:
            (inputs, keys): {port: [batch, ...]} and the keys of what they came from
        """
        spec = self._spec(step)
        inputs, keys = {}, []
        for port in spec.ports:
            ids = step.inputs.get(port.name, [])
            name = port.label or port.name
            if not ids and not port.optional:
                raise RuntimeError(f"'{name}' has nothing connected.")
            if len(ids) > 1 and not port.multiple:
                raise RuntimeError(f"'{name}' takes one input, not {len(ids)}.")
            batches = []
            for source_id in ids:
                actual = self.workflow.type_of(source_id, self._specs)
                if not port.accepts(actual):
                    raise RuntimeError(
                        f"'{name}' cannot read {actual or 'nothing'} from "
                        f"'{source_id}'.")
                batch, key = self._batch(source_id)
                batches.append(batch)
                keys.append(key)
            inputs[port.name] = batches
        return inputs, keys

    def _result(self, step):
        """(outputs, report, fresh, key) of a compute step, from cache when it is current."""
        spec = self._spec(step)
        if spec.is_graph:
            raise RuntimeError(f"'{step.id}' ({spec.label}) does not produce data.")
        inputs, keys = self._gather(step)
        key = self._key(step, keys)
        cached = self._cache.get(step.id)
        if cached and cached[0] == key:
            return cached[1], cached[2], False, key
        batch, report = self._compute(step, inputs)
        outputs = batch if isinstance(batch, dict) else {"": batch}
        self._cache[step.id] = (key, outputs, report)
        self.computed.append(step.id)
        return outputs, report, True, key

    @staticmethod
    def _key(step, source_keys):
        options = json.dumps(step.options, sort_keys=True, default=str)
        ports = json.dumps(step.inputs, sort_keys=True)
        digest = hashlib.md5("|".join(source_keys).encode("utf-8")).hexdigest()
        return f"{step.tool}|{options}|{ports}|{digest}"

    def invalidate(self, step_id=None):
        """Forget cached results: one step's, or all of them."""
        if step_id is None:
            self._cache.clear()
        else:
            self._cache.pop(step_id, None)

    # ------------------------------------------------------------------- runs

    def run_step(self, step_id):
        """Run one step (and whatever it needs) and report how it went."""
        self._begin()
        return self._run(step_id)

    def _run(self, step_id):
        step = self.workflow.get(step_id)
        try:
            if self._spec(step).is_graph:
                inputs, _ = self._gather(step)
                report, fresh = self._render(step, inputs), True
            else:
                _, report, fresh, _ = self._result(step)
        except Exception as error:
            return StepResult(step.id, ERROR, str(error))
        return StepResult(step.id, OK, report=report, fresh=fresh)

    def run_all(self):
        """
        Run every step in order.

        A step reading one that failed is skipped rather than run on nothing,
        and says which step let it down.
        """
        self._begin()
        results = []
        failed = set()
        for step in self.workflow.steps:
            broken = [s for s in step.source_steps if s in failed]
            if broken:
                results.append(StepResult(
                    step.id, SKIPPED, f"'{broken[0]}' did not run."))
                failed.add(step.id)
                continue
            result = self._run(step.id)
            results.append(result)
            if result.status != OK:
                failed.add(step.id)
        return results
