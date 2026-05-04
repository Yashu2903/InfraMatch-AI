import json


def _coerce_list(values) -> list[str]:
    if values is None:
        return []

    if isinstance(values, str):
        try:
            parsed = json.loads(values)
        except json.JSONDecodeError:
            parsed = [values]
    else:
        parsed = values

    cleaned = []

    for value in parsed:
        text = str(value).strip()

        if text and text not in cleaned:
            cleaned.append(text)

    return cleaned


def naics_similarity(project_naics_prefixes, supplier_naics_codes) -> float | None:
    """
    Return a simple overlap score between project NAICS prefixes and supplier codes.

    Missing supplier NAICS data returns None so callers can distinguish between an
    absent signal and a true zero-match.
    """
    supplier_codes = _coerce_list(supplier_naics_codes)
    project_prefixes = _coerce_list(project_naics_prefixes)

    if not supplier_codes:
        return None

    if not project_prefixes:
        return None

    matches = sum(
        1
        for supplier_code in supplier_codes
        if any(supplier_code.startswith(prefix) for prefix in project_prefixes)
    )

    return matches / len(supplier_codes)


def agency_familiarity(
    project_subagency,
    supplier_subagencies_worked_with,
    project_agency=None,
    supplier_agencies_worked_with=None,
) -> float | None:
    """
    Score agency familiarity at the subagency level first, with a top-tier fallback.
    """
    supplier_subagencies = {value.casefold() for value in _coerce_list(supplier_subagencies_worked_with)}
    supplier_agencies = {value.casefold() for value in _coerce_list(supplier_agencies_worked_with)}

    if project_subagency and supplier_subagencies:
        return 1.0 if str(project_subagency).strip().casefold() in supplier_subagencies else 0.0

    if project_agency and supplier_agencies:
        return 1.0 if str(project_agency).strip().casefold() in supplier_agencies else 0.0

    return None
