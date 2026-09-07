"""Render a QA analysis as a standalone HTML page.

Everything is inlined - charts are generated SVG, there is no build step, no
server and no JavaScript. The file opens on its own and prints correctly.

The page states what the data is worth before it shows any of it, because the
failure mode this tool exists to prevent is someone reading estimated body-fat
figures as measurements.
"""

from __future__ import annotations

import datetime as dt
import html
from collections import Counter
from typing import Any

from .qa import NO_IMPEDANCE, densest_run, parse_local, summarise

CSS = """
  :root{
    --ground:#EFF2F1; --surface:#FFF; --surface-2:#E4EAE9;
    --ink:#0B1F22; --ink-soft:#4A6362; --ink-faint:#7A918F;
    --line:#CFD9D7; --line-soft:#E1E8E7;
    --water:#16565B; --water-bright:#2C8A87;
    --warm:#A84E27; --warm-wash:#F6E3D8;
    --alert:#8E2F2F;
    --shadow:0 1px 2px rgba(11,31,34,.06),0 8px 24px -12px rgba(11,31,34,.18);
  }
  @media (prefers-color-scheme:dark){
    :root:not([data-theme="light"]){
      --ground:#071618; --surface:#0E2427; --surface-2:#143034;
      --ink:#E6EFEE; --ink-soft:#97B0AE; --ink-faint:#6A8583;
      --line:#1E3B3E; --line-soft:#16302F;
      --water:#4FB3AF; --water-bright:#6FD0CA;
      --warm:#E2895B; --warm-wash:#33200F;
      --alert:#E8817A;
      --shadow:0 1px 2px rgba(0,0,0,.4),0 8px 24px -12px rgba(0,0,0,.7);
    }
  }
  :root[data-theme="dark"]{
    --ground:#071618; --surface:#0E2427; --surface-2:#143034;
    --ink:#E6EFEE; --ink-soft:#97B0AE; --ink-faint:#6A8583;
    --line:#1E3B3E; --line-soft:#16302F;
    --water:#4FB3AF; --water-bright:#6FD0CA;
    --warm:#E2895B; --warm-wash:#33200F;
    --alert:#E8817A;
    --shadow:0 1px 2px rgba(0,0,0,.4),0 8px 24px -12px rgba(0,0,0,.7);
  }
  *{box-sizing:border-box}
  body{margin:0;background:var(--ground);color:var(--ink);
    font-family:ui-sans-serif,system-ui,-apple-system,"Segoe UI",Roboto,sans-serif;
    font-size:16px;line-height:1.6;-webkit-font-smoothing:antialiased}
  .wrap{max-width:60rem;margin:0 auto;padding:2.5rem 1.25rem 5rem;
    display:flex;flex-direction:column;gap:2.75rem}
  h1{font-size:clamp(1.8rem,4.5vw,2.7rem);line-height:1.1;margin:0 0 .5rem;
    letter-spacing:-.02em;font-weight:800}
  h2{font-size:1.35rem;margin:0 0 1rem;letter-spacing:-.01em;font-weight:700}
  h3{font-size:1.05rem;font-weight:600;margin:0 0 .5rem;line-height:1.35}
  p{margin:0 0 .85rem}
  .lede{color:var(--ink-soft);font-size:1.05rem;max-width:44rem}
  .meta{font-family:ui-monospace,Consolas,monospace;font-size:.75rem;
    color:var(--ink-faint);text-transform:uppercase;letter-spacing:.09em;margin-bottom:.9rem}
  .card{background:var(--surface);border:1px solid var(--line-soft);
    border-radius:14px;padding:1.5rem;box-shadow:var(--shadow)}
  .verdict{border-left:4px solid var(--warm);background:var(--warm-wash);
    border-radius:0 14px 14px 0;padding:1.35rem 1.6rem}
  .verdict p{margin:0}
  .tiles{display:grid;gap:.85rem;grid-template-columns:repeat(auto-fit,minmax(9.5rem,1fr))}
  .tile{background:var(--surface);border:1px solid var(--line-soft);
    border-radius:12px;padding:1rem 1.1rem}
  .tile .n{font-size:1.8rem;line-height:1;font-weight:800;letter-spacing:-.02em;display:block}
  .tile .k{font-family:ui-monospace,monospace;font-size:.68rem;text-transform:uppercase;
    letter-spacing:.08em;color:var(--ink-faint);margin-top:.45rem;display:block}
  .tile.good .n{color:var(--water-bright)}
  .tile.warn .n{color:var(--warm)}
  svg{width:100%;height:auto;display:block}
  .grid{stroke:var(--line-soft);stroke-width:1}
  .grid-v{stroke:var(--line-soft);stroke-width:1;stroke-dasharray:3 4}
  .ax{fill:var(--ink-faint);font-family:ui-monospace,monospace;font-size:11px}
  .ln{fill:none;stroke:var(--water-bright);stroke-width:2;stroke-linejoin:round;stroke-linecap:round}
  .dot-measured{fill:var(--water);stroke:var(--surface);stroke-width:1.5}
  .dot-est{fill:none;stroke:var(--water-bright);stroke-width:1.5}
  .cov{fill:var(--water-bright)}
  .cov-none{fill:var(--line)}
  .legend{display:flex;gap:1.4rem;flex-wrap:wrap;font-size:.82rem;
    color:var(--ink-soft);margin-top:.9rem}
  .legend span{display:inline-flex;align-items:center;gap:.45rem}
  .sw{width:11px;height:11px;border-radius:50%;display:inline-block}
  .sw.m{background:var(--water)}
  .sw.e{background:transparent;border:1.5px solid var(--water-bright)}
  .findings{display:flex;flex-direction:column;gap:1rem}
  .finding{background:var(--surface);border:1px solid var(--line-soft);
    border-left:4px solid var(--line);border-radius:0 12px 12px 0;padding:1.2rem 1.4rem}
  .finding.sev-high{border-left-color:var(--alert)}
  .finding.sev-medium{border-left-color:var(--warm)}
  .finding.sev-low{border-left-color:var(--water-bright)}
  .sev-tag{font-family:ui-monospace,monospace;font-size:.65rem;letter-spacing:.11em;
    color:var(--ink-faint);margin-bottom:.4rem}
  .sev-high .sev-tag{color:var(--alert)}
  .sev-medium .sev-tag{color:var(--warm)}
  .obs{color:var(--ink-soft);font-size:.93rem}
  .why{font-size:.93rem;margin-bottom:0}
  .why .lbl{font-family:ui-monospace,monospace;font-size:.66rem;text-transform:uppercase;
    letter-spacing:.09em;color:var(--ink-faint);display:block;margin-bottom:.15rem}
  code{font-family:ui-monospace,monospace;font-size:.86em;background:var(--surface-2);
    padding:.1em .38em;border-radius:4px}
  .scroll{overflow-x:auto;border:1px solid var(--line-soft);border-radius:12px;
    background:var(--surface)}
  table{border-collapse:collapse;width:100%;font-size:.85rem}
  th{text-align:left;font-family:ui-monospace,monospace;font-size:.66rem;
    text-transform:uppercase;letter-spacing:.08em;color:var(--ink-faint);
    padding:.7rem .85rem;border-bottom:1px solid var(--line);
    background:var(--surface-2);position:sticky;top:0;white-space:nowrap}
  td{padding:.55rem .85rem;border-bottom:1px solid var(--line-soft);white-space:nowrap}
  tr:last-child td{border-bottom:none}
  .mono{font-family:ui-monospace,monospace}
  .num{text-align:right}
  .est{color:var(--warm)}
  .tall{max-height:26rem;overflow-y:auto}
  ul{margin:0 0 .85rem;padding-left:1.15rem}
  li{margin-bottom:.4rem}
  footer{color:var(--ink-faint);font-size:.8rem;border-top:1px solid var(--line-soft);
    padding-top:1.25rem}
  footer a{color:var(--water-bright)}
"""


