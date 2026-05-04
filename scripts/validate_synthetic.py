import json
from pathlib import Path
import sys

from sqlmodel import Session, select

PROJECT_ROOT = Path(__file__).resolve().parents[1]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from inframatch.db.models import Opportunity, Supplier
from inframatch.db.session import engine


CORRIDOR_STATES = {"CT", "DE", "MA", "MD", "NJ", "NY", "PA"}

VALID_PSC_CODES = {"C1LB", "C211", "C219", "Y1LB", "Z1LB", "Z2LB"}

BRIDGE_RELATED_PSC = {"C1LB", "Y1LB", "Z1LB"}


def parse_json_list(value):
    if not value:
        return []

    try:
        parsed = json.loads(value)
        return parsed if isinstance(parsed, list) else []
    except json.JSONDecodeError:
        return []


def main():
    with Session(engine) as session:
        suppliers = session.exec(select(Supplier)).all()
        opportunities = session.exec(select(Opportunity)).all()

    assert suppliers, "No suppliers loaded."
    assert opportunities, "No opportunities loaded."

    print(f"Suppliers: {len(suppliers)}")
    print(f"Opportunities: {len(opportunities)}")

    supplier_states = {supplier.state for supplier in suppliers}
    opportunity_states = {opp.state for opp in opportunities}

    assert all(state and str(state).strip() for state in supplier_states), (
        "Supplier states must be populated."
    )

    assert opportunity_states <= CORRIDOR_STATES, (
        f"Opportunity states outside corridor: {opportunity_states - CORRIDOR_STATES}"
    )

    assert len(opportunities) >= 10, "Expected at least 10 opportunities."

    for supplier in suppliers:
        assert supplier.psc_codes_json, f"Missing PSC codes for supplier {supplier.id}"
        assert supplier.subagencies_json, f"Missing subagencies for supplier {supplier.id}"

        psc_codes = parse_json_list(supplier.psc_codes_json)
        subagencies = parse_json_list(supplier.subagencies_json)

        assert isinstance(psc_codes, list), "Supplier PSC field must be JSON list."
        assert isinstance(subagencies, list), "Supplier subagency field must be JSON list."

    for opp in opportunities:
        assert opp.psc_code, f"Missing PSC code for opportunity {opp.id}"
        assert opp.psc_code in VALID_PSC_CODES, (
            f"Invalid PSC code for opportunity {opp.id}: {opp.psc_code}"
        )
        assert opp.awarding_subagency, f"Missing subagency for opportunity {opp.id}"
        assert opp.city, f"Missing city for opportunity {opp.id}"
        assert opp.budget > 0, f"Budget must be positive for opportunity {opp.id}"

    small_budget_opps = [opp for opp in opportunities if opp.budget < 250_000]

    if small_budget_opps:
        pct_small_business_required = sum(
            opp.requires_small_business for opp in small_budget_opps
        ) / len(small_budget_opps)

        assert pct_small_business_required >= 0.40, (
            "Small-budget opportunities should often require small business. "
            f"Observed: {pct_small_business_required:.2f}"
        )

    local_scores = [supplier.local_content_score for supplier in suppliers]
    risk_scores = [supplier.risk_score for supplier in suppliers]

    assert all(0 <= score <= 100 for score in local_scores), (
        "Local content scores must be between 0 and 100."
    )

    assert all(0 <= score <= 100 for score in risk_scores), (
        "Risk scores must be between 0 and 100."
    )

    bridge_cert_holders = [
        supplier
        for supplier in suppliers
        if "Bridge_Inspection_NHI" in parse_json_list(supplier.certifications_json)
    ]

    if bridge_cert_holders:
        relevant_count = 0

        for supplier in bridge_cert_holders:
            psc_codes = set(parse_json_list(supplier.psc_codes_json))

            if psc_codes & BRIDGE_RELATED_PSC:
                relevant_count += 1

        bridge_relevance_rate = relevant_count / len(bridge_cert_holders)

        assert bridge_relevance_rate >= 0.50, (
            "Bridge inspection certification should correlate with bridge PSC history. "
            f"Observed: {bridge_relevance_rate:.2f}"
        )

    print("\nSynthetic validation passed.")
    print("Checks completed:")
    print("- Supplier headquarters are populated and opportunity states stay within the 7-state corridor")
    print("- PSC fields are populated")
    print("- Subagency fields are populated")
    print("- Opportunity city fields are populated")
    print("- Budget/compliance sanity checks passed")
    print("- Risk/local content ranges are valid")
    print("- Bridge certification correlation check passed")


if __name__ == "__main__":
    main()

