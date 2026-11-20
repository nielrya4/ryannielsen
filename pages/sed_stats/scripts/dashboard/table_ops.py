"""
Cleaning and reshaping a table: filter its grains, add a transformed column, add a
ratio. Each returns a new table and leaves the one it was given alone; what
happened is returned alongside, so the step can say what it did.
"""
import math
from dataclasses import dataclass, field

import numpy as np

from sed_stats import dates as dt
from sed_stats import isotopes as iso
from workflow_lib import NodeProblem

# How a column can be transformed: key -> (label for the new column's name, function,
# what the function cannot take, as a phrase for the report).
TRANSFORMS = {
    "log10": ("log10", lambda v: math.log10(v), lambda v: v > 0, "not above zero"),
    "ln": ("ln", lambda v: math.log(v), lambda v: v > 0, "not above zero"),
    "sqrt": ("sqrt", lambda v: math.sqrt(v), lambda v: v >= 0, "negative"),
    "reciprocal": ("1/", lambda v: 1.0 / v, lambda v: v != 0, "zero"),
}
TRANSFORM_LABELS = {
    "log10": "log₁₀", "ln": "natural log", "sqrt": "square root", "reciprocal": "reciprocal (1/x)",
    "zscore": "z-score (over all grains)", "zscore_sample": "z-score within each sample",
}
FILTER_HOW = {
    "samples": "Only choose samples",
    "range": "Keep grains whose value is within a range",
    "values": "Keep grains whose value is one of these",
    "present": "Drop grains that have no value",
}


def number_of(value):
    """A finite float from a cell, or None for blank, text, NaN and infinity."""
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _sample_of(row, sample_col):
    return str(row.get(sample_col, "") or "").strip()


def _blank(value):
    return value is None or str(value).strip() == ""


# --------------------------------------------------------------------- filtering

@dataclass
class FilterResult:
    rows: list
    before: dict = field(default_factory=dict)       # sample -> grains in
    after: dict = field(default_factory=dict)        # sample -> grains kept
    summary: str = ""


def filter_rows(rows, sample_col, samples=None, how="samples", column=None,
                minimum=None, maximum=None, values=None):
    """
    Keep some of the grains.

    Args:
        samples: only these samples (all when None)
        how: "samples" (nothing more), "range" (`column` between `minimum` and
            `maximum`, either may be left out, both inclusive), "values" (`column`
            is one of the comma-separated `values`) or "present" (`column` has a
            value)

    Raises:
        NodeProblem: for a filter that is missing a piece, or leaves no grains
    """
    if how not in FILTER_HOW:
        raise NodeProblem(f"Unknown filter '{how}'.")
    if how != "samples" and not column:
        raise NodeProblem("Choose the column to filter on.")
    if how == "range" and minimum is None and maximum is None:
        raise NodeProblem("Give a minimum, a maximum, or both.")
    wanted = None
    if how == "values":
        wanted = {v.strip() for v in str(values or "").split(",") if v.strip()}
        if not wanted:
            raise NodeProblem("List the values to keep, separated by commas.")
    chosen = set(samples) if samples is not None else None

    result = FilterResult([])
    for row in rows:
        sample = _sample_of(row, sample_col)
        if chosen is not None and sample not in chosen:
            continue
        result.before[sample] = result.before.get(sample, 0) + 1
        if not _passes(row.get(column) if column else None, how, minimum, maximum, wanted):
            continue
        result.after[sample] = result.after.get(sample, 0) + 1
        result.rows.append(dict(row))
    kept, seen = len(result.rows), sum(result.before.values())
    if not kept:
        raise NodeProblem("No grains are left after this filter.")
    result.summary = (f"Kept {kept:,} of {seen:,} grains"
                      + (f" ({_describe(how, column, minimum, maximum, wanted)})"
                         if how != "samples" else "") + ".")
    return result


def _passes(value, how, minimum, maximum, wanted):
    if how == "samples":
        return True
    if how == "present":
        return not _blank(value)
    if how == "values":
        return str(value).strip() in wanted
    number = number_of(value)
    if number is None:
        return False
    return ((minimum is None or number >= minimum)
            and (maximum is None or number <= maximum))


def _describe(how, column, minimum, maximum, wanted):
    if how == "present":
        return f"{column} has a value"
    if how == "values":
        return f"{column} is {' or '.join(sorted(wanted))}"
    low = f"{minimum:g} ≤ " if minimum is not None else ""
    high = f" ≤ {maximum:g}" if maximum is not None else ""
    return f"{low}{column}{high}"


