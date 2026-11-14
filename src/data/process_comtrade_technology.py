"""Process UN Comtrade bulk files into the technology-trade pillar.

Pipeline (accepted methodology, DS608 technology pillar):

    raw Comtrade ZIPs
      -> load + concatenate every batch
      -> validate columns
      -> build reporter crosswalk
      -> filter: imports, total MoT, partners CHN/USA, HS 8471/8517/8541/8542
      -> duplicate audit (cross-batch overlap, then dimensional duplicates)
      -> harmonise labels
      -> category-level bilateral table + category orientation
      -> combined technology orientation per country-year
      -> coverage / QA audit
      -> long-form pillar panel

Score (per country i, year t):

    TechnologyOrientation = (US - China) / (US + China)

    -1 = fully China-sourced, 0 = equal, +1 = fully US-sourced
    (within the bilateral technology-goods comparison only).

Missing values are never converted to zero. A score is only computed
when both partner values are present and the denominator is > 0.

Run from the repository root:

    python -m src.data.process_comtrade_technology
"""

from __future__ import annotations

import argparse
import io
import json
import warnings
import zipfile
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd

try:  # ISO 3166 lookup used to build the reporter crosswalk.
    import pycountry
except ImportError:  # pragma: no cover - handled at runtime
    pycountry = None


# ---------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------

REPO_ROOT = Path(__file__).resolve().parents[2]

RAW_DIR = REPO_ROOT / "data" / "raw" / "un_comtrade" / "technology"
INTERIM_DIR = REPO_ROOT / "data" / "interim"
PROCESSED_DIR = REPO_ROOT / "data" / "processed"
REFERENCE_DIR = REPO_ROOT / "data" / "reference"
TABLES_DIR = REPO_ROOT / "outputs" / "tables"
FIGURES_DIR = REPO_ROOT / "outputs" / "figures"

CHINA_CODE = 156
US_CODE = 842
PARTNER_LABELS = {CHINA_CODE: "China", US_CODE: "United States"}
PARTNER_COLUMNS = {CHINA_CODE: "china_imports", US_CODE: "us_imports"}

ANCHOR_REPORTER_CODES = {CHINA_CODE, US_CODE}

FLOW_CODE = "M"
MOT_CODE = 0

TECH_CATEGORIES = {
    "8471": "Computers and data-processing equipment",
    "8517": "Telecommunications equipment",
    "8541": "Semiconductor devices",
    "8542": "Integrated circuits",
}

PILLAR = "technology"
INDICATOR = "technology_goods_trade_orientation"
SOURCE = "UN Comtrade"

REQUIRED_COLUMNS = [
    "refYear",
    "reporterCode",
    "reporterISO",
    "reporterDesc",
    "flowCode",
    "partnerCode",
    "partnerISO",
    "partnerDesc",
    "cmdCode",
    "motCode",
    "primaryValue",
]

# Dimensions that can split one reporter-year-partner-commodity cell
# into several rows. Used by the duplicate audit.
SECONDARY_DIMENSIONS = [
    "flowCode",
    "motCode",
    "customsCode",
    "mosCode",
    "partner2Code",
    "classificationCode",
]

# The "total" value of each secondary dimension.
TOTAL_DIMENSION_VALUES = {
    "customsCode": "C00",
    "mosCode": "0",
    "partner2Code": "0",
    "motCode": "0",
}

# UN Comtrade uses M49-style codes that differ from ISO 3166-1 numeric
# for a handful of economies (territory groupings). These are the only
# manual entries; everything else comes from the source fields or the
# ISO 3166 standard via pycountry.
COMTRADE_CODE_OVERRIDES = {
    251: ("FRA", "France", "Comtrade 251 = France incl. Monaco"),
    490: ("S19", "Other Asia, nes", "Comtrade 490 = Other Asia, nes "
          "(Taiwan); Comtrade pseudo-ISO S19, not ISO 3166"),
    579: ("NOR", "Norway", "Comtrade 579 = Norway incl. Svalbard/Jan Mayen"),
    699: ("IND", "India", "Comtrade 699 = India (pre-1975 code 356)"),
    757: ("CHE", "Switzerland", "Comtrade 757 = Switzerland incl. "
          "Liechtenstein"),
    842: ("USA", "United States", "Comtrade 842 = USA incl. PR and VI"),
}

# QA thresholds (flags only, nothing is removed).
NEAR_BOUND_TOLERANCE = 0.05          # |score| >= 0.95
LARGE_CHANGE_THRESHOLD = 0.50        # |score_t - score_{t-1}| > 0.5
SMALL_VALUE_TOTAL_USD = 1_000_000    # combined partner tech imports
SMALL_VALUE_CATEGORY_USD = 10_000    # single category, single partner


