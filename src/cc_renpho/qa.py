"""Data-quality analysis of a Renpho measurement history.

This is the part of cc-renpho that does not exist elsewhere. Pulling the data is
a solved problem (the `renpho-api` package does it). Knowing whether the numbers
that come back mean anything is not.

The headline problem: when a Renpho scale takes no impedance reading, it stores
``resistance = 100`` as a placeholder - and the API still returns a fully
populated set of body-fat, muscle, water, protein and bone figures for that
record. Those figures are a formula over weight, height, age and sex. Nothing
in the response marks them as derived, so a consumer that trusts the payload
reports estimates as measurements.

Every check returns a Finding with structured evidence rather than a printed
string, so an agent can branch on the result.
"""

from __future__ import annotations

import datetime as dt
from collections import Counter
from dataclasses import dataclass, field, asdict
from typing import Any

# The placeholder a Renpho scale writes into `resistance` when it took no
# impedance reading. Real readings land in the tens of thousands.
NO_IMPEDANCE = 100

# Renpho's backend stamps `timeStamp` in UTC+8 rather than UTC. `createdAt`
# (true UTC) and `localCreatedAt` (the scale's local wall clock) agree with each
# other, so they are the pair to trust.
BACKEND_UTC_OFFSET_HOURS = 8

# Two weigh-ins this close together are one session, not two observations.
SESSION_SECONDS = 600

# A gap longer than this breaks a run of readings into separate clusters.
GAP_DAYS = 30

# BMI is stored as well as derivable; they should agree to within rounding.
BMI_TOLERANCE = 0.15

SEVERITIES = ("high", "medium", "low")


@dataclass
class Finding:
    """One data-quality problem, with the evidence that established it."""

    id: str
    severity: str
    title: str
    observed: str
    why: str
    evidence: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def parse_local(record: dict) -> dt.datetime:
    """The trustworthy timestamp. See BACKEND_UTC_OFFSET_HOURS."""
    return dt.datetime.strptime(record["localCreatedAt"], "%Y-%m-%d %H:%M:%S")


def parse_utc(record: dict) -> dt.datetime:
    return dt.datetime.strptime(record["createdAt"], "%Y-%m-%d %H:%M:%S")


def _sorted(records: list[dict]) -> list[dict]:
    return sorted(records, key=lambda m: m["localCreatedAt"])


# --------------------------------------------------------------- statistics

def summarise(records: list[dict]) -> dict[str, Any]:
    """Descriptive statistics. No judgements - those are the findings' job."""
    if not records:
        return {"count": 0}

    ms = _sorted(records)
    days = sorted({m["localCreatedAt"][:10] for m in ms})
    first, last = parse_local(ms[0]).date(), parse_local(ms[-1]).date()
    span = max((last - first).days, 1)
    weights = [m["weight"] for m in ms]
    measured = [m for m in ms if m.get("resistance") != NO_IMPEDANCE]

    return {
        "count": len(ms),
        "distinct_days": len(days),
        "first_reading": ms[0]["localCreatedAt"],
        "last_reading": ms[-1]["localCreatedAt"],
        "span_days": span,
        "day_coverage_pct": round(100.0 * len(days) / span, 2),
        "impedance_measured": len(measured),
        "composition_estimated": len(ms) - len(measured),
        "weight_min": min(weights),
        "weight_max": max(weights),
        "weight_first": weights[0],
        "weight_last": weights[-1],
        "readings_per_year": dict(sorted(Counter(m["localCreatedAt"][:4] for m in ms).items())),
    }


def gaps(records: list[dict], min_days: int = GAP_DAYS) -> list[dict]:
    """Stretches with no readings at all."""
    ms = _sorted(records)
    out = []
    for a, b in zip(ms, ms[1:]):
        days = (parse_local(b) - parse_local(a)).days
        if days > min_days:
            out.append({"from": a["localCreatedAt"][:10], "to": b["localCreatedAt"][:10], "days": days})
    return out


def densest_run(records: list[dict], within_days: int = 7) -> list[dict]:
    """The longest run of readings each within `within_days` of the next.

    Found rather than hardcoded, so it tracks the data as more arrives. This is
    the stretch where consecutive points are close enough to read as a trend.
    """
    ms = _sorted(records)
    if not ms:
        return []
    best: list[dict] = []
    run = [ms[0]]
    for a, b in zip(ms, ms[1:]):
        if (parse_local(b) - parse_local(a)).days <= within_days:
            run.append(b)
        else:
            best = max([best, run], key=len)
            run = [b]
    return max([best, run], key=len)