# ------------------------------------------------------------------ new columns

@dataclass
class ColumnResult:
    rows: list
    name: str
    made: int = 0               # grains given a value
    blank: int = 0              # grains left blank, and why (see `reason`)
    reason: str = ""
    replaced: bool = False      # an existing column of that name was overwritten
    summary: str = ""


def _finish(rows, name, values, reason):
    existing = bool(rows) and name in rows[0]
    out = []
    for row, value in zip(rows, values):
        new = dict(row)
        new[name] = "" if value is None else value
        out.append(new)
    made = sum(1 for v in values if v is not None)
    result = ColumnResult(out, name, made, len(values) - made, reason, existing)
    parts = [f"Added '{name}': {made:,} value{'s' if made != 1 else ''}"]
    if result.blank:
        parts.append(f"{result.blank:,} left blank ({reason})")
    summary = "; ".join(parts) + "."
    if existing:
        summary += f" This replaced the column that was already called '{name}'."
    result.summary = summary
    if not made:
        raise NodeProblem(f"Every value came out blank ({reason}), so there is nothing "
                          "to add.")
    return result


def transform_column(rows, sample_col, column, function, name=None):
    """
    A copy of the table with `column` transformed into a new column.

    Values the function cannot take (the log of zero) are left blank rather than
    guessed. Uncertainty columns are not transformed with it, and a new name no
    longer matches the old column's, so the new column is treated as having none.

    Raises:
        NodeProblem: for an unknown function or no usable values
    """
    if function not in TRANSFORM_LABELS:
        raise NodeProblem(f"Unknown transformation '{function}'.")
    if not column:
        raise NodeProblem("Choose the column to transform.")
    numbers = [number_of(row.get(column)) for row in rows]
    if function in TRANSFORMS:
        label, apply, valid, reason = TRANSFORMS[function]
        values = [apply(v) if v is not None and valid(v) else None for v in numbers]
        blank_reason = f"values that are {reason} or missing"
        default = f"{label}{column}" if label.endswith("/") else f"{label}({column})"
    else:
        values = _standardised(rows, sample_col, numbers, within=function == "zscore_sample")
        blank_reason = "missing, or a sample with no spread"
        default = f"z({column})"
    return _finish(rows, (name or "").strip() or default, values, blank_reason)


def _standardised(rows, sample_col, numbers, within):
    groups = {}
    for index, (row, number) in enumerate(zip(rows, numbers)):
        if number is not None:
            key = _sample_of(row, sample_col) if within else ""
            groups.setdefault(key, []).append(index)
    out = [None] * len(rows)
    for indexes in groups.values():
        data = np.array([numbers[i] for i in indexes])
        spread = data.std(ddof=1) if len(data) > 1 else 0.0
        if spread <= 0:
            continue
        for i, z in zip(indexes, (data - data.mean()) / spread):
            out[i] = float(z)
    return out


def ratio_column(rows, numerator, denominator, name=None, factor=1.0):
    """
    A copy of the table with `factor * numerator / denominator` as a new column
    (blank where either is missing or the denominator is zero). The factor turns a
    ratio of weights into one of atoms, or a ratio into per mil.

    Raises:
        NodeProblem: for the same column twice, or no usable pairs
    """
    if not numerator or not denominator:
        raise NodeProblem("Choose both columns.")
    if numerator == denominator:
        raise NodeProblem("The ratio of a column to itself is always 1; choose two "
                          "different columns.")
    values = []
    for row in rows:
        top, bottom = number_of(row.get(numerator)), number_of(row.get(denominator))
        values.append(factor * top / bottom
                      if top is not None and bottom not in (None, 0) else None)
    return _finish(rows, (name or "").strip() or f"{numerator}/{denominator}", values,
                   "either value missing, or the denominator zero")


# --------------------------------------------------------------------- isotopes

def _derived(rows, name, columns, function, reason):
    """
    A new column from `function(*numbers)` of the named columns, row by row. A row
    with any of them missing, or for which the function raises ValueError (outside
    its domain), is left blank.
    """
    values = []
    for row in rows:
        numbers = [number_of(row.get(c)) for c in columns]
        if any(n is None for n in numbers):
            values.append(None)
            continue
        try:
            values.append(function(*numbers))
        except (ValueError, ZeroDivisionError):
            values.append(None)
    return _finish(rows, name, values, reason)


