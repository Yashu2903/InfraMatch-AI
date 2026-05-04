import json

from sqlmodel import Session, delete, select

from inframatch.db.models import Match, Opportunity, Supplier
from inframatch.db.session import engine
from inframatch.matching.scoring import DEFAULT_WEIGHTS, ENTRANT_WEIGHTS, score_supplier


def get_opportunity(session: Session, opportunity_id: int) -> Opportunity:
    opportunity = session.get(Opportunity, opportunity_id)

    if opportunity is None:
        raise ValueError(f"Opportunity not found: {opportunity_id}")

    return opportunity


def get_supplier_pool(session: Session) -> list[Supplier]:
    return list(session.exec(select(Supplier)).all())


def supplier_pool_maxima(suppliers: list[Supplier]) -> tuple[int, float]:
    max_count = max((supplier.past_awards_count for supplier in suppliers), default=1)
    max_value = max((supplier.total_award_value for supplier in suppliers), default=1.0)

    return max_count, max_value


def rank_suppliers(
    opportunity_id: int,
    top_n: int = 10,
    save: bool = True,
) -> list[dict]:
    """
    Rank incumbent suppliers for one opportunity.

    Uses the updated Phase 3 7-factor formula.
    """
    with Session(engine) as session:
        opportunity = get_opportunity(session, opportunity_id)
        suppliers = get_supplier_pool(session)

        max_count, max_value = supplier_pool_maxima(suppliers)

        scored = [
            score_supplier(
                supplier=supplier,
                opportunity=opportunity,
                max_count=max_count,
                max_value=max_value,
                weights=DEFAULT_WEIGHTS,
            )
            for supplier in suppliers
        ]

        ranked = sorted(scored, key=lambda item: item["final_score"], reverse=True)

        for index, item in enumerate(ranked, start=1):
            item["rank"] = index

        top_results = ranked[:top_n]

        if save:
            save_matches(session, opportunity_id, top_results)

        return top_results


def rank_entrants(
    opportunity_id: int,
    top_n: int = 5,
    max_awards: int = 3,
) -> list[dict]:
    """
    Cold-start ranking for emerging suppliers.

    Removes past_performance and agency_familiarity weights,
    then re-normalizes the remaining factors.
    """
    with Session(engine) as session:
        opportunity = get_opportunity(session, opportunity_id)
        suppliers = [
            supplier
            for supplier in get_supplier_pool(session)
            if supplier.past_awards_count < max_awards
        ]

        max_count, max_value = supplier_pool_maxima(suppliers)

        scored = [
            score_supplier(
                supplier=supplier,
                opportunity=opportunity,
                max_count=max_count,
                max_value=max_value,
                weights=ENTRANT_WEIGHTS,
            )
            for supplier in suppliers
        ]

        ranked = sorted(scored, key=lambda item: item["final_score"], reverse=True)

        for index, item in enumerate(ranked, start=1):
            item["rank"] = index

        return ranked[:top_n]


def save_matches(
    session: Session,
    opportunity_id: int,
    ranked_results: list[dict],
) -> None:
    """
    Replace saved matches for this opportunity.
    """
    session.exec(delete(Match).where(Match.opportunity_id == opportunity_id))
    session.commit()

    match_rows = []

    for item in ranked_results:
        match_rows.append(
            Match(
                opportunity_id=opportunity_id,
                supplier_id=item["supplier_id"],
                final_score=item["final_score"],
                rank=item["rank"],
                score_breakdown_json=json.dumps(item["score_breakdown"]),
                top_factors_json=json.dumps(item["top_factors"]),
                concerns_json=json.dumps(item["concerns"]),
                compliance_outcomes_json=json.dumps(item["compliance_outcomes"]),
            )
        )

    session.add_all(match_rows)
    session.commit()


def get_saved_matches(opportunity_id: int) -> list[dict]:
    with Session(engine) as session:
        rows = list(
            session.exec(
                select(Match)
                .where(Match.opportunity_id == opportunity_id)
                .order_by(Match.rank)
            ).all()
        )

    return [
        {
            "rank": row.rank,
            "supplier_id": row.supplier_id,
            "final_score": row.final_score,
            "score_breakdown": json.loads(row.score_breakdown_json),
            "top_factors": json.loads(row.top_factors_json),
            "concerns": json.loads(row.concerns_json),
            "compliance_outcomes": json.loads(row.compliance_outcomes_json),
        }
        for row in rows
    ]
