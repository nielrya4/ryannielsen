"""
Geometry for the graph canvas, with no browser in it.

A node is a fixed-width box: a header, a body, one row per input port and, once it has
something to show, an output area (a thumbnail to click). Every height is fixed, so where a port sits is
arithmetic, not something read back from the page — the wires can be drawn, and
tested, without the nodes being on screen.
"""
NODE_WIDTH = 214
HEAD_H = 34
BODY_H = 50
PORT_H = 24
OUTPUT_H = 88
GRID = 22                 # the spacing of the dots on the canvas, and of the grid blocks snap to
GAP_X = 76
GAP_Y = 26
MARGIN = 28
PORT_RADIUS = 7


def path_between(edges, first, second):
    """
    Every block on a path between two blocks, the two included: the blocks that are downstream of
    the earlier one and upstream of the later one, so a chain 1 -> 1.1 -> 1.1.1 gives all three
    from either end, and a fork that leads from one to the other is all there. Wires are followed
    in their direction, and the pair may be given in either order.

    Args:
        edges: [(source id, target id), ...]; ids may repeat

    Returns:
        the set of ids; just the two when neither can be reached from the other (they are on
        different branches)
    """
    forward, backward = {}, {}
    for source, target in edges:
        forward.setdefault(source, set()).add(target)
        backward.setdefault(target, set()).add(source)

    def reach(start, links):
        seen, frontier = {start}, [start]
        while frontier:
            for nxt in links.get(frontier.pop(), ()):
                if nxt not in seen:
                    seen.add(nxt)
                    frontier.append(nxt)
        return seen

    for early, late in ((first, second), (second, first)):
        on_path = reach(early, forward) & reach(late, backward)
        if late in on_path and early in on_path:
            return on_path
    return {first, second}


def boxes_in_rect(boxes, x0, y0, x1, y1):
    """
    The ids of the boxes a rectangle touches, in the order given.

    Args:
        boxes: {id: (x, y, width, height)}
        x0, y0, x1, y1: two opposite corners of the rectangle, in either order; a box that only
            touches the rectangle along an edge counts
    """
    left, right = min(x0, x1), max(x0, x1)
    top, bottom = min(y0, y1), max(y0, y1)
    return [i for i, (x, y, w, h) in boxes.items()
            if x <= right and x + w >= left and y <= bottom and y + h >= top]


def clamp_shift(starts, dx, dy):
    """
    The shift (dx, dy) to apply to a group of things at `starts` ({id: (x, y)}), cut back so
    that none of them goes left of or above the canvas edge: the group stops together and keeps
    its shape, rather than the one at the edge being left behind.
    """
    if not starts:
        return dx, dy
    return (max(dx, -min(x for x, _ in starts.values())),
            max(dy, -min(y for _, y in starts.values())))


def snap(value, grid):
    """`value` moved to the nearest multiple of `grid`."""
    return round(float(value) / grid) * grid


def node_height(port_count, output=False):
    """A node's height: its header, body and ports, and the output area below them if it has one."""
    return HEAD_H + BODY_H + port_count * PORT_H + (OUTPUT_H if output else 0)


def input_anchor(x, y, index):
    """Where a wire meets input port `index` of a node at (x, y)."""
    return x, y + HEAD_H + BODY_H + index * PORT_H + PORT_H / 2


def output_anchor(x, y, index=0):
    """Where a wire leaves a node at (x, y): output `index`, the first at the header
    and any others below it on the same edge."""
    return x + NODE_WIDTH, y + HEAD_H / 2 + index * PORT_H


def edge_endpoints(source_at, outputs, output, target_at, ports, port):
    """
    Both ends of a wire.

    Args:
        source_at, target_at: (x, y) of the two nodes
        outputs: the names of the source node's outputs, top to bottom
        output: which of them the wire leaves
        ports: the names of the target node's input ports, top to bottom
        port: which of them it arrives at

    Returns:
        (x1, y1, x2, y2). The output and the port are looked up separately: where a
        wire leaves has nothing to do with where it arrives.
    """
    leaving = outputs.index(output) if output in outputs else 0
    arriving = ports.index(port) if port in ports else 0
    return (*output_anchor(source_at[0], source_at[1], leaving),
            *input_anchor(target_at[0], target_at[1], arriving))


def wire_path(x1, y1, x2, y2):
    """An SVG cubic curve leaving rightwards and arriving from the left."""
    reach = max(50.0, abs(x2 - x1) / 2)
    return (f"M {x1:.1f} {y1:.1f} C {x1 + reach:.1f} {y1:.1f}, "
            f"{x2 - reach:.1f} {y2:.1f}, {x2:.1f} {y2:.1f}")


def wire_midpoint(x1, y1, x2, y2):
    """The middle of `wire_path`'s curve (its control offsets are symmetric)."""
    return (x1 + x2) / 2, (y1 + y2) / 2


def auto_place(wanted, occupied):
    """
    Positions for nodes that have none, in columns by depth.

    Args:
        wanted: [(id, depth, height), ...] nodes to place
        occupied: {id: (x, y, height)} nodes already on the canvas, which stay
            where they are

    Returns:
        {id: (x, y)} — each new node in its depth's column, below whatever is
        already in that column
    """
    placed = dict(occupied)
    result = {}
    for node_id, depth, height in wanted:
        x = MARGIN + depth * (NODE_WIDTH + GAP_X)
        bottoms = [py + ph for px, py, ph in placed.values()
                   if abs(px - x) < NODE_WIDTH / 2]
        y = max(bottoms) + GAP_Y if bottoms else MARGIN
        result[node_id] = (x, y)
        placed[node_id] = (x, y, height)
    return result


def arrange_group(items, origin):
    """
    Positions for a few nodes laid out together from `origin`, in columns by depth.

    Args:
        items: [(id, depth, height), ...] depth counted within the group
        origin: (x, y) of the top-left of the first column

    Returns:
        {id: (x, y)}
    """
    ox, oy = origin
    bottoms = {}
    placed = {}
    for node_id, depth, height in items:
        y = bottoms.get(depth, oy)
        placed[node_id] = (ox + depth * (NODE_WIDTH + GAP_X), y)
        bottoms[depth] = y + height + GAP_Y
    return placed


def surface_size(boxes, min_width=900, min_height=520):
    """
    How big the scrolling surface must be: every node plus room to drop more.

    Args:
        boxes: [(x, y, height), ...]
    """
    width = max([x + NODE_WIDTH for x, _, _ in boxes], default=0) + 260
    height = max([y + h for _, y, h in boxes], default=0) + 200
    return max(width, min_width), max(height, min_height)
