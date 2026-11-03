"""Point labels on the canvas legends that step aside instead of overlapping."""

# Where to try a label, relative to its point (pixels): right of it, then above and below.
OFFSETS = [(9, 0), (9, -11), (9, 11), (9, -22), (9, 22)]
HEIGHT = 11  # label box height


def place_label(ctx, text, x, y, placed):
    """Draw text beside (x, y) at the first offset whose box misses every box in placed (and
    add its box there); if none is free, at the first offset."""
    width = ctx.measureText(text).width
    boxes = [(x + dx, y + dy - HEIGHT / 2, width, HEIGHT) for dx, dy in OFFSETS]
    box = next((b for b in boxes if not any(_overlap(b, other) for other in placed)), boxes[0])
    placed.append(box)
    ctx.textAlign = "left"
    ctx.textBaseline = "middle"
    ctx.fillText(text, box[0], box[1] + HEIGHT / 2)


def _overlap(a, b):
    return a[0] < b[0] + b[2] and b[0] < a[0] + a[2] and a[1] < b[1] + b[3] and b[1] < a[1] + a[3]
