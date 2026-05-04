import json
import math
import random
from datetime import date
from pathlib import Path

import pandas as pd


SEED = 42
random.seed(SEED)

INPUT_PATH = Path("data/processed/suppliers.parquet")
OUTPUT_PATH = Path("data/processed/suppliers_with_compliance.parquet")

CORRIDOR_STATES = {"CT", "DE", "MA", "MD", "NJ", "NY", "PA"}

SBA_REVENUE_THRESHOLDS = {
    "541330": 25_500_000,
    "541350": 16_500_000,
    "541310": 12_500_000,
    "237310": 45_000_000,
}

CERT_RULES = {
    # cert: (base probability, naics_prefix, psc_codes)
    "PE_License": (0.85, "541", None),
    "ISO_9001": (0.40, None, None),
    "DBE_Certified": (0.25, None, None),
    "8(a)_Certified": (0.10, None, None),
    "Bridge_Inspection_NHI": (0.30, "541", ["C1LB", "Y1LB", "Z1LB"]),
    "OSHA_30": (0.70, "237", None),
}


def parse_json_list(value):
    if value is None or pd.isna(value):
        return []

    if isinstance(value, list):
        return value

    if isinstance(value, str):
        value = value.strip()

        if not value:
            return []

        try:
            parsed = json.loads(value)
            return parsed if isinstance(parsed, list) else []
        except json.JSONDecodeError:
            return []

    return []


def clip(value, low=0, high=100):
    return max(low, min(high, value))


def first_or_none(values):
    return values[0] if values else None


def primary_naics(naics_codes):
    return first_or_none(naics_codes)


def size_decile(series, value):
    if len(series) <= 1:
        return 5

    rank_pct = (series < value).mean()
    return int(rank_pct * 10)


def synth_small_business(row):
    naics_codes = row["naics_codes_parsed"]
    primary = primary_naics(naics_codes)

    threshold = SBA_REVENUE_THRESHOLDS.get(primary, 30_000_000)

    # Government awards are a proxy, not total revenue.
    # Assume federal awards are 20–60% of total revenue.
    implied_revenue = float(row["total_award_value"]) / random.uniform(0.2, 0.6)

    return implied_revenue < threshold


def synth_local_content(row, all_award_values):
    base = 50

    # Supplier headquarters are nationwide; corridor-based firms start with a
    # mild advantage for local staffing and mobilization.
    if row["state"] in CORRIDOR_STATES:
        base += random.gauss(8, 6)
    else:
        base -= random.gauss(5, 4)

    decile = size_decile(all_award_values, float(row["total_award_value"]))
    base -= 2 * decile

    base += random.gauss(0, 8)

    return round(clip(base), 2)


def synth_certifications(row):
    certs = []

    naics_codes = row["naics_codes_parsed"]
    psc_codes = row["psc_codes_parsed"]

    for cert, (probability, naics_prefix, psc_required) in CERT_RULES.items():
        p = probability

        naics_applies = (
            naics_prefix is None
            or any(str(code).startswith(naics_prefix) for code in naics_codes)
        )

        if not naics_applies:
            continue

        if psc_required is not None:
            has_relevant_psc = any(code in psc_codes for code in psc_required)

            if not has_relevant_psc:
                # Bridge-specific credentials should be backed by bridge-like PSC history.
                continue

            p *= 2.5

        if cert in {"DBE_Certified", "8(a)_Certified"} and row["small_business_flag"]:
            p *= 2.5

        if random.random() < min(p, 1.0):
            certs.append(cert)

    return certs


def years_since_last_award(value):
    if value is None or pd.isna(value):
        return 5

    parsed = pd.to_datetime(value, errors="coerce")

    if pd.isna(parsed):
        return 5

    today = pd.Timestamp(date.today())
    return max((today - parsed).days / 365.25, 0)


def synth_risk_score(row):
    score = 50

    score -= 5 * math.log10(float(row["past_awards_count"]) + 1)
    score += 3 * years_since_last_award(row["last_award_date"])
    score -= 2 * len(row["subagencies_parsed"])
    score += random.gauss(0, 5)

    return round(clip(score), 2)


def synth_esg_score(row):
    base = 55

    if row["small_business_flag"]:
        base += 5

    if "ISO_9001" in row["certifications"]:
        base += 5

    base += random.gauss(0, 12)

    return round(clip(base), 2)


def main():
    if not INPUT_PATH.exists():
        raise FileNotFoundError(
            f"Missing {INPUT_PATH}. Run Phase 1 supplier build first."
        )

    df = pd.read_parquet(INPUT_PATH)

    required_columns = [
        "canonical_supplier_id",
        "canonical_name",
        "state",
        "past_awards_count",
        "total_award_value",
        "avg_award_value",
        "last_award_date",
        "naics_codes",
        "psc_codes",
        "agencies_worked_with",
        "subagencies_worked_with",
    ]

    missing = [col for col in required_columns if col not in df.columns]

    if missing:
        raise ValueError(f"Missing required Phase 1 columns: {missing}")

    df["naics_codes_parsed"] = df["naics_codes"].apply(parse_json_list)
    df["psc_codes_parsed"] = df["psc_codes"].apply(parse_json_list)
    df["agencies_parsed"] = df["agencies_worked_with"].apply(parse_json_list)
    df["subagencies_parsed"] = df["subagencies_worked_with"].apply(parse_json_list)

    all_award_values = df["total_award_value"].astype(float)

    df["small_business_flag"] = df.apply(synth_small_business, axis=1)
    df["local_content_score"] = df.apply(
        lambda row: synth_local_content(row, all_award_values),
        axis=1,
    )
    df["certifications"] = df.apply(synth_certifications, axis=1)
    df["synthetic_esg_score"] = df.apply(synth_esg_score, axis=1)
    df["risk_score"] = df.apply(synth_risk_score, axis=1)

    df["certifications_json"] = df["certifications"].apply(json.dumps)

    df = df.drop(
        columns=[
            "naics_codes_parsed",
            "psc_codes_parsed",
            "agencies_parsed",
            "subagencies_parsed",
            "certifications",
        ],
        errors="ignore",
    )

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(OUTPUT_PATH, index=False)

    print(f"Saved suppliers with compliance overlay to {OUTPUT_PATH}")
    print(f"Rows: {len(df)}")
    print("\nCompliance summary:")
    print(df[["local_content_score", "small_business_flag", "synthetic_esg_score", "risk_score"]].describe())
    print("\nCertification counts:")
    print(df["certifications_json"].value_counts().head(10))


if __name__ == "__main__":
    main()
