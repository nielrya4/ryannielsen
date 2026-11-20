"""
Groundwater: drawdown to a pumping well, by the Thiem equation (`sed_stats.thiem`).

    Thiem drawdown   (a source)   the drawdown profile and the contours round a pumping well in a
                                  confined aquifer, from its pumping rate, the aquifer's thickness
                                  and the radius its cone of depression reaches, with either K or the
                                  drawdown measured in the well

The block reads no table: its numbers are typed in its dialog. It makes the profile as a table,
the curve as a line (Polygon) and the contours as circles (Polygon), and the wells as Points, so
the existing Scatterplot draws the semilog cone of depression and the plan-view map.
"""
import math

from workflow_lib import NodeProblem, Output, POINTS, POLYGON, TABLE
from workflow_lib.types import Points, Polygons

from sed_stats import thiem

from ..tables import result_table
from .base import DATA_PAGE, Field, NUMBER, Node, OPTIONS_PAGE, SELECT, StepOutput, TEXT

from antioch.elements import Div, P

NOTE = {"font-size": "13px", "color": "#555", "margin": "0 0 6px 0"}
SOLVES = {"from_drawdown": "Find K from the drawdown in the pumping well",
          "known": "I know K"}
PROFILE_POINTS = 60
CIRCLE_POINTS = 120


def _units(opts):
    return thiem.UNITS[opts.get("units", "us")]


def _g(x):
    return f"{x:,.4g}"


def _aquifer(opts):
    """(units key, Q, b, R, r_w, K, s_w, how K was found), from the options."""
    units = opts.get("units", "us")
    flow, thickness = opts["flow"], opts["thickness"]
    radius, well = opts["radius"], opts["well_radius"]
    try:
        if opts.get("solve", "from_drawdown") == "known":
            k = float(opts["conductivity"])
            s_w = thiem.drawdown(well, flow, k, thickness, radius, well, units)
            how = "given"
        else:
            s_w = float(opts["drawdown_well"])
            k = thiem.conductivity(flow, thickness, radius, well, s_w, units)
            how = "from the drawdown in the pumping well"
    except (TypeError, ValueError) as error:
        raise NodeProblem(str(error)) from None
    return units, flow, thickness, radius, well, k, s_w, how


def _ramp(t):
    """A "#rrggbb" along a blue → grey → red ramp (as the usual drawdown maps colour them), t in 0-1."""
    stops = [(59, 76, 192), (221, 221, 221), (180, 4, 38)]
    t = min(max(t, 0.0), 1.0) * (len(stops) - 1)
    i = min(int(t), len(stops) - 2)
    a, b, f = stops[i], stops[i + 1], t - i
    return "#" + "".join(f"{round(x + (y - x) * f):02x}" for x, y in zip(a, b))


def _circle(radius):
    return [(radius * math.cos(2 * math.pi * i / CIRCLE_POINTS),
             radius * math.sin(2 * math.pi * i / CIRCLE_POINTS)) for i in range(CIRCLE_POINTS)]


