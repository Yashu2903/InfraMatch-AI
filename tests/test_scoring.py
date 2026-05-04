from inframatch.matching.scoring import agency_familiarity, naics_similarity


def test_naics_similarity_returns_none_for_missing_supplier_data():
    assert naics_similarity(["5413"], "[]") is None


def test_agency_familiarity_prefers_subagency_matches():
    assert (
        agency_familiarity(
            "Federal Highway Administration",
            '["Federal Highway Administration"]',
            project_agency="Department of Transportation",
            supplier_agencies_worked_with='["Department of Transportation"]',
        )
        == 1.0
    )


def test_agency_familiarity_falls_back_to_top_tier_when_subagency_missing():
    assert (
        agency_familiarity(
            None,
            "[]",
            project_agency="Department of Transportation",
            supplier_agencies_worked_with='["Department of Transportation"]',
        )
        == 1.0
    )
