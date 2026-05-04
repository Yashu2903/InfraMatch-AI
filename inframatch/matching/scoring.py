import json
import math
from datetime import date
from typing import Any

from inframatch.compliance.engine import evaluate_rules

CORRIDOR_STATES = {"CT", "DE", "MA", "MD", "NJ", "NY", "PA"}

ADJACENCY = {
    "NJ": ["NY", "PA", "DE"],
    "NY": ["NJ", "PA", "CT", "MA"],
    "PA": ["NJ", "NY", "MD", "DE"],
    "MD": ["PA", "DE"],
    "DE": ["NJ", "PA", "MD"],
    "MA": ["NY", "CT"],
    "CT": ["NY", "MA"],
}


DEFAULT_WEIGHTS = {
    "naics_similarity": 0.20,
    "psc_similarity": 0.15,
    "past_performance": 0.20,
    "compliance_fit": 0.20,
    "location_score": 0.10,
    "agency_familiarity": 0.10,
    "recency": 0.05,
}


ENTRANT_WEIGHTS = {
    "naics_similarity": 0.20,
    "psc_similarity": 0.15,
    "compliance_fit": 0.20,
    "location_score": 0.10,
    "recency": 0.05,
}


def parse_json_list(value: Any) -> list[str]:
    if value is None:
        return []

    if isinstance(value, list):
        return [str(item) for item in value if item is not None]

    if isinstance(value, str):
        value = value.strip()

        if not value:
            return []

        try:
            parsed = json.loads(value)
            if isinstance(parsed, list):
                return [str(item) for item in parsed if item is not None]
        except json.JSONDecodeError:
            return []

    return []


def normalize_weights(weights: dict[str, float]) -> dict[str, float]:
    total = sum(weights.values())

    if total <= 0:
        raise ValueError("Weights must sum to a positive number.")

    return {key: value / total for key, value in weights.items()}


def _coerce_str_list(value: Any) -> list[str]:
    return [str(item).strip() for item in parse_json_list(value) if str(item).strip()]


def _looks_like_list_payload(value: Any) -> bool:
    if isinstance(value, list):
        return True

    if isinstance(value, str):
        stripped = value.strip()
        return stripped.startswith("[") and stripped.endswith("]")

    return False


def _legacy_naics_similarity(
    project_naics_prefixes: Any,
    supplier_naics_codes: Any,
) -> float | None:
    """
    Backward-compatible Phase 1/2 behavior.
    """
    supplier_codes = _coerce_str_list(supplier_naics_codes)
    project_prefixes = _coerce_str_list(project_naics_prefixes)

    if not supplier_codes or not project_prefixes:
        return None

    matches = sum(
        1
        for supplier_code in supplier_codes
        if any(supplier_code.startswith(prefix) for prefix in project_prefixes)
    )

    return matches / len(supplier_codes)


def naics_similarity(supplier_codes: Any, project_code: Any) -> float | None:
    """
    Hierarchical NAICS similarity.

    6-digit match: 1.00
    4-digit match: 0.66
    2-digit match: 0.33

    Returns None when supplier has no NAICS history.
    """
    if _looks_like_list_payload(project_code):
        return _legacy_naics_similarity(supplier_codes, project_code)

    supplier_codes = _coerce_str_list(supplier_codes)
    project_code = str(project_code).strip()

    if not supplier_codes:
        return None

    if not project_code:
        return 0.0

    best = 0.0

    for code in supplier_codes:
        code = str(code)

        for length, score in [(6, 1.0), (4, 0.66), (2, 0.33)]:
            if len(code) >= length and len(project_code) >= length:
                if code[:length] == project_code[:length]:
                    best = max(best, score)
                    break

    return best


