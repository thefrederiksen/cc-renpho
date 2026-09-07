"""Tests for the quality checks, driven by the synthetic fixture.

The fixture in examples/ is seeded with one instance of every problem the checks
look for, so a check that stops firing here has regressed.
"""

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "examples"))

from cc_renpho import qa  # noqa: E402
from cc_renpho.report import render  # noqa: E402

FIXTURE = Path(__file__).resolve().parents[1] / "examples" / "sample_measurements.json"


@pytest.fixture(scope="module")
def records():
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def ids(findings):
    return {f.id if hasattr(f, "id") else f["id"] for f in findings}


# ------------------------------------------------------------- every check fires


def test_fixture_triggers_every_check(records):
    """The fixture exists to exercise all of them; a silent check is a broken check."""
    found = ids(qa.run_checks(records))
    expected = {
        "composition-not-measured",
        "too-sparse-for-trend",
        "timestamp-field-offset",
        "backfilled-records",
        "repeat-weigh-ins",
        "inconsistent-timezone-label",
        "empty-fields",
    }
    assert expected <= found, f"checks that did not fire: {expected - found}"


def test_findings_ordered_by_severity(records):
    severities = [f.severity for f in qa.run_checks(records)]
    ranks = [qa.SEVERITIES.index(s) for s in severities]
    assert ranks == sorted(ranks)


# ------------------------------------------------------------------- individual


def test_impedance_check_counts_placeholders(records):
    finding = qa.check_impedance(records)
    estimated = sum(1 for m in records if m["resistance"] == qa.NO_IMPEDANCE)
    assert finding.evidence["estimated"] == estimated
    assert finding.evidence["measured"] == len(records) - estimated
    assert finding.severity == "high"


def test_impedance_check_silent_when_all_measured(records):
    all_measured = [dict(m, resistance=31000) for m in records]
    assert qa.check_impedance(all_measured) is None


def test_timestamp_offset_detects_the_utc8_quirk(records):
    finding = qa.check_timestamp_offset(records)
    assert finding.evidence["offset_hours"] == qa.BACKEND_UTC_OFFSET_HOURS
    assert finding.evidence["records_affected"] == len(records)


def test_backfill_check_ignores_the_sync_delay(records):
    """A live record's createdAt is a second or two past the wall clock offset.

    An equality test on the offset flags every record in the account; this
    regression guard is why the check rounds to the hour.
    """
    finding = qa.check_backfilled(records)
    assert finding.evidence["count"] == 1
    assert finding.evidence["records"][0]["local"].startswith("2025-04-09")


def test_repeat_session_check_finds_the_seconds_apart_pair(records):
    finding = qa.check_duplicate_sessions(records)
    assert finding.evidence["count"] == 1
    assert finding.evidence["pairs"][0]["seconds_apart"] < qa.SESSION_SECONDS


def test_bmi_check_silent_on_consistent_data(records):
    assert qa.check_bmi_consistency(records) is None


def test_bmi_check_fires_when_stored_bmi_is_wrong(records):
    broken = [dict(records[0], bmi=99.0)] + records[1:]
    finding = qa.check_bmi_consistency(broken)
    assert finding.evidence["count"] == 1


def test_profile_drift_silent_on_stable_profile(records):
    assert qa.check_profile_drift(records) is None


def test_profile_drift_fires_when_height_changes(records):
    drifted = [dict(records[0], height=180.0)] + records[1:]
    finding = qa.check_profile_drift(drifted)
    assert "height" in finding.evidence["drifted"]


def test_completeness_check_fires_on_short_download(records):
    finding = qa.check_completeness(records, server_count=len(records) + 3)
    assert finding.severity == "high"
    assert finding.evidence["missing"] == 3


def test_completeness_check_silent_when_counts_agree(records):
    assert qa.check_completeness(records, server_count=len(records)) is None


def test_completeness_check_silent_when_server_count_unknown(records):
    assert qa.check_completeness(records, server_count=None) is None


# ------------------------------------------------------- absence is not success


def test_empty_history_raises_rather_than_passing():
    """A failed download must never look like a clean bill of health."""
    with pytest.raises(ValueError):
        qa.run_checks([])


# ------------------------------------------------------------------ statistics


def test_summarise_counts_days_not_records(records):
    stats = qa.summarise(records)
    assert stats["count"] == len(records)
    # The fixture holds one same-session repeat, so days must trail records.
    assert stats["distinct_days"] == stats["count"] - 1


def test_densest_run_is_the_daily_stretch(records):
    run = qa.densest_run(records)
    assert len(run) > len(records) / 2
    assert run[0]["localCreatedAt"].startswith("2024-03-01")


def test_gaps_are_ordered_and_positive(records):
    found = qa.gaps(records)
    assert found
    assert all(g["days"] > qa.GAP_DAYS for g in found)


# ---------------------------------------------------------------------- report


def test_report_omits_the_account_email_when_not_given(records):
    """--anonymous passes account_label=None; the address must not leak anyway."""
    analysis = qa.analyse(records)
    with_label = render(records, analysis, account_label="someone@example.com")
    without = render(records, analysis, account_label=None)

    assert "someone@example.com" in with_label
    assert "someone@example.com" not in without
    assert "<!doctype html>" in without


def test_report_includes_every_finding_id(records):
    analysis = qa.analyse(records)
    html = render(records, analysis)
    for finding in analysis["findings"]:
        assert finding["id"] in html


def test_analyse_is_json_serialisable(records):
    json.dumps(qa.analyse(records))