def _bounds(records: list[dict]) -> tuple[float, float]:
    weights = [m["weight"] for m in records]
    lo, hi = min(weights), max(weights)
    pad = max((hi - lo) * 0.15, 0.5)
    return lo - pad, hi + pad


def weight_chart(records, w=920, h=300, pad_l=52, pad_r=18, pad_t=18, pad_b=34):
    """Weight on a true linear date axis, so gaps in the record read as gaps."""
    t0 = parse_local(records[0]).timestamp()
    t1 = parse_local(records[-1]).timestamp()
    if t1 == t0:
        t1 = t0 + 1
    lo, hi = _bounds(records)
    iw, ih = w - pad_l - pad_r, h - pad_t - pad_b

    def X(m):
        return pad_l + iw * (parse_local(m).timestamp() - t0) / (t1 - t0)

    def Y(v):
        return pad_t + ih * (hi - v) / (hi - lo)

    parts = []
    step = max(1, round((hi - lo) / 5))
    tick = int(lo) + 1
    while tick < hi:
        y = Y(tick)
        parts.append('<line class="grid" x1="%d" y1="%.1f" x2="%d" y2="%.1f"/>' % (pad_l, y, w - pad_r, y))
        parts.append('<text class="ax" x="%d" y="%.1f" text-anchor="end">%d</text>' % (pad_l - 9, y + 4, tick))
        tick += step

    y0 = dt.datetime.fromtimestamp(t0).year
    y1 = dt.datetime.fromtimestamp(t1).year
    for year in range(y0, y1 + 2):
        ts = dt.datetime(year, 1, 1).timestamp()
        if not (t0 <= ts <= t1):
            continue
        x = pad_l + iw * (ts - t0) / (t1 - t0)
        parts.append('<line class="grid-v" x1="%.1f" y1="%d" x2="%.1f" y2="%d"/>' % (x, pad_t, x, h - pad_b))
        parts.append('<text class="ax" x="%.1f" y="%d" text-anchor="middle">%d</text>' % (x, h - pad_b + 20, year))

    # Only join readings less than 60 days apart. A line drawn across a year-long
    # gap asserts a trajectory nobody observed.
    def flush(seg):
        if len(seg) > 1:
            d = " ".join("%s%.1f,%.1f" % ("M" if i == 0 else "L", X(p), Y(p["weight"]))
                         for i, p in enumerate(seg))
            parts.append('<path class="ln" d="%s"/>' % d)

    seg = []
    for m in records:
        if seg and (parse_local(m) - parse_local(seg[-1])).days > 60:
            flush(seg)
            seg = []
        seg.append(m)
    flush(seg)

    for m in records:
        measured = m.get("resistance") != NO_IMPEDANCE
        title = "%s - %s kg, %s%% fat, %s" % (
            m["localCreatedAt"][:16], m["weight"], m.get("bodyfat"),
            "impedance measured" if measured else "estimated from weight",
        )
        parts.append(
            '<circle class="%s" cx="%.1f" cy="%.1f" r="%d"><title>%s</title></circle>'
            % ("dot-measured" if measured else "dot-est", X(m), Y(m["weight"]),
               4 if measured else 3, html.escape(title))
        )
    return '<svg viewBox="0 0 %d %d" role="img" aria-label="Weight over time">%s</svg>' % (w, h, "".join(parts))