def _run_thiem(inputs, opts):
    units, flow, thickness, radius, well, k, s_w, how = _aquifer(opts)
    u = thiem.UNITS[units]
    length = u["length"]
    try:
        monitors = thiem.parse_distances(opts.get("monitors"))
        interval = float(opts.get("interval") or 5)
        levels = thiem.contour_radii(interval, flow, k, thickness, radius, well, units)
    except ValueError as error:
        raise NodeProblem(str(error)) from None

    def s_at(r):
        return thiem.drawdown(r, flow, k, thickness, radius, well, units)

    # the profile, log-spaced from the well's wall to the radius of influence
    distances = [well * (radius / well) ** (i / (PROFILE_POINTS - 1)) for i in range(PROFILE_POINTS)]
    profile = [{"sample": "Cone of depression", "point": i + 1, f"distance_{length}": round(r, 4),
                f"drawdown_{length}": round(s_at(r), 4)} for i, r in enumerate(distances)]
    wells = [{"sample": "Monitoring wells", "well": f"MW-{i + 1}", f"distance_{length}": r,
              f"drawdown_{length}": round(s_at(r), 4)} for i, r in enumerate(monitors)]
    t = thiem.transmissivity(k, thickness)
    summary = [{"sample": "Aquifer", "quantity": name, "value": value, "units": unit, "how": source}
               for name, value, unit, source in (
                   ("Hydraulic conductivity K", round(k, 4), u["k"], how),
                   ("Transmissivity T = K·b", round(t, 4), f"{u['k'].split('/')[0]}/{length}", "K × b"),
                   ("Pumping rate Q", flow, u["flow"], "given"),
                   ("Aquifer thickness b", thickness, length, "given"),
                   ("Radius of influence R", radius, length, "given"),
                   ("Well radius r", well, length, "given"),
                   ("Drawdown in the pumping well", round(s_w, 4), length,
                    "given" if how != "given" else "from K")) ]
    summary += [{"sample": "Monitoring wells", "quantity": f"Drawdown at {_g(r)} {length}",
                 "value": round(s_at(r), 4), "units": length,
                 "how": "beyond the radius of influence: none" if r >= radius else "Thiem"} for r in monitors]

    cone = Polygons(f"Distance from the well ({length})", f"Drawdown ({length})",
                    [("Drawdown", [(r, s_at(r)) for r in distances])], name="Cone of depression",
                    open=True, bare=True, colors={"Drawdown": "#2c7fb8"},
                    note=f"K = {_g(k)} {u['k']}, R = {_g(radius)} {length}.")
    top = max((level for level, _ in levels), default=1.0)
    contours = Polygons(f"Distance east of the well ({length})", f"Distance north of the well ({length})",
                        [(f"{_g(level)} {length}", _circle(r)) for level, r in levels],
                        name="Drawdown contours", bare=True,
                        colors={f"{_g(level)} {length}": _ramp(level / top) for level, _ in levels},
                        note=f"Contours every {_g(interval)} {length} of drawdown, blue (least) to red (most).")
    order = {"Pumping well": 0, "Monitoring wells": 1}
    cone_wells = Points(f"Distance from the well ({length})", f"Drawdown ({length})",
                        [("Pumping well", [well], [s_w])]
                        + ([("Monitoring wells", list(monitors), [s_at(r) for r in monitors])] if monitors else []),
                        name="Wells", meta={"order": order})
    plan_wells = Points(f"Distance east of the well ({length})", f"Distance north of the well ({length})",
                        [("Pumping well", [0.0], [0.0])]
                        + ([("Monitoring wells", list(monitors), [0.0] * len(monitors))] if monitors else []),
                        name="Wells", meta={"order": order},
                        note="Monitoring wells are drawn along the east axis; only their distance matters.")

    notes = [f"Thiem equation for a confined aquifer, steady flow: s = {thiem.FACTOR[units]:.4g}·Q·log₁₀(R/r)/(K·b)"
             + (" (Driscoll's form, with 528 rounded from 527.7)" if units == "us" else " with ln(10)/(2π)")
             + ".",
             "It assumes a confined, uniform, homogeneous aquifer, a fully penetrating well, no regional "
             "gradient, and that the pumping level stays above the top of the aquifer, which this cannot "
             "check. It is not for an unconfined aquifer with large drawdown, nor for flow still changing "
             "(the Theis equation)."]
    if not levels:
        notes.append(f"The contour interval ({_g(interval)} {length}) is larger than the drawdown in the "
                     f"well ({_g(s_w)} {length}), so no contour is drawn.")
    far = [r for r in monitors if r >= radius]
    if far:
        notes.append("Monitoring well" + ("s" if len(far) > 1 else "") + f" at {', '.join(_g(r) for r in far)} {length}"
                     " lie at or beyond the radius of influence, where there is no drawdown.")
    card = StepOutput(opts.get("title") or "Thiem drawdown", Div(
        P(f"K = {_g(k)} {u['k']}; T = {_g(t)}; drawdown in the pumping well {_g(s_w)} {length} "
          f"({how if how != 'given' else 'from K'}).", style={**NOTE, "font-weight": "600"}),
        result_table(["Quantity", "Value", "Units"],
                     [[row["quantity"], _g(row["value"]), row["units"]] for row in summary]),
        *[P(n, style=NOTE) for n in notes]), [], None)
    return {"": [profile], "summary": [summary], "wells": [wells], "cone": [cone],
            "contours": [contours], "profile_wells": [cone_wells], "plan_wells": [plan_wells]}, card


