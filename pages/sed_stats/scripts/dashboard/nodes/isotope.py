"""
Blocks for stable-isotope work that are not just a new column.

    Isotopic niche   Points -> Polygon       the standard ellipse (SEA) of each sample,
                                             and its area, overlap and convex hull area
    Fit a line       Points -> Polygon       a straight line through each sample's points,
                                             with a published reference line beside it
    Mixing solutions Table  -> Proportions   every source mix that reproduces a mixture
                                             (IsoSource), as a distribution per source
    End-member mixing Table -> Proportions   the one mix that does, from the mass balance
                                             (EMMA), with a Monte Carlo uncertainty
    End-member splitting Table -> Proportions  what share of each of two precipitation end
                                             members leaves as each kind of streamflow
                                             (EMSA), with the mixing shares as well

The calculations are in `sed_stats.niche`, `regression`, `isosource`, `emma` and `emsa`; this only dresses them as blocks.
"""
from antioch.elements import Div, P

from workflow_lib import NodeProblem, Output, POINTS, POLYGON, Port, PROPORTIONS, TABLE
from workflow_lib.types import Polygons, Proportions

import numpy as np

from sed_stats import emma, emsa, isosource, niche, regression

from ..table_ops import number_of
from ..tables import result_table
from .base import (
    CHECKBOX, DATA_PAGE, DIMENSION, DIMENSIONS, Field, NUMBER, Node, OPTIONS_PAGE, SAMPLE,
    SAMPLES, SELECT, StepOutput, table_of,
)

NOTE = {"font-size": "13px", "color": "#555", "margin": "0 0 6px 0"}
CAPTION = {**NOTE, "margin": "16px 0 6px 0"}

# Craig (1961): the global meteoric water line, delta-2H = 8 * delta-18O + 10.
GMWL = (8.0, 10.0)
REFERENCE_LINES = {
    "none": "None",
    "gmwl": "Global meteoric water line (Craig 1961): δ²H = 8·δ¹⁸O + 10",
    "custom": "A line of your own",
}


def _fmt(value, digits=2):
    return "–" if value is None else f"{value:,.{digits}f}"


# ----------------------------------------------------------------------- niche

NICHE_SHAPES = {
    "sea": "Standard ellipse (holds about 40% of the points)",
    "prediction": "Ellipse holding a chosen share of the points",
    "hull": "Convex hull (total area)",
}
NICHE_LEVELS = {"68": "68%", "90": "90%", "95": "95%", "99": "99%"}


def _outline(name, xs, ys, opts):
    shape = opts.get("shape", "sea")
    if shape == "hull":
        from sed_stats.hull import convex_hull
        return convex_hull(xs, ys)
    scale = niche.prediction_scale(float(opts.get("level", 95)) / 100) if shape == "prediction" else 1.0
    return niche.ellipse(xs, ys, scale)


def _run_niche(inputs, opts):
    batch, cards = [], []
    for points in inputs["points"][0]:
        shapes, rows, skipped, small = [], [], [], []
        for name, xs, ys in points.groups:
            m = niche.metrics(xs, ys)
            outline = _outline(name, xs, ys, opts)
            if not outline:
                skipped.append(name)
                continue
            if m["n"] < niche.COMFORTABLE_POINTS:
                small.append(name)
            shapes.append((name, outline))
            rows.append([name, str(m["n"]), _fmt(m["mean_x"]), _fmt(m["mean_y"]),
                         _fmt(m["sea"]), _fmt(m["seac"]), _fmt(m["ta"]),
                         _fmt(m["cd"]), _fmt(m["mnnd"])])
        if not shapes:
            raise NodeProblem("No sample has three or more points that are not on one "
                              "line, so there is no niche to draw.")
        what = NICHE_SHAPES[opts.get("shape", "sea")].split(" (")[0].lower()
        notes = [f"{points.name or 'Points'}: {what} of each sample."]
        if skipped:
            notes.append(f"No outline for {', '.join(skipped)} (fewer than three points, or "
                         "all on a line).")
        if small:
            notes.append(f"{', '.join(small)} has fewer than {niche.COMFORTABLE_POINTS} points: "
                         "SEAc corrects the bias of a small sample but is still a rough "
                         "estimate there.")
        batch.append(Polygons(points.x_title, points.y_title, shapes,
                              note=" ".join(notes), name=points.name))
        parts = [P(" ".join(notes), style=NOTE),
                 result_table(["Sample", "n", f"Mean {points.x_title}", f"Mean {points.y_title}",
                               "SEA", "SEAc", "TA (hull)", "CD", "MNND"], rows)]
        parts.append(P("SEA is the area of the standard ellipse (π·√det of the covariance, "
                       "Jackson et al. 2011), SEAc the same corrected for sample size by "
                       "(n−1)/(n−2). TA is the convex hull area, which grows with every extra "
                       "point, so compare it only between samples of similar size. CD is the "
                       "mean distance to the centroid, MNND the mean nearest-neighbour "
                       "distance (Layman et al. 2007). Units are the axes' units squared "
                       "(‰²) for areas.", style=NOTE))
        overlap = _overlap_table(shapes)
        if overlap is not None:
            parts.extend([P("Overlap of the drawn outlines, as a share of the sample in the row",
                            style=CAPTION), overlap])
        cards.append(Div(*parts))
    return batch, StepOutput(opts.get("title") or "Isotopic niche", Div(*cards), [], None)


