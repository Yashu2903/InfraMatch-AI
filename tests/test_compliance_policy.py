from datetime import date
from types import SimpleNamespace

from inframatch.matching.compliance import evaluate_compliance_policy, load_compliance_policy


def test_load_compliance_policy_has_expected_rules():
    policy = load_compliance_policy()

    assert policy["version"] == 1
    assert policy["aggregate"]["strategy"] == "weighted_average"
    assert [rule["id"] for rule in policy["rules"]] == [
        "local_content",
        "small_business",
        "certifications",
    ]


def test_evaluate_compliance_policy_returns_weighted_outcomes():
    supplier = SimpleNamespace(
        id=1,
        canonical_name="Policy Test Supplier",
        state="NJ",
        past_awards_count=4,
        total_award_value=100_000,
        last_award_date=date.today(),
        local_content_score=50,
        small_business_flag=False,
        certifications_json='["PE_License"]',
    )

    opportunity = SimpleNamespace(
        state="NJ",
        required_local_content=100,
        requires_small_business=True,
        required_certifications_json='["PE_License", "Bridge_Inspection_NHI"]',
    )

    score, outcomes = evaluate_compliance_policy(supplier, opportunity)
    by_rule = {item["rule"]: item for item in outcomes}

    assert round(score, 4) == round((0.5 + 0.0 + 0.5) / 3, 4)
    assert by_rule["local_content"]["score"] == 0.5
    assert by_rule["small_business"]["passed"] is False
    assert by_rule["certifications"]["missing"] == ["Bridge_Inspection_NHI"]
