"""Approximate a filing-period date for an FEC disbursement, for the weekly
disclosure-timeline histogram.

FEC's oppexp bulk file (the only source this pipeline uses for Schedule B)
does NOT carry the report's actual filed/received date -- only RPT_TP (a
report-type code, e.g. "Q1", "M3", "12G") and RPT_YR (a year). Getting the
true filed date would require a separate data source (the FEC's electronic
filing index, via the openFEC API) that this pipeline does not fetch.

What this module does instead: map the well-defined, calendar-fixed report
types (quarterly, monthly, mid-year, year-end) to that period's own
deadline date, and the two pre/post-GENERAL-election codes to a date
computed from the federal general election's own fixed calendar rule (the
Tuesday after the first Monday in November). Every other code --
pre-primary, pre-convention, pre-runoff, special-election, and termination
reports, whose windows depend on a specific state's own election calendar
this pipeline does not have -- falls back to the transaction's own date
rather than guessing. This is a deadline approximation, not a disclosed
fact, and the dashboard labels it as such.
"""
from __future__ import annotations

from calendar import monthrange
from datetime import date, timedelta


def _last_day(year: int, month: int) -> date:
    return date(year, month, monthrange(year, month)[1])


def general_election_date(year: int) -> date:
    """The federal general election: the Tuesday after the first Monday in November."""
    d = date(year, 11, 1)
    days_to_monday = (7 - d.weekday()) % 7  # weekday(): Monday=0
    first_monday = d + timedelta(days=days_to_monday)
    return first_monday + timedelta(days=1)


_MONTH_CODES = {f"M{m}": m for m in range(1, 13)}


def approximate_report_date(rpt_tp: str, rpt_yr: str, transaction_dt: str) -> date | None:
    """Best-available date for the report an oppexp row was disclosed under.

    Returns a real calendar-rule deadline for quarterly/monthly/mid-year/
    year-end reports and pre/post-GENERAL reports; falls back to parsing
    `transaction_dt` for every other report type (see module docstring).
    Returns None if neither is available/parseable.
    """
    rpt_tp = (rpt_tp or "").strip().upper()
    try:
        year = int(rpt_yr)
    except (TypeError, ValueError):
        year = None

    if year:
        if rpt_tp == "Q1":
            return date(year, 4, 15)
        if rpt_tp == "Q2":
            return date(year, 7, 15)
        if rpt_tp == "Q3":
            return date(year, 10, 15)
        if rpt_tp == "MY":
            return date(year, 7, 31)
        if rpt_tp == "YE":
            return date(year + 1, 1, 31)
        if rpt_tp in _MONTH_CODES:
            month = _MONTH_CODES[rpt_tp]
            due_month, due_year = (month + 1, year) if month < 12 else (1, year + 1)
            return date(due_year, due_month, 20)
        if rpt_tp == "12G":
            return general_election_date(year) - timedelta(days=12)
        if rpt_tp == "30G":
            return general_election_date(year) + timedelta(days=30)

    return parse_mmddyyyy(transaction_dt)


def parse_mmddyyyy(value: str) -> date | None:
    if not value:
        return None
    value = value.strip()
    for fmt_sep in ("/", "-"):
        parts = value.split(fmt_sep)
        if len(parts) == 3:
            try:
                a, b, c = (int(p) for p in parts)
            except ValueError:
                continue
            # FEC's TRANSACTION_DT is MMDDYYYY (no separator) most of the time;
            # handle both that and an already-separated M/D/YYYY just in case.
            return date(c, a, b) if c > 31 else None
    if len(value) == 8 and value.isdigit():
        try:
            return date(int(value[4:8]), int(value[0:2]), int(value[2:4]))
        except ValueError:
            return None
    return None
