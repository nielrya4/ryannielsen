"""
A node-and-wire canvas: boxes you drag around and connect.

Generic — it knows nothing about workflows. The caller describes nodes (with
named input ports and an optional output) and the wires between them, says which
connections are allowed, and is told when the user moves a node, drags a wire,
or presses a button. It draws nothing the caller did not describe and changes
nothing the caller does not apply: every edit comes back as a callback and the
caller re-describes the result.

Components:
    GraphCanvas, CanvasNode, CanvasEdge, CanvasFrame - the widget and what it draws
    layout                              - port and wire geometry, auto-placement
"""
from . import layout

__all__ = ["CanvasEdge", "CanvasFrame", "CanvasNode", "GraphCanvas", "layout"]


def __getattr__(name):
    # The widget needs the browser; `layout` does not, so it stays importable
    # (and testable) without one. The widget is loaded the first time it is asked for.
    if name in ("CanvasEdge", "CanvasFrame", "CanvasNode", "GraphCanvas"):
        from . import canvas
        return getattr(canvas, name)
    raise AttributeError(name)
