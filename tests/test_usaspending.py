from inframatch.ingest.usaspending import build_filter_payload, collapse_transactions_to_awards


def test_build_filter_payload_uses_place_of_performance_psc_and_agencies():
    payload = build_filter_payload(
        states=["NY", "PA"],
        naics_prefixes=["5413"],
        psc_codes=["C1LB", "H156"],
        agency_names=["Department of Transportation"],
        start_date="2024-01-01",
        end_date="2024-12-31",
        min_amount=25_000,
        page=1,
        limit=50,
    )

    filters = payload["filters"]

    assert filters["place_of_performance_locations"] == [
        {"country": "USA", "state": "NY"},
        {"country": "USA", "state": "PA"},
    ]
    assert filters["psc_codes"]["require"] == ["C1LB", "H156"]
    assert filters["agencies"] == [
        {
            "type": "awarding",
            "tier": "toptier",
            "name": "Department of Transportation",
        }
    ]
    assert filters["naics_codes"]["require"] == ["5413"]


def test_collapse_transactions_to_awards_sums_transaction_rows():
    rows = [
        {
            "Award ID": "ABC-1",
            "Recipient Name": "Acme Engineering",
            "Recipient UEI": "UEI123",
            "Action Date": "2024-06-01",
            "Transaction Amount": 100.0,
            "Awarding Agency": "Department of Transportation",
            "Awarding Sub Agency": "Federal Highway Administration",
            "naics_code": "541330",
            "naics_description": "ENGINEERING SERVICES",
            "product_or_service_code": "C1LB",
            "product_or_service_description": "BRIDGE A&E",
            "Recipient Location": {"state_code": "NJ"},
            "Primary Place of Performance": {"state_code": "NY"},
            "internal_id": 123,
        },
        {
            "Award ID": "ABC-1",
            "Recipient Name": "Acme Engineering",
            "Recipient UEI": "UEI123",
            "Action Date": "2024-08-15",
            "Transaction Amount": 25.5,
            "Awarding Agency": "Department of Transportation",
            "Awarding Sub Agency": "Federal Highway Administration",
            "naics_code": "541330",
            "naics_description": "ENGINEERING SERVICES",
            "product_or_service_code": "C1LB",
            "product_or_service_description": "BRIDGE A&E",
            "Recipient Location": {"state_code": "NJ"},
            "Primary Place of Performance": {"state_code": "NY"},
            "internal_id": 123,
        },
    ]

    awards = collapse_transactions_to_awards(rows)

    assert len(awards) == 1

    award = awards[0]

    assert award["Award ID"] == "ABC-1"
    assert award["Award Amount"] == 125.5
    assert award["Start Date"] == "2024-08-15"
    assert award["NAICS Code"] == "541330"
    assert award["PSC Code"] == "C1LB"
    assert award["Recipient Location"] == {"state_code": "NJ"}
    assert award["Primary Place of Performance"] == {"state_code": "NY"}
