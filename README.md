# cc-renpho

Download your Renpho smart scale history, and find out what the numbers are actually worth.

Renpho publishes no API. The Renpho Health app talks to a private REST backend at
`cloud.renpho.com` where every request and response body is AES-128-ECB encrypted with a key
compiled into the app. Getting the data out of it is a solved problem — the
[`renpho-api`](https://github.com/danvaneijck/renpho-api) package does the protocol work, and
cc-renpho depends on it rather than reimplementing it.

What is not solved is knowing whether the data means anything. That is what this tool is for.

## The finding that motivated it

**When a Renpho scale takes no impedance reading, it stores `resistance = 100` as a
placeholder — and the API still returns a fully populated set of body-fat, muscle, water,
protein and bone figures for that record.**

Those figures are a formula over weight, height, age and sex. Two people with the same weight,
height, age and sex get identical numbers. Nothing in the API response marks them as derived.
A consumer that trusts the payload reports estimates as measurements, and a user watching their
body-fat percentage move is watching their weight move with extra decimal places.

On the account this tool was built against, 34 of 42 records were like that — 81% of the
body-composition history, computed rather than measured.

A second one worth knowing: **`timeStamp` is stamped in UTC+8, not UTC.** Code that reads the
raw epoch places every weigh-in eight hours early, which moves some of them onto the previous
day. Use `localCreatedAt` or `createdAt`.

## Install

```bash
pip install cc-renpho
```

Credentials come from the environment (or a file — see below). The password is your plaintext
account password; the client performs the same encryption the app does.

```bash
export RENPHO_EMAIL=you@example.com
export RENPHO_PASSWORD=...
```

## Use

```bash
cc-renpho doctor                  # check credentials and connectivity, download nothing
cc-renpho pull                    # full history to renpho_data/measurements.{json,csv}
cc-renpho qa                      # run the quality checks
cc-renpho report -o report.html   # standalone HTML report
```

`qa` and `report` also work offline against a previous pull:

```bash
cc-renpho report -i renpho_data/measurements.json -o report.html
```

The report is a single self-contained HTML file — no server, no build step, no JavaScript. It
states what the data is worth before it shows any of it. See
[`examples/sample_report.html`](examples/sample_report.html), generated from the synthetic
fixture in this repo.

## Built for agents

Every command takes `--json` and prints exactly one JSON object on stdout. Nothing ever
prompts, so it cannot hang in an unattended run. Exit codes are a contract:

| Code | Meaning |
|---|---|
| 0 | success |
| 1 | unexpected failure |
| 2 | configuration problem (missing credentials, bad path) |
| 3 | authentication rejected |
| 4 | API accepted the login but refused the request |
| 5 | download was short of what the server reports |
| 6 | QA findings met or exceeded `--fail-on` |

Exit 5 matters more than it looks. The server reports its own record count, and `pull`
compares against it. Without that check a short download is indistinguishable from a complete
one — which is exactly how a health export quietly loses half a history.

Gate a pipeline on data quality:

```bash
cc-renpho qa --json --fail-on high || echo "not fit to draw conclusions from"
```

Findings are structured, not prose:

```json
{
  "id": "composition-not-measured",
  "severity": "high",
  "title": "Body-composition figures were not measured on most records",
  "observed": "34 of 42 records (81%) carry resistance = 100 ...",
  "why": "Body fat, muscle, water, protein and bone on those records are a formula ...",
  "evidence": { "estimated": 34, "measured": 8, "percent_estimated": 81 }
}
```

There is also a Python API:

```python
from cc_renpho import Renpho, analyse, render

account = Renpho(email, password)
account.login()
records = account.measurements()
result = analyse(records, account.server_record_count())

print(result["severity_counts"])
open("report.html", "w", encoding="utf-8").write(render(records, result))
```

Agent-facing usage notes live in [AGENTS.md](AGENTS.md).

## The checks

| id | Severity | What it catches |
|---|---|---|
| `incomplete-download` | high | Fewer records retrieved than the server reports |
| `composition-not-measured` | high | Body composition computed from weight, not sensed |
| `too-sparse-for-trend` | high | Day coverage too low for a trend line to mean anything |
| `timestamp-field-offset` | medium | `timeStamp` disagreeing with `createdAt` by a constant |
| `backfilled-records` | medium | Readings that reached the server long after their stated date |
| `bmi-inconsistent` | medium | Stored BMI disagreeing with weight and height |
| `profile-drift` | medium | Height, birthday or sex changing mid-history |
| `repeat-weigh-ins` | low | Two readings seconds apart — one session, not two observations |
| `inconsistent-timezone-label` | low | Mixed zone abbreviations and numeric offsets |
| `empty-fields` | low | Fields that are empty on every record |

A check that finds nothing returns nothing. An empty findings list means every check ran and
none fired — and an empty measurement history raises rather than reporting a clean bill of
health, because a failed download must never look like good news.

## Which app do you have?

This targets **Renpho Health**, the current app, on `cloud.renpho.com`. The older **Renpho**
app used a different backend (`renpho.qnclouds.com`) with different credentials. If `doctor`
reports the login as rejected and the password is definitely right, that is the likely reason.

There is also a sanctioned no-credentials route: the app exports CSV directly (Trend, then the
clock icon, then Data Select). It is a manual click-through, but it needs no reverse
engineering.

## Privacy

No personal data ships in this repository. The example fixture is synthetic — generated by
[`examples/make_sample.py`](examples/make_sample.py), deliberately seeded with every problem
the checks look for. Your own exports stay on your machine; nothing is uploaded anywhere. Pass
`--anonymous` to keep the account email out of a report you intend to share.

## Stability

This reads a private API that its owner never published and does not support. It works today.
It can break the day Renpho changes their backend, and no amount of care here prevents that.

## Licence

MIT. Built by [Center Consulting](https://www.centerconsulting.com).