def _overlap_table(shapes):
    if len(shapes) < 2:
        return None
    names = [n for n, _ in shapes]
    area = {n: niche.polygon_area(v) for n, v in shapes}
    rows = []
    for name, outline in shapes:
        row = [name]
        for other, other_outline in shapes:
            if other == name:
                row.append("–")
            else:
                shared = niche.overlap_area(outline, other_outline)
                row.append(f"{100 * shared / area[name]:.0f}%" if area[name] else "–")
        rows.append(row)
    return result_table(["Sample"] + names, rows)


def _validate_niche(opts, context):
    if opts.get("shape") == "prediction" and not opts.get("level"):
        return "Choose the share of points the ellipse should hold."
    return None


niche_block = Node(
    "niche", "Isotopic niche", "Describe",
    [Port("points", (POINTS,), "Points")], POLYGON,
    [
        Field("shape", "Draw", SELECT, choices=NICHE_SHAPES, default="sea", page=DATA_PAGE),
        Field("level", "Share of points", SELECT, choices=NICHE_LEVELS, default="95",
              page=DATA_PAGE, when=lambda o: o.get("shape") == "prediction",
              hint="Assumes the points are bivariate normal, which small samples seldom show"),
    ],
    _run_niche, _validate_niche,
    description="The isotopic niche of each sample: the area its points occupy in two isotope "
                "dimensions (δ¹³C against δ¹⁵N, usually). Gives the standard ellipse area "
                "SEA and SEAc, the convex hull area, and how much the samples' niches overlap; "
                "draw the outlines over the points with a Scatterplot. After SIBER "
                "(Jackson et al. 2011).")


# ------------------------------------------------------------------------- fit

FIT_SCOPES = {"each": "A line for each sample", "all": "One line through all the points",
              "none": "No fit: draw only the reference line"}


