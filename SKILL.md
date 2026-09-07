---
name: renpho
description: Download a Renpho smart scale history and check what the numbers are worth. Use when the task involves Renpho, a smart scale, weight history, body composition, body fat percentage, weigh-ins, or exporting health data from a scale app.
---

# renpho

Pull a Renpho Health account's full weigh-in history and run a data-quality pass over it.

Renpho publishes no API. This reads the private backend the Renpho Health app uses.

## Before anything else

Read [AGENTS.md](AGENTS.md) for the exit-code contract. The short version: every command takes
`--json`, nothing prompts, and the exit code is the signal.

## Setup

Not on PyPI yet — install from source:

```bash
git clone https://github.com/thefrederiksen/cc-renpho
cd cc-renpho && pip install .
export RENPHO_EMAIL=... RENPHO_PASSWORD=...
```

Or keep them in a file and pass `--credentials-file PATH`.

## The sequence

```bash
cc-renpho doctor --json                              # credentials work? downloads nothing
cc-renpho pull --json -o data                        # exit 5 = incomplete, do not analyse
cc-renpho qa --json -i data/measurements.json        # structured findings
cc-renpho report -i data/measurements.json -o report.html --anonymous
```

## The one thing not to get wrong

Renpho returns a full set of body-fat, muscle and water figures **even for weigh-ins where the
scale took no impedance reading**. Those are computed from weight, height, age and sex, and
nothing in the response marks them as derived.

Check `summary.composition_estimated` in the `qa` output. If it is above zero, report those
records' composition as estimated, never as measured. Per record the marker is
`resistance == 100`.

## Reporting back

Lead with what the data is worth, not with the latest weight. `severity_counts` and the
`findings[].id` list are the summary — quote ids, not wording, since prose can change and ids
cannot.

If the history is sparse (`day_coverage_pct` low, or a large `gaps` list), say so plainly and
do not present a trend line. The tool will have raised `too-sparse-for-trend` for you.

## Do not

* Do not commit an output directory or a report to a repository — it is personal health data.
* Do not retry a rejected password. Exit 3 usually means the account is on the older Renpho
  app, which uses a different backend entirely.
* Do not treat an empty findings list from an offline (`-i`) run as proof the download was
  complete — the completeness check needs the server and cannot fire offline.
