"""Collect UN Comtrade technology-goods imports through the Comtrade+ API.

This collector fills the slices that the bulk download did not provide:
by default, imports from the United States (partner 842) for 2014-2025
and imports from China (partner 156) for 2023. Each slice uses the same
query as the bulk files:

    typeCode C, freqCode A, clCode HS, flowCode M,
    cmdCode 8471,8517,8541,8542,
    motCode 0 (total), customsCode C00 (total), partner2Code 0 (world),
    all reporters.

Each slice is saved as ``api_p<partner>_<year>.zip`` (one tab-delimited
.txt inside, same layout as a bulk batch) in
``data/raw/un_comtrade/technology/``, so
``src.data.process_comtrade_technology`` loads it with no changes.
Completed slices are cached: re-running skips existing files unless
``--overwrite`` is given.

Requires a personal key in ``.env``:

    COMTRADE_API_KEY=...

Run from the repository root:

    python -m src.data.collect_comtrade_technology_hs4                # missing slices
    python -m src.data.collect_comtrade_technology_hs4 --partners 842 --years 2014-2025
    python -m src.data.collect_comtrade_technology_hs4 --dry-run      # show the plan only
"""

from __future__ import annotations

import argparse
import io
import os
import time
import zipfile
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]
RAW_DIR = REPO_ROOT / "data" / "raw" / "un_comtrade" / "technology"
MANIFEST = RAW_DIR / "api_request_manifest.csv"

CMD_CODES = "8471,8517,8541,8542"
CHINA_CODE, US_CODE = 156, 842

# Slices missing from the 2026-10-31 bulk pull.
DEFAULT_SLICES = [(US_CODE, y) for y in range(2014, 2026)] + [(CHINA_CODE, 2023)]

API_DELAY_SECONDS = 1.1   # free tier: about 1 request per second
MAX_RETRIES = 3
MAX_RECORDS = 100_000     # one slice is ~800 rows (about 200 reporters x 4 HS codes)


def slice_path(partner: int, year: int, raw_dir: Path = RAW_DIR) -> Path:
    return raw_dir / f"api_p{partner}_{year}.zip"


def fetch_slice(api_key: str, partner: int, year: int,
                client=None) -> pd.DataFrame:
    """Fetch one partner-year slice for all reporters. Retries on failure."""

    if client is None:
        import certifi
        os.environ.setdefault("SSL_CERT_FILE", certifi.where())
        os.environ.setdefault("REQUESTS_CA_BUNDLE", certifi.where())
        import comtradeapicall as client

    last_error = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            frame = client.getFinalData(
                api_key,
                typeCode="C",
                freqCode="A",
                clCode="HS",
                period=str(year),
                reporterCode=None,
                cmdCode=CMD_CODES,
                flowCode="M",
                partnerCode=str(partner),
                partner2Code="0",
                customsCode="C00",
                motCode="0",
                maxRecords=MAX_RECORDS,
                format_output="JSON",
                aggregateBy=None,
                breakdownMode="classic",
                countOnly=None,
                includeDesc=True,
            )
            if frame is None:
                raise ConnectionError("Comtrade returned no DataFrame "
                                      "(request failed or key rejected).")
            if not isinstance(frame, pd.DataFrame):
                raise TypeError(f"Unexpected return type {type(frame).__name__}")
            if len(frame) >= MAX_RECORDS:
                raise RuntimeError(f"Hit maxRecords={MAX_RECORDS}; result truncated.")
            return frame
        except Exception as error:  # noqa: BLE001 - retried, then re-raised
            last_error = error
            if attempt < MAX_RETRIES:
                wait = API_DELAY_SECONDS * 2 ** attempt
                print(f"  p{partner} {year}: {error} - retrying in {wait:.1f}s")
                time.sleep(wait)
    raise RuntimeError(f"Request failed for partner {partner}, {year}") from last_error


def save_slice(frame: pd.DataFrame, path: Path) -> None:
    """Write one slice as a bulk-style ZIP (tab-delimited, UTF-8 BOM)."""

    buffer = io.StringIO()
    frame.to_csv(buffer, sep="\t", index=False)
    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(path.with_suffix(".txt").name, "﻿" + buffer.getvalue())