# ----------------------------------------------------------------- checks
#
# Each check takes the records (and optionally the server's own count) and
# returns a Finding or None. A check that finds nothing returns None - it never
# returns a "passed" Finding, so an empty findings list means every check ran
# and found nothing, not that the checks were skipped.


def check_completeness(records: list[dict], server_count: int | None) -> Finding | None:
    if server_count is None or len(records) == server_count:
        return None
    missing = server_count - len(records)
    return Finding(
        id="incomplete-download",
        severity="high",
        title="The download is short of what the server holds",
        observed=(
            f"Retrieved {len(records)} records; the server's device/count endpoint reports "
            f"{server_count}. {missing} record(s) unaccounted for."
        ),
        why=(
            "Every figure computed from this export is computed from a subset of unknown "
            "shape. Re-run the pull before drawing any conclusion from it."
        ),
        evidence={"retrieved": len(records), "server_count": server_count, "missing": missing},
    )


def check_impedance(records: list[dict]) -> Finding | None:
    estimated = [m for m in records if m.get("resistance") == NO_IMPEDANCE]
    if not estimated:
        return None

    # If composition really is a function of weight alone, the same weight must
    # produce the same composition. Count the exceptions.
    by_weight: dict[float, set] = {}
    for m in estimated:
        key = (m.get("bodyfat"), m.get("muscle"), m.get("water"))
        by_weight.setdefault(m["weight"], set()).add(key)
    conflicts = [w for w, v in by_weight.items() if len(v) > 1]

    pct = round(100.0 * len(estimated) / len(records))
    return Finding(
        id="composition-not-measured",
        severity="high" if pct >= 50 else "medium",
        title="Body-composition figures were not measured on most records",
        observed=(
            f"{len(estimated)} of {len(records)} records ({pct}%) carry "
            f"resistance = {NO_IMPEDANCE}, the placeholder the scale writes when it takes no "
            f"impedance reading. Across them there are {len(by_weight)} distinct weights and "
            f"{len(conflicts)} case(s) where the same weight yielded different composition."
        ),
        why=(
            "Body fat, muscle, water, protein and bone on those records are a formula over "
            "weight, height, age and sex - not a measurement. Two people of the same weight, "
            "height, age and sex would get identical figures. Nothing in the API response "
            "marks them as derived. Treat them as a restatement of weight."
        ),
        evidence={
            "estimated": len(estimated),
            "measured": len(records) - len(estimated),
            "percent_estimated": pct,
            "distinct_weights": len(by_weight),
            "same_weight_different_composition": len(conflicts),
        },
    )


def check_sparsity(records: list[dict]) -> Finding | None:
    stats = summarise(records)
    coverage = stats["day_coverage_pct"]
    if coverage >= 25:
        return None
    run = densest_run(records)
    concentration = round(100.0 * len(run) / len(records))
    return Finding(
        id="too-sparse-for-trend",
        severity="high" if coverage < 10 else "medium",
        title="The record is too sparse to support a trend",
        observed=(
            f"{stats['count']} readings on {stats['distinct_days']} distinct days across "
            f"{stats['span_days']} days - {coverage}% coverage. The densest run holds "
            f"{len(run)} of them ({concentration}%)."
        ),
        why=(
            "A trend line over data this sparse describes where the sampling happened to "
            "land, not what the body did. Densely sampled stretches can be read; isolated "
            "points cannot be joined to them."
        ),
        evidence={
            "coverage_pct": coverage,
            "distinct_days": stats["distinct_days"],
            "span_days": stats["span_days"],
            "densest_run": len(run),
            "densest_run_pct": concentration,
        },
    )