def window_chart(records, w=920, h=260, pad_l=52, pad_r=18, pad_t=18, pad_b=34):
    """The densest run of readings, zoomed, with weekly ticks."""
    t0 = parse_local(records[0]).timestamp()
    t1 = parse_local(records[-1]).timestamp()
    if t1 == t0:
        t1 = t0 + 1
    lo, hi = _bounds(records)
    iw, ih = w - pad_l - pad_r, h - pad_t - pad_b

    def X(m):
        return pad_l + iw * (parse_local(m).timestamp() - t0) / (t1 - t0)

    def Y(v):
        return pad_t + ih * (hi - v) / (hi - lo)

    parts = []
    step = max(1, round((hi - lo) / 5))
    tick = int(lo) + 1
    while tick < hi:
        y = Y(tick)
        parts.append('<line class="grid" x1="%d" y1="%.1f" x2="%d" y2="%.1f"/>' % (pad_l, y, w - pad_r, y))
        parts.append('<text class="ax" x="%d" y="%.1f" text-anchor="end">%d</text>' % (pad_l - 9, y + 4, tick))
        tick += step

    day = dt.datetime.fromtimestamp(t0).date()
    end = dt.datetime.fromtimestamp(t1).date()
    while day <= end:
        ts = dt.datetime(day.year, day.month, day.day).timestamp()
        if t0 <= ts <= t1:
            x = pad_l + iw * (ts - t0) / (t1 - t0)
            parts.append('<line class="grid-v" x1="%.1f" y1="%d" x2="%.1f" y2="%d"/>' % (x, pad_t, x, h - pad_b))
            parts.append('<text class="ax" x="%.1f" y="%d" text-anchor="middle">%s</text>'
                         % (x, h - pad_b + 20, day.strftime("%b %d")))
        day += dt.timedelta(days=7)

    d = " ".join("%s%.1f,%.1f" % ("M" if i == 0 else "L", X(p), Y(p["weight"]))
                 for i, p in enumerate(records))
    parts.append('<path class="ln" d="%s"/>' % d)
    for m in records:
        parts.append('<circle class="dot-est" cx="%.1f" cy="%.1f" r="3"><title>%s</title></circle>'
                     % (X(m), Y(m["weight"]),
                        html.escape("%s - %s kg" % (m["localCreatedAt"][:16], m["weight"]))))
    return '<svg viewBox="0 0 %d %d" role="img" aria-label="The densest run of readings">%s</svg>' % (w, h, "".join(parts))


