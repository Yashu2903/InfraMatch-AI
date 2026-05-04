from datetime import date, timedelta
from types import SimpleNamespace

from inframatch.matching.scoring import (
    agency_familiarity,
    location_score,
    naics_similarity,
    past_performance_score,
    psc_similarity,
    recency_score,
    score_supplier,
)


def test_naics_exact_match():
    assert naics_similarity(["541330"], "541330") == 1.0


def test_naics_four_digit_match():
    assert naics_similarity(["541310"], "541330") == 0.66


def test_naics_two_digit_match():
    assert naics_similarity(["541999"], "541330") == 0.33


def test_naics_no_data_returns_none():
    assert naics_similarity([], "541330") is None


def test_psc_exact_match():
    assert psc_similarity(["C1LB"], "C1LB") == 1.0


def test_psc_family_match():
    assert psc_similarity(["C211"], "C219") == 0.5


def test_psc_broad_category_match():
    assert psc_similarity(["C1LB"], "C219") == 0.25


def test_psc_no_match():
    assert psc_similarity(["Y1LB"], "C211") == 0.0


def test_location_same_state():
    assert location_score("NJ", "NJ") == 1.0


def test_location_adjacent_state():
    assert location_score("NJ", "NY") == 0.7


def test_location_corridor_state():
    assert location_score("NJ", "MA") == 0.4


def test_agency_familiarity_subagency_match():
    assert (
        agency_familiarity(
            supplier_subagencies=["Federal Highway Administration"],
            supplier_agencies=["Department of Transportation"],
            opportunity_subagency="Federal Highway Administration",
            opportunity_agency="Department of Transportation",
        )
        == 1.0
    )


def test_agency_familiarity_top_tier_partial_match():
    assert (
        agency_familiarity(
            supplier_subagencies=["Federal Transit Administration"],
            supplier_agencies=["Department of Transportation"],
            opportunity_subagency="Federal Highway Administration",
            opportunity_agency="Department of Transportation",
        )
        == 0.5
    )


def test_past_performance_score_bounds():
    score = past_performance_score(
        past_awards_count=10,
        total_award_value=1_000_000,
        max_count=100,
        max_value=10_000_000,
    )

    assert 0 <= score <= 1


def test_recency_recent_award_higher_than_old_award():
    recent = date.today() - timedelta(days=30)
    old = date.today() - timedelta(days=365 * 5)

    assert recency_score(recent) > recency_score(old)


def test_score_supplier_returns_breakdown():
    supplier = SimpleNamespace(
        id=1,
        canonical_name="Test Engineering",
        state="NJ",
        past_awards_count=10,
        total_award_value=1_000_000,
        last_award_date=date.today(),
        naics_codes_json='["541330"]',
        psc_codes_json='["C1LB"]',
        agencies_json='["Department of Transportation"]',
        subagencies_json='["Federal Highway Administration"]',
        local_content_score=80,
        small_business_flag=True,
        certifications_json='["PE_License", "Bridge_Inspection_NHI"]',
    )

    opportunity = SimpleNamespace(
        state="NJ",
        naics_code="541330",
        psc_code="C1LB",
        awarding_agency="Department of Transportation",
        awarding_subagency="Federal Highway Administration",
        required_local_content=60,
        requires_small_business=True,
        required_certifications_json='["PE_License"]',
    )

    result = score_supplier(
        supplier=supplier,
        opportunity=opportunity,
        max_count=100,
        max_value=10_000_000,
    )

    assert result["final_score"] > 0
    assert len(result["score_breakdown"]) == 7
    assert len(result["top_factors"]) == 3
    assert len(result["compliance_outcomes"]) == 3
    assert {item["rule"] for item in result["compliance_outcomes"]} == {
        "local_content",
        "small_business",
        "certifications",
    }
    assert all(item["passed"] for item in result["compliance_outcomes"])


def test_score_supplier_surfaces_failed_compliance_checks():
    supplier = SimpleNamespace(
        id=2,
        canonical_name="Out-of-spec Supplier",
        state="VA",
        past_awards_count=1,
        total_award_value=10_000,
        last_award_date=date.today(),
        naics_codes_json='["541330"]',
        psc_codes_json='["C1LB"]',
        agencies_json='["Department of Transportation"]',
        subagencies_json='["Federal Highway Administration"]',
        local_content_score=20,
        small_business_flag=False,
        certifications_json='["PE_License"]',
    )

    opportunity = SimpleNamespace(
        state="NJ",
        naics_code="541330",
        psc_code="C1LB",
        awarding_agency="Department of Transportation",
        awarding_subagency="Federal Highway Administration",
        required_local_content=60,
        requires_small_business=True,
        required_certifications_json='["PE_License", "Bridge_Inspection_NHI"]',
    )

    result = score_supplier(
        supplier=supplier,
        opportunity=opportunity,
        max_count=100,
        max_value=10_000_000,
    )

    compliance = {item["rule"]: item for item in result["compliance_outcomes"]}

    assert compliance["local_content"]["passed"] is False
    assert compliance["small_business"]["passed"] is False
    assert compliance["certifications"]["passed"] is False
    assert "gaps in" in next(
        item["note"]
        for item in result["score_breakdown"]
        if item["factor"] == "compliance_fit"
    )
    concern_factors = {item["factor"] for item in result["concerns"]}
    assert "compliance:small_business" in concern_factors
    assert "compliance:certifications" in concern_factors
