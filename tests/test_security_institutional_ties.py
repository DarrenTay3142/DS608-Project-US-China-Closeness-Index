from pathlib import Path

import pandas as pd
import pytest

from src.data.build_security_institutional_ties import (
    build_panel,
    load_country_master,
    load_register,
    validate_panel,
)

ROOT = Path(__file__).resolve().parents[1]
REGISTER = ROOT / "data/sources/relations/security_arrangement_membership_register.csv"
MASTER = ROOT / "outputs/tables/relations_condition/relationship_condition_country_master.csv"


@pytest.fixture(scope="module")
def production_inputs():
    return load_register(REGISTER), load_country_master(MASTER)


@pytest.fixture(scope="module")
def production_panel(production_inputs):
    register, master = production_inputs
    return build_panel(register, master)


def test_panel_dimensions_and_keys(production_panel):
    panel, evidence = production_panel
    assert len(panel) == 8410
    assert panel.groupby("anchor").size().to_dict() == {
        "China": 4205,
        "United States": 4205,
    }
    assert not panel.duplicated(["country_iso3", "anchor", "year"]).any()
    assert len(evidence) == 1659


def test_historical_and_special_entity_policy(production_panel):
    panel, _ = production_panel
    assert set(panel.loc[panel["country_iso3"].eq("SCG"), "year"]) == {2004, 2005, 2006}
    excluded = {"COK", "ESH", "GIB", "HKG", "KSV", "MSR", "NIU", "PSE", "TWN", "VAT"}
    assert not panel["country_iso3"].isin(excluded).any()
    assert not panel["country_iso3"].isin({"CHN", "USA"}).any()


def test_verified_membership_edge_cases(production_panel):
    panel, evidence = production_panel

    nato = evidence.loc[evidence["arrangement_id"].eq("nato")]
    assert not nato["country_iso3"].eq("HND").any()
    assert nato.loc[nato["country_iso3"].eq("ALB"), "year"].min() == 2009
    assert nato.loc[nato["country_iso3"].eq("HRV"), "year"].min() == 2009
    assert nato.loc[nato["country_iso3"].eq("FIN"), "year"].min() == 2023
    assert nato.loc[nato["country_iso3"].eq("SWE"), "year"].min() == 2024

    aukus = evidence.loc[evidence["arrangement_id"].eq("aukus")]
    assert aukus["year"].min() == 2021

    sco = evidence.loc[evidence["arrangement_id"].eq("sco_full_member")]
    assert sco["depth"].eq(1).all()
    assert not evidence["arrangement_id"].str.contains("observer|dialogue", case=False, regex=True).any()

    solomon = evidence.loc[evidence["arrangement_id"].eq("china_solomon_security")]
    assert solomon["country_iso3"].eq("SLB").all()
    assert solomon["year"].min() == 2022
    assert solomon["depth"].eq(2).all()


def test_rio_treaty_and_score_method(production_panel):
    panel, evidence = production_panel
    rio = evidence.loc[evidence["arrangement_id"].eq("rio_treaty")]
    assert rio["depth"].eq(3).all()
    assert set(rio.loc[rio["country_iso3"].eq("BOL"), "year"]) == set(range(2004, 2015))
    assert set(rio.loc[rio["country_iso3"].eq("VEN"), "year"]) == (
        set(range(2004, 2016)) | set(range(2019, 2026))
    )
    validate_panel(panel)
    assert set(panel["security_institutional_score_raw"].unique()).issubset({0.0, 1 / 3, 2 / 3, 1.0})


def test_builder_matches_validated_notebook_candidate(production_panel):
    panel, _ = production_panel
    candidate_path = Path(
        "outputs/tables/security_institutional_ties/security_institutional_score_candidate_verified.csv"
    )
    if not candidate_path.exists():
        pytest.skip("Validated Notebook 12 candidate is not present.")
    candidate = pd.read_csv(candidate_path)
    comparison_columns = [
        "country_iso3",
        "country_name",
        "anchor",
        "year",
        "observed",
        "status",
        "maximum_depth",
        "active_arrangement_count",
        "controlling_arrangements",
        "supporting_arrangements",
        "relationship_types",
        "security_institutional_score_raw",
        "source_completeness_status",
        "method",
        "source",
    ]
    actual = panel[comparison_columns].sort_values(["country_iso3", "anchor", "year"]).reset_index(drop=True)
    expected = candidate[comparison_columns].sort_values(["country_iso3", "anchor", "year"]).reset_index(drop=True)
    # CSV round-tripping reads empty evidence strings as NaN. Normalize the
    # representation before comparing semantic equality with the builder.
    evidence_text_columns = [
        "controlling_arrangements", "supporting_arrangements", "relationship_types"
    ]
    for column in evidence_text_columns:
        actual[column] = actual[column].fillna("")
        expected[column] = expected[column].fillna("")
    pd.testing.assert_frame_equal(actual, expected, check_dtype=False)