def collect(api_key: str, slices: list[tuple[int, int]], raw_dir: Path = RAW_DIR,
            overwrite: bool = False, client=None) -> pd.DataFrame:
    """Fetch and save each slice. Returns the request manifest."""

    raw_dir.mkdir(parents=True, exist_ok=True)
    log = []
    any_success = False
    for partner, year in slices:
        path = slice_path(partner, year, raw_dir)
        record = {"partner_code": partner, "year": year, "file": path.name,
                  "requested_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds")}
        if path.exists() and not overwrite:
            print(f"p{partner} {year}: cached, skipped")
            log.append(record | {"status": "cached", "rows": pd.NA, "reporters": pd.NA})
            continue
        try:
            frame = fetch_slice(api_key, partner, year, client=client)
        except Exception as error:  # noqa: BLE001 - logged, run continues
            print(f"p{partner} {year}: FAILED - {error}")
            log.append(record | {"status": f"failed: {error}", "rows": 0, "reporters": 0})
            if not any_success:
                # The first request failing every retry almost always means a
                # rejected key (HTTP 401). Stop instead of repeating it 13 times.
                print("\nStopping: the first request failed. If the lines above show "
                      "statusCode 401, the API key was rejected. Check COMTRADE_API_KEY "
                      "in .env and your 'comtrade - v1' subscription.")
                break
            continue
        any_success = True
        if frame.empty:
            # An empty result is information, not a file: no ZIP is written.
            print(f"p{partner} {year}: 0 rows returned - nothing saved")
            log.append(record | {"status": "empty", "rows": 0, "reporters": 0})
        else:
            save_slice(frame, path)
            reporters = frame["reporterCode"].nunique() if "reporterCode" in frame else pd.NA
            print(f"p{partner} {year}: {len(frame)} rows, {reporters} reporters -> {path.name}")
            log.append(record | {"status": "saved", "rows": len(frame), "reporters": reporters})
        time.sleep(API_DELAY_SECONDS)

    manifest = pd.DataFrame(log)
    if not manifest.empty:
        out = raw_dir / MANIFEST.name
        previous = pd.read_csv(out) if out.exists() else pd.DataFrame()
        pd.concat([previous, manifest], ignore_index=True).to_csv(out, index=False)
    return manifest


def _parse_years(text: str) -> list[int]:
    years: list[int] = []
    for part in text.split(","):
        if "-" in part:
            start, end = part.split("-")
            years.extend(range(int(start), int(end) + 1))
        else:
            years.append(int(part))
    return years


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--partners", default=None,
                        help="comma-separated partner codes, e.g. 842 or 156,842")
    parser.add_argument("--years", default=None, help="e.g. 2014-2025 or 2021,2023")
    parser.add_argument("--raw-dir", type=Path, default=RAW_DIR)
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    if args.partners or args.years:
        partners = [int(p) for p in (args.partners or f"{US_CODE}").split(",")]
        years = _parse_years(args.years or "2014-2025")
        slices = [(p, y) for p in partners for y in years]
    else:
        slices = DEFAULT_SLICES

    print(f"{len(slices)} slices -> {args.raw_dir}")
    if args.dry_run:
        for partner, year in slices:
            state = "cached" if slice_path(partner, year, args.raw_dir).exists() else "to fetch"
            print(f"  partner {partner}, {year}: {state}")
        return

    from dotenv import load_dotenv
    load_dotenv(REPO_ROOT / ".env")
    api_key = (os.getenv("COMTRADE_API_KEY") or "").strip().strip('"').strip("'")
    if not api_key or api_key == "replace_with_your_own_key":
        raise SystemExit("COMTRADE_API_KEY is not set. Copy .env.example to .env and add your key.")
    # Show a masked fingerprint so a wrong or truncated key is easy to spot.
    print(f"Using key {api_key[:4]}...{api_key[-2:]} ({len(api_key)} characters; "
          "Comtrade primary keys are 32 hex characters)")

    manifest = collect(api_key, slices, args.raw_dir, args.overwrite)
    print(manifest["status"].str.split(":").str[0].value_counts().to_string())


if __name__ == "__main__":
    main()