def _run_fit(inputs, opts):
    batch, cards = [], []
    method = opts.get("method", "ols")
    for points in inputs["points"][0]:
        scope = opts.get("scope", "each")
        groups = ([("All samples", [x for g in points.groups for x in g[1]],
                    [y for g in points.groups for y in g[2]])]
                  if scope == "all" else [] if scope == "none" else list(points.groups))
        weights = points.meta.get("weights")
        weights_of = {}
        if weights:
            weights_of = ({"All samples": [w for g in points.groups for w in weights.get(g[0], [])]}
                          if opts.get("scope", "each") == "all" else weights)
        shapes, rows, skipped = [], [], []
        for name, xs, ys in groups:
            try:
                fit = regression.linear_fit(xs, ys, method, weights_of.get(name))
            except ValueError:
                skipped.append(name)
                continue
            shapes.append((name, [(fit["x_min"], fit["slope"] * fit["x_min"] + fit["intercept"]),
                                  (fit["x_max"], fit["slope"] * fit["x_max"] + fit["intercept"])]))
            rows.append([name, str(fit["n"]),
                         f"{fit['slope']:.3f} ± {fit['slope_se']:.3f}",
                         f"{fit['intercept']:.3f} ± {fit['intercept_se']:.3f}",
                         f"{fit['r2']:.3f}"])
        if scope == "none" and opts.get("reference", "none") == "none":
            raise NodeProblem("Nothing to draw: choose a reference line, or a fit.")
        if not shapes and scope != "none":
            raise NodeProblem("No group has three or more points that vary in x, so no line "
                              "can be fitted.")
        reference = []
        all_x = [x for g in points.groups for x in g[1]]
        kind = opts.get("reference", "none")
        if kind != "none" and all_x:
            slope, intercept = GMWL if kind == "gmwl" else (opts["ref_slope"], opts["ref_intercept"])
            label = ("GMWL (Craig 1961)" if kind == "gmwl"
                     else f"Reference line (y = {slope:g}x {intercept:+g})")
            low, high = min(all_x), max(all_x)
            shapes.append((label, [(low, slope * low + intercept), (high, slope * high + intercept)]))
            reference.append(label)
        notes = ([] if scope == "none" else
                 [f"{regression.METHODS[method]}, {points.y_title} on {points.x_title}"
                  + (f", weighted by {points.meta['weight_column']}." if weights else ".")])
        if skipped:
            notes.append(f"No line for {', '.join(skipped)} (fewer than three points, or no spread in x).")
        batch.append(Polygons(points.x_title, points.y_title, shapes, note=" ".join(notes),
                              name=points.name, open=True, reference=reference))
        cards.append(Div(
            P(" ".join(notes) or "Reference line only.", style=NOTE),
            *([result_table(["Sample", "n", "Slope ± SE", "Intercept ± SE", "r²"], rows)] if rows else []),
            P("Standard errors are those of the least squares fit. A slope or "
              "intercept that differs from the reference by more than a couple of standard "
              "errors is a real difference, if the points are independent.", style=NOTE)))
    return batch, StepOutput(opts.get("title") or "Fit a line", Div(*cards), [], None)


def _validate_fit(opts, context):
    if opts.get("reference") == "custom" and (opts.get("ref_slope") is None
                                              or opts.get("ref_intercept") is None):
        return "Give the reference line's slope and intercept."
    return None


fit_line = Node(
    "fit_line", "Fit a line", "Model",
    [Port("points", (POINTS,), "Points")], POLYGON,
    [
        Field("scope", "Fit", SELECT, choices=FIT_SCOPES, default="each", page=DATA_PAGE),
        Field("method", "Method", SELECT, choices=regression.METHODS, default="ols",
              page=DATA_PAGE,
              hint="Both variables are measured with error, so reduced major axis is often "
                   "preferred; for a tight line the two agree"),
        Field("reference", "Reference line", SELECT, choices=REFERENCE_LINES, default="none",
              page=OPTIONS_PAGE,
              hint="Drawn dashed for comparison. The meteoric water line is for δ²H (y) "
                   "against δ¹⁸O (x)"),
        Field("ref_slope", "Reference slope", NUMBER, signed=True, page=OPTIONS_PAGE,
              when=lambda o: o.get("reference") == "custom"),
        Field("ref_intercept", "Reference intercept", NUMBER, signed=True, page=OPTIONS_PAGE,
              when=lambda o: o.get("reference") == "custom"),
    ],
    _run_fit, _validate_fit,
    description="Fits a straight line through each sample's points (or all of them) with its "
                "slope, intercept, their standard errors and r². Drawn over the points with "
                "a Scatterplot, this is a local water line; give the global meteoric water "
                "line as a reference to see how the samples depart from it (evaporation "
                "lowers the slope).")


# ---------------------------------------------------------------------- mixing

INCREMENTS = {"1": "1% (finest)", "2": "2%", "5": "5% (fast)"}