# ---------------------------------------------------------------------
# Step 1 - Inspect and load ZIP files
# ---------------------------------------------------------------------

def discover_zip_files(raw_dir: Path = RAW_DIR) -> list[Path]:
    """Return every ZIP file in the raw directory, sorted by name."""

    files = sorted(Path(raw_dir).glob("*.zip"))
    if not files:
        raise FileNotFoundError(f"No ZIP files found in {raw_dir}")
    return files


def inspect_zip_files(zip_paths: list[Path]) -> pd.DataFrame:
    """List the members of each ZIP without extracting them."""

    records = []
    for path in zip_paths:
        with zipfile.ZipFile(path) as archive:
            for info in archive.infolist():
                if info.is_dir():
                    continue
                records.append(
                    {
                        "zip_file": path.name,
                        "member": info.filename,
                        "uncompressed_bytes": info.file_size,
                        "compressed_bytes": info.compress_size,
                    }
                )
    return pd.DataFrame(records)


def _read_member(raw_bytes: bytes, member: str) -> pd.DataFrame:
    """Read one Comtrade bulk file (tab- or comma-delimited)."""

    text = raw_bytes.decode("utf-8-sig")
    if not text.strip():
        # Comtrade returns a BOM-only file when a batch query matched no
        # records. Treat it as an empty batch, not a parse error.
        return pd.DataFrame()
    first_line = text.split("\n", 1)[0]
    separator = "\t" if first_line.count("\t") > first_line.count(",") else ","
    frame = pd.read_csv(
        io.StringIO(text),
        sep=separator,
        dtype=str,
        keep_default_na=False,
    )
    # Comtrade bulk files contain stray whitespace (e.g. mosCode "0 ").
    frame.columns = [column.strip() for column in frame.columns]
    for column in frame.columns:
        frame[column] = frame[column].str.strip()
    return frame