def psc_similarity(supplier_pscs: list[str], project_psc: str) -> float | None:
    """
    PSC similarity.

    Exact PSC match: 1.00
    Same PSC family, first two chars: 0.50
    Same broad category, first char: 0.25
    No match: 0.00

    Returns None when supplier has no PSC history.
    """
    if not supplier_pscs:
        return None

    project_psc = str(project_psc).strip().upper()

    if not project_psc:
        return 0.0

    normalized_pscs = [str(code).strip().upper() for code in supplier_pscs]

    if project_psc in normalized_pscs:
        return 1.0

    project_family = project_psc[:2]

    if any(code.startswith(project_family) for code in normalized_pscs):
        return 0.5

    project_category = project_psc[0]

    if any(code.startswith(project_category) for code in normalized_pscs):
        return 0.25

    return 0.0


def past_performance_score(
    past_awards_count: int,
    total_award_value: float,
    max_count: int,
    max_value: float,
) -> float:
    if max_count <= 0 or max_value <= 0:
        return 0.0

    count_score = math.log1p(past_awards_count) / math.log1p(max_count)
    value_score = math.log1p(total_award_value) / math.log1p(max_value)

    return 0.5 * count_score + 0.5 * value_score


def location_score(supplier_state: str, project_state: str) -> float:
    supplier_state = str(supplier_state).upper()
    project_state = str(project_state).upper()

    if supplier_state == project_state:
        return 1.0

    if project_state in ADJACENCY.get(supplier_state, []):
        return 0.7

    if supplier_state in CORRIDOR_STATES:
        return 0.4

    return 0.1


def _legacy_agency_familiarity(
    project_subagency: Any,
    supplier_subagencies_worked_with: Any,
    project_agency: Any = None,
    supplier_agencies_worked_with: Any = None,
) -> float | None:
    """
    Backward-compatible Phase 1/2 behavior.
    """
    supplier_subagencies = {
        value.casefold() for value in _coerce_str_list(supplier_subagencies_worked_with)
    }
    supplier_agencies = {
        value.casefold() for value in _coerce_str_list(supplier_agencies_worked_with)
    }

    if project_subagency and supplier_subagencies:
        return (
            1.0
            if str(project_subagency).strip().casefold() in supplier_subagencies
            else 0.0
        )

    if project_agency and supplier_agencies:
        return (
            1.0 if str(project_agency).strip().casefold() in supplier_agencies else 0.0
        )

    return None


def agency_familiarity(*args, **kwargs) -> float | None:
    """
    Subagency match is strongest.
    Top-tier agency match gets partial credit.
    """
    if kwargs.get("project_agency") is not None or kwargs.get(
        "supplier_agencies_worked_with"
    ) is not None:
        project_subagency = args[0] if args else kwargs.get("project_subagency")
        supplier_subagencies_worked_with = (
            args[1] if len(args) > 1 else kwargs.get("supplier_subagencies_worked_with")
        )
        return _legacy_agency_familiarity(
            project_subagency=project_subagency,
            supplier_subagencies_worked_with=supplier_subagencies_worked_with,
            project_agency=kwargs.get("project_agency"),
            supplier_agencies_worked_with=kwargs.get("supplier_agencies_worked_with"),
        )

    if kwargs:
        supplier_subagencies = kwargs.get("supplier_subagencies", [])
        supplier_agencies = kwargs.get("supplier_agencies", [])
        opportunity_subagency = kwargs.get("opportunity_subagency")
        opportunity_agency = kwargs.get("opportunity_agency")
    else:
        if len(args) != 4:
            raise TypeError(
                "agency_familiarity expects either 4 positional Phase 3 arguments "
                "or the legacy keyword-based signature."
            )

        supplier_subagencies, supplier_agencies, opportunity_subagency, opportunity_agency = args

    supplier_subagency_set = {str(item).strip().lower() for item in _coerce_str_list(supplier_subagencies)}
    supplier_agency_set = {str(item).strip().lower() for item in _coerce_str_list(supplier_agencies)}

    opportunity_subagency_clean = str(opportunity_subagency).strip().lower()
    opportunity_agency_clean = str(opportunity_agency).strip().lower()

    if opportunity_subagency_clean and opportunity_subagency_clean in supplier_subagency_set:
        return 1.0

    if opportunity_agency_clean and opportunity_agency_clean in supplier_agency_set:
        return 0.5

    return 0.0