def _run_isosource(inputs, opts):
    rows, sample_col = table_of(inputs, "table")
    tracers = list(opts["tracers"])
    sources = list(opts["sources"])

    def mean_of(sample):
        selected = [r for r in rows if str(r.get(sample_col, "") or "").strip() == sample]
        out = []
        for tracer in tracers:
            values = [v for v in (number_of(r.get(tracer)) for r in selected) if v is not None]
            if not values:
                raise NodeProblem(f"'{sample}' has no values for {tracer}.")
            out.append(sum(values) / len(values))
        return out

    source_values = [mean_of(s) for s in sources]
    mixture = mean_of(opts["mixture"])
    increment = float(opts.get("increment", 1))
    tolerance = 0.1 if opts.get("tolerance") is None else float(opts["tolerance"])
    try:
        solutions, tried = isosource.feasible_solutions(source_values, mixture, increment, tolerance)
    except ValueError as error:
        raise NodeProblem(str(error)) from None
    if not len(solutions):
        raise NodeProblem(
            f"No combination of the sources in steps of {increment:g}% reproduces "
            f"{opts['mixture']} within {tolerance:g}. The mixture probably lies outside the "
            "sources (a source is missing, or the sources need correcting for fractionation "
            "first); otherwise widen the tolerance.")
    summary = isosource.summarize(solutions)
    underdetermined = len(sources) > len(tracers) + 1
    note = (f"{len(solutions):,} of {tried:,} combinations (steps of {increment:g}%) reproduce "
            f"{opts['mixture']} within {tolerance:g} on every tracer. The bars give each "
            "source's mean share with its standard deviation across them; the table gives the "
            "range." + (" With more sources than tracers + 1 the answer is a range, not a "
                        "number, and a source that spans 0–60% cannot be said to contribute 30%."
                        if underdetermined else ""))
    detail = (["Source", "Mean %", "Std. dev.", "Min", "1st %ile", "Median", "99th %ile", "Max"],
              [[name, f"{s['mean']:.1f}", f"{s['sd']:.1f}", f"{s['min']:.0f}", f"{s['p1']:.0f}",
                f"{s['median']:.0f}", f"{s['p99']:.0f}", f"{s['max']:.0f}"]
               for name, s in zip(sources, summary)])
    return [Proportions(
        name=f"{opts['mixture']} from {len(sources)} sources", names=sources,
        values=[s["mean"] for s in summary], errors=[s["sd"] for s in summary],
        label=f"% contribution (mean of {len(solutions):,} solutions)", note=note,
        meta={"detail": detail, "solutions": len(solutions)})], None


def _validate_isosource(opts, context):
    if not opts.get("tracers"):
        return "Choose at least one isotope to mix on."
    if not opts.get("mixture"):
        return "Choose the mixture sample."
    sources = opts.get("sources") or []
    if len(sources) < 2:
        return "Choose at least two source samples."
    if opts["mixture"] in sources:
        return "The mixture cannot also be one of its sources."
    return None


isosource_block = Node(
    "isosource", "Mixing solutions", "Model",
    [Port("table", (TABLE,), "Table")], PROPORTIONS,
    [
        Field("tracers", "Isotopes", DIMENSIONS, numeric_only=True, page=DATA_PAGE,
              hint="The columns the sources and mixture are compared on, e.g. δ¹³C and δ¹⁵N"),
        Field("mixture", "Mixture sample", SAMPLE, page=DATA_PAGE,
              hint="The consumer, sediment or water that is the blend; its mean is used"),
        Field("sources", "Source samples", SAMPLES, unchecked=True, page=DATA_PAGE,
              hint="The end members; each one's mean is used"),
        Field("increment", "Increment", SELECT, choices=INCREMENTS, default="1", cast=float,
              page=OPTIONS_PAGE, hint="Source shares are tried in steps of this size"),
        Field("tolerance", "Tolerance", NUMBER, default=0.1, page=OPTIONS_PAGE,
              hint="How far a combination's mixture may be from the real one, in the "
                   "isotope's units (‰). Typically 0.1; larger if the sources are close"),
    ],
    _run_isosource, _validate_isosource,
    description="Finds every combination of source shares that adds to 100% and reproduces "
                "the mixture's isotope values (IsoSource, Phillips & Gregg 2003), and reports "
                "each source's contribution as a distribution over them. Uses each source's "
                "mean only; correct the sources for fractionation beforehand if needed, and "
                "use End-member mixing when their variability must be carried "
                "through, if the sources and tracers allow one solution. Draw the result with a Bar chart.")


# ------------------------------------------------------------------------ EMMA