def load_raw_comtrade(raw_dir: Path = RAW_DIR) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Load every data member of every ZIP into one dataframe.

    All columns are read as strings so that blank fields stay blank
    instead of being coerced. Provenance columns ``source_zip`` and
    ``source_member`` are appended.
    """

    zip_paths = discover_zip_files(raw_dir)
    inventory = inspect_zip_files(zip_paths)

    frames = []
    for path in zip_paths:
        with zipfile.ZipFile(path) as archive:
            for member in archive.namelist():
                if member.endswith("/"):
                    continue
                if not member.lower().endswith((".txt", ".csv", ".tsv")):
                    continue
                frame = _read_member(archive.read(member), member)
                if frame.empty:
                    warnings.warn(
                        f"{path.name}/{member} contains no records "
                        "(empty Comtrade batch); skipped.",
                        stacklevel=2,
                    )
                    continue
                frame["source_zip"] = path.name
                frame["source_member"] = member
                frames.append(frame)

    if not frames:
        raise ValueError(f"Every ZIP in {raw_dir} is empty; nothing to process.")
    raw = pd.concat(frames, ignore_index=True)
    rows = raw.groupby("source_member").size()
    inventory["rows"] = inventory["member"].map(rows).fillna(0).astype(int)
    inventory["loaded"] = inventory["rows"] > 0
    inventory["status"] = np.where(inventory["loaded"], "loaded", "empty_batch")
    return raw, inventory


def summarise_raw(raw: pd.DataFrame, inventory: pd.DataFrame) -> dict:
    """Headline facts about the concatenated raw data."""

    years = pd.to_numeric(raw["refYear"], errors="coerce")
    return {
        "zip_files": int(inventory["zip_file"].nunique()),
        "data_files_loaded": int(inventory["loaded"].sum()),
        "empty_batches": inventory.loc[~inventory["loaded"], "zip_file"].tolist(),
        "rows": int(len(raw)),
        "columns": int(raw.shape[1] - 2),  # excluding provenance columns
        "year_min": int(years.min()),
        "year_max": int(years.max()),
        "years_present": sorted(int(y) for y in years.dropna().unique()),
        "unique_reporters": int(raw["reporterCode"].nunique()),
        "partner_codes": sorted(raw["partnerCode"].unique().tolist()),
        "hs_codes": sorted(raw["cmdCode"].unique().tolist()),
        "flow_codes": sorted(raw["flowCode"].unique().tolist()),
        "mot_codes": sorted(raw["motCode"].unique().tolist()),
    }


def year_batch_matrix(raw: pd.DataFrame) -> pd.DataFrame:
    """Rows per year per source ZIP - exposes overlapping batches."""

    return pd.crosstab(raw["refYear"], raw["source_zip"])


# ---------------------------------------------------------------------
# Step 2 - Validate raw data and build country crosswalk
# ---------------------------------------------------------------------

def validate_columns(raw: pd.DataFrame) -> pd.DataFrame:
    """Report presence and fill rate of each required column."""

    records = []
    for column in REQUIRED_COLUMNS:
        present = column in raw.columns
        filled = int((raw[column] != "").sum()) if present else 0
        records.append(
            {
                "column": column,
                "present": present,
                "non_blank_rows": filled,
                "blank_rows": int(len(raw) - filled) if present else len(raw),
                "fill_rate": round(filled / len(raw), 4) if present else 0.0,
            }
        )
    report = pd.DataFrame(records)
    missing = report.loc[~report["present"], "column"].tolist()
    if missing:
        raise KeyError(f"Required Comtrade columns missing: {missing}")
    return report


def _iso_lookup(code: int) -> tuple[str, str] | None:
    """ISO 3166-1 numeric -> (alpha-3, name) via pycountry."""

    if pycountry is None:
        return None
    country = pycountry.countries.get(numeric=f"{code:03d}")
    if country is None:
        return None
    name = getattr(country, "common_name", None) or country.name
    return country.alpha_3, name


def build_country_crosswalk(raw: pd.DataFrame) -> pd.DataFrame:
    """Map every reporter and partner code to ISO-3 and a readable name.

    Priority:
      1. source-supplied ISO / description fields (when non-blank);
      2. documented Comtrade code overrides (M49 variants);
      3. ISO 3166-1 numeric lookup (pycountry).
    Codes that resolve through none of these are flagged ``unresolved``.
    """

    pairs = pd.concat(
        [
            raw[["reporterCode", "reporterISO", "reporterDesc"]].set_axis(
                ["code", "iso", "desc"], axis=1
            ),
            raw[["partnerCode", "partnerISO", "partnerDesc"]].set_axis(
                ["code", "iso", "desc"], axis=1
            ),
        ]
    )
    pairs["code"] = pd.to_numeric(pairs["code"], errors="coerce").astype("Int64")

    records = []
    for code, group in pairs.groupby("code"):
        code = int(code)
        source_iso = group.loc[group["iso"] != "", "iso"]
        source_desc = group.loc[group["desc"] != "", "desc"]
        if not source_iso.empty:
            iso, name, method, note = (
                source_iso.mode().iat[0],
                source_desc.mode().iat[0] if not source_desc.empty else "",
                "source_field",
                "",
            )
        elif code in COMTRADE_CODE_OVERRIDES:
            iso, name, note = COMTRADE_CODE_OVERRIDES[code]
            method = "comtrade_override"
        elif (hit := _iso_lookup(code)) is not None:
            iso, name = hit
            method, note = "iso3166_numeric", ""
        else:
            iso, name, method, note = "", "", "unresolved", "No mapping found"
        records.append(
            {
                "comtrade_code": code,
                "country_iso3": iso,
                "country": name,
                "mapping_method": method,
                "is_iso3166": method != "unresolved" and not iso.startswith("S"),
                "note": note,
            }
        )
    return pd.DataFrame(records).sort_values("comtrade_code").reset_index(drop=True)


# ---------------------------------------------------------------------
# Step 3 - Trade filters
# ---------------------------------------------------------------------

def apply_trade_filters(raw: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Apply the accepted filters and log rows remaining after each."""

    steps = [
        ("raw", pd.Series(True, index=raw.index)),
        ("flowCode == M", raw["flowCode"] == FLOW_CODE),
        ("motCode == 0", pd.to_numeric(raw["motCode"], errors="coerce") == MOT_CODE),
        (
            "partnerCode in {156, 842}",
            pd.to_numeric(raw["partnerCode"], errors="coerce").isin(
                [CHINA_CODE, US_CODE]
            ),
        ),
        ("cmdCode in HS basket", raw["cmdCode"].isin(TECH_CATEGORIES)),
    ]
    mask = pd.Series(True, index=raw.index)
    log = []
    for label, condition in steps:
        mask &= condition
        log.append({"filter_step": label, "rows_remaining": int(mask.sum())})
    filtered = raw.loc[mask].copy()

    filtered["refYear"] = filtered["refYear"].astype(int)
    filtered["reporterCode"] = filtered["reporterCode"].astype(int)
    filtered["partnerCode"] = filtered["partnerCode"].astype(int)
    filtered["primaryValue"] = pd.to_numeric(filtered["primaryValue"], errors="coerce")
    return filtered, pd.DataFrame(log)