def check_timestamp_offset(records: list[dict]) -> Finding | None:
    """`timeStamp` disagreeing with `createdAt` by a constant is a backend quirk."""
    offsets = []
    for m in records:
        epoch_utc = dt.datetime.utcfromtimestamp(m["timeStamp"])
        offsets.append(round((parse_utc(m) - epoch_utc).total_seconds() / 3600))
    common = Counter(offsets).most_common(1)[0]
    hours, n = common
    if hours == 0:
        return None
    return Finding(
        id="timestamp-field-offset",
        severity="medium",
        title=f"The timeStamp field is {hours} hours off UTC",
        observed=(
            f"On {n} of {len(records)} records, createdAt minus "
            f"utcfromtimestamp(timeStamp) is {hours} hours. Renpho's backend stamps the "
            f"epoch in UTC+{hours}, not UTC."
        ),
        why=(
            "Code that reads the raw epoch places every weigh-in "
            f"{hours} hours early, which moves some of them onto the previous day. Use "
            "localCreatedAt (local wall clock) or createdAt (true UTC) instead."
        ),
        evidence={"offset_hours": hours, "records_affected": n, "all_offsets": dict(Counter(offsets))},
    )


def check_backfilled(records: list[dict]) -> Finding | None:
    """A record that reached the server long after its stated date.

    Rounds to the hour first: a live sync takes a second or two, so a genuine
    record sits at 5.0008 hours offset, not exactly 5.0, and an equality test
    would flag every record in the account.
    """
    live_offsets = Counter()
    for m in records:
        live_offsets[round((parse_utc(m) - parse_local(m)).total_seconds() / 3600)] += 1
    if not live_offsets:
        return None
    # The account's real UTC offsets are whichever appear often; a backfilled
    # record shows an offset of hundreds or thousands of hours.
    normal = {h for h, n in live_offsets.items() if abs(h) <= 14}
    odd = [
        m
        for m in records
        if round((parse_utc(m) - parse_local(m)).total_seconds() / 3600) not in normal
    ]
    if not odd:
        return None
    return Finding(
        id="backfilled-records",
        severity="medium",
        title="Some readings were backfilled, not recorded live",
        observed="; ".join(
            f"{m['localCreatedAt'][:10]} ({m['weight']} kg) arrived at {m['createdAt']}"
            for m in odd[:5]
        )
        + (f"; and {len(odd) - 5} more" if len(odd) > 5 else ""),
        why=(
            "These reached the server long after the date they claim, so their timing rests "
            "entirely on the app rather than on when the reading arrived. Treat their dates "
            "as asserted, not corroborated."
        ),
        evidence={
            "count": len(odd),
            "records": [
                {"local": m["localCreatedAt"], "created": m["createdAt"], "weight": m["weight"]}
                for m in odd
            ],
        },
    )


def check_duplicate_sessions(records: list[dict]) -> Finding | None:
    ms = _sorted(records)
    dupes = []
    for a, b in zip(ms, ms[1:]):
        secs = (parse_local(b) - parse_local(a)).total_seconds()
        if 0 <= secs < SESSION_SECONDS:
            dupes.append(
                {
                    "first": a["localCreatedAt"],
                    "second": b["localCreatedAt"],
                    "seconds_apart": int(secs),
                    "weights": [a["weight"], b["weight"]],
                }
            )
    if not dupes:
        return None
    return Finding(
        id="repeat-weigh-ins",
        severity="low",
        title="Some weigh-ins are repeats of the same session",
        observed=(
            f"{len(dupes)} pair(s) of readings less than {SESSION_SECONDS // 60} minutes apart - "
            "someone stepping on the scale twice, not two observations."
        ),
        why=(
            "They inflate the reading count without adding information. Count distinct days, "
            "not records, when reporting how much data there is."
        ),
        evidence={"count": len(dupes), "pairs": dupes},
    )


def check_timezone_labels(records: list[dict]) -> Finding | None:
    labels = Counter(m.get("timeZone") for m in records)
    if len(labels) <= 1:
        return None
    return Finding(
        id="inconsistent-timezone-label",
        severity="low",
        title="The timezone label is inconsistent",
        observed="Labels present: " + ", ".join(f"{k} ({v})" for k, v in labels.most_common()),
        why=(
            "The label is written by whichever app version uploaded the record, and mixes "
            "abbreviations with numeric offsets. It is not a reliable zone identifier - the "
            "local and UTC timestamps are."
        ),
        evidence={"labels": dict(labels)},
    )


