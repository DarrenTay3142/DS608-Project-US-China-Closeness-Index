import importlib.util
from pathlib import Path
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "data/interim/relations/drd_anchor_country_year.csv"

if not SOURCE.exists():
    pytest.skip(
        "Local-only DRD intermediate is unavailable: "
        "data/interim/relations/drd_anchor_country_year.csv. "
        "See docs/local_data_requirements.md.",
        allow_module_level=True,
    )

spec = importlib.util.spec_from_file_location("builder", ROOT / "src/data/build_diplomatic_structural_ties.py")
b = importlib.util.module_from_spec(spec)
spec.loader.exec_module(b)

@pytest.fixture(scope="module")
def inputs():
    source = pd.read_csv(SOURCE, low_memory=False)
    master = pd.read_csv(ROOT / "outputs/tables/relations_condition/relationship_condition_country_master.csv", low_memory=False)
    return source, master

@pytest.fixture(scope="module")
def panel(inputs):
    return b.build_panel(*inputs)

def test_expected_shape_and_period(panel):
    assert panel.shape[0] == 8410
    assert panel.country_iso3.nunique() == 192
    assert (panel.year.min(), panel.year.max()) == (2004, 2025)

def test_unique_keys(panel):
    assert not panel.duplicated(["country_iso3", "anchor", "year"]).any()

def test_excluded_entities_and_anchor_self_relations_absent(panel):
    excluded = {"CHN", "USA", "HKG", "KSV", "PSE", "TWN", "VAT"}
    assert excluded.isdisjoint(set(panel.country_iso3))

def test_scg_validity_window(panel):
    assert set(panel.loc[panel.country_iso3.eq("SCG"), "year"]) == {2004, 2005, 2006}

def test_preferred_names(panel):
    expected = {"LKA":"Sri Lanka", "MKD":"North Macedonia", "MYS":"Malaysia", "SWZ":"Eswatini", "TLS":"Timor-Leste", "TUR":"Turkiye"}
    actual = panel.drop_duplicates("country_iso3").set_index("country_iso3").preferred_country_name.to_dict()
    for iso3, name in expected.items(): assert actual[iso3] == name

def test_source_aware_zero_for_unrecorded_direction(panel):
    x = panel[(panel.year <= 2024) & panel.direction_count.eq(1)]
    assert len(x) > 0
    assert x.diplomatic_structural_score_raw.notna().all()
    absent_a = ~x.anchor_to_country_observed
    assert x.loc[absent_a, "anchor_to_country_depth"].eq(0).all()
    assert x.loc[~absent_a, "country_to_anchor_depth"].eq(0).all()

def test_no_recorded_representation_scores_zero(panel):
    x = panel[(panel.year <= 2024) & panel.direction_count.eq(0)]
    assert len(x) > 0
    assert x.diplomatic_structural_score_raw.eq(0).all()

def test_observed_lor_zero_remains_observed(panel):
    x = panel[(panel.anchor_to_country_adverse) | (panel.country_to_anchor_adverse)]
    assert len(x) > 0
    assert x.loc[x.anchor_to_country_adverse, "anchor_to_country_observed"].all()
    assert x.loc[x.country_to_anchor_adverse, "country_to_anchor_observed"].all()

def test_2025_source_unavailable(panel):
    x = panel[panel.year.eq(2025)]
    assert len(x) == 382
    assert x.source_coverage_status.eq("source_year_unavailable").all()
    assert x.diplomatic_structural_score_raw.isna().all()

def test_scores_complete_through_2024_and_bounded(panel):
    x = panel[panel.year <= 2024]
    assert x.diplomatic_structural_score_raw.notna().all()
    assert x.diplomatic_structural_score_raw.between(0, 1).all()

def test_baseline_formula(panel):
    x = panel[panel.diplomatic_structural_score_raw.notna()]
    expected = 0.75 * x.mean_depth + 0.25 * x.reciprocity_depth
    assert (x.diplomatic_structural_score_raw - expected).abs().max() < 1e-12

def test_summary_reconciles(panel):
    summary = b.validate_panel(panel)
    assert summary["rows"] == 8410
    assert sum(summary["coverage_status_counts"].values()) == 8410
    assert summary["scored_rows"] + summary["missing_score_rows"] == 8410