# ---------------------------------------------------------------------
# Step 4 - Duplicate audit
# ---------------------------------------------------------------------

KEY = ["reporterCode", "refYear", "partnerCode", "cmdCode"]

# Columns that define "the same record" across batches (bulk or API).
RECORD_IDENTITY = KEY + [
    "flowCode", "motCode", "customsCode", "mosCode", "partner2Code",
    "classificationCode", "primaryValue",
]


@dataclass
class DuplicateAudit:
    """Result of the duplicate audit."""

    cross_batch_exact: int = 0
    cross_batch_detail: pd.DataFrame = field(default_factory=pd.DataFrame)
    dimension_duplicates: pd.DataFrame = field(default_factory=pd.DataFrame)
    unresolved: pd.DataFrame = field(default_factory=pd.DataFrame)
    summary: pd.DataFrame = field(default_factory=pd.DataFrame)


def audit_and_resolve_duplicates(
    filtered: pd.DataFrame,
) -> tuple[pd.DataFrame, DuplicateAudit]:
    """Remove double counting at reporter x year x partner x HS.

    Stage A: the same record loaded from overlapping batches is reduced
    to one copy. Records match when every identifying dimension and the
    trade value are equal (``RECORD_IDENTITY``). Label fields are left
    out of the comparison because bulk files leave them blank and API
    files fill them in. If two copies disagree on value, Stage A does
    not merge them, and Stage B stops the run.

    Stage B: remaining key duplicates are inspected for the dimension
    that splits them (customs procedure, mode of supply, secondary
    partner, classification). Only the documented "total" row is kept.
    Anything still duplicated after that is NOT dropped; it is reported
    as unresolved and excluded from aggregation by raising an error.
    """

    audit = DuplicateAudit()
    content_columns = [c for c in RECORD_IDENTITY if c in filtered.columns]

    # Stage A - cross-batch overlap.
    key_dups = filtered.duplicated(KEY, keep=False)
    exact_dups = filtered.duplicated(content_columns, keep="first")
    audit.cross_batch_exact = int(exact_dups.sum())
    if audit.cross_batch_exact:
        dup_rows = filtered.loc[filtered.duplicated(content_columns, keep=False)]
        audit.cross_batch_detail = (
            dup_rows.groupby(["refYear", "source_zip"])
            .size()
            .rename("rows")
            .reset_index()
        )
    stage_a = filtered.loc[~exact_dups].copy()

    # Stage B - dimensional duplicates.
    remaining = stage_a.duplicated(KEY, keep=False)
    if remaining.any():
        groups = stage_a.loc[remaining]
        records = []
        for key, group in groups.groupby(KEY):
            varying = [
                column for column in SECONDARY_DIMENSIONS + ["primaryValue"]
                if group[column].nunique(dropna=False) > 1
            ]
            records.append(dict(zip(KEY, key), rows=len(group),
                                varying_dimensions=",".join(varying)))
        audit.dimension_duplicates = pd.DataFrame(records)

        keep = pd.Series(True, index=stage_a.index)
        for column, total_value in TOTAL_DIMENSION_VALUES.items():
            if column in stage_a.columns:
                in_dup = stage_a.duplicated(KEY, keep=False)
                keep &= ~(in_dup & (stage_a[column] != total_value))
        stage_b = stage_a.loc[keep]
        # Classification duplicates: prefer the original classification.
        if stage_b.duplicated(KEY, keep=False).any() and \
                "isOriginalClassification" in stage_b.columns:
            in_dup = stage_b.duplicated(KEY, keep=False)
            stage_b = stage_b.loc[~(in_dup & (stage_b["isOriginalClassification"] != "True"))]
        unresolved = stage_b.loc[stage_b.duplicated(KEY, keep=False)]
        audit.unresolved = unresolved
        if not unresolved.empty:
            raise ValueError(
                f"{len(unresolved)} rows remain duplicated after keeping total "
                "dimensions. Inspect audit.unresolved before aggregating."
            )
    else:
        stage_b = stage_a

    audit.summary = pd.DataFrame(
        [
            {"stage": "after filters", "rows": len(filtered),
             "key_duplicate_rows": int(key_dups.sum())},
            {"stage": "A: drop exact cross-batch copies", "rows": len(stage_a),
             "key_duplicate_rows": int(remaining.sum())},
            {"stage": "B: keep total-dimension rows", "rows": len(stage_b),
             "key_duplicate_rows": int(stage_b.duplicated(KEY, keep=False).sum())},
        ]
    )
    return stage_b.reset_index(drop=True), audit


