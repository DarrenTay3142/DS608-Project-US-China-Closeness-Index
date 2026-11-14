import importlib.util
from pathlib import Path
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "data/interim/fdi/imf_dip_primary_candidates.csv"

if not SOURCE.exists():
    pytest.skip(
        "Local-only IMF DIP candidate panel is unavailable: "
        "data/interim/fdi/imf_dip_primary_candidates.csv. "
        "See docs/local_data_requirements.md.",
        allow_module_level=True,
    )

spec = importlib.util.spec_from_file_location("builder", ROOT / "src/data/build_fdi_structural_ties.py")
b = importlib.util.module_from_spec(spec)
spec.loader.exec_module(b)

@pytest.fixture(scope="module")
def inputs():
    return (
        pd.read_csv(SOURCE, low_memory=False),
        pd.read_csv(ROOT / "outputs/tables/fdi/fdi_country_crosswalk_production_audit.csv", low_memory=False),
        pd.read_csv(ROOT / "outputs/tables/relations_condition/relationship_condition_country_master.csv", low_memory=False),
    )

@pytest.fixture(scope="module")
def result(inputs): return b.build_panel(*inputs)

@pytest.fixture(scope="module")
def panel(result): return result[0]

@pytest.fixture(scope="module")
def audit(result): return result[1]

def test_dimensions(panel):
    assert len(panel) == 8410
    assert panel.country_iso3.nunique() == 192
    assert (panel.year.min(), panel.year.max()) == (2004, 2025)

def test_unique_keys(panel):
    assert not panel.duplicated(["country_iso3", "anchor", "year"]).any()

def test_regime_counts(audit):
    assert audit.fdi_reporting_regime.value_counts().to_dict() == {
        "anchor_official_fixed_regime": 112,
        "host_official_fixed_regime": 79,
    }

def test_host_threshold_rule(audit):
    host = audit[audit.fdi_reporting_regime.eq("host_official_fixed_regime")]
    anchor = audit[audit.fdi_reporting_regime.eq("anchor_official_fixed_regime")]
    assert host.host_signed_years_2009_2017.ge(6).all()
    assert host.host_signed_years_2018_2024.ge(4).all()
    assert ((anchor.host_signed_years_2009_2017.lt(6)) | (anchor.host_signed_years_2018_2024.lt(4))).all()

def test_no_country_switches_perspective(panel):
    observed = panel[panel.observed]
    host = observed[observed.fdi_reporting_regime.eq("host_official_fixed_regime")]
    anchor = observed[observed.fdi_reporting_regime.eq("anchor_official_fixed_regime")]
    assert host.fdi_position_provenance.eq("host_reported_official").all()
    assert anchor.fdi_position_provenance.eq("anchor_reported_official").all()

def test_source_period_boundaries(panel):
    assert panel.loc[panel.year.lt(2009), "fdi_structural_score_raw"].isna().all()
    assert panel.loc[panel.year.eq(2025), "fdi_structural_score_raw"].isna().all()
    anchor = panel.fdi_reporting_regime.eq("anchor_official_fixed_regime")
    assert panel.loc[anchor & panel.year.between(2009, 2017), "fdi_structural_score_raw"].isna().all()

def test_observed_positions_scored(panel):
    assert panel.loc[panel.observed, "fdi_structural_score_raw"].notna().all()
    assert panel.loc[~panel.observed, "fdi_structural_score_raw"].isna().all()

def test_zero_and_negative_score_zero(panel):
    x = panel[panel.observed_zero | panel.observed_negative]
    assert len(x) > 0
    assert x.fdi_structural_score_raw.eq(0).all()

def test_score_formula_and_bounds(panel):
    x = panel[panel.observed & panel.fdi_outward_position_usd_mn.gt(0)]
    expected = (x.log_positive_position / x.log_p95_cap).clip(upper=1.0)
    assert (x.fdi_structural_score_raw - expected).abs().max() < 1e-12
    assert panel.fdi_structural_score_raw.dropna().between(0, 1).all()

def test_signed_coverage(panel):
    signed = panel.pivot(index=["country_iso3", "year"], columns="anchor", values="fdi_structural_score_raw").reset_index()
    signed["available"] = signed.China.notna() & signed["United States"].notna()
    annual = signed.groupby("year").available.sum().to_dict()
    assert annual[2009] == 63
    assert annual[2017] == 78
    assert annual[2018] == 170
    assert annual[2024] == 161
    assert annual[2025] == 0

def test_scg_and_exclusions(panel):
    assert set(panel.loc[panel.country_iso3.eq("SCG"), "year"]) == {2004, 2005, 2006}
    assert {"CHN", "USA", "HKG", "PSE", "TWN", "VAT"}.isdisjoint(set(panel.country_iso3))

def test_summary_validation(panel, audit):
    summary = b.build_summary(panel, audit)
    assert summary["rows"] == 8410
    assert summary["regime_assignment"]["regime_counts"] == {
        "anchor_official_fixed_regime": 112,
        "host_official_fixed_regime": 79,
    }
    assert all(value == 0 for value in summary["validation_failures"].values())
