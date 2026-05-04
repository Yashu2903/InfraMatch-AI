import json

import pandas as pd


def _unique_non_empty(values) -> list[str]:
    cleaned = []

    for value in values:
        if value is None or pd.isna(value):
            continue

        value = str(value).strip()

        if value and value not in cleaned:
            cleaned.append(value)

    return cleaned


def build_supplier_features(awards_df: pd.DataFrame) -> pd.DataFrame:
    """
    Aggregate award-level rows into one row per canonical supplier.
    """
    grouped = awards_df.groupby("canonical_supplier_id", dropna=False)

    suppliers = grouped.agg(
        canonical_name=("recipient_name", "first"),
        uei=("recipient_uei", "first"),
        state=("recipient_state", "first"),
        past_awards_count=("award_id", "count"),
        total_award_value=("award_amount", "sum"),
        avg_award_value=("award_amount", "mean"),
        last_award_date=("start_date", "max"),
    ).reset_index()

    suppliers["naics_codes"] = grouped["naics_code"].apply(_unique_non_empty).values
    suppliers["psc_codes"] = grouped["psc_code"].apply(_unique_non_empty).values
    suppliers["agencies_worked_with"] = grouped["awarding_agency"].apply(_unique_non_empty).values
    suppliers["subagencies_worked_with"] = grouped["awarding_subagency"].apply(_unique_non_empty).values

    suppliers["naics_codes"] = suppliers["naics_codes"].apply(json.dumps)
    suppliers["psc_codes"] = suppliers["psc_codes"].apply(json.dumps)
    suppliers["agencies_worked_with"] = suppliers["agencies_worked_with"].apply(json.dumps)
    suppliers["subagencies_worked_with"] = suppliers["subagencies_worked_with"].apply(json.dumps)

    suppliers = suppliers.sort_values("total_award_value", ascending=False)

    return suppliers