def years_since(value) -> float:
    if value is None:
        return 5.0

    if isinstance(value, date):
        parsed = value
    else:
        try:
            parsed = date.fromisoformat(str(value)[:10])
        except ValueError:
            return 5.0

    delta_days = (date.today() - parsed).days

    if delta_days < 0:
        return 0.0

    return delta_days / 365.25


def recency_score(last_award_date) -> float:
    """
    Exponential decay on years since last award.

    Current/recent award is near 1.
    Older history gradually decays toward 0.
    """
    years = years_since(last_award_date)
    return math.exp(-0.35 * years)


def normalize_compliance_outcomes(outcomes: list[dict]) -> list[dict]:
    normalized = []

    for item in outcomes:
        normalized.append(
            {
                "rule": item.get("rule_id"),
                "name": item.get("name"),
                "rule_type": item.get("type"),
                "passed": bool(item.get("passed", False)),
                "score": round(float(item.get("partial_score", 0.0)), 4),
                "weight": round(float(item.get("weight", 0.0)), 4),
                "weighted_score": round(float(item.get("weighted_score", 0.0)), 4),
                "note": item.get("message", ""),
                "supplier_value": item.get("supplier_value"),
                "required_value": item.get("required_value"),
                "missing": item.get("missing", []),
            }
        )

    return normalized


def compliance_fit(supplier, opportunity) -> tuple[float, list[dict]]:
    """
    Phase 3 compliance policy evaluation.
    """
    score, outcomes = evaluate_rules(supplier, opportunity)
    return score, normalize_compliance_outcomes(outcomes)


def compliance_fit_stub(supplier, opportunity) -> float:
    score, _ = compliance_fit(supplier, opportunity)
    return score


def factor_note(
    factor: str,
    value: float | None,
    supplier,
    opportunity,
    compliance_outcomes: list[dict] | None = None,
) -> str:
    if value is None:
        return "No historical data available for this factor."

    if factor == "naics_similarity":
        if value == 1.0:
            return f"Exact NAICS match for project code {opportunity.naics_code}."
        if value >= 0.66:
            return f"Same 4-digit NAICS family as project code {opportunity.naics_code}."
        if value >= 0.33:
            return f"Same 2-digit NAICS sector as project code {opportunity.naics_code}."
        return f"No close NAICS match for project code {opportunity.naics_code}."

    if factor == "psc_similarity":
        if value == 1.0:
            return f"Exact PSC match for project code {opportunity.psc_code}."
        if value >= 0.5:
            return f"Same PSC family as project code {opportunity.psc_code}."
        if value >= 0.25:
            return f"Same broad PSC category as project code {opportunity.psc_code}."
        return f"No PSC match for project code {opportunity.psc_code}."

    if factor == "past_performance":
        return (
            f"{supplier.past_awards_count} prior awards, "
            f"${supplier.total_award_value:,.0f} total award value."
        )

    if factor == "compliance_fit":
        if not compliance_outcomes:
            return "No compliance outcomes available."

        passed = sum(1 for item in compliance_outcomes if item["passed"])
        failed_rules = [item["rule"] for item in compliance_outcomes if not item["passed"]]

        if not failed_rules:
            return f"Passed all {len(compliance_outcomes)} compliance checks."

        return (
            f"Passed {passed} of {len(compliance_outcomes)} compliance checks; "
            f"gaps in {', '.join(failed_rules)}."
        )

    if factor == "location_score":
        if value == 1.0:
            return f"Same state as opportunity ({opportunity.state})."
        if value >= 0.7:
            return f"Adjacent to opportunity state ({opportunity.state})."
        if value >= 0.4:
            return "Supplier is within the Northeast corridor."
        return "Supplier is outside the target corridor."

    if factor == "agency_familiarity":
        if value == 1.0:
            return f"Has worked with subagency: {opportunity.awarding_subagency}."
        if value >= 0.5:
            return f"Has worked with top-tier agency: {opportunity.awarding_agency}."
        return "No matching agency or subagency history."

    if factor == "recency":
        return f"Last award date: {supplier.last_award_date}."

    return ""


