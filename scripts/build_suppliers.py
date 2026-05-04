from pathlib import Path
import sys

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from inframatch.ingest.build_features import build_supplier_features
from inframatch.ingest.dedup import dedupe_awards
from inframatch.ingest.usaspending import collapse_transactions_to_awards, fetch_award_transactions


RAW_OUTPUT = Path("data/processed/awards.parquet")
SUPPLIERS_OUTPUT = Path("data/processed/suppliers.parquet")
START_DATE = "2018-01-01"
END_DATE = "2025-12-31"
PLACE_OF_PERFORMANCE_STATES = ["NJ", "NY", "PA", "CT", "MA", "MD", "DE"]
TOP_TIER_AGENCIES = [
    "Department of Transportation",
    "General Services Administration",
    "Department of the Interior",
    "Department of Veterans Affairs",
    "Department of Homeland Security",
    "Department of Agriculture",
    "Environmental Protection Agency",
]
PSC_CODES = [
    "Y1LB",
    "Z1LB",
    "Z2LB",
    "C1LB",
    "Y1KA",
    "C1KA",
    "C1KF",
    "C1ND",
    "C1NE",
    "H156",
    "H356",
    "C213",
    "R404",
    "C211",
    "C219",
]


def extract_state(recipient_location):
    """
    USAspending may return recipient location as either a dict-like object
    or a string depending on selected fields. This keeps Phase 1 robust.
    """
    if isinstance(recipient_location, dict):
        return (
            recipient_location.get("state")
            or recipient_location.get("state_code")
            or recipient_location.get("recipient_state")
        )

    return None


def normalize_award_row(row: dict) -> dict:
    location = row.get("Recipient Location") or row.get("recipient_location")
    place_of_performance = (
        row.get("Primary Place of Performance")
        or row.get("place_of_performance")
    )

    return {
        "award_id": row.get("Award ID"),
        "recipient_name": row.get("Recipient Name"),
        "recipient_uei": row.get("Recipient UEI"),
        "award_amount": pd.to_numeric(
            row.get("Award Amount", row.get("Transaction Amount")),
            errors="coerce",
        ),
        "start_date": row.get("Start Date") or row.get("Action Date"),
        "end_date": row.get("End Date"),
        "awarding_agency": row.get("Awarding Agency"),
        "awarding_subagency": row.get("Awarding Sub Agency"),
        "naics_code": str(row.get("NAICS Code") or row.get("naics_code") or "").strip(),
        "naics_description": row.get("NAICS Description") or row.get("naics_description"),
        "psc_code": str(
            row.get("PSC Code") or row.get("product_or_service_code") or ""
        ).strip(),
        "psc_description": row.get("PSC Description") or row.get("product_or_service_description"),
        "recipient_location": location,
        "recipient_state": extract_state(location),
        "place_of_performance": place_of_performance,
        "place_of_performance_state": extract_state(place_of_performance),
    }


def main():
    print("Fetching USAspending awards...")

    rows = list(
        fetch_award_transactions(
            states=PLACE_OF_PERFORMANCE_STATES,
            naics_prefixes=None,
            psc_codes=PSC_CODES,
            agency_names=TOP_TIER_AGENCIES,
            start_date=START_DATE,
            end_date=END_DATE,
            min_amount=25_000,
            limit=100,
            max_pages=None,
        )
    )
    rows = collapse_transactions_to_awards(rows)

    print(f"Total raw award rows fetched: {len(rows)}")

    if not rows:
        raise RuntimeError(
            "No awards fetched. Check whether USAspending is returning populated NAICS codes "
            "for the requested sectors and whether the current date, states, and minimum award "
            "amount filters are too restrictive."
        )

    awards_df = pd.DataFrame([normalize_award_row(row) for row in rows])

    awards_df = awards_df[awards_df["start_date"] >= START_DATE]
    awards_df = awards_df.dropna(subset=["recipient_name"])
    awards_df["award_amount"] = awards_df["award_amount"].fillna(0)

    print("Running supplier deduplication...")
    deduped_awards_df = dedupe_awards(awards_df)

    print("Building supplier features...")
    suppliers_df = build_supplier_features(deduped_awards_df)

    RAW_OUTPUT.parent.mkdir(parents=True, exist_ok=True)

    deduped_awards_df.to_parquet(RAW_OUTPUT, index=False)
    suppliers_df.to_parquet(SUPPLIERS_OUTPUT, index=False)

    total_awards = len(deduped_awards_df)
    unique_suppliers = suppliers_df["canonical_supplier_id"].nunique()
    compression_ratio = total_awards / unique_suppliers if unique_suppliers else 0

    print("\nPhase 1 complete.")
    print(f"Saved awards to: {RAW_OUTPUT}")
    print(f"Saved suppliers to: {SUPPLIERS_OUTPUT}")
    print(f"Total awards pulled: {total_awards}")
    print(f"Unique suppliers post-dedup: {unique_suppliers}")
    print(f"Dedup compression ratio: {compression_ratio:.2f}")

    print("\nTop 10 suppliers by award value:")
    print(
        suppliers_df[
            [
                "canonical_name",
                "state",
                "past_awards_count",
                "total_award_value",
                "last_award_date",
            ]
        ]
        .head(10)
        .to_string(index=False)
    )


if __name__ == "__main__":
    main()