def _sample_stats(rows, sample_col, sample, tracers):
    """(mean, standard deviation, count) of each tracer over a sample's rows."""
    selected = [r for r in rows if str(r.get(sample_col, "") or "").strip() == sample]
    means, sds, counts = [], [], []
    for tracer in tracers:
        values = np.array([v for v in (number_of(r.get(tracer)) for r in selected)
                           if v is not None])
        if not len(values):
            raise NodeProblem(f"'{sample}' has no values for {tracer}.")
        means.append(float(values.mean()))
        sds.append(float(values.std(ddof=1)) if len(values) > 1 else 0.0)
        counts.append(len(values))
    return means, sds, counts


EMMA_CONSTRAINTS = {
    "bounded": "Fractions between 0 and 100%",
    "free": "Sum to 100% only (negative fractions allowed)",
}
EMMA_SPREADS = {
    "se": "Standard error of each mean",
    "sd": "Standard deviation of each end member",
    "none": "None — solve once",
}
EMMA_TRIALS = {"1000": "1,000", "5000": "5,000", "20000": "20,000"}


def _run_emma(inputs, opts):
    rows, sample_col = table_of(inputs, "table")
    tracers, sources = list(opts["tracers"]), list(opts["sources"])
    try:
        emma.check_shape(len(sources), len(tracers))
    except ValueError as error:
        raise NodeProblem(str(error)) from None
    stats = [_sample_stats(rows, sample_col, s, tracers) for s in sources]
    mix_mean, mix_sd, mix_n = _sample_stats(rows, sample_col, opts["mixture"], tracers)
    means = np.array([st[0] for st in stats])
    spread_kind = opts.get("spread", "se")
    notes = []
    if spread_kind == "none":
        source_spread = mixture_spread = None
    else:
        sds = np.array([st[1] for st in stats])
        counts = np.array([st[2] for st in stats])
        divisor = np.sqrt(counts) if spread_kind == "se" else 1.0
        source_spread, mixture_spread = sds / divisor, np.array(mix_sd) / (
            np.sqrt(mix_n) if spread_kind == "se" else 1.0)
        single = [s for s, st in zip(sources, stats) if min(st[2]) < 2]
        if single:
            notes.append(f"{', '.join(single)} has a single value for a tracer, so that "
                         "end member's own uncertainty is not included.")
        if min(mix_n) < 2:
            notes.append(f"{opts['mixture']} has a single value for a tracer, so its own "
                         "uncertainty is not included.")
    try:
        result = emma.mix(means, mix_mean, source_spread, mixture_spread,
                          opts.get("constraint", "bounded") == "bounded",
                          int(opts.get("trials", 5000)))
    except ValueError as error:
        raise NodeProblem(str(error)) from None

    fractions = result.fractions * 100
    summary = result.summary
    errors = [x["sd"] * 100 for x in summary] if summary else [float("nan")] * len(sources)
    how = ("solved exactly from the mass balance" if result.exact
           else f"fitted by least squares ({len(tracers)} tracers, {len(sources)} end members)")
    residual = ", ".join(f"{t} {r:+.2g}" for t, r in zip(tracers, result.residual))
    note = [f"{opts['mixture']} {how}; modelled minus observed: {residual}."]
    if result.clipped:
        note.append("With the fractions held between 0 and 100% the fit is not exact: the "
                    "mixture lies outside the end members, so one may be missing, or the "
                    "tracers need correcting for fractionation. Choose the other constraint "
                    "to see how far outside.")
    if summary:
        note.append(f"Uncertainty: {int(opts.get('trials', 5000)):,} Monte Carlo draws of the "
                    f"end members' and mixture's means with their "
                    f"{'standard errors' if spread_kind == 'se' else 'standard deviations'}.")
        if spread_kind == "sd":
            note.append("With standard deviations, the spread shows how much the fractions "
                        "would vary with the end members' variability, not how well the means "
                        "are known.")
    note += notes
    detail = None
    if summary:
        detail = (["Source", "Mean %", "Std. dev.", "2.5th %ile", "Median", "97.5th %ile"],
                  [[name, f"{f:.1f}", f"{x['sd'] * 100:.1f}", f"{x['p2_5'] * 100:.1f}",
                    f"{x['median'] * 100:.1f}", f"{x['p97_5'] * 100:.1f}"]
                   for name, f, x in zip(sources, fractions, summary)])
    meta = {"detail": detail} if detail else {}
    return [Proportions(
        name=f"{opts['mixture']} from {len(sources)} end members", names=sources,
        values=list(fractions), errors=errors,
        label="% contribution (from the means)", note=" ".join(note), meta=meta)], None


