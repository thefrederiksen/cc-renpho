"""cc-renpho command line.

Built to be driven by an agent as much as by a person:

* every command takes --json and prints one JSON object on stdout, nothing else
* human output goes to stdout only when --json is absent; errors always go to stderr
* nothing ever prompts, so it cannot hang in an unattended run
* exit codes are a contract (see errors.py and `cc-renpho --help`)

The exit codes:

    0  success
    1  unexpected failure
    2  configuration problem (missing credentials, bad path)
    3  authentication rejected
    4  the API accepted the login but refused the request
    5  the download was short of what the server reports
    6  QA findings met or exceeded --fail-on
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import __version__
from .client import Renpho, load_credentials
from .errors import CcRenphoError, ConfigError, IncompleteDownloadError
from .export import read_json, write_csv, write_json
from .qa import SEVERITIES, analyse
from .report import render

FAIL_ON_EXIT = 6


def _emit(payload: dict, as_json: bool, human: str) -> None:
    if as_json:
        print(json.dumps(payload, indent=2))
    else:
        print(human)


def _connect(args) -> Renpho:
    email, password = load_credentials(args.credentials_file)
    account = Renpho(email, password, debug=args.debug)
    account.login()
    return account


def _load_records(args) -> tuple[list[dict], int | None, str | None]:
    """Records either from a previous pull on disk, or straight from the API.

    Returns (records, server_count, account_label). server_count is None when
    reading from a file - there is no server to ask, and inventing a count that
    always matches would turn the completeness check into one that cannot fail.
    """
    if args.input:
        path = Path(args.input)
        if not path.exists():
            raise ConfigError(f"Input file not found: {path}")
        return read_json(path), None, None
    account = _connect(args)
    return account.measurements(), account.server_record_count(), account.email


# ------------------------------------------------------------------ commands

def cmd_doctor(args) -> int:
    """Check credentials and connectivity without downloading anything."""
    email, password = load_credentials(args.credentials_file)
    account = Renpho(email, password, debug=args.debug)
    user_id = account.login()
    count = account.server_record_count()
    payload = {
        "ok": True,
        "account": email,
        "user_id": user_id,
        "server_record_count": count,
        "version": __version__,
    }
    _emit(
        payload,
        args.json,
        f"OK. Signed in as {email} (user_id {user_id}). "
        f"Server reports {count if count is not None else 'an unknown number of'} scale records.",
    )
    return 0


def cmd_pull(args) -> int:
    """Download the full measurement history to JSON and CSV."""
    account = _connect(args)
    expected = account.server_record_count()
    records = account.measurements()

    out = Path(args.output_dir)
    json_path = write_json(records, out / "measurements.json")
    csv_path = write_csv(records, out / "measurements.csv")

    payload = {
        "ok": True,
        "account": account.email,
        "retrieved": len(records),
        "server_record_count": expected,
        "complete": expected is None or len(records) == expected,
        "files": {"json": str(json_path), "csv": str(csv_path)},
        "first_reading": records[0]["localCreatedAt"] if records else None,
        "last_reading": records[-1]["localCreatedAt"] if records else None,
    }

    if expected is not None and len(records) != expected:
        # Write the files anyway - a partial export is still evidence - but fail
        # loudly. A short download that exits 0 is indistinguishable from a good one.
        if args.json:
            print(json.dumps({**payload, "ok": False}, indent=2))
        raise IncompleteDownloadError(
            f"Retrieved {len(records)} records but the server reports {expected}. "
            f"Files were written to {out} but are incomplete."
        )

    _emit(
        payload,
        args.json,
        f"Downloaded {len(records)} of {expected} records to {json_path} and {csv_path}.",
    )
    return 0


def cmd_qa(args) -> int:
    """Run the quality checks and report findings."""
    records, server_count, _ = _load_records(args)
    result = analyse(records, server_count)

    if args.json:
        print(json.dumps(result, indent=2))
    else:
        stats = result["summary"]
        sev = result["severity_counts"]
        print(f"{stats['count']} records, {stats['distinct_days']} distinct days, "
              f"{stats['day_coverage_pct']}% coverage")
        print(f"{stats['impedance_measured']} with real impedance, "
              f"{stats['composition_estimated']} with composition estimated from weight")
        print(f"Findings: {sev['high']} high, {sev['medium']} medium, {sev['low']} low")
        for finding in result["findings"]:
            print()
            print(f"[{finding['severity'].upper()}] {finding['title']}  ({finding['id']})")
            print(f"  {finding['observed']}")
            print(f"  Why: {finding['why']}")

    if args.fail_on != "none":
        threshold = SEVERITIES.index(args.fail_on)
        triggered = [f for f in result["findings"] if SEVERITIES.index(f["severity"]) <= threshold]
        if triggered:
            print(
                f"cc-renpho: {len(triggered)} finding(s) at or above severity "
                f"'{args.fail_on}'",
                file=sys.stderr,
            )
            return FAIL_ON_EXIT
    return 0


def cmd_report(args) -> int:
    """Generate the standalone HTML quality report."""
    records, server_count, label = _load_records(args)
    result = analyse(records, server_count)
    html = render(records, result, account_label=None if args.anonymous else label)

    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(html, encoding="utf-8")

    payload = {
        "ok": True,
        "report": str(out),
        "bytes": out.stat().st_size,
        "records": result["summary"]["count"],
        "severity_counts": result["severity_counts"],
    }
    _emit(payload, args.json, f"Wrote {out} ({out.stat().st_size:,} bytes) "
                              f"covering {result['summary']['count']} records.")
    return 0


# -------------------------------------------------------------------- parser

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="cc-renpho",
        description="Download and quality-check a Renpho smart scale history.",
        epilog=(
            "Exit codes: 0 ok, 1 unexpected, 2 config, 3 auth, 4 api, "
            "5 incomplete download, 6 QA threshold met."
        ),
    )
    parser.add_argument("--version", action="version", version=f"cc-renpho {__version__}")

    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--json", action="store_true",
                        help="print one JSON object on stdout and nothing else")
    common.add_argument("--credentials-file", metavar="PATH",
                        help="file with RENPHO_EMAIL and RENPHO_PASSWORD as KEY=VALUE lines")
    common.add_argument("--debug", action="store_true", help="verbose client logging")

    offline = argparse.ArgumentParser(add_help=False)
    offline.add_argument("-i", "--input", metavar="FILE",
                         help="analyse a measurements.json from a previous pull instead of "
                              "downloading (skips the server-count completeness check)")

    sub = parser.add_subparsers(dest="command", required=True)

    doctor = sub.add_parser("doctor", parents=[common],
                            help="check credentials and connectivity, download nothing")
    doctor.set_defaults(func=cmd_doctor)

    pull = sub.add_parser("pull", parents=[common],
                          help="download the full history to JSON and CSV")
    pull.add_argument("-o", "--output-dir", default="renpho_data", metavar="DIR",
                      help="where to write measurements.json and measurements.csv "
                           "(default: renpho_data)")
    pull.set_defaults(func=cmd_pull)

    qa = sub.add_parser("qa", parents=[common, offline],
                        help="run the data-quality checks")
    qa.add_argument("--fail-on", choices=("none",) + SEVERITIES, default="none",
                    help="exit 6 if any finding is at or above this severity "
                         "(default: none, always exit 0)")
    qa.set_defaults(func=cmd_qa)

    report = sub.add_parser("report", parents=[common, offline],
                            help="generate the standalone HTML quality report")
    report.add_argument("-o", "--output", default="renpho-report.html", metavar="FILE",
                        help="output path (default: renpho-report.html)")
    report.add_argument("--anonymous", action="store_true",
                        help="omit the account email from the page")
    report.set_defaults(func=cmd_report)

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return args.func(args)
    except CcRenphoError as exc:
        print(f"cc-renpho: {exc}", file=sys.stderr)
        return exc.exit_code
    except KeyboardInterrupt:
        print("cc-renpho: interrupted", file=sys.stderr)
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
