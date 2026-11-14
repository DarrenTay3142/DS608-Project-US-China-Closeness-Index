"""Unit tests for the technology-trade pillar (UN Comtrade HS basket)."""

import io
import zipfile

import numpy as np
import pandas as pd
import pytest

from src.data import process_comtrade_technology as tech


COLUMNS = [
    "typeCode", "freqCode", "refPeriodId", "refYear", "refMonth", "period",
    "reporterCode", "reporterISO", "reporterDesc", "flowCode", "flowDesc",
    "partnerCode", "partnerISO", "partnerDesc", "partner2Code", "partner2ISO",
    "partner2Desc", "classificationCode", "classificationSearchCode",
    "isOriginalClassification", "cmdCode", "cmdDesc", "aggrLevel", "isLeaf",
    "customsCode", "customsDesc", "mosCode", "motCode", "motDesc",
    "primaryValue", "legacyEstimationFlag", "isReported", "isAggregate",
]


def row(reporter, year, partner, cmd, value, flow="M", mot="0",
        customs="C00", partner2="0"):
    base = {c: "" for c in COLUMNS}
    base.update(
        typeCode="C", freqCode="A", refYear=str(year), period=str(year),
        reporterCode=str(reporter), flowCode=flow, partnerCode=str(partner),
        partner2Code=partner2, classificationCode="H5",
        classificationSearchCode="HS", isOriginalClassification="True",
        cmdCode=str(cmd), customsCode=customs, mosCode="0", motCode=mot,
        primaryValue=str(value), legacyEstimationFlag="0", isReported="True",
        isAggregate="False",
    )
    return base


def write_zip(path, rows):
    buffer = io.StringIO()
    pd.DataFrame(rows, columns=COLUMNS).to_csv(buffer, sep="\t", index=False)
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr(path.stem + ".txt", "﻿" + buffer.getvalue())


# ---------------------------------------------------------------------
# Scoring formula
# ---------------------------------------------------------------------

def test_orientation_formula_and_bounds():
    us = pd.Series([30.0, 100.0, 0.0, 50.0])
    cn = pd.Series([70.0, 0.0, 100.0, 50.0])
    score = tech.orientation_score(us, cn)
    assert score.tolist() == pytest.approx([-0.4, 1.0, -1.0, 0.0])


def test_missing_is_not_zero():
    score = tech.orientation_score(pd.Series([np.nan, 10.0]),
                                   pd.Series([10.0, np.nan]))
    assert score.isna().all()


def test_zero_denominator_returns_nan():
    score = tech.orientation_score(pd.Series([0.0]), pd.Series([0.0]))
    assert score.isna().all()


# ---------------------------------------------------------------------
# End-to-end on synthetic ZIPs
# ---------------------------------------------------------------------

@pytest.fixture
def synthetic_raw(tmp_path):
    a, b = [], []
    # Country 36 (AUS), 2020, full basket for both partners.
    for cmd, cn, us in [("8471", 60, 40), ("8517", 30, 10),
                        ("8541", 5, 5), ("8542", 5, 45)]:
        a.append(row(36, 2020, 156, cmd, cn))
        a.append(row(36, 2020, 842, cmd, us))
    # Rows that must be filtered out.
    a.append(row(36, 2020, 156, "8471", 999, flow="X"))       # export
    a.append(row(36, 2020, 156, "8471", 999, mot="1000"))     # transport mode
    a.append(row(36, 2020, 156, "9999", 999))                 # off-basket
    a.append(row(36, 2020, 410, "8471", 999))                 # other partner
    # Customs-procedure split: only the C00 total must survive.
    a.append(row(36, 2020, 156, "8471", 7, customs="C01"))
    # Country 392 (JPN), 2020: US missing for HS 8542 -> partial basket.
    for cmd in ["8471", "8517", "8541", "8542"]:
        a.append(row(392, 2020, 156, cmd, 10))
    for cmd in ["8471", "8517", "8541"]:
        a.append(row(392, 2020, 842, cmd, 30))
    # Country 410 (KOR): China only -> no score.
    a.append(row(410, 2020, 156, "8471", 10))
    # Overlapping batch: exact copy of a row already in batch A.
    b.append(row(36, 2020, 156, "8471", 60))
    b.append(row(36, 2022, 156, "8471", 1))  # leaves 2021 as a gap year
    b.append(row(36, 2022, 842, "8471", 3))
    write_zip(tmp_path / "batch_a.zip", a)
    write_zip(tmp_path / "batch_b.zip", b)
    return tmp_path


