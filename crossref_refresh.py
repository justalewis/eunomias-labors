#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Refresh the coverage table from the Crossref REST API.

Reads data/journals.json, asks Crossref how many records each journal has
registered and how many of those carry a deposited reference list, and writes
data/coverage.json for the templates to read.

Run it nightly. Roughly two API calls per journal with an ISSN, so about eighty
calls; Crossref's polite pool handles that comfortably. If the run fails, the
existing coverage.json is left untouched rather than replaced with a partial
file, so the site never shows half a table.

    python crossref_refresh.py
    python crossref_refresh.py --dry-run    # print, don't write
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

BASE = Path(__file__).parent
DATA = BASE / "data"                                # journals.json ships in the image
OUT = Path(os.environ.get("EUNOMIA_DATA") or DATA)  # coverage.json lives on the volume
JOURNALS = DATA / "journals.json"
COVERAGE = OUT / "coverage.json"

API = "https://api.crossref.org/works"
# Crossref's polite pool wants a contact address in the User-Agent.
MAILTO = os.environ.get("CROSSREF_MAILTO", "jlewis2@olympic.edu")
UA = f"EunomiasLabors/1.0 (+https://eunomiaslabors.xyz; mailto:{MAILTO})"

# Be a good citizen: Crossref asks for reasonable rates, not maximum throughput.
DELAY_SECONDS = 0.4
TIMEOUT_SECONDS = 60
RETRIES = 3


class RefreshError(RuntimeError):
    """Raised when the run can't produce a complete, trustworthy table."""


def _get(params: dict) -> dict:
    url = f"{API}?{urllib.parse.urlencode(params)}"
    request = urllib.request.Request(url, headers={"User-Agent": UA})
    last = None
    for attempt in range(RETRIES):
        try:
            with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
                return json.load(response)
        except urllib.error.HTTPError as exc:
            # A 4xx is our fault -- a bad ISSN, most likely -- and retrying it
            # just burns three requests before the abort. HTTPError subclasses
            # URLError, so it has to be caught first.
            last = exc
            if 400 <= exc.code < 500 and exc.code != 429:
                break
            if attempt < RETRIES - 1:
                retry_after = exc.headers.get("Retry-After") if exc.headers else None
                time.sleep(int(retry_after) if retry_after and retry_after.isdigit()
                           else 2 ** attempt)
        except (urllib.error.URLError, OSError, ValueError) as exc:
            last = exc
            if attempt < RETRIES - 1:
                time.sleep(2 ** attempt)
    raise RefreshError(f"{url} failed after {RETRIES} attempts: {last}")


def _count(issn: str, has_references: bool) -> int:
    filters = f"issn:{issn}"
    if has_references:
        filters += ",has-references:true"
    payload = _get({"filter": filters, "rows": 0, "mailto": MAILTO})
    try:
        return int(payload["message"]["total-results"])
    except (KeyError, TypeError, ValueError) as exc:
        # Turn a shape surprise into the exception main() already handles, so
        # the nightly job prints one line instead of a traceback.
        raise RefreshError(
            f"Crossref returned an unexpected shape for ISSN {issn}: {exc}"
        ) from exc


def survey(journals: list[dict]) -> list[dict]:
    rows = []
    for journal in journals:
        issn = journal.get("issn")
        if not issn:
            # No Crossref presence at all. This is a finding, not a gap: the DOI
            # column reads 0 of however many articles the journal has published.
            rows.append({
                **journal,
                "records": 0,
                "with_references": 0,
                "percent": None,
                "doi_percent": 0.0 if journal.get("indexed_articles") else None,
                "tier": "no-dois",
            })
            continue

        records = _count(issn, has_references=False)
        time.sleep(DELAY_SECONDS)
        with_references = _count(issn, has_references=True)
        time.sleep(DELAY_SECONDS)

        if records == 0:
            raise RefreshError(
                f"{journal['name']} (ISSN {issn}) returned zero registered records. "
                "That almost certainly means the ISSN is wrong, not that the journal "
                "vanished — fix data/journals.json rather than publishing a zero."
            )

        percent = round(100.0 * with_references / records, 1)

        # What share of the journal's known output carries a DOI at all. Crossref
        # can't answer this on its own — it only knows what was registered — so
        # the denominator is the article count Pinakes has indexed from all its
        # sources. Capped at 100: for journals Pinakes indexes FROM Crossref the
        # two counts are the same pipeline and can differ by a few records.
        indexed = journal.get("indexed_articles")
        doi_percent = min(100.0, round(100.0 * records / indexed, 1)) if indexed else None

        rows.append({
            **journal,
            "records": records,
            "with_references": with_references,
            "percent": percent,
            "doi_percent": doi_percent,
            "tier": _tier(percent),
        })
        doi_note = f"{doi_percent:5.1f}%" if doi_percent is not None else "    --"
        print(f"  DOI {doi_note}   refs {percent:5.1f}%  "
              f"{with_references:6d}/{records:<6d}  {journal['name']}")

    return rows


def _tier(percent: float) -> str:
    if percent >= 60:
        return "good"
    if percent > 0:
        return "partial"
    return "none"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true",
                        help="survey and print, but don't write coverage.json")
    args = parser.parse_args()

    journals = json.loads(JOURNALS.read_text(encoding="utf-8"))
    print(f"Surveying {len(journals)} journals against Crossref...")

    try:
        rows = survey(journals)
    except RefreshError as exc:
        # Leave the previous coverage.json in place. A stale table beats a broken one.
        print(f"\nRefresh aborted: {exc}", file=sys.stderr)
        return 1

    # Best-first. The landing page says the four backfilled journals "sit at the
    # top of that table", and they do: descending reference coverage, with the
    # journals that have no Crossref presence at all last. Flip both comparisons
    # to put the worst first instead.
    rows.sort(key=lambda r: (r["percent"] is None, -(r["percent"] or 0), r["name"]))

    done = [r for r in rows if r.get("status") == "done"]
    payload = {
        "generated": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "source": "https://api.crossref.org",
        "journals": rows,
        "totals": {
            "surveyed": len(rows),
            "no_dois": sum(1 for r in rows if r["tier"] == "no-dois"),
            "no_references": sum(1 for r in rows if r["tier"] == "none"),
            # The six completed backfills, counted from the live table.
            "completed_journals": len(done),
            "completed_articles": sum(r["with_references"] for r in done),
        },
    }

    if args.dry_run:
        print("\n--dry-run: not writing.")
        print(json.dumps(payload["totals"], indent=2))
        return 0

    # Write to a temporary file and swap, so a reader never sees a half-written file.
    tmp = COVERAGE.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    tmp.replace(COVERAGE)
    print(f"\nWrote {COVERAGE} ({len(rows)} journals, generated {payload['generated']})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