def coverage_strip(records, w=920, h=74, pad_l=52, pad_r=18):
    """One tick per month across the whole span; bar height is readings that month."""
    months = Counter(m["localCreatedAt"][:7] for m in records)
    start = parse_local(records[0]).date().replace(day=1)
    end = parse_local(records[-1]).date().replace(day=1)
    total = (end.year - start.year) * 12 + (end.month - start.month) + 1
    iw = w - pad_l - pad_r
    bw = iw / total
    top, base = 14, h - 26
    peak = max(months.values())
    parts = ['<line class="grid" x1="%d" y1="%d" x2="%d" y2="%d"/>' % (pad_l, base, w - pad_r, base)]
    for i in range(total):
        y_, m_ = divmod(start.month - 1 + i, 12)
        key = "%04d-%02d" % (start.year + y_, m_ + 1)
        n = months.get(key, 0)
        x = pad_l + i * bw
        if n:
            bh = max(4.0, (base - top) * n / peak)
            parts.append('<rect class="cov" x="%.1f" y="%.1f" width="%.1f" height="%.1f">'
                         '<title>%s: %d reading%s</title></rect>'
                         % (x + 0.7, base - bh, max(2.0, bw - 1.4), bh, key, n, "s" if n != 1 else ""))
        else:
            parts.append('<rect class="cov-none" x="%.1f" y="%.1f" width="%.1f" height="3">'
                         '<title>%s: no readings</title></rect>'
                         % (x + 0.7, base - 3, max(2.0, bw - 1.4), key))
        if m_ + 1 == 1 or i == 0:
            parts.append('<text class="ax" x="%.1f" y="%d" text-anchor="start">%d</text>'
                         % (x, h - 8, start.year + y_))
    return '<svg viewBox="0 0 %d %d" role="img" aria-label="Readings per month">%s</svg>' % (w, h, "".join(parts))


def _verdict(stats: dict, findings: list[dict]) -> str:
    high = [f for f in findings if f["severity"] == "high"]
    if not findings:
        return ("Every check ran and none fired. The export is complete and the data behind it "
                "is dense enough and measured enough to work with as it stands.")
    lead = ("%d of %d readings carry a real impedance measurement, so %d set(s) of body-fat, "
            "muscle and water figures are a formula over weight rather than a measurement. "
            % (stats["impedance_measured"], stats["count"], stats["composition_estimated"])
            ) if stats["composition_estimated"] else ""
    return (
        "%sCoverage is %.1f%% of the elapsed period. %s"
        % (lead, stats["day_coverage_pct"],
           "Use this for weight; do not use it for body composition, and do not read a trend "
           "into it." if high else "Read the findings below before drawing conclusions.")
    )