def check_empty_fields(records: list[dict]) -> Finding | None:
    if not records:
        return None
    keysets = [set(m.keys()) for m in records]
    all_fields = set().union(*keysets)
    common = set.intersection(*keysets)
    empty = {None, 0, 0.0, "", False}
    dead = sorted(k for k in common if all(records[i].get(k) in empty for i in range(len(records))))
    if not dead:
        return None
    return Finding(
        id="empty-fields",
        severity="low",
        title="A large part of the payload carries no data",
        observed=(
            f"{len(dead)} of {len(all_fields)} fields are empty on every record. "
            f"{len(all_fields - common)} field(s) are missing from some records entirely."
        ),
        why=(
            "These reflect hardware the scale does not have and health services that are not "
            "connected. They are schema, not data - do not model them as nullable measurements."
        ),
        evidence={
            "empty_fields": dead,
            "total_fields": len(all_fields),
            "fields_missing_from_some_records": sorted(all_fields - common),
        },
    )


def check_bmi_consistency(records: list[dict]) -> Finding | None:
    bad = []
    for m in records:
        height_m = (m.get("height") or 0) / 100.0
        if height_m <= 0 or not m.get("bmi"):
            continue
        calc = m["weight"] / (height_m * height_m)
        if abs(calc - m["bmi"]) > BMI_TOLERANCE:
            bad.append(
                {"local": m["localCreatedAt"], "stored": m["bmi"], "calculated": round(calc, 2)}
            )
    if not bad:
        return None
    return Finding(
        id="bmi-inconsistent",
        severity="medium",
        title="Stored BMI does not match weight and height",
        observed=f"{len(bad)} record(s) where stored BMI differs from weight/height^2 by more than {BMI_TOLERANCE}.",
        why=(
            "Either the stored height changed without the BMI being recomputed, or the BMI "
            "was calculated against a different profile. Recompute rather than trusting the "
            "stored value."
        ),
        evidence={"count": len(bad), "records": bad[:20]},
    )


def check_profile_drift(records: list[dict]) -> Finding | None:
    """Height, birthday and sex feed every derived figure. They should not move."""
    drifted = {}
    for key in ("height", "birthday", "gender"):
        values = Counter(m.get(key) for m in records if key in m)
        if len(values) > 1:
            drifted[key] = dict(values)
    if not drifted:
        return None
    return Finding(
        id="profile-drift",
        severity="medium",
        title="Profile constants changed across the history",
        observed="Fields that changed: "
        + "; ".join(f"{k} = {v}" for k, v in drifted.items()),
        why=(
            "BMI, BMR, body age and the whole composition estimate are computed from these. "
            "A change part-way through means readings before and after are not comparable."
        ),
        evidence={"drifted": drifted},
    )


CHECKS_WITH_SERVER_COUNT = (check_completeness,)

CHECKS = (
    check_impedance,
    check_sparsity,
    check_timestamp_offset,
    check_backfilled,
    check_bmi_consistency,
    check_profile_drift,
    check_duplicate_sessions,
    check_timezone_labels,
    check_empty_fields,
)


def run_checks(records: list[dict], server_count: int | None = None) -> list[Finding]:
    """Run every check. Returns findings ordered high severity first.

    An empty list means all checks ran and none fired. It never means the checks
    were skipped: an empty `records` list raises instead.
    """
    if not records:
        raise ValueError(
            "No records to analyse. An empty history is a failed download, not a clean bill "
            "of health - re-run the pull and check the credentials."
        )

    findings: list[Finding] = []
    for check in CHECKS_WITH_SERVER_COUNT:
        found = check(records, server_count)
        if found:
            findings.append(found)
    for check in CHECKS:
        found = check(records)
        if found:
            findings.append(found)

    findings.sort(key=lambda f: SEVERITIES.index(f.severity))
    return findings


def analyse(records: list[dict], server_count: int | None = None) -> dict[str, Any]:
    """The whole QA pass as one JSON-serialisable dict."""
    findings = run_checks(records, server_count)
    return {
        "summary": summarise(records),
        "gaps": gaps(records),
        "densest_run": {
            "readings": len(densest_run(records)),
            "from": densest_run(records)[0]["localCreatedAt"][:10] if records else None,
            "to": densest_run(records)[-1]["localCreatedAt"][:10] if records else None,
        },
        "findings": [f.to_dict() for f in findings],
        "severity_counts": {s: sum(1 for f in findings if f.severity == s) for s in SEVERITIES},
    }
