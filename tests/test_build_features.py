import json

import pandas as pd

from inframatch.ingest.build_features import build_supplier_features


def test_build_supplier_features_drops_empty_codes_and_captures_subagencies():
    awards_df = pd.DataFrame(
        [
            {
                "canonical_supplier_id": "uei:ABC123",
                "recipient_name": "Acme Engineering",
                "recipient_uei": "ABC123",
                "recipient_state": "NJ",
                "award_id": "1",
                "award_amount": 100.0,
                "start_date": "2024-01-01",
                "naics_code": "541330",
                "psc_code": "C1LB",
                "awarding_agency": "Department of Transportation",
                "awarding_subagency": "Federal Highway Administration",
            },
            {
                "canonical_supplier_id": "uei:ABC123",
                "recipient_name": "Acme Engineering",
                "recipient_uei": "ABC123",
                "recipient_state": "NJ",
                "award_id": "2",
                "award_amount": 50.0,
                "start_date": "2024-02-01",
                "naics_code": "",
                "psc_code": "",
                "awarding_agency": "Department of Transportation",
                "awarding_subagency": "Federal Highway Administration",
            },
        ]
    )

    suppliers = build_supplier_features(awards_df)
    supplier = suppliers.iloc[0]

    assert json.loads(supplier["naics_codes"]) == ["541330"]
    assert json.loads(supplier["psc_codes"]) == ["C1LB"]
    assert json.loads(supplier["subagencies_worked_with"]) == ["Federal Highway Administration"]
