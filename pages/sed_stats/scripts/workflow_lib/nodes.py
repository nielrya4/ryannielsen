"""
What a node is, as far as the workflow needs to know: its inputs and output.

A node either *computes* — typed batches in, a typed batch out — or *graphs*:
typed batches in, something to look at out. The workflow only ever asks three
questions of a node: what can it read (its ports), what does it produce (its
output type, which may depend on its options), and which of the two it is.
What it actually does is handed to the engine as callbacks, so this module
stays free of the browser.
"""
from dataclasses import dataclass


class NodeProblem(ValueError):
    """
    A step cannot do what it was asked, for a reason the user can act on: too
    few samples, an axis paired with itself. Its message is shown as it is, so
    it should read as advice, not as a traceback.
    """


@dataclass(frozen=True)
class Port:
    """
    One input of a node.

    Args:
        name: key in the step's `inputs`
        types: the data types this port accepts
        label: what the dialog calls it
        multiple: take several sources, which the dialog offers as "+ Add
            input" — a graph with more than one series
        optional: may be left empty
    """
    name: str
    types: tuple
    label: str = ""
    multiple: bool = False
    optional: bool = False
    hint: str = ""

    def accepts(self, data_type):
        return data_type in self.types


@dataclass(frozen=True)
class Output:
    """
    A further output of a node that makes more than one thing.

    Args:
        name: how a wire refers to it: "step.name" (the first output, a node's own
            result, is just "step")
        type: the type it produces, or a function of the step's options
        label: what menus and the canvas call it
    """
    name: str
    type: object
    label: str = ""


@dataclass(frozen=True)
class NodeSpec:
    """
    A kind of step.

    Args:
        key: how a saved step names it
        label: what menus and cards call it
        category: the menu it is listed under
        ports: its inputs, in the order the dialog shows them
        output: the type it produces, a function of the step's options when
            that varies (a bivariate Distribution makes rasters, a univariate
            one lines), or None for a graph. This is the node's first output, the
            one a wire from the step itself carries
        extras: further named outputs, for a node where one run yields several
            different things (an NMF: the sources, how much of each every sample
            holds, and the fit). Only a node that really makes them has any
        output_label: what the first output is called, when there are extras
    """
    key: str
    label: str
    category: str
    ports: tuple
    output: object = None
    extras: tuple = ()
    output_label: str = ""

    @property
    def is_graph(self):
        return self.output is None and not self.extras

    def output_type(self, options):
        """The type this node's first output has with `options`, or None for a graph."""
        if callable(self.output):
            return self.output(options)
        return self.output

    def output_names(self):
        """The names of the outputs, the first as "" (it is addressed by the step alone)."""
        return [""] + [extra.name for extra in self.extras]

    def type_of_output(self, name, options):
        """The type of the output called `name` ("" for the first)."""
        if not name:
            return self.output_type(options)
        for extra in self.extras:
            if extra.name == name:
                return extra.type(options) if callable(extra.type) else extra.type
        return None

    def output_label_of(self, name):
        if not name:
            return self.output_label
        return next((e.label or e.name for e in self.extras if e.name == name), name)

    def port(self, name):
        for port in self.ports:
            if port.name == name:
                return port
        raise KeyError(name)
