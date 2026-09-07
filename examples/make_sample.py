"""Generate the synthetic sample history used by the tests and the demo report.

No real person's data ships in this repository. This builds a fictional account
that deliberately contains every problem the QA checks look for, so the checks
have something to find and the example report shows what a real one looks like:

  * a dense month of daily weigh-ins, then long gaps
  * most records with `resistance = 100`, a handful with real impedance
  * composition on the placeholder records derived from weight, as the app does
  * a `timeStamp` field stamped in UTC+8
  * one backfilled record that arrived months after its stated date
  * two weigh-ins seconds apart in one session
  * mixed timezone labels
  * the usual crowd of always-empty fields

Deterministic - no randomness, so the fixture and the tests never drift.

Run:  python examples/make_sample.py
"""

import datetime as dt
import json
from pathlib import Path

OUT = Path(__file__).parent / "sample_measurements.json"

HEIGHT_CM = 175.0
BIRTHDAY = "1980-06-15"
GENDER = 1
MAC = "A1:B2:C3:D4:E5:F6"
LOCAL_UTC_OFFSET = 5  # the fictional account sits at UTC-5
BACKEND_OFFSET = 8  # Renpho stamps timeStamp in UTC+8

# A month of daily weights, then scattered follow-ups. Values are invented.
DENSE = [
    82.4, 82.1, 81.8, 82.0, 81.6, 81.5, 81.9, 81.3, 81.1, 81.4,
    80.9, 80.7, 81.0, 80.6, 80.4, 80.8, 80.3, 80.1, 80.5, 80.0,
    79.8, 80.2, 79.7, 79.5, 79.9, 79.4, 79.2, 79.6, 79.1, 78.9,
]
SCATTER = [
    ("2024-05-02 07:10:00", 80.6, True),
    ("2024-05-04 07:22:00", 80.9, True),
    ("2025-01-18 08:05:00", 82.1, False),
    ("2025-09-27 07:44:00", 81.3, True),
]


def composition(weight: float) -> dict:
    """What the app returns when it has no impedance reading: a formula.

    Reproducing the shape of that behaviour is the whole point of the fixture -
    composition that moves only because weight moved.
    """
    bmi = weight / (HEIGHT_CM / 100) ** 2
    bodyfat = round(8.0 + (weight - 70.0) * 0.62, 1)
    return {
        "bmi": round(bmi, 1),
        "bodyfat": bodyfat,
        "water": round(70.0 - bodyfat * 0.62, 1),
        "muscle": round(64.0 - bodyfat * 0.42, 1),
        "bone": round(3.2 + weight * 0.008, 2),
        "bmr": int(1500 + weight * 8.4),
        "visfat": float(int(4 + (weight - 70) * 0.18)),
        "subfat": round(bodyfat * 0.86, 1),
        "protein": round(19.5 - bodyfat * 0.06, 1),
        "bodyage": int(34 + (weight - 70) * 0.35),
        "sinew": round(weight * (1 - bodyfat / 100) * 0.94, 2),
        "fatFreeWeight": round(weight * (1 - bodyfat / 100), 2),
    }


def record(local: dt.datetime, weight: float, measured: bool, index: int,
           created_override: dt.datetime | None = None, is_auto: int = 1,
           tz_label: str | None = None) -> dict:
    created = created_override or (local + dt.timedelta(hours=LOCAL_UTC_OFFSET))
    # The backend quirk the tool exists to warn about: timeStamp is UTC+8.
    epoch = int((created - dt.timedelta(hours=BACKEND_OFFSET)).replace(
        tzinfo=dt.timezone.utc).timestamp())

    row = {
        "id": 6000000000000000000 + index,
        "timeStamp": epoch,
        "localCreatedAt": local.strftime("%Y-%m-%d %H:%M:%S"),
        "createdAt": created.strftime("%Y-%m-%d %H:%M:%S"),
        "updatedAt": created.strftime("%Y-%m-%d %H:%M:%S"),
        "timeZone": tz_label or ("-5:00" if index % 3 else "EST"),
        "weight": weight,
        "weightUnit": 1,
        "height": HEIGHT_CM,
        "heightUnit": 0,
        "birthday": BIRTHDAY,
        "gender": GENDER,
        "mac": MAC,
        "deviceType": "00008",
        "internalModel": "0000",
        "scaleType": 0,
        "scaleName": "",
        "method": 5,
        "isAuto": is_auto,
        "invalidFlag": 0,
        "resistance": (30500 + index * 137) if measured else 100,
        "secResistance": 0,
        "actualResistance": 0,
        "actualSecResistance": 0,
        "heartRate": 0,
        "cardiacIndex": 0.0,
        "waistline": 0,
        "hip": 0,
        "bodyShape": 0,
        "categoryType": 0,
        "personType": 0,
        "appId": "Health",
        "fitBitAuth": None,
        "healthConnectAuth": None,
        "samsungHealthAuth": None,
        "appleHealthAuth": None,
    }
    row.update(composition(weight))
    return row


def build() -> list[dict]:
    rows = []
    start = dt.datetime(2024, 3, 1, 7, 30, 0)
    for i, weight in enumerate(DENSE):
        rows.append(record(start + dt.timedelta(days=i), weight, measured=(i % 10 == 0), index=i))

    # Two readings 41 seconds apart - one session, not two observations.
    dupe_at = start + dt.timedelta(days=len(DENSE) - 1, seconds=41)
    rows.append(record(dupe_at, DENSE[-1], measured=False, index=len(DENSE)))

    for j, (stamp, weight, measured) in enumerate(SCATTER):
        local = dt.datetime.strptime(stamp, "%Y-%m-%d %H:%M:%S")
        rows.append(record(local, weight, measured, index=len(DENSE) + 1 + j,
                           tz_label="-4:00" if j == 0 else None))

    # A backfilled record: stated date months before the moment it reached the
    # server, and an isAuto value the live records never use.
    backfilled_local = dt.datetime(2025, 4, 9, 9, 15, 0)
    rows.append(record(backfilled_local, 81.7, measured=False, index=99,
                       created_override=dt.datetime(2025, 9, 27, 12, 44, 3),
                       is_auto=19))

    rows.sort(key=lambda r: r["localCreatedAt"])
    return rows


if __name__ == "__main__":
    rows = build()
    OUT.write_text(json.dumps(rows, indent=2), encoding="utf-8")
    print(f"Wrote {OUT} with {len(rows)} synthetic records")