def _validate_thiem(opts, context):
    for key, label in (("flow", "the pumping rate"), ("thickness", "the aquifer thickness"),
                       ("radius", "the radius of influence"), ("well_radius", "the well radius")):
        if not opts.get(key) or opts[key] <= 0:
            return f"Give {label}, above zero."
    if opts["radius"] <= opts["well_radius"]:
        return "The radius of influence must be larger than the well's radius."
    if opts.get("solve", "from_drawdown") == "known":
        if not opts.get("conductivity") or opts["conductivity"] <= 0:
            return "Give the hydraulic conductivity K, above zero."
    elif not opts.get("drawdown_well") or opts["drawdown_well"] <= 0:
        return "Give the drawdown in the pumping well, above zero."
    if opts.get("interval") is not None and opts["interval"] <= 0:
        return "The contour interval must be above zero."
    try:
        thiem.parse_distances(opts.get("monitors"))
    except ValueError as error:
        return str(error)
    return None


def _when_known(o):
    return o.get("solve", "from_drawdown") == "known"


def _when_solving(o):
    return o.get("solve", "from_drawdown") != "known"


thiem_block = Node(
    "thiem", "Thiem drawdown", "Groundwater", [], TABLE,
    [
        Field("units", "Units", SELECT, choices={k: v["label"] for k, v in thiem.UNITS.items()},
              default="us", page=DATA_PAGE,
              hint="Everything below is in these units; mixing them is the usual mistake"),
        Field("flow", "Pumping rate Q", NUMBER, default=60, page=DATA_PAGE, hint="gpm, or m³/day"),
        Field("thickness", "Aquifer thickness b", NUMBER, default=20, page=DATA_PAGE, hint="ft, or m"),
        Field("radius", "Radius of influence R", NUMBER, default=1000, page=DATA_PAGE,
              hint="How far the cone of depression reaches, where the drawdown is zero (ft, or m)"),
        Field("well_radius", "Well radius r", NUMBER, default=1.25, page=DATA_PAGE,
              hint="Half the well's diameter: a 30-inch well is 1.25 ft"),
        Field("solve", "Conductivity", SELECT, choices=SOLVES, default="from_drawdown", page=DATA_PAGE),
        Field("drawdown_well", "Drawdown in the pumping well", NUMBER, default=40, page=DATA_PAGE,
              when=_when_solving, hint="H − h at the well's wall (ft, or m)"),
        Field("conductivity", "Hydraulic conductivity K", NUMBER, default=100, page=DATA_PAGE,
              when=_when_known, hint="gpd/ft², or m/day"),
        Field("monitors", "Monitoring wells at distances", TEXT, default="200, 600", page=OPTIONS_PAGE,
              hint="Distances from the pumping well, separated by commas; the drawdown at each is found"),
        Field("interval", "Contour interval", NUMBER, default=5, page=OPTIONS_PAGE,
              hint="Of drawdown, for the map (ft, or m)"),
    ],
    _run_thiem, _validate_thiem,
    description="Drawdown round a pumping well in a confined aquifer by the Thiem equation. From the "
                "pumping rate, aquifer thickness and the radius its cone of depression reaches, "
                "and either K or the drawdown measured in the well, it finds K (and the "
                "transmissivity), the drawdown at any distance, the cone of depression (a line, "
                "straight on a log distance axis) and circular drawdown contours. It reads no "
                "table; draw its outputs with a Scatterplot.",
    extras=(Output("summary", TABLE, "Aquifer summary"),
            Output("wells", TABLE, "Monitoring wells"),
            Output("cone", POLYGON, "Cone of depression (line)"),
            Output("contours", POLYGON, "Drawdown contours"),
            Output("profile_wells", POINTS, "Wells on the cone"),
            Output("plan_wells", POINTS, "Wells on the map")),
    output_label="Drawdown profile")


GROUNDWATER_NODES = [thiem_block]