# ---------------------------------------------------------------------
# Step 5 - Harmonise labels
# ---------------------------------------------------------------------

def harmonise_labels(deduped: pd.DataFrame, crosswalk: pd.DataFrame) -> pd.DataFrame:
    """Attach readable country, partner and technology labels."""

    lookup = crosswalk.set_index("comtrade_code")
    out = pd.DataFrame(
        {
            "reporter_code": deduped["reporterCode"],
            "country_iso3": deduped["reporterCode"].map(lookup["country_iso3"]),
            "country": deduped["reporterCode"].map(lookup["country"]),
            "year": deduped["refYear"],
            "partner_code": deduped["partnerCode"],
            "partner": deduped["partnerCode"].map(PARTNER_LABELS),
            "hs_code": deduped["cmdCode"],
            "tech_category": deduped["cmdCode"].map(TECH_CATEGORIES),
            "value_usd": deduped["primaryValue"],
            "classification": deduped["classificationCode"],
            "is_reported": deduped["isReported"],
            "is_aggregate": deduped["isAggregate"],
            "legacy_estimation_flag": deduped["legacyEstimationFlag"],
            "source_zip": deduped["source_zip"],
        }
    )
    return out


# ---------------------------------------------------------------------
# Step 6/7 - Scoring
# ---------------------------------------------------------------------

def orientation_score(us: pd.Series, china: pd.Series) -> pd.Series:
    """(US - China) / (US + China), NaN unless both present and denom > 0."""

    us = pd.to_numeric(us, errors="coerce")
    china = pd.to_numeric(china, errors="coerce")
    denominator = us + china
    valid = us.notna() & china.notna() & (denominator > 0)
    score = pd.Series(np.nan, index=us.index, dtype="float64")
    score.loc[valid] = (us[valid] - china[valid]) / denominator[valid]
    return score


def _status(us: pd.Series, china: pd.Series) -> pd.Series:
    status = pd.Series("complete", index=us.index, dtype="object")
    status[us.isna() & china.notna()] = "missing_us"
    status[china.isna() & us.notna()] = "missing_china"
    status[us.isna() & china.isna()] = "missing_both"
    status[us.notna() & china.notna() & ((us + china) <= 0)] = "zero_denominator"
    return status


def build_category_components(labelled: pd.DataFrame,
                              crosswalk: pd.DataFrame,
                              years: list[int] | None = None) -> pd.DataFrame:
    """country x year x tech_category with China and US import columns.

    The grid covers every non-anchor reporter that appears in the
    filtered data x every year in ``years`` (default: the full span of
    the pull, including years absent from every batch) x all four HS
    codes, so absent observations stay visible as NaN, not zero.
    """

    # groupby-sum with min_count=1 keeps an all-missing cell as NaN
    # (works on pandas 2.x and 3.x; pivot_table lacks min_count on 2.x).
    wide = (
        labelled.groupby(["reporter_code", "year", "hs_code", "partner_code"])
        ["value_usd"].sum(min_count=1)
        .unstack("partner_code")
    )
    for code in PARTNER_COLUMNS:
        if code not in wide.columns:
            wide[code] = np.nan
    wide = wide[list(PARTNER_COLUMNS)].rename(columns=PARTNER_COLUMNS)

    reporters = sorted(set(labelled["reporter_code"]) - ANCHOR_REPORTER_CODES)
    if years is None:
        years = list(range(labelled["year"].min(), labelled["year"].max() + 1))
    years_in_pull = set(labelled["year"].unique())
    grid = pd.MultiIndex.from_product(
        [reporters, years, list(TECH_CATEGORIES)],
        names=["reporter_code", "year", "hs_code"],
    )
    components = wide.reindex(grid).reset_index()

    lookup = crosswalk.set_index("comtrade_code")
    components["country_iso3"] = components["reporter_code"].map(lookup["country_iso3"])
    components["country"] = components["reporter_code"].map(lookup["country"])
    components["tech_category"] = components["hs_code"].map(TECH_CATEGORIES)
    components["category_orientation_score"] = orientation_score(
        components["us_imports"], components["china_imports"]
    )
    components["data_status"] = _status(
        components["us_imports"], components["china_imports"]
    )
    components.loc[~components["year"].isin(years_in_pull), "data_status"] = \
        "year_not_in_source_pull"
    components["data_complete"] = components["category_orientation_score"].notna()

    order = [
        "country_iso3", "country", "reporter_code", "year", "hs_code",
        "tech_category", "china_imports", "us_imports",
        "category_orientation_score", "data_complete", "data_status",
    ]
    return components[order].sort_values(["country_iso3", "year", "hs_code"]) \
        .reset_index(drop=True)


