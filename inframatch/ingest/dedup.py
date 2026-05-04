import hashlib
import re

import pandas as pd


BUSINESS_SUFFIXES = {
    "inc",
    "incorporated",
    "llc",
    "l.l.c",
    "corp",
    "corporation",
    "co",
    "company",
    "ltd",
    "limited",
    "lp",
    "llp",
    "pllc",
    "pc",
}


def normalize_name(name: str | None) -> str:
    """
    Normalize supplier names for deduplication.

    Example:
    'ACME Engineering, LLC' -> 'acme engineering'
    """
    if name is None or pd.isna(name):
        return ""

    name = str(name).lower()
    name = re.sub(r"[^\w\s]", " ", name)
    tokens = [token for token in name.split() if token not in BUSINESS_SUFFIXES]
    return " ".join(tokens)


def make_supplier_id(prefix: str, value: str) -> str:
    raw = f"{prefix}:{value}".encode("utf-8")
    return hashlib.md5(raw).hexdigest()[:12]


def dedupe_awards(awards_df: pd.DataFrame) -> pd.DataFrame:
    """
    Three-tier deduplication.

    Tier 1: exact UEI match.
    Tier 2: normalized recipient name + state.
    Tier 3: fuzzy match is intentionally skipped for Phase 1 core.
    """
    df = awards_df.copy()

    df["recipient_name_normalized"] = df["recipient_name"].apply(normalize_name)
    df["recipient_uei_clean"] = df["recipient_uei"].fillna("").astype(str).str.strip()
    df["state_clean"] = df["recipient_state"].fillna("").astype(str).str.upper().str.strip()

    df["canonical_supplier_id"] = None

    has_uei = df["recipient_uei_clean"] != ""

    df.loc[has_uei, "canonical_supplier_id"] = df.loc[has_uei, "recipient_uei_clean"].apply(
        lambda uei: make_supplier_id("uei", uei)
    )

    no_uei = ~has_uei

    df.loc[no_uei, "canonical_supplier_id"] = df.loc[no_uei].apply(
        lambda row: make_supplier_id(
            "name_state",
            f"{row['recipient_name_normalized']}::{row['state_clean']}",
        ),
        axis=1,
    )

    return df