def _need(**columns):
    for label, column in columns.items():
        if not column:
            raise NodeProblem(f"Choose the {label.replace('_', ' ')} column.")


def convert_scale(rows, column, conversion, name=None):
    """
    Delta-18O between the VPDB and VSMOW scales, by Coplen et al. (1983) or the IUPAC
    values; `conversion` is "vpdb_to_vsmow" or "vsmow_to_vpdb", optionally suffixed
    ":iupac".
    """
    _need(**{"delta": column})
    direction, _, which = str(conversion).partition(":")
    which = which or "coplen"
    if direction not in ("vpdb_to_vsmow", "vsmow_to_vpdb") or which not in iso.OXYGEN_SCALE_CONVERSIONS:
        raise NodeProblem(f"Unknown conversion '{conversion}'.")
    convert = iso.vpdb_to_vsmow if direction == "vpdb_to_vsmow" else iso.vsmow_to_vpdb
    target = "VSMOW" if direction == "vpdb_to_vsmow" else "VPDB"
    return _derived(rows, (name or "").strip() or f"{column} ({target})", [column],
                    lambda d: convert(d, which), "value missing")


def difference_column(rows, first, second, form="difference", factor=1.0, name=None):
    """
    first - factor * second ("difference": d-excess with factor 8, or an
    enrichment), or 1000 ln(alpha) of the first against the second ("ln_alpha").
    """
    _need(first=first, second=second)
    if first == second:
        raise NodeProblem("Choose two different columns.")
    if form == "ln_alpha":
        return _derived(rows, (name or "").strip() or f"1000 ln α ({first}/{second})",
                        [first, second], iso.thousand_ln_alpha,
                        "value missing, or a delta at or below -1000")
    if form != "difference":
        raise NodeProblem(f"Unknown form '{form}'.")
    default = f"{first} - {factor:g}*{second}" if factor != 1 else f"{first} - {second}"
    return _derived(rows, (name or "").strip() or default, [first, second],
                    lambda a, b: a - factor * b, "value missing")


def lipid_column(rows, d13c, cn, name=None, intercept=iso.LIPID_INTERCEPT, slope=iso.LIPID_SLOPE):
    """Post et al. (2007) lipid-normalised delta-13C from delta-13C and atomic C:N."""
    _need(delta_13C=d13c, C_N=cn)
    return _derived(rows, (name or "").strip() or f"{d13c} (lipid-normalised)", [d13c, cn],
                    lambda d, c: d + intercept + slope * c, "value missing")


def trophic_column(rows, d15n, baseline, position=2.0, enrichment=iso.DEFAULT_ENRICHMENT,
                   name=None):
    """Trophic position (Post 2002) from delta-15N, against a baseline delta-15N."""
    _need(delta_15N=d15n)
    if enrichment <= 0:
        raise NodeProblem("The enrichment per trophic level must be above zero.")
    if baseline is None:
        raise NodeProblem("Give the baseline delta-15N.")
    return _derived(rows, (name or "").strip() or "Trophic position", [d15n],
                    lambda d: iso.trophic_position(d, baseline, position, enrichment),
                    "value missing")


CARBONATE_EQUATIONS = {
    "shackleton": "Shackleton (1974) / O'Neil et al. (1969)",
    "kim_oneil": "Kim & O'Neil (1997)",
    "kim_oneil_recalculated": "Kim & O'Neil (1997), recalculated",
    "custom": "Your own: T = a + b·x + c·x²",
}


def temperature_column(rows, calcite, equation="shackleton", calcite_scale="vpdb",
                       water=0.0, water_column=None, coefficients=(0.0, 0.0, 0.0), name=None):
    """
    Carbonate-water temperature (degrees C) from delta-18O of the calcite and of the
    water it grew in (a constant, or a column), both on the scales stated: calcite on
    `calcite_scale` ("vpdb" or "vsmow"), water on VSMOW.
    """
    _need(calcite=calcite)
    if equation not in CARBONATE_EQUATIONS:
        raise NodeProblem(f"Unknown equation '{equation}'.")
    columns = [calcite] + ([water_column] if water_column else [])

    def vpdb(d):
        return d if calcite_scale == "vpdb" else iso.vsmow_to_vpdb(d)

    def vsmow(d):
        return iso.vpdb_to_vsmow(d) if calcite_scale == "vpdb" else d

    def temperature(d, w=None):
        w = water if w is None else w
        if equation == "shackleton":
            return iso.temperature_shackleton(vpdb(d), w)
        if equation == "custom":
            return iso.temperature_polynomial(vpdb(d), w, *coefficients)
        constants = iso.KIM_ONEIL if equation == "kim_oneil" else iso.KIM_ONEIL_RECALCULATED
        return iso.temperature_kim_oneil(vsmow(d), w, constants)

    return _derived(rows, (name or "").strip() or "Temperature (°C)", columns, temperature,
                    "value missing, or outside the equation's range")