def build_combined_orientation(components: pd.DataFrame) -> pd.DataFrame:
    """Combine the four categories into one score per country-year.

    To avoid treating a missing category as zero, totals are summed
    over the *matched basket*: categories where both partners have a
    value. ``n_categories_matched`` records how many of the four
    categories enter the score; ``data_complete`` is True only when all
    four do. Raw (unmatched) totals per partner are kept for audit.
    """

    c = components.copy()
    matched = c["china_imports"].notna() & c["us_imports"].notna()
    c["china_matched"] = c["china_imports"].where(matched)
    c["us_matched"] = c["us_imports"].where(matched)

    keys = ["reporter_code", "country_iso3", "country", "year"]
    grouped = c.groupby(keys, dropna=False)
    combined = pd.DataFrame(
        {
            "china_tech_imports": grouped["china_matched"].sum(min_count=1),
            "us_tech_imports": grouped["us_matched"].sum(min_count=1),
            "n_categories_matched": grouped["china_matched"].count(),
            "n_categories_china": grouped["china_imports"].count(),
            "n_categories_us": grouped["us_imports"].count(),
            "china_tech_imports_reported": grouped["china_imports"].sum(min_count=1),
            "us_tech_imports_reported": grouped["us_imports"].sum(min_count=1),
        }
    ).reset_index()

    combined["tech_orientation_score"] = orientation_score(
        combined["us_tech_imports"], combined["china_tech_imports"]
    )

    n = len(TECH_CATEGORIES)
    status = pd.Series("complete", index=combined.index, dtype="object")
    has_cn = combined["n_categories_china"] > 0
    has_us = combined["n_categories_us"] > 0
    status[~has_cn & ~has_us] = "no_data"
    status[has_cn & ~has_us] = "missing_us"
    status[~has_cn & has_us] = "missing_china"
    partial = has_cn & has_us & (combined["n_categories_matched"] < n)
    status[partial & (combined["n_categories_matched"] > 0)] = "partial_basket"
    status[has_cn & has_us & (combined["n_categories_matched"] == 0)] = "no_matched_category"
    zero = combined["tech_orientation_score"].isna() & \
        (combined["n_categories_matched"] > 0)
    status[zero] = "zero_denominator"
    status[combined["year"].isin(
        components.loc[components["data_status"] == "year_not_in_source_pull", "year"]
    )] = "year_not_in_source_pull"
    combined["data_status"] = status
    combined["data_complete"] = (combined["n_categories_matched"] == n) & \
        combined["tech_orientation_score"].notna()

    order = [
        "country_iso3", "country", "reporter_code", "year",
        "china_tech_imports", "us_tech_imports", "tech_orientation_score",
        "data_complete", "data_status", "n_categories_matched",
        "n_categories_china", "n_categories_us",
        "china_tech_imports_reported", "us_tech_imports_reported",
    ]
    return combined[order].sort_values(["country_iso3", "year"]).reset_index(drop=True)


# ---------------------------------------------------------------------
# Step 8 - Coverage audit
# ---------------------------------------------------------------------

def coverage_by_year(combined: pd.DataFrame,
                     expected_years: list[int] | None = None) -> pd.DataFrame:
    """Per-year coverage and score distribution summary."""

    years = sorted(set(combined["year"]) | set(expected_years or []))
    rows = []
    for year in years:
        sub = combined[combined["year"] == year]
        scores = sub["tech_orientation_score"].dropna()
        rows.append(
            {
                "year": year,
                "year_in_source_pull": bool(
                    (sub["data_status"] != "year_not_in_source_pull").any()),
                "countries_in_panel": int(len(sub)),
                "countries_with_any_data": int(
                    (~sub["data_status"].isin(["no_data", "year_not_in_source_pull"])).sum()),
                "countries_with_china_data": int((sub["n_categories_china"] > 0).sum()),
                "countries_with_us_data": int((sub["n_categories_us"] > 0).sum()),
                "complete_observations": int(sub["data_complete"].sum()),
                "scored_observations": int(scores.size),
                "missing_observations": int((~sub["data_complete"]).sum()),
                "min_score": scores.min() if scores.size else np.nan,
                "max_score": scores.max() if scores.size else np.nan,
                "mean_score": scores.mean() if scores.size else np.nan,
                "n_near_minus_1": int((scores <= -1 + NEAR_BOUND_TOLERANCE).sum()),
                "n_near_plus_1": int((scores >= 1 - NEAR_BOUND_TOLERANCE).sum()),
            }
        )
    return pd.DataFrame(rows)


