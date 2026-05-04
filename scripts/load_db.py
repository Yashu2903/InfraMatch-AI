import json
from datetime import date
from pathlib import Path
import sys

import pandas as pd
from sqlmodel import Session, SQLModel, delete

PROJECT_ROOT = Path(__file__).resolve().parents[1]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from inframatch.db.models import DefectResult, Inspection, Match, Opportunity, Supplier
from inframatch.db.session import DEFAULT_DB_PATH, engine


SUPPLIERS_PATH = Path("data/processed/suppliers_with_compliance.parquet")
OPPORTUNITIES_PATH = Path("data/opportunities.json")


def parse_date(value):
    if value is None or pd.isna(value):
        return None

    parsed = pd.to_datetime(value, errors="coerce")

    if pd.isna(parsed):
        return None

    return parsed.date()


def safe_str(value):
    if value is None or pd.isna(value):
        return ""

    return str(value)


def ensure_json_text(value):
    if value is None or pd.isna(value):
        return "[]"

    if isinstance(value, list):
        return json.dumps(value)

    if isinstance(value, str):
        stripped = value.strip()

        if not stripped:
            return "[]"

        try:
            parsed = json.loads(stripped)
            if isinstance(parsed, list):
                return json.dumps(parsed)
        except json.JSONDecodeError:
            pass

    return "[]"


def load_suppliers(session: Session):
    if not SUPPLIERS_PATH.exists():
        raise FileNotFoundError(
            f"Missing {SUPPLIERS_PATH}. Run scripts/generate_compliance.py first."
        )

    df = pd.read_parquet(SUPPLIERS_PATH)

    suppliers = []

    for _, row in df.iterrows():
        supplier = Supplier(
            canonical_supplier_id=safe_str(row["canonical_supplier_id"]),
            canonical_name=safe_str(row["canonical_name"]),
            uei=safe_str(row.get("uei", "")),
            state=safe_str(row["state"]),

            past_awards_count=int(row["past_awards_count"]),
            total_award_value=float(row["total_award_value"]),
            avg_award_value=float(row["avg_award_value"]),
            last_award_date=parse_date(row["last_award_date"]),

            naics_codes_json=ensure_json_text(row["naics_codes"]),
            psc_codes_json=ensure_json_text(row["psc_codes"]),
            agencies_json=ensure_json_text(row["agencies_worked_with"]),
            subagencies_json=ensure_json_text(row["subagencies_worked_with"]),

            local_content_score=float(row["local_content_score"]),
            small_business_flag=bool(row["small_business_flag"]),
            certifications_json=ensure_json_text(row["certifications_json"]),
            synthetic_esg_score=float(row["synthetic_esg_score"]),
            risk_score=float(row["risk_score"]),
        )

        suppliers.append(supplier)

    session.add_all(suppliers)
    session.commit()

    return len(suppliers)


def load_opportunities(session: Session):
    if not OPPORTUNITIES_PATH.exists():
        raise FileNotFoundError(
            f"Missing {OPPORTUNITIES_PATH}. Run scripts/generate_opportunities.py first."
        )

    with OPPORTUNITIES_PATH.open("r", encoding="utf-8") as f:
        rows = json.load(f)

    opportunities = []

    for row in rows:
        opportunity = Opportunity(
            title=row["title"],
            asset_type=row["asset_type"],
            state=row["state"],
            city=row["city"],
            naics_code=row["naics_code"],
            psc_code=row["psc_code"],
            awarding_agency=row["awarding_agency"],
            awarding_subagency=row["awarding_subagency"],
            budget=float(row["budget"]),
            required_local_content=float(row["required_local_content"]),
            requires_small_business=bool(row["requires_small_business"]),
            required_certifications_json=json.dumps(row["required_certifications"]),
            risk_tolerance=row["risk_tolerance"],
        )

        opportunities.append(opportunity)

    session.add_all(opportunities)
    session.commit()

    return len(opportunities)


def reset_tables(session: Session):
    # Delete child/demo tables first.
    session.exec(delete(DefectResult))
    session.exec(delete(Inspection))
    session.exec(delete(Match))
    session.exec(delete(Opportunity))
    session.exec(delete(Supplier))
    session.commit()


def main():
    SQLModel.metadata.create_all(engine)

    with Session(engine) as session:
        print("Resetting database tables...")
        reset_tables(session)

        print("Loading suppliers...")
        supplier_count = load_suppliers(session)

        print("Loading opportunities...")
        opportunity_count = load_opportunities(session)

    print("\nPhase 2 database load complete.")
    print(f"Suppliers loaded: {supplier_count}")
    print(f"Opportunities loaded: {opportunity_count}")
    print(f"Database: {DEFAULT_DB_PATH}")


if __name__ == "__main__":
    main()