# ------------------------------------------------------------------------- dates

DATE_PARTS = {
    "year": "Year",
    "month": "Month number",
    "month_name": "Month name",
    "year_month": "Year and month (2021-01)",
    "water_year": "Water year",
    "day_of_water_year": "Day of the water year",
    "day_of_year": "Day of the year (1–366; often called the “Julian day”)",
    "decimal_year": "Decimal year (2021.54)",
    "julian_date": "Julian date, JD (days from noon 1 Jan 4713 BC: 2459215.5)",
    "modified_julian_date": "Modified Julian date, MJD (JD − 2400000.5: 59215.0)",
    "julian_day_number": "Julian day number (whole days: 2459216)",
    "season": "Season (Winter, Spring, Summer, Autumn)",
    "two_seasons": "Two seasons, by the months you give",
}
_DEFAULT_NAMES = {
    "year": "year", "month": "month", "month_name": "month_name", "year_month": "year_month",
    "water_year": "water_year", "day_of_water_year": "day_of_water_year",
    "day_of_year": "day_of_year", "decimal_year": "decimal_year", "season": "season",
    "julian_date": "julian_date", "modified_julian_date": "mjd", "julian_day_number": "julian_day_number",
    "two_seasons": "season",
}


def date_part_column(rows, column, part, name=None, day_first=False, water_year_start=10,
                     hemisphere="north", season_months="", first_name="First season",
                     second_name="Second season"):
    """
    A copy of the table with one part of each row's date as a new column.

    Rows whose date cannot be read are left blank, and the first few such values are named in
    the result so a format that is not understood is easy to spot.

    Raises:
        NodeProblem: for no column or part, a bad month list, or no readable date at all
    """
    if not column:
        raise NodeProblem("Choose the date column.")
    if part not in DATE_PARTS:
        raise NodeProblem(f"Unknown date part '{part}'.")
    months = None
    if part == "two_seasons":
        try:
            months = dt.parse_months(season_months)
        except ValueError as error:
            raise NodeProblem(str(error)) from None
        if not first_name.strip() or not second_name.strip() or first_name == second_name:
            raise NodeProblem("Give the two seasons different names.")
    start = int(water_year_start or 10)
    if not 1 <= start <= 12:
        raise NodeProblem("The water year must start in a month from 1 to 12.")

    def make(when):
        if part == "year":
            return when.year
        if part == "month":
            return when.month
        if part == "month_name":
            return dt.MONTH_NAMES[when.month - 1]
        if part == "year_month":
            return f"{when.year}-{when.month:02d}"
        if part == "water_year":
            return dt.water_year(when, start)
        if part == "day_of_water_year":
            return dt.day_of_water_year(when, start)
        if part == "day_of_year":
            return dt.day_of_year(when)
        if part == "decimal_year":
            return round(dt.decimal_year(when), 4)
        if part == "julian_date":
            return round(dt.julian_date(when), 6)
        if part == "modified_julian_date":
            return round(dt.modified_julian_date(when), 6)
        if part == "julian_day_number":
            return dt.julian_day_number(when)
        if part == "season":
            return dt.season(when, hemisphere)
        return dt.two_seasons(when, months, first_name.strip(), second_name.strip())

    values, bad = [], []
    for row in rows:
        raw = row.get(column)
        when = dt.parse_date(raw, day_first)
        if when is None:
            values.append(None)
            if not _blank(raw) and len(bad) < 3 and str(raw) not in bad:
                bad.append(str(raw))
        else:
            values.append(make(when))
    reason = "no readable date" + (f" (for example '{bad[0]}')" if bad else "")
    result = _finish(rows, (name or "").strip() or _DEFAULT_NAMES[part], values, reason)
    if bad:
        result.summary += (" Not read as dates: " + ", ".join(f"'{b}'" for b in bad)
                           + ("; the order of day and month can be switched." if "/" in "".join(bad) else "."))
    return result