def qa_flags(combined: pd.DataFrame, components: pd.DataFrame,
             expected_years: list[int]) -> pd.DataFrame:
    """Country-level review flags. Nothing is removed or changed."""

    flags = []

    def add(row, flag, detail):
        flags.append({"country_iso3": row.country_iso3, "country": row.country,
                      "year": getattr(row, "year", pd.NA), "flag": flag,
                      "detail": detail})

    # Large year-to-year changes.
    scored = combined.dropna(subset=["tech_orientation_score"]).sort_values(
        ["country_iso3", "year"])
    scored["prev_year"] = scored.groupby("country_iso3")["year"].shift()
    scored["prev_score"] = scored.groupby("country_iso3")["tech_orientation_score"].shift()
    scored["change"] = scored["tech_orientation_score"] - scored["prev_score"]
    for row in scored[scored["change"].abs() > LARGE_CHANGE_THRESHOLD].itertuples():
        add(row, "large_yoy_change",
            f"{row.prev_score:+.2f} ({int(row.prev_year)}) -> "
            f"{row.tech_orientation_score:+.2f}")

    # Near-bound scores.
    for row in combined[combined["tech_orientation_score"].abs()
                        >= 1 - NEAR_BOUND_TOLERANCE].itertuples():
        add(row, "near_bound_score", f"score {row.tech_orientation_score:+.3f}")

    # Country-level flags.
    for (iso, name), sub in combined.groupby(["country_iso3", "country"]):
        no_data = ["no_data", "year_not_in_source_pull"]
        present = sorted(sub.loc[~sub["data_status"].isin(no_data), "year"])
        base = type("R", (), {"country_iso3": iso, "country": name, "year": pd.NA})
        if present:
            span = [y for y in expected_years if present[0] <= y <= present[-1]]
            gaps = [y for y in span if y not in present]
            if gaps:
                add(base, "suspicious_gap",
                    f"no data in {gaps} between {present[0]}-{present[-1]}")
        with_data = sub[~sub["data_status"].isin(no_data)]
        if len(with_data) and (with_data["n_categories_us"] == 0).all():
            add(base, "us_partner_always_missing",
                f"US imports absent in all {len(with_data)} years with data")
        if len(with_data) and (with_data["n_categories_china"] == 0).all():
            add(base, "china_partner_always_missing",
                f"China imports absent in all {len(with_data)} years with data")

    # Implausibly small values.
    for row in combined.itertuples():
        for partner, column in (("China", "china_tech_imports_reported"),
                                ("US", "us_tech_imports_reported")):
            value = getattr(row, column)
            if pd.notna(value) and value < SMALL_VALUE_TOTAL_USD:
                add(row, "small_total_value",
                    f"{partner} tech imports US${value:,.0f} < "
                    f"US${SMALL_VALUE_TOTAL_USD:,.0f}")
    small_cat = components[
        (components["china_imports"] < SMALL_VALUE_CATEGORY_USD)
        | (components["us_imports"] < SMALL_VALUE_CATEGORY_USD)
    ]
    for row in small_cat.itertuples():
        add(row, "small_category_value",
            f"HS {row.hs_code}: China={row.china_imports}, US={row.us_imports}")

    return pd.DataFrame(flags, columns=["country_iso3", "country", "year",
                                        "flag", "detail"])


# ---------------------------------------------------------------------
# Step 9 - Long-form pillar panel
# ---------------------------------------------------------------------

def build_pillar_long(combined: pd.DataFrame) -> pd.DataFrame:
    """Long-form country-year panel for the index engine."""

    long = pd.DataFrame(
        {
            "country_iso3": combined["country_iso3"],
            "country": combined["country"],
            "year": combined["year"],
            "pillar": PILLAR,
            "indicator": INDICATOR,
            "score": combined["tech_orientation_score"],
            "data_status": combined["data_status"],
            "source": SOURCE,
        }
    )
    return long.sort_values(["country_iso3", "year"]).reset_index(drop=True)


# ---------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------

