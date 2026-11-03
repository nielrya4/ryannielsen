"""The land-cover legend: the truncated agricultural / urban / wilderness triangle of the land-cover
figures, drawn on a canvas, with each watershed as a dot in its catchment color."""
import math

import js
from antioch.elements import Canvas

from . import config as c
from .labels import place_label
from .data import CONFIG

WIDTH, HEIGHT = 300, 268   # CSS pixels
SIDE = 196                 # triangle side
LEFT = (WIDTH - SIDE) / 2
BASE = HEIGHT - 50         # y of the triangle's base
SQRT3_2 = math.sqrt(3) / 2
GRID_STEP = 0.05           # gridlines and ticks every 5 points of agricultural / urban share
TICK_FONT = f"10.5px {c.FONT}"
CORNER_FONT = f"11px {c.FONT}"
POINT_FONT = f"600 10px {c.FONT}"


def ternary_key(spec):
    """A Canvas drawing the triangle and spec["points"] (x, y in triangle units; color)."""
    ratio = js.window.devicePixelRatio or 1
    canvas = Canvas(width=int(WIDTH * ratio), height=int(HEIGHT * ratio),
                    style={"width": f"{WIDTH}px", "height": f"{HEIGHT}px", "display": "block",
                           "margin": "4px 0 6px"})
    ctx = canvas.dom_element.getContext("2d")
    ctx.scale(ratio, ratio)
    w_min = CONFIG["ternary"]["w_min"]
    span = 1 - w_min

    for cell in CONFIG["ternary"]["cells"]:
        *xy, color = cell
        _path(ctx, list(zip(xy[0::2], xy[1::2])))
        ctx.fillStyle = color
        ctx.strokeStyle = color  # hairline in the same color closes the seams between cells
        ctx.lineWidth = 0.6
        ctx.fill()
        ctx.stroke()

    # Gridlines at each step of agricultural, urban and wilderness share (as on the figures).
    ctx.strokeStyle = "rgba(255, 255, 255, 0.7)"
    ctx.lineWidth = 0.8
    steps = [k * GRID_STEP / span for k in range(1, round(span / GRID_STEP))]
    for t in steps:
        for line in ([(1 - t, 0), ((1 - t) / 2, (1 - t) * SQRT3_2)],
                     [(t, 0), (1 - (1 - t) / 2, (1 - t) * SQRT3_2)],
                     [(t / 2, t * SQRT3_2), (1 - t / 2, t * SQRT3_2)]):
            _path(ctx, line, close=False)
            ctx.stroke()

    _path(ctx, [(0, 0), (1, 0), (0.5, SQRT3_2)])
    ctx.strokeStyle = c.INK
    ctx.lineWidth = 1
    ctx.stroke()

    score = spec["score"]
    fmt = (lambda v: f"{v:.2f}") if score else (lambda v: f"{v:.0%}")
    ctx.fillStyle = c.INK_MUTED
    ctx.font = TICK_FONT
    for k, t in enumerate(steps, start=1):
        v = k * GRID_STEP
        _text(ctx, fmt(v), (1 - t, 0), "center", "top", dy=4)                         # ag
        _text(ctx, fmt(v), (1 - (1 - t) / 2, (1 - t) * SQRT3_2), "left", "middle", dx=5)  # urban
        _text(ctx, fmt(w_min + v), (t / 2, t * SQRT3_2), "right", "middle", dx=-5)    # wild.
    ctx.font = CORNER_FONT
    ctx.fillStyle = c.INK
    _text(ctx, f"{fmt(1)} wilderness", (0.5, SQRT3_2), "center", "bottom", dy=-5)
    _text(ctx, f"{fmt(span)} agricultural", (0, 0), "left", "top", dy=20, dx=-30)
    _text(ctx, f"{fmt(span)} urban", (1, 0), "right", "top", dy=20, dx=30)

    placed = []
    for point in spec["points"]:
        x, y = _px(point["x"], point["y"])
        ctx.beginPath()
        ctx.arc(x, y, 5, 0, 2 * math.pi)
        ctx.fillStyle = point["color"]
        ctx.fill()
        ctx.lineWidth = 1.5
        ctx.strokeStyle = c.OUTLINE
        ctx.stroke()
        ctx.beginPath()
        ctx.arc(x, y, 6, 0, 2 * math.pi)
        ctx.lineWidth = 0.75
        ctx.strokeStyle = c.INK
        ctx.stroke()
        # Numbered, to match the legend rows.
        ctx.font = POINT_FONT
        ctx.fillStyle = c.INK
        place_label(ctx, point["label"], x, y, placed)
    return canvas


def _px(x, y):
    return LEFT + x * SIDE, BASE - y * SIDE


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


def _text(ctx, text, at, align, baseline, dx=0, dy=0):
    x, y = _px(*at)
    ctx.textAlign = align
    ctx.textBaseline = baseline
    ctx.fillText(text, x + dx, y + dy)