def regroup_samples(rows, sample_col, column, mode="replace", separator=" · "):
    """
    A copy of the table whose sample names come from another column — a season, a year, a
    site — so that every tool that works by sample now works by that grouping. The old names
    are kept in a column of their own.

    Args:
        mode: "replace" (the column's value is the sample) or "append" (old name, separator, value)

    Returns:
        ColumnResult whose rows carry the new names, and whose `summary` says how many
        samples there now are
    """
    if not column:
        raise NodeProblem("Choose the column to group by.")
    if column == sample_col:
        raise NodeProblem("That is already the sample column.")
    if mode not in ("replace", "append"):
        raise NodeProblem(f"Unknown mode '{mode}'.")
    kept = f"{sample_col} (original)"
    out, blanks = [], 0
    for row in rows:
        value = str(row.get(column, "") if row.get(column) is not None else "").strip()
        if value.endswith(".0") and value[:-2].lstrip("-").isdigit():
            value = value[:-2]                     # 2021.0 from a column read as numbers
        if not value:
            value, blanks = "(blank)", blanks + 1
        old = str(row.get(sample_col, "") if row.get(sample_col) is not None else "").strip()
        new = {}
        for key, cell in row.items():
            new[key] = (value if mode == "replace" else f"{old}{separator}{value}") if key == sample_col else cell
        new[kept] = old
        out.append(new)
    names = list(dict.fromkeys(r[sample_col] for r in out))
    summary = (f"{len(rows):,} rows now fall in {len(names)} sample{'s' if len(names) != 1 else ''}: "
               + ", ".join(names[:8]) + ("…" if len(names) > 8 else "") + "."
               + (f" {blanks:,} had no value in '{column}' and are called '(blank)'." if blanks else ""))
    result = ColumnResult(out, sample_col, made=len(out), blank=blanks, summary=summary)
    return result


@dataclass
class SummaryResult:
    rows: list
    columns: list
    summary: str = ""


def sample_summary(rows, sample_col, columns, weight_column=None):
    """
    One row per sample: how many values, and for each column the mean, standard deviation and
    standard error of the mean; with a weight column also the weighted mean and its standard
    error, where the weights are amounts (precipitation depth, discharge), not precisions —
    so a large storm counts for more, which is how an amount-weighted mean of precipitation
    isotopes is defined.

    Raises:
        NodeProblem: for no columns, or no sample with a number in any of them
    """
    if not columns:
        raise NodeProblem("Choose at least one column.")
    out, order = [], []
    for row in rows:
        sample = _sample_of(row, sample_col)
        if sample and sample not in order:
            order.append(sample)
    for sample in order:
        selected = [r for r in rows if _sample_of(r, sample_col) == sample]
        line = {sample_col: sample, "n": len(selected)}
        for column in columns:
            pairs = [(number_of(r.get(column)), number_of(r.get(weight_column)) if weight_column else 1.0)
                     for r in selected]
            values = np.array([v for v, w in pairs if v is not None])
            line[f"{column} mean"] = float(values.mean()) if len(values) else ""
            line[f"{column} SD"] = float(values.std(ddof=1)) if len(values) > 1 else ""
            line[f"{column} SE"] = float(values.std(ddof=1) / math.sqrt(len(values))) if len(values) > 1 else ""
            line[f"{column} n"] = len(values)
            if weight_column:
                both = [(v, w) for v, w in pairs if v is not None and w is not None and w >= 0]
                if len(both) > 1 and sum(w for _, w in both) > 0:
                    mean, se = iso_weighted(both)
                    line[f"{column} weighted mean"] = mean
                    line[f"{column} weighted SE"] = se if math.isfinite(se) else ""
                else:
                    line[f"{column} weighted mean"] = line[f"{column} weighted SE"] = ""
        out.append(line)
    if not any(isinstance(v, float) for line in out for k, v in line.items() if k.endswith(" mean")):
        raise NodeProblem("None of the chosen columns holds a number in any sample.")
    titles = list(out[0].keys())
    weighted = f", weighted by {weight_column}" if weight_column else ""
    return SummaryResult(out, titles, f"{len(out)} sample{'s' if len(out) != 1 else ''}, "
                                      f"{len(columns)} column{'s' if len(columns) != 1 else ''}{weighted}.")


def iso_weighted(pairs):
    """(weighted mean, standard error) of [(value, weight)], by Kirchner & Allen's amount-weighted formulas."""
    from sed_stats.emsa import weighted_mean_and_se
    return weighted_mean_and_se([v for v, _ in pairs], [w for _, w in pairs])
