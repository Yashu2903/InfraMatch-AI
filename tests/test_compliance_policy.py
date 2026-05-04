from datetime import date
from types import SimpleNamespace

from inframatch.compliance.engine import evaluate_rules, load_rules


def test_load_rules_has_expected_rules():
    rules = load_rules()

    assert [rule["id"] for rule in rules] == [
        "local_content",
        "small_business",
        "certifications",
    ]
    assert [rule["weight"] for rule in rules] == [0.4, 0.3, 0.3]


def test_evaluate_rules_returns_weighted_outcomes():
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

    score, outcomes = evaluate_rules(supplier, opportunity)
    by_rule = {item["rule_id"]: item for item in outcomes}

    assert round(score, 4) == round((0.5 * 0.4) + (0.0 * 0.3) + (0.5 * 0.3), 4)
    assert by_rule["local_content"]["partial_score"] == 0.5
    assert by_rule["small_business"]["passed"] is False
    assert by_rule["certifications"]["missing"] == ["Bridge_Inspection_NHI"]