def run_pipeline(raw_dir: Path = RAW_DIR, write: bool = True,
                 verbose: bool = True) -> dict:
    """Run every stage and (optionally) write outputs. Returns all tables."""

    log = print if verbose else (lambda *a, **k: None)

    raw, inventory = load_raw_comtrade(raw_dir)
    summary = summarise_raw(raw, inventory)
    log("Step 1 - raw load:", json.dumps(summary, default=str))

    column_report = validate_columns(raw)
    crosswalk = build_country_crosswalk(raw)
    unresolved = crosswalk[crosswalk["mapping_method"] == "unresolved"]
    log(f"Step 2 - crosswalk: {len(crosswalk)} codes, {len(unresolved)} unresolved")

    filtered, filter_log = apply_trade_filters(raw)
    log(f"Step 3 - rows after filters: {len(filtered)}")

    deduped, dup_audit = audit_and_resolve_duplicates(filtered)
    log(f"Step 4 - removed {dup_audit.cross_batch_exact} exact cross-batch copies; "
        f"{len(deduped)} rows remain")

    labelled = harmonise_labels(deduped, crosswalk)
    anchors = sorted(set(labelled["reporter_code"]) & ANCHOR_REPORTER_CODES)
    anchor_rows = labelled[labelled["reporter_code"].isin(anchors)]
    log(f"Step 5 - anchor reporters excluded from scoring: {anchors} "
        f"({len(anchor_rows)} rows)")
    year_range = list(range(summary["year_min"], summary["year_max"] + 1))
    components = build_category_components(labelled, crosswalk, year_range)
    combined = build_combined_orientation(components)
    coverage = coverage_by_year(combined, year_range)
    flags = qa_flags(combined, components, summary["years_present"])
    long = build_pillar_long(combined)

    for column in ("category_orientation_score",):
        s = components[column].dropna()
        assert s.between(-1, 1).all(), "category score out of bounds"
    s = combined["tech_orientation_score"].dropna()
    assert s.between(-1, 1).all(), "technology score out of bounds"

    log(f"Steps 6-9 - {len(combined)} country-years, "
        f"{int(combined['tech_orientation_score'].notna().sum())} scored")

    tables = dict(
        raw=raw, inventory=inventory, summary=summary,
        column_report=column_report, crosswalk=crosswalk,
        filter_log=filter_log, filtered=filtered, dup_audit=dup_audit,
        deduped=deduped, labelled=labelled, components=components,
        anchor_rows=anchor_rows, combined=combined, coverage=coverage, flags=flags, long=long,
    )
    if write:
        write_outputs(tables)
    return tables


def write_outputs(t: dict) -> None:
    """Write interim, processed, reference and QA tables."""

    for directory in (INTERIM_DIR, PROCESSED_DIR, REFERENCE_DIR, TABLES_DIR):
        directory.mkdir(parents=True, exist_ok=True)

    t["labelled"].to_parquet(INTERIM_DIR / "comtrade_technology_filtered.parquet",
                             index=False)
    t["components"].to_csv(PROCESSED_DIR / "technology_trade_components.csv", index=False)
    t["combined"].to_csv(PROCESSED_DIR / "technology_trade_orientation.csv", index=False)
    t["long"].to_csv(PROCESSED_DIR / "technology_pillar_long.csv", index=False)
    t["crosswalk"].to_csv(REFERENCE_DIR / "comtrade_country_crosswalk.csv", index=False)

    t["inventory"].to_csv(TABLES_DIR / "technology_raw_file_inventory.csv", index=False)
    t["column_report"].to_csv(TABLES_DIR / "technology_column_validation.csv", index=False)
    t["filter_log"].to_csv(TABLES_DIR / "technology_filter_log.csv", index=False)
    t["dup_audit"].summary.to_csv(TABLES_DIR / "technology_duplicate_audit.csv", index=False)
    if not t["dup_audit"].cross_batch_detail.empty:
        t["dup_audit"].cross_batch_detail.to_csv(
            TABLES_DIR / "technology_duplicate_cross_batch_detail.csv", index=False)
    t["coverage"].to_csv(TABLES_DIR / "technology_coverage_by_year.csv", index=False)
    t["flags"].to_csv(TABLES_DIR / "technology_qa_flags.csv", index=False)
    (t["flags"].groupby("flag").size().rename("n").reset_index()
     .to_csv(TABLES_DIR / "technology_qa_flag_summary.csv", index=False))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--raw-dir", type=Path, default=RAW_DIR)
    parser.add_argument("--no-write", action="store_true")
    args = parser.parse_args()
    run_pipeline(args.raw_dir, write=not args.no_write)


if __name__ == "__main__":
    main()