def _validate_emma(opts, context):
    if not opts.get("tracers"):
        return "Choose at least one tracer."
    if not opts.get("mixture"):
        return "Choose the mixture sample."
    sources = opts.get("sources") or []
    if len(sources) < 2:
        return "Choose at least two end-member samples."
    if opts["mixture"] in sources:
        return "The mixture cannot also be one of its end members."
    if len(sources) > len(opts["tracers"]) + 1:
        return (f"{len(sources)} end members need at least {len(sources) - 1} tracers; "
                f"{len(opts['tracers'])} chosen. Add a tracer, or use Mixing solutions.")
    return None


emma_block = Node(
    "emma", "End-member mixing", "Model",
    [Port("table", (TABLE,), "Table")], PROPORTIONS,
    [
        Field("tracers", "Tracers", DIMENSIONS, numeric_only=True, page=DATA_PAGE,
              hint="The columns the end members and mixture are compared on, e.g. δ¹⁸O and δ²H "
                   "or solute concentrations. Needs at least one fewer than the end members"),
        Field("mixture", "Mixture sample", SAMPLE, page=DATA_PAGE,
              hint="The blend (a stream, a consumer); its mean is solved"),
        Field("sources", "End-member samples", SAMPLES, unchecked=True, page=DATA_PAGE,
              hint="One sample per end member; each one's mean and spread are used"),
        Field("constraint", "Fractions", SELECT, choices=EMMA_CONSTRAINTS, default="bounded",
              page=OPTIONS_PAGE),
        Field("spread", "Uncertainty from", SELECT, choices=EMMA_SPREADS, default="se",
              page=OPTIONS_PAGE,
              hint="Each end member's mean and the mixture's are redrawn with this spread, and "
                   "the mix solved again each time"),
        Field("trials", "Draws", SELECT, choices=EMMA_TRIALS, default="5000", page=OPTIONS_PAGE,
              when=lambda o: o.get("spread", "se") != "none"),
    ],
    _run_emma, _validate_emma,
    description="End-member mixing analysis: solves the mass balance for what share of the "
                "mixture came from each end member — exactly when there is one more end "
                "member than tracers, by least squares when there are fewer — and carries the "
                "end members' uncertainty through by Monte Carlo (after Hooper et al. 1990, "
                "Christophersen & Hooper 1992 and Genereux 1998). With more end members than "
                "tracers + 1 there is no single answer: use Mixing solutions. Draw the result "
                "with a Bar chart.")


# ------------------------------------------------------------------------ EMSA

ROW_LABELS = {"all_streamflow": "All streamflow",
              "non_streamflow": "Not streamflow (evapotranspiration and storage)"}


def _emsa_series(rows, sample_col, tracer, categories, flux_col):
    """Tracer values, weights and categories (and the flux's) for the samples chosen."""
    values, weights, cats = [], [], []
    for row in rows:
        sample = str(row.get(sample_col, "") or "").strip()
        if sample not in categories:
            continue
        value = number_of(row.get(tracer))
        flux = number_of(row.get(flux_col)) if flux_col else 1.0
        if value is None or flux is None:
            continue
        if flux < 0:
            raise NodeProblem(f"A negative flux in {sample} ({flux:g}); fluxes are amounts "
                              "of water and cannot be below zero.")
        values.append(value)
        weights.append(flux)
        cats.append(sample)
    return values, weights, cats


