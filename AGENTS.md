# Driving cc-renpho as an agent

Everything here is designed so you never have to parse prose or answer a prompt.

## The contract

* Every command accepts `--json` and prints **one** JSON object on stdout, nothing else.
* Human-readable output appears only when `--json` is absent. Errors always go to stderr.
* Nothing prompts, ever. A missing credential is an error with an exit code, not a question.
* Exit codes are stable and are the primary signal:

| Code | Meaning | What to do |
|---|---|---|
| 0 | success | continue |
| 1 | unexpected failure | read stderr, report it, stop |
| 2 | configuration problem | credentials or a path are missing; fix and retry |
| 3 | authentication rejected | wrong password, or the account is on the older Renpho app; do not retry the same password |
| 4 | API refused the request | Renpho-side; retry once, then stop |
| 5 | download was short | the export is incomplete; do not analyse it, re-run `pull` |
| 6 | QA threshold met | data quality below the bar you set with `--fail-on` |

## Credentials

Read from `RENPHO_EMAIL` and `RENPHO_PASSWORD` in the environment, or from a file passed with
`--credentials-file` containing them as `KEY=VALUE` lines. The password is the plaintext
account password — the client performs the encryption the app does. Never write credentials
into this repository or into an output directory.

## The normal sequence

```bash
cc-renpho doctor --json          # exit 0 proves the credentials work before anything else runs
cc-renpho pull --json -o data    # exit 5 here means do not trust the files
cc-renpho qa --json -i data/measurements.json
cc-renpho report -i data/measurements.json -o report.html --anonymous
```

`doctor` downloads nothing, so it is the cheap way to check credentials before a longer run.

## Reading the QA output

```json
{
  "summary": { "count": 42, "distinct_days": 32, "day_coverage_pct": 2.39,
               "impedance_measured": 8, "composition_estimated": 34 },
  "gaps": [ { "from": "2023-04-30", "to": "2024-09-16", "days": 504 } ],
  "densest_run": { "readings": 32, "from": "2023-01-09", "to": "2023-02-08" },
  "findings": [ { "id": "...", "severity": "high", "title": "...",
                  "observed": "...", "why": "...", "evidence": { } } ],
  "severity_counts": { "high": 2, "medium": 2, "low": 3 }
}
```

Branch on `findings[].id`, never on the wording of `title` or `observed` — ids are stable,
prose is not. `evidence` holds the numbers behind each finding so you can apply your own
threshold instead of accepting the built-in severity.

## Two things to get right

**`composition_estimated` is the number that matters.** Records where the scale took no
impedance reading still come back with a full set of body-fat, muscle and water figures,
computed from weight. If `composition_estimated` is greater than zero, do not report body
composition as measured, and do not attribute a change in body fat to anything but the weight
change that produced it. The per-record marker is `resistance == 100`.

**An empty result is a broken instrument, not a clean run.** `qa` raises on an empty
measurement history rather than reporting no findings, and `pull` exits 5 rather than 0 when
the download is short of the server's own count. If you add checks of your own, hold them to
the same rule: a check whose pass condition is an absence will certify a run that never
happened.

## Offline analysis

`qa` and `report` accept `-i/--input` pointing at a `measurements.json` from an earlier pull,
so repeated analysis costs no API calls. Note that offline runs skip the completeness check —
there is no server to ask — so the `incomplete-download` finding cannot fire. Run `pull` for
that check, and only trust its exit code, not the absence of the finding.

## Python API

```python
from cc_renpho import Renpho, analyse, render

account = Renpho(email, password)
account.login()
records = account.measurements()
result = analyse(records, account.server_record_count())

if any(f["severity"] == "high" for f in result["findings"]):
    ...
```

`cc_renpho.qa` exposes each check individually (`check_impedance`, `check_sparsity`, and the
rest). Each returns a `Finding` or `None` — never a "passed" finding — so composing your own
subset is straightforward.

## Privacy

Measurement data is personal health data. It stays on the machine that ran the pull; this tool
uploads nothing. Pass `--anonymous` to keep the account email out of a report you intend to
share, and do not commit an output directory to a repository.
