"""
Dates: reading the date formats that turn up in field and lab spreadsheets, and the parts
of a date that hydrology groups by (water year, season, day of water year).

Everything is naive local time: a time zone in the text (a trailing Z, +01:00) is
dropped, not converted. A number is never taken to be a date, because a year (2021) and
an Excel serial number are indistinguishable from other numbers.

Formats read, by trying each in turn:
    2021-01-16   2021-01-16 13:45[:30]   2021-01-16T13:45[:30]   2021/01/16   2021-01
    1/16/2021    1/16/21                  16-Jan-2021              Jan 16, 2021
The last two numeric forms read month first unless `day_first` (16/1/2021) says otherwise.
A year and month alone is the first of the month.
"""
import calendar
import math
import re
from datetime import date, datetime, timedelta

MONTH_NAMES = ["January", "February", "March", "April", "May", "June", "July", "August",
               "September", "October", "November", "December"]

_ISO = ("%Y-%m-%d", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%dT%H:%M", "%Y/%m/%d", "%Y/%m/%d %H:%M", "%Y-%m")
_NAMED = ("%d-%b-%Y", "%d-%B-%Y", "%b %d, %Y", "%B %d, %Y", "%d %b %Y", "%d %B %Y")
_MONTH_FIRST = ("%m/%d/%Y", "%m/%d/%y", "%m/%d/%Y %H:%M", "%m-%d-%Y")
_DAY_FIRST = ("%d/%m/%Y", "%d/%m/%y", "%d/%m/%Y %H:%M", "%d-%m-%Y")
_ZONE = re.compile(r"(Z|[+-]\d{2}:?\d{2})$")


def parse_date(value, day_first=False):
    """
    A datetime from a cell, or None if it is blank or not a date.

    Args:
        value: a datetime or date, or text in one of the formats above
        day_first: read 16/1/2021 as 16 January rather than failing on month 16
    """
    if isinstance(value, datetime):
        return value.replace(tzinfo=None)
    if isinstance(value, date):
        return datetime(value.year, value.month, value.day)
    if not isinstance(value, str):
        return None
    text = value.strip()
    if not text:
        return None
    text = _ZONE.sub("", text) if "T" in text or ":" in text else text
    for formats in (_ISO, _NAMED, _DAY_FIRST if day_first else _MONTH_FIRST):
        for fmt in formats:
            try:
                return datetime.strptime(text, fmt)
            except ValueError:
                continue
    return None


def is_leap(year):
    return calendar.isleap(year)


def water_year(when, start_month=10):
    """
    The water year a date falls in, named by the year it ends in: with the usual October
    start, 1 October 2020 to 30 September 2021 is water year 2021.
    """
    if not 1 <= start_month <= 12:
        raise ValueError("The water year must start in a month from 1 to 12.")
    if start_month == 1:
        return when.year
    return when.year + 1 if when.month >= start_month else when.year


def water_year_start(when, start_month=10):
    """The first day of the water year `when` falls in."""
    year = water_year(when, start_month) - (1 if start_month != 1 else 0)
    return datetime(year, start_month, 1)


def day_of_water_year(when, start_month=10):
    """1 on the first day of the water year (so 1 October, usually), up to 365 or 366."""
    return (datetime(when.year, when.month, when.day) - water_year_start(when, start_month)).days + 1


def day_of_year(when):
    return when.timetuple().tm_yday


def decimal_year(when):
    """The year and the fraction of it elapsed at the start of the day: 2021.5 is about 2 July."""
    days = 366 if is_leap(when.year) else 365
    return when.year + (day_of_year(when) - 1 + (when.hour * 3600 + when.minute * 60 + when.second) / 86400) / days


# ----------------------------------------------------------------------- Julian dates
# The Julian date (JD) counts days, with the fraction of a day, from noon on 1 January 4713 BC in
# the Julian calendar (24 November 4714 BC in the Gregorian). A day therefore begins at noon, and
# midnight is a half: 1 January 2021 at 00:00 is 2459215.5, and at noon 2459216.0. Dates are taken as
# written (no time zone is applied) and in the proleptic Gregorian calendar. Not to be confused
# with the "Julian day" of hydrology and ecology, which is the day of the year, 1 to 366
# (`day_of_year`).

JD_OF_ORDINAL_ZERO = 1721424.5          # the JD of midnight at the start of day 0 of Python's ordinal
MJD_OFFSET = 2400000.5                  # MJD = JD - 2400000.5, which makes the count start at midnight


def julian_date(when):
    """The Julian date of a datetime: 2000-01-01 12:00 is 2451545.0."""
    seconds = when.hour * 3600 + when.minute * 60 + when.second + when.microsecond / 1e6
    return when.toordinal() + JD_OF_ORDINAL_ZERO + seconds / 86400.0


def modified_julian_date(when):
    """The Modified Julian date, JD - 2400000.5, which begins each day at midnight: 2021-01-01 is 59215.0."""
    return julian_date(when) - MJD_OFFSET


def julian_day_number(when):
    """
    The whole number of the Julian day that holds the noon of this date: 1 January 2021 is 2459216,
    whatever the time of day. (The JD of that date at midnight is 2459215.5.)
    """
    return math.floor(julian_date(datetime(when.year, when.month, when.day)) + 0.5)


def from_julian_date(jd):
    """
    The datetime a Julian date is, the inverse of `julian_date`, to the millisecond (a double holds
    a Julian date of today to only about ten microseconds).
    """
    whole = math.floor(jd - JD_OF_ORDINAL_ZERO)
    fraction = jd - JD_OF_ORDINAL_ZERO - whole
    return datetime.fromordinal(int(whole)) + timedelta(seconds=round(fraction * 86400.0, 3))


# Meteorological seasons, northern hemisphere; the southern ones are six months apart.
_SEASONS_NORTH = {12: "Winter", 1: "Winter", 2: "Winter", 3: "Spring", 4: "Spring", 5: "Spring",
                  6: "Summer", 7: "Summer", 8: "Summer", 9: "Autumn", 10: "Autumn", 11: "Autumn"}
_SEASONS_SOUTH = {m: _SEASONS_NORTH[(m - 1 + 6) % 12 + 1] for m in range(1, 13)}


def season(when, hemisphere="north"):
    """Winter (Dec-Feb), Spring (Mar-May), Summer (Jun-Aug) or Autumn (Sep-Nov); flipped in the south."""
    return (_SEASONS_SOUTH if hemisphere == "south" else _SEASONS_NORTH)[when.month]


def parse_months(text):
    """
    A set of months from "12,1,2,3", "Dec-Mar" or "Nov, Dec, Jan"; a range may wrap the year.

    Raises:
        ValueError: for anything else, naming the part it could not read
    """
    names = {n[:3].lower(): i + 1 for i, n in enumerate(MONTH_NAMES)}

    def month(token):
        token = token.strip().lower()
        if token.isdigit():
            number = int(token)
        else:
            number = names.get(token[:3])
        if number is None or not 1 <= number <= 12:
            raise ValueError(f"'{token}' is not a month (use 1-12 or names like Dec).")
        return number

    months = set()
    for part in str(text or "").split(","):
        if not part.strip():
            continue
        if "-" in part:
            first, _, last = part.partition("-")
            a, b = month(first), month(last)
            span = range(a, b + 1) if a <= b else list(range(a, 13)) + list(range(1, b + 1))
            months.update(span)
        else:
            months.add(month(part))
    if not months:
        raise ValueError("List at least one month.")
    return months


def two_seasons(when, months, first_name, second_name):
    """`first_name` when the date's month is in `months`, else `second_name`."""
    return first_name if when.month in months else second_name


def month_tick_positions(start_month=10, year=2001):
    """
    (day of water year, month name) for the first of each month of a (non-leap) water year,
    for labelling an axis of day of water year.
    """
    ticks = []
    for k in range(12):
        month = (start_month - 1 + k) % 12 + 1
        when = datetime(year + (1 if (start_month != 1 and month < start_month) else 0), month, 1)
        ticks.append((day_of_water_year(when, start_month), MONTH_NAMES[month - 1][:3]))
    return ticks


_MONTH_DAYS = [31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]          # a year without a leap day


def reference_day(month, day, start_month=10):
    """
    The day of the water year of a calendar day, counted in a year without a leap day, so
    that the same date has the same number in every year; None for 29 February.
    """
    if month == 2 and day == 29:
        return None
    before = 0
    m = start_month
    while m != month:
        before += _MONTH_DAYS[m - 1]
        m = m % 12 + 1
    return before + day


def month_span(month, start_month=10):
    """(first reference day, number of days) of a month in the water year."""
    return reference_day(month, 1, start_month), _MONTH_DAYS[month - 1]