def _run_emsa(inputs, opts):
    rows, sample_col = table_of(inputs, "table")
    flux_col = opts.get("flux") if opts.get("use_flux") else None
    precip, stream = list(opts["precipitation"]), list(opts["streamflow"])
    pv, pw, pc = _emsa_series(rows, sample_col, opts["tracer"], precip, flux_col)
    sv, sw, sc = _emsa_series(rows, sample_col, opts["tracer"], stream, flux_col)
    for chosen, cats, kind in ((precip, pc, "precipitation"), (stream, sc, "streamflow")):
        missing = [c for c in chosen if c not in set(cats)]
        if missing:
            raise NodeProblem(f"No usable {kind} rows for {', '.join(missing)} (each needs a "
                              "value for the tracer" + (" and the flux" if flux_col else "") + ").")
    bounded = bool(opts.get("bounded", True))      # a step saved before the option existed keeps shares physical
    try:
        result = emsa.end_member_splitting(
            pv, sv, pc, sc, pw, sw, pc, sc, pw if flux_col else None, sw if flux_col else None,
            float(opts.get("years") or 1), bounded=bounded, constrain_water=bool(flux_col))
    except ValueError as error:
        raise NodeProblem(str(error).replace("untick the limit", "untick “Keep shares physical”")) from None

    def pct(x):
        return "–" if not np.isfinite(x) else f"{100 * x:.1f}"

    nj = len(result.streamflow)
    free = result.free_mixing
    caveats = []
    if not flux_col:
        caveats.append("Without a flux column every sample counts as one unit of water, so "
                       "the mixing fractions mean what they say but the splitting fractions "
                       "only reflect how many samples each category has.")
    first, second = result.precipitation
    if bounded:
        if result.held:
            shown = ", ".join(
                f"{name} ({100 * free[result.streamflow.index(name), 0]:.0f}% {first}, "
                f"{100 * free[result.streamflow.index(name), 1]:.0f}% {second})" for name in result.held)
            caveats.append(f"The {opts['tracer']} of {shown} lies outside the two precipitation end "
                           "members, so the equations give a share below 0 or above 100%. Each was held "
                           "at the nearest possible share; the tracer cannot account for that streamflow "
                           "from these two end members alone (a third source, fractionation, or "
                           "end members that do not span it).")
        if result.water_limited:
            caveats.append("The fluxes ask for more of one end member to leave as streamflow than "
                           "fell. The shares were moved, the better-measured streamflows least, until "
                           "no end member sends out more water than it received. Check the flux "
                           "columns' units and period.")
        if result.held or result.water_limited:
            caveats.append("Standard errors are left blank for shares that were held or moved, and "
                           "for the totals worked out from them: the first-order error of the "
                           "paper does not apply there.")
    elif np.any((free[:nj + 1] < 0) | (free[:nj + 1] > 1)) or np.any(result.splitting[:nj + 2] < -1e-12):
        caveats.append("Shown as the equations give them, unlimited. A share below 0 or above 100% "
                       "means that streamflow's tracer lies outside the two precipitation end members, "
                       "or more water leaves than arrived; neither can be, so tick “Keep shares physical”.")
    mixing_batch = []
    for j, row in enumerate(result.rows):
        label = ROW_LABELS.get(row, row)
        detail = (["End member", "Mixing %", "± SE", "Splitting %", "± SE"],
                  [[cat, pct(result.mixing[j, i]), pct(result.mixing_se[j, i]),
                    pct(result.splitting[j, i]), pct(result.splitting_se[j, i])]
                   for i, cat in enumerate(result.precipitation)])
        mixing_batch.append(Proportions(
            name=label, names=list(result.precipitation),
            values=[100 * x for x in result.mixing[j]],
            errors=[100 * x for x in result.mixing_se[j]],
            label="% of this water",
            note=f"What share of {label.lower() if j >= nj else label}'s water came from each "
                 f"precipitation end member, by the {opts['tracer']} mass balance. "
                 + " ".join(caveats),
            meta={"detail": detail}))
    split_names = list(result.streamflow) + ["Not streamflow (evapotranspiration and storage)"]
    split_rows = list(range(nj)) + [nj + 1]
    splitting_batch = []
    for i, cat in enumerate(result.precipitation):
        splitting_batch.append(Proportions(
            name=f"Where the {cat} went", names=split_names,
            values=[100 * result.splitting[j, i] for j in split_rows],
            errors=[100 * result.splitting_se[j, i] for j in split_rows],
            label=f"% of the {cat} that leaves as",
            note=f"What share of the {cat} precipitation leaves as each kind of streamflow, "
                 "and what share is left over (evapotranspiration, and any change in storage, "
                 "which the method cannot tell apart). " + " ".join(caveats)))

    summary = [[cat, f"{result.precipitation_mean[i]:.2f} ± {result.precipitation_se[i]:.2f}",
                f"{result.total_precipitation[i]:,.4g} ± {result.total_precipitation_se[i]:,.2g}"]
               for i, cat in enumerate(result.precipitation)]
    summary += [[ROW_LABELS.get(row, row), f"{result.streamflow_mean[j]:.2f} ± {result.streamflow_se[j]:.2f}",
                 f"{result.total_streamflow[j]:,.4g} ± {result.total_streamflow_se[j]:,.2g}"]
                for j, row in enumerate(result.rows)]
    card = StepOutput(opts.get("title") or "End-member splitting", Div(
        P(f"{opts['tracer']} of each category, as a flux-weighted mean ± its standard error, "
          f"and the yearly flux ({float(opts.get('years') or 1):g} year"
          f"{'' if float(opts.get('years') or 1) == 1 else 's'} of data).", style=NOTE),
        result_table(["Category", f"Mean {opts['tracer']}", "Flux per year"], summary),
        *[P(c, style=NOTE) for c in caveats]), [], None)
    return {"": mixing_batch, "splitting": splitting_batch}, card