def _profile_items(records: list[dict]) -> str:
    """Whatever profile constants this account actually carries."""
    items = []
    heights = {m.get("height") for m in records if m.get("height")}
    if len(heights) == 1:
        h = heights.pop()
        items.append("<li><b>Height %s cm.</b> BMI is weight over height squared, so every BMI "
                     "in this export depends on this one number being right in the app.</li>" % h)
    birthdays = {m.get("birthday") for m in records if m.get("birthday")}
    if len(birthdays) == 1:
        items.append("<li><b>Birthday %s.</b> Feeds BMR and body age.</li>" % esc(birthdays.pop()))
    macs = {m.get("mac") for m in records if m.get("mac")}
    if macs:
        items.append("<li><b>%d device(s)</b> on the account: %s.</li>"
                     % (len(macs), esc(", ".join(sorted(m for m in macs if m)))))
    items.append("<li><b>Weight is stored in kilograms</b> regardless of the unit the app "
                 "displays.</li>")
    return "".join(items)


def esc(value: Any) -> str:
    return html.escape(str(value))


def render(records: list[dict], analysis: dict, account_label: str | None = None) -> str:
    """Build the whole page. `analysis` is the dict from qa.analyse()."""
    stats = analysis["summary"]
    findings = analysis["findings"]
    sev = analysis["severity_counts"]
    run = densest_run(records)
    generated = dt.datetime.now().strftime("%Y-%m-%d %H:%M")

    who = (" for <span class='mono'>%s</span>" % esc(account_label)) if account_label else ""

    finding_html = "".join(
        '<article class="finding sev-%s"><div class="sev-tag">%s &middot; %s</div><h3>%s</h3>'
        '<p class="obs">%s</p><p class="why"><span class="lbl">Why it matters</span> %s</p></article>'
        % (f["severity"], f["severity"].upper(), esc(f["id"]), esc(f["title"]),
           esc(f["observed"]), esc(f["why"]))
        for f in findings
    )

    gap_rows = "".join(
        '<tr><td class="mono">%s</td><td class="mono">%s</td><td class="mono num">%d</td></tr>'
        % (esc(g["from"]), esc(g["to"]), g["days"])
        for g in analysis["gaps"]
    ) or '<tr><td colspan="3">No gap longer than 30 days.</td></tr>'

    rows = "".join(
        '<tr><td class="mono">%s</td><td class="mono num">%s</td><td class="mono num">%s</td>'
        '<td class="mono num">%s</td><td class="mono num">%s</td><td class="mono num">%s</td>'
        '<td class="mono num">%s</td><td>%s</td></tr>'
        % (esc(m["localCreatedAt"][:16]), m["weight"], m.get("bmi", ""), m.get("bodyfat", ""),
           m.get("muscle", ""), m.get("water", ""), m.get("bmr", ""),
           "measured" if m.get("resistance") != NO_IMPEDANCE else '<span class="est">estimated</span>')
        for m in reversed(records)
    )

    window_section = ""
    if len(run) >= 5 and len(run) < len(records):
        window_section = """
<section class="card">
  <h2>The densest run of readings</h2>
  <p class="lede" style="font-size:.93rem">%d of the %d readings sit in this stretch, %s to %s.
  Zoomed out it is a smear at one edge of the chart above; here it is the only part where
  consecutive points are close enough together to read as a trend.</p>
  %s
</section>""" % (len(run), stats["count"], esc(run[0]["localCreatedAt"][:10]),
                 esc(run[-1]["localCreatedAt"][:10]), window_chart(run))

    return """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Renpho Data Quality Report</title>
<style>%(css)s</style>
</head>
<body>
<div class="wrap">

<header>
  <div class="meta">Data quality report &middot; generated %(generated)s &middot; cc-renpho</div>
  <h1>Renpho scale data: what arrived, and what it is worth</h1>
  <p class="lede">A full pull of the Renpho Health account%(who)s over the unofficial
  cloud.renpho.com REST API, then a quality pass over what came back.</p>
</header>

<section class="verdict"><p><strong>Verdict.</strong> %(verdict)s</p></section>

<section>
  <h2>At a glance</h2>
  <div class="tiles">
    <div class="tile"><span class="n">%(count)d</span><span class="k">Records retrieved</span></div>
    <div class="tile %(imp_class)s"><span class="n">%(measured)d</span><span class="k">With real impedance</span></div>
    <div class="tile %(cov_class)s"><span class="n">%(coverage).1f%%</span><span class="k">Day coverage over %(span)d days</span></div>
    <div class="tile"><span class="n">%(days)d</span><span class="k">Distinct weigh-in days</span></div>
    <div class="tile %(gap_class)s"><span class="n">%(gaps)d</span><span class="k">Gaps over 30 days</span></div>
    <div class="tile"><span class="n">%(w_last)s</span><span class="k">Latest weight, kg</span></div>
  </div>
</section>

<section class="card">
  <h2>Weight over real time</h2>
  <p class="lede" style="font-size:.93rem">Plotted on a true date axis, so the emptiness is
  visible. The line joins readings less than 60 days apart only - drawing it across a long
  gap would assert a trajectory nobody observed.</p>
  %(weight_chart)s
  <div class="legend">
    <span><i class="sw m"></i> impedance measured (%(measured)d)</span>
    <span><i class="sw e"></i> composition estimated from weight (%(estimated)d)</span>
  </div>
</section>
%(window_section)s
<section class="card">
  <h2>Readings per month</h2>
  <p class="lede" style="font-size:.93rem">Flat grey means no weigh-in that month.</p>
  %(coverage_strip)s
</section>

<section>
  <h2>Findings</h2>
  <p class="lede">%(n_high)d high, %(n_med)d medium, %(n_low)d low.</p>
  <div class="findings">%(findings)s</div>
</section>

<section class="card">
  <h2>The gaps</h2>
  <div class="scroll"><table>
    <thead><tr><th>Last reading</th><th>Next reading</th><th class="num">Days</th></tr></thead>
    <tbody>%(gap_rows)s</tbody>
  </table></div>
</section>

<section class="card">
  <h2>Profile constants every number leans on</h2>
  <p>The derived figures are computed from these. If one is wrong in the app, it is wrong in
  every reading ever taken.</p>
  <ul>%(profile)s</ul>
</section>

<section>
  <h2>All %(count)d readings</h2>
  <div class="scroll tall"><table>
    <thead><tr><th>Local time</th><th class="num">Weight kg</th><th class="num">BMI</th>
    <th class="num">Fat %%</th><th class="num">Muscle %%</th><th class="num">Water %%</th>
    <th class="num">BMR</th><th>Composition</th></tr></thead>
    <tbody>%(rows)s</tbody>
  </table></div>
</section>

<footer>
  <p>Generated by <a href="https://github.com/thefrederiksen/cc-renpho">cc-renpho</a>. Renpho
  publishes no public API; this reads the same private backend the Renpho Health app uses. It
  works today and can break without notice.</p>
</footer>

</div>
</body>
</html>
""" % {
        "css": CSS,
        "generated": generated,
        "who": who,
        "verdict": _verdict(stats, findings),
        "count": stats["count"],
        "measured": stats["impedance_measured"],
        "estimated": stats["composition_estimated"],
        "coverage": stats["day_coverage_pct"],
        "span": stats["span_days"],
        "days": stats["distinct_days"],
        "gaps": len(analysis["gaps"]),
        "w_last": stats["weight_last"],
        "imp_class": "warn" if stats["composition_estimated"] else "good",
        "cov_class": "warn" if stats["day_coverage_pct"] < 25 else "good",
        "gap_class": "warn" if analysis["gaps"] else "good",
        "weight_chart": weight_chart(records),
        "window_section": window_section,
        "coverage_strip": coverage_strip(records),
        "findings": finding_html or "<p>Every check ran and none fired.</p>",
        "gap_rows": gap_rows,
        "profile": _profile_items(records),
        "rows": rows,
        "n_high": sev["high"],
        "n_med": sev["medium"],
        "n_low": sev["low"],
    }
