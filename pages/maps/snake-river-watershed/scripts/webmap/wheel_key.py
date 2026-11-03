"""The polymer-mix legend: a PCA biplot of the samples' polymer mixes over the stretched color
wheel that colors them (export_web_map.polymer_wheel), drawn on a canvas."""
import math

import js
from antioch.elements import Canvas

from . import config as c
from .labels import place_label

WIDTH, HEIGHT = 300, 290  # CSS pixels
CENTER = (WIDTH / 2, 134)
SCALE = 82                 # pixels per plot unit (the farthest sample is at 1); leaves room
                           # for the rim labels inside the canvas
RIM_GAP = 8                # anchor labels sit this far outside the wheel
ANCHOR_FONT = f"600 10.5px {c.FONT}"
POINT_FONT = f"600 10px {c.FONT}"
AXIS_FONT = f"10px {c.FONT}"


def wheel_key(spec):
    """A Canvas drawing the wheel's cells, the polymer lines and the numbered samples."""
    ratio = js.window.devicePixelRatio or 1
    canvas = Canvas(width=int(WIDTH * ratio), height=int(HEIGHT * ratio),
                    style={"width": f"{WIDTH}px", "height": f"{HEIGHT}px", "display": "block",
                           "margin": "4px 0 6px"})
    ctx = canvas.dom_element.getContext("2d")
    ctx.scale(ratio, ratio)

    for cell in spec["cells"]:
        *xy, color = cell
        _path(ctx, list(zip(xy[0::2], xy[1::2])))
        ctx.fillStyle = color
        ctx.strokeStyle = color  # hairline in the same color closes the seams between cells
        ctx.lineWidth = 0.6
        ctx.fill()
        ctx.stroke()

    # PC axes, faint; the share of variance they hold is the caption.
    ctx.strokeStyle = "rgba(255, 255, 255, 0.6)"
    ctx.lineWidth = 0.8
    r = spec["radius"]
    for line in ([(-r, 0), (r, 0)], [(0, -r), (0, r)]):
        _path(ctx, line, close=False)
        ctx.stroke()
    ctx.fillStyle = c.INK_MUTED
    ctx.font = AXIS_FONT
    ctx.textAlign = "center"
    ctx.textBaseline = "bottom"
    ctx.fillText(f"{spec['axes'][0]} across · {spec['axes'][1]} up, of the variance",
                 WIDTH / 2, HEIGHT - 2)

    # Polymer lines from the center: the anchors (which set the hues) heavier and labelled
    # just outside the rim, in their direction; the rest faint and unlabelled.
    for line in spec["lines"]:
        _path(ctx, [(0, 0), (line["x"], line["y"])], close=False)
        ctx.strokeStyle = c.POPUP_INK if line["anchor"] else "rgba(11, 11, 11, 0.4)"
        ctx.lineWidth = 1.4 if line["anchor"] else 0.8
        ctx.stroke()
        if not line["anchor"]:
            continue
        length = math.hypot(line["x"], line["y"]) or 1
        ux, uy = line["x"] / length, line["y"] / length
        x, y = _px(ux * r, uy * r)
        ctx.font = ANCHOR_FONT
        ctx.fillStyle = c.INK
        ctx.textAlign = "left" if ux > 0.3 else "right" if ux < -0.3 else "center"
        ctx.textBaseline = "top" if uy < -0.3 else "bottom" if uy > 0.3 else "middle"
        ctx.fillText(line["label"], x + RIM_GAP * ux, y - RIM_GAP * uy)

    # Samples: a dot in the color its watershed gets, numbered.
    placed = []
    for point in spec["points"]:
        x, y = _px(point["x"], point["y"])
        ctx.beginPath()
        ctx.arc(x, y, 6, 0, 2 * math.pi)
        ctx.fillStyle = point["color"]
        ctx.fill()
        ctx.lineWidth = 1.5
        ctx.strokeStyle = c.OUTLINE
        ctx.stroke()
        ctx.beginPath()
        ctx.arc(x, y, 7, 0, 2 * math.pi)
        ctx.lineWidth = 0.75
        ctx.strokeStyle = c.POPUP_INK
        ctx.stroke()
        ctx.font = POINT_FONT
        ctx.fillStyle = c.POPUP_INK
        place_label(ctx, point["label"], x, y, placed)
    return canvas


def _px(x, y):
    return CENTER[0] + x * SCALE, CENTER[1] - y * SCALE


def _path(ctx, points, close=True):
    ctx.beginPath()
    for i, (x, y) in enumerate(points):
        px, py = _px(x, y)
        if i == 0:
            ctx.moveTo(px, py)
        else:
            ctx.lineTo(px, py)
    if close:
        ctx.closePath()