def _validate_emsa(opts, context):
    if not opts.get("tracer"):
        return "Choose the tracer."
    precip, stream = opts.get("precipitation") or [], opts.get("streamflow") or []
    if len(precip) != 2:
        return f"Precipitation needs exactly two samples (end members); {len(precip)} chosen."
    if not stream:
        return "Choose at least one streamflow sample."
    if set(precip) & set(stream):
        return "A sample cannot be both precipitation and streamflow."
    if opts.get("use_flux") and not opts.get("flux"):
        return "Choose the flux column."
    if opts.get("years") is not None and float(opts["years"]) <= 0:
        return "The number of years must be above zero."
    return None


emsa_block = Node(
    "emsa", "End-member splitting", "Model",
    [Port("table", (TABLE,), "Table")], PROPORTIONS,
    [
        Field("tracer", "Tracer", DIMENSION, numeric_only=True, page=DATA_PAGE,
              hint="The isotope or concentration that tells the precipitation apart, e.g. δ¹⁸O"),
        Field("precipitation", "Precipitation end members", SAMPLES, unchecked=True,
              page=DATA_PAGE, hint="Exactly two samples, e.g. snow and rain; one row each "
                                   "precipitation event or interval"),
        Field("streamflow", "Streamflow samples", SAMPLES, unchecked=True, page=DATA_PAGE,
              hint="One or more, e.g. baseflow and stormflow, or the seasons; each is split "
                   "separately"),
        Field("use_flux", "Weight by flux", CHECKBOX, page=DATA_PAGE,
              hint="Each row's amount of water (precipitation depth, discharge) weights its "
                   "tracer value and gives the totals the splitting needs"),
        Field("flux", "Flux column", DIMENSION, numeric_only=True, nth=1, page=DATA_PAGE,
              when=lambda o: bool(o.get("use_flux"))),
        Field("years", "Years of data", NUMBER, default=1, page=OPTIONS_PAGE,
              hint="Turns the flux totals into yearly ones; matters only if you want the "
                   "yearly totals, not the fractions"),
        Field("bounded", "Keep shares physical", CHECKBOX, default=True, page=OPTIONS_PAGE,
              hint="No share below 0 or above 100%, and no end member sending out more water than "
                   "fell, so the water balances. Where the equations already give such an answer "
                   "nothing changes; untick to see them exactly as published, negative shares and all"),
    ],
    _run_emsa, _validate_emsa,
    extras=[Output("splitting", PROPORTIONS, "Splitting")], output_label="Mixing",
    description="End-member splitting analysis (Kirchner & Allen 2020). Mixing: what share of "
                "each kind of streamflow came from each of two precipitation end members. "
                "Splitting: what share of each precipitation end member left as each kind of "
                "streamflow, and what share is left for evapotranspiration. Each sample is a "
                "category, so name your samples by season or type; with a flux column the "
                "tracer values are weighted by it and the totals found. Draw either output "
                "with a Bar chart.")


ISOTOPE_NODES = [niche_block, fit_line, isosource_block, emma_block, emsa_block]