def build_concerns(
    breakdown: list[dict],
    compliance_outcomes: list[dict],
    weights: dict[str, float],
) -> list[dict]:
    factor_concerns = [
        item
        for item in breakdown
        if item["value"] is not None and item["factor"] != "compliance_fit"
    ]

    compliance_weight = float(weights.get("compliance_fit", 0.0))
    compliance_concerns = []

    for outcome in compliance_outcomes:
        if outcome["passed"]:
            continue

        compliance_concerns.append(
            {
                "factor": f"compliance:{outcome['rule']}",
                "value": round(float(outcome["score"]), 4),
                "weight": round(compliance_weight * float(outcome["weight"]), 4),
                "weighted_score": round(
                    compliance_weight * float(outcome["weighted_score"]),
                    4,
                ),
                "note": outcome["note"],
            }
        )

    compliance_concerns = sorted(
        compliance_concerns,
        key=lambda item: (item["value"], item["weighted_score"]),
    )
    factor_concerns = sorted(
        factor_concerns,
        key=lambda item: (item["value"], item["weighted_score"]),
    )

    combined = compliance_concerns + factor_concerns

    return combined[:3]


def score_supplier(
    supplier,
    opportunity,
    max_count: int,
    max_value: float,
    weights: dict[str, float] | None = None,
) -> dict:
    weights = normalize_weights(weights or DEFAULT_WEIGHTS)

    supplier_naics = parse_json_list(supplier.naics_codes_json)
    supplier_pscs = parse_json_list(supplier.psc_codes_json)
    supplier_agencies = parse_json_list(supplier.agencies_json)
    supplier_subagencies = parse_json_list(supplier.subagencies_json)

    compliance_score, compliance_outcomes = compliance_fit(supplier, opportunity)

    raw_scores = {
        "naics_similarity": naics_similarity(supplier_naics, opportunity.naics_code),
        "psc_similarity": psc_similarity(supplier_pscs, opportunity.psc_code),
        "past_performance": past_performance_score(
            supplier.past_awards_count,
            supplier.total_award_value,
            max_count,
            max_value,
        ),
        "compliance_fit": compliance_score,
        "location_score": location_score(supplier.state, opportunity.state),
        "agency_familiarity": agency_familiarity(
            supplier_subagencies,
            supplier_agencies,
            opportunity.awarding_subagency,
            opportunity.awarding_agency,
        ),
        "recency": recency_score(supplier.last_award_date),
    }

    # Missing classification history should not crash scoring.
    # Treat None as 0 in final weighted score, but preserve note.
    weighted_parts = {}

    for factor, weight in weights.items():
        value = raw_scores.get(factor)
        weighted_parts[factor] = (value or 0.0) * weight

    final_score = sum(weighted_parts.values())

    breakdown = []

    for factor, value in raw_scores.items():
        if factor not in weights:
            continue

        breakdown.append(
            {
                "factor": factor,
                "value": None if value is None else round(value, 4),
                "weight": round(weights[factor], 4),
                "weighted_score": round(weighted_parts[factor], 4),
                "note": factor_note(
                    factor,
                    value,
                    supplier,
                    opportunity,
                    compliance_outcomes=compliance_outcomes,
                ),
            }
        )

    top_factors = sorted(
        breakdown,
        key=lambda item: item["weighted_score"],
        reverse=True,
    )[:3]

    concerns = build_concerns(breakdown, compliance_outcomes, weights)

    return {
        "supplier_id": supplier.id,
        "supplier": supplier.canonical_name,
        "final_score": round(final_score, 4),
        "score_breakdown": breakdown,
        "top_factors": top_factors,
        "concerns": concerns,
        "compliance_outcomes": compliance_outcomes,
    }