def test_end_to_end(synthetic_raw):
    t = tech.run_pipeline(synthetic_raw, write=False, verbose=False)

    assert t["summary"]["zip_files"] == 2
    assert t["dup_audit"].cross_batch_exact == 1
    assert t["dup_audit"].dimension_duplicates["varying_dimensions"] \
        .str.contains("customsCode").any()

    comb = t["combined"].set_index(["country_iso3", "year"])

    aus = comb.loc[("AUS", 2020)]
    assert aus["china_tech_imports"] == 100
    assert aus["us_tech_imports"] == 100
    assert aus["tech_orientation_score"] == pytest.approx(0.0)
    assert aus["data_complete"]

    # Partial basket: matched categories only (3 x 10 vs 3 x 30).
    jpn = comb.loc[("JPN", 2020)]
    assert jpn["n_categories_matched"] == 3
    assert jpn["china_tech_imports"] == 30
    assert jpn["tech_orientation_score"] == pytest.approx(0.5)
    assert not jpn["data_complete"]
    assert jpn["data_status"] == "partial_basket"

    kor = comb.loc[("KOR", 2020)]
    assert np.isnan(kor["tech_orientation_score"])
    assert kor["data_status"] == "missing_us"

    assert comb.loc[("AUS", 2021), "data_status"] == "year_not_in_source_pull"

    comp = t["components"].set_index(["country_iso3", "year", "hs_code"])
    assert comp.loc[("AUS", 2020, "8542"), "category_orientation_score"] == \
        pytest.approx(0.8)

    long = t["long"]
    assert set(long["pillar"]) == {"technology"}
    assert long["score"].dropna().between(-1, 1).all()


def test_empty_batch_is_skipped(synthetic_raw):
    with zipfile.ZipFile(synthetic_raw / "batch_empty.zip", "w") as archive:
        archive.writestr("batch_empty.txt", "\ufeff")
    with pytest.warns(UserWarning, match="no records"):
        t = tech.run_pipeline(synthetic_raw, write=False, verbose=False)
    assert t["summary"]["empty_batches"] == ["batch_empty.zip"]
    assert t["summary"]["data_files_loaded"] == 2


def test_api_and_bulk_overlap_deduplicated(synthetic_raw):
    """An API copy of a bulk row (labels filled, value as float) is one record."""
    api = row(36, 2020, 156, "8471", "60.0")
    api.update(reporterISO="AUS", reporterDesc="Australia", partnerISO="CHN",
               partnerDesc="China")
    write_zip(synthetic_raw / "api_p156_2020.zip", [api])
    t = tech.run_pipeline(synthetic_raw, write=False, verbose=False)
    comb = t["combined"].set_index(["country_iso3", "year"])
    assert comb.loc[("AUS", 2020), "china_tech_imports"] == 100


def test_conflicting_overlap_stops(synthetic_raw):
    """Two batches disagreeing on a value must not be silently resolved."""
    write_zip(synthetic_raw / "api_p156_2020.zip", [row(36, 2020, 156, "8471", 61)])
    with pytest.raises(ValueError, match="remain duplicated"):
        tech.run_pipeline(synthetic_raw, write=False, verbose=False)


class FakeClient:
    """Stands in for comtradeapicall: returns rows for 842, nothing for 156."""

    def __init__(self):
        self.calls = []

    def getFinalData(self, key, **kw):
        self.calls.append(kw)
        if kw["partnerCode"] == "842":
            rows = [row(36, int(kw["period"]), 842, c, 50) for c in kw["cmdCode"].split(",")]
            return pd.DataFrame(rows, columns=COLUMNS)
        return pd.DataFrame(columns=COLUMNS)


def test_collector_writes_loadable_slices(tmp_path, monkeypatch):
    from src.data import collect_comtrade_technology_hs4 as col
    monkeypatch.setattr(col, "API_DELAY_SECONDS", 0)
    client = FakeClient()
    manifest = col.collect("KEY", [(842, 2020), (156, 2023)], tmp_path, client=client)

    q = client.calls[0]
    assert (q["flowCode"], q["motCode"], q["customsCode"], q["partner2Code"]) == \
        ("M", "0", "C00", "0")
    assert q["cmdCode"] == "8471,8517,8541,8542" and q["reporterCode"] is None
    assert manifest.set_index("partner_code").loc[156, "status"] == "empty"
    assert (tmp_path / "api_p842_2020.zip").exists()
    assert not (tmp_path / "api_p156_2023.zip").exists()

    raw, inventory = tech.load_raw_comtrade(tmp_path)
    assert len(raw) == 4 and set(raw["partnerCode"]) == {"842"}

    again = col.collect("KEY", [(842, 2020)], tmp_path, client=client)
    assert again["status"].iat[0] == "cached" and len(client.calls) == 2


class RejectingClient:
    """Mimics comtradeapicall after a 401: prints, returns None."""

    def __init__(self):
        self.calls = 0

    def getFinalData(self, key, **kw):
        self.calls += 1
        return None


def test_collector_stops_on_rejected_key_and_creates_folder(tmp_path, monkeypatch):
    from src.data import collect_comtrade_technology_hs4 as col
    monkeypatch.setattr(col, "API_DELAY_SECONDS", 0)
    target = tmp_path / "does" / "not" / "exist"
    client = RejectingClient()
    manifest = col.collect("BAD", [(842, 2014), (842, 2015)], target, client=client)
    assert client.calls == col.MAX_RETRIES          # first slice only
    assert len(manifest) == 1 and manifest["status"].iat[0].startswith("failed")
    assert (target / "api_request_manifest.csv").exists()
