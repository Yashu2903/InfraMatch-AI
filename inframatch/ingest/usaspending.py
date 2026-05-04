from concurrent.futures import ThreadPoolExecutor, as_completed
import hashlib
import json
import threading
import time
from datetime import date
from pathlib import Path
from typing import Iterable

import requests
from requests import HTTPError
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


BASE_URL = "https://api.usaspending.gov/api/v2/search/spending_by_award/"
TRANSACTION_SEARCH_URL = "https://api.usaspending.gov/api/v2/search/spending_by_transaction/"
AWARD_DETAILS_URL = "https://api.usaspending.gov/api/v2/awards/{award_id}/"
_THREAD_LOCAL = threading.local()


DEFAULT_FIELDS = [
    "Award ID",
    "Recipient Name",
    "Recipient UEI",
    "Award Amount",
    "Start Date",
    "End Date",
    "Awarding Agency",
    "Awarding Sub Agency",
    "NAICS Code",
    "NAICS Description",
    "Recipient Location",
]

TRANSACTION_FIELDS = [
    "internal_id",
    "Award ID",
    "Recipient Name",
    "Recipient UEI",
    "Action Date",
    "Awarding Agency",
    "Awarding Sub Agency",
    "Transaction Amount",
    "product_or_service_code",
    "product_or_service_description",
    "naics_code",
    "naics_description",
    "Primary Place of Performance",
    "Recipient Location",
]


def _build_session() -> requests.Session:
    retry = Retry(
        total=5,
        connect=5,
        read=5,
        backoff_factor=1.0,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=frozenset(["GET", "POST"]),
        raise_on_status=False,
    )
    adapter = HTTPAdapter(max_retries=retry)
    session = requests.Session()
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    return session


def _get_thread_session() -> requests.Session:
    session = getattr(_THREAD_LOCAL, "session", None)

    if session is None:
        session = _build_session()
        _THREAD_LOCAL.session = session

    return session


def _supports_api_naics_filter(naics_prefixes: list[str]) -> bool:
    return all(len(str(code).strip()) in {2, 4, 6} for code in naics_prefixes)


def _format_api_naics_filter(naics_prefixes: list[str] | None) -> list[str] | None:
    if not naics_prefixes:
        return None

    if _supports_api_naics_filter(naics_prefixes):
        return [str(code).strip() for code in naics_prefixes if str(code).strip()]

    coarse_prefixes = _coarse_api_naics_prefixes(naics_prefixes)

    if not coarse_prefixes:
        return None

    return coarse_prefixes


def _coarse_api_naics_prefixes(naics_prefixes: list[str]) -> list[str] | None:
    if not naics_prefixes:
        return None

    if _supports_api_naics_filter(naics_prefixes):
        return naics_prefixes

    coarse_prefixes = []

    for prefix in naics_prefixes:
        cleaned = str(prefix).strip()

        if len(cleaned) >= 2:
            coarse_prefix = cleaned[:2]

            if coarse_prefix not in coarse_prefixes:
                coarse_prefixes.append(coarse_prefix)

    return coarse_prefixes or None


def _fetch_award_details(award_id: int | str, cache_dir: Path) -> dict:
    cache_path = cache_dir / f"{award_id}.json"

    if cache_path.exists():
        with cache_path.open("r", encoding="utf-8") as f:
            return json.load(f)

    session = _get_thread_session()
    response = session.get(AWARD_DETAILS_URL.format(award_id=award_id), timeout=60)

    try:
        response.raise_for_status()
    except HTTPError as exc:
        response_text = response.text.strip()
        raise HTTPError(
            f"{exc}. Response body: {response_text}",
            response=response,
            request=response.request,
        ) from exc

    response_json = response.json()

    with cache_path.open("w", encoding="utf-8") as f:
        json.dump(response_json, f, indent=2)

    return response_json


def _extract_naics_from_award_details(award_details: dict) -> tuple[str | None, str | None]:
    latest_transaction_contract_data = award_details.get("latest_transaction_contract_data") or {}
    naics_code = latest_transaction_contract_data.get("naics")
    naics_description = latest_transaction_contract_data.get("naics_description")

    if naics_code is not None:
        naics_code = str(naics_code).strip() or None

    if naics_description is not None:
        naics_description = str(naics_description).strip() or None

    return naics_code, naics_description


def _matches_naics_prefixes(row: dict, naics_prefixes: list[str]) -> bool:
    if not naics_prefixes:
        return True

    naics_code = str(row.get("NAICS Code") or "").strip()

    return any(naics_code.startswith(prefix) for prefix in naics_prefixes)


def _needs_client_side_naics_filter(
    requested_naics_prefixes: list[str], api_naics_prefixes: list[str] | None
) -> bool:
    return bool(requested_naics_prefixes) and requested_naics_prefixes != (api_naics_prefixes or [])


def _build_agency_filters(agency_names: list[str] | None) -> list[dict] | None:
    if not agency_names:
        return None

    return [
        {
            "type": "awarding",
            "tier": "toptier",
            "toptier_name": agency_name,
            "name": agency_name,
        }
        for agency_name in agency_names
    ]


def build_filter_payload(
    states: list[str],
    naics_prefixes: list[str] | None,
    psc_codes: list[str] | None,
    agency_names: list[str] | None,
    start_date: str,
    end_date: str,
    min_amount: float,
    page: int,
    limit: int = 100,
) -> dict:
    """
    Build USAspending Advanced Search payload.

    Phase 1 bounded slice:
    - states: Northeast corridor place-of-performance states
    - civilian top-tier agencies relevant to infrastructure work
    - infrastructure-oriented PSC codes
    - optional NAICS backstop
    - award types: C, D
    - min amount: 25,000
    """
    filters = {
        "time_period": [
            {
                "start_date": start_date,
                "end_date": end_date,
                "date_type": "new_awards_only",
            }
        ],
        "place_of_performance_scope": "domestic",
        "place_of_performance_locations": [
            {
                "country": "USA",
                "state": state,
            }
            for state in states
        ],
        "award_type_codes": ["C", "D"],
        "award_amounts": [
            {
                "lower_bound": min_amount,
            }
        ],
    }

    if naics_prefixes:
        filters["naics_codes"] = {
            "require": naics_prefixes,
        }

    if psc_codes:
        filters["psc_codes"] = psc_codes

    agencies = _build_agency_filters(agency_names)

    if agencies:
        filters["agencies"] = agencies

    return {
        "filters": {
            **filters,
        },
        "fields": DEFAULT_FIELDS,
        "page": page,
        "limit": limit,
        "sort": "Award Amount",
        "order": "desc",
        "subawards": False,
    }


def fetch_awards(
    states: list[str] | None = None,
    naics_prefixes: list[str] | None = None,
    psc_codes: list[str] | None = None,
    agency_names: list[str] | None = None,
    start_date: str = "2020-01-01",
    end_date: str | None = None,
    min_amount: float = 25_000,
    cache_dir: str | Path = "data/raw/usaspending",
    limit: int = 100,
    max_pages: int | None = None,
    sleep_seconds: float = 0.2,
) -> Iterable[dict]:
    """
    Fetch paginated USAspending award records.

    Caches each page locally so reruns are resumable and the demo can work offline.
    """
    states = states or ["NJ", "NY", "PA"]
    naics_prefixes = naics_prefixes or ["541", "237"]
    end_date = end_date or date.today().isoformat()
    api_naics_prefixes = _format_api_naics_filter(naics_prefixes)
    needs_client_side_naics_filter = _needs_client_side_naics_filter(
        naics_prefixes, api_naics_prefixes
    )

    cache_dir = Path(cache_dir)
    cache_key_payload = {
        "states": states,
        "naics_prefixes": naics_prefixes,
        "psc_codes": psc_codes,
        "agency_names": agency_names,
        "start_date": start_date,
        "end_date": end_date,
        "min_amount": min_amount,
        "limit": limit,
        "api_naics_prefixes": api_naics_prefixes,
    }
    cache_key = hashlib.sha1(
        json.dumps(cache_key_payload, sort_keys=True).encode("utf-8")
    ).hexdigest()[:12]
    cache_dir = cache_dir / cache_key
    cache_dir.mkdir(parents=True, exist_ok=True)
    session = _build_session()

    page = 1

    while True:
        if max_pages is not None and page > max_pages:
            break

        cache_path = cache_dir / f"page_{page}.json"

        if cache_path.exists():
            with cache_path.open("r", encoding="utf-8") as f:
                response_json = json.load(f)
        else:
            payload = build_filter_payload(
                states=states,
                naics_prefixes=api_naics_prefixes,
                psc_codes=psc_codes,
                agency_names=agency_names,
                start_date=start_date,
                end_date=end_date,
                min_amount=min_amount,
                page=page,
                limit=limit,
            )

            response = session.post(BASE_URL, json=payload, timeout=60)

            try:
                response.raise_for_status()
            except HTTPError as exc:
                response_text = response.text.strip()
                raise HTTPError(
                    f"{exc}. Response body: {response_text}",
                    response=response,
                    request=response.request,
                ) from exc

            response_json = response.json()

            with cache_path.open("w", encoding="utf-8") as f:
                json.dump(response_json, f, indent=2)

            time.sleep(sleep_seconds)

        results = response_json.get("results", [])

        if not results:
            break

        for row in results:
            if needs_client_side_naics_filter and not _matches_naics_prefixes(row, naics_prefixes):
                continue

            yield row

        page_metadata = response_json.get("page_metadata", {})
        has_next_page = page_metadata.get("hasNext") or page_metadata.get("has_next_page")

        if not has_next_page:
            break

        page += 1


def fetch_award_transactions(
    states: list[str] | None = None,
    naics_prefixes: list[str] | None = None,
    psc_codes: list[str] | None = None,
    agency_names: list[str] | None = None,
    start_date: str = "2020-01-01",
    end_date: str | None = None,
    min_amount: float = 25_000,
    cache_dir: str | Path = "data/raw/usaspending_transactions",
    limit: int = 100,
    max_pages: int | None = None,
    sleep_seconds: float = 0.2,
) -> Iterable[dict]:
    """
    Fetch paginated USAspending transaction records.

    This endpoint returns populated naics_code fields for contract transactions,
    which makes it a better Phase 1 source than spending_by_award for supplier
    feature construction.
    """
    states = states or ["NJ", "NY", "PA"]
    end_date = end_date or date.today().isoformat()
    api_naics_prefixes = _format_api_naics_filter(naics_prefixes)
    needs_client_side_naics_filter = _needs_client_side_naics_filter(
        naics_prefixes, api_naics_prefixes
    )

    cache_dir = Path(cache_dir)
    cache_key_payload = {
        "states": states,
        "naics_prefixes": naics_prefixes,
        "psc_codes": psc_codes,
        "agency_names": agency_names,
        "start_date": start_date,
        "end_date": end_date,
        "min_amount": min_amount,
        "limit": limit,
        "api_naics_prefixes": api_naics_prefixes,
        "endpoint": "transactions",
    }
    cache_key = hashlib.sha1(
        json.dumps(cache_key_payload, sort_keys=True).encode("utf-8")
    ).hexdigest()[:12]
    cache_dir = cache_dir / cache_key
    cache_dir.mkdir(parents=True, exist_ok=True)
    session = _build_session()

    page = 1

    while True:
        if max_pages is not None and page > max_pages:
            break

        cache_path = cache_dir / f"page_{page}.json"

        if cache_path.exists():
            with cache_path.open("r", encoding="utf-8") as f:
                response_json = json.load(f)
        else:
            payload = build_filter_payload(
                states=states,
                naics_prefixes=api_naics_prefixes,
                psc_codes=psc_codes,
                agency_names=agency_names,
                start_date=start_date,
                end_date=end_date,
                min_amount=min_amount,
                page=page,
                limit=limit,
            )
            payload["fields"] = TRANSACTION_FIELDS
            payload["sort"] = "Transaction Amount"

            response = session.post(TRANSACTION_SEARCH_URL, json=payload, timeout=60)

            try:
                response.raise_for_status()
            except HTTPError as exc:
                response_text = response.text.strip()
                raise HTTPError(
                    f"{exc}. Response body: {response_text}",
                    response=response,
                    request=response.request,
                ) from exc

            response_json = response.json()

            with cache_path.open("w", encoding="utf-8") as f:
                json.dump(response_json, f, indent=2)

            time.sleep(sleep_seconds)

        results = response_json.get("results", [])

        if not results:
            break

        for row in results:
            if needs_client_side_naics_filter and not str(row.get("naics_code") or "").startswith(tuple(naics_prefixes)):
                continue

            yield row

        page_metadata = response_json.get("page_metadata", {})
        has_next_page = page_metadata.get("hasNext") or page_metadata.get("has_next_page")

        if not has_next_page:
            break

        page += 1


def collapse_transactions_to_awards(transaction_rows: list[dict]) -> list[dict]:
    """
    Convert transaction-level search results into one row per award.
    """
    awards_by_id = {}

    for row in transaction_rows:
        award_id = row.get("Award ID")

        if not award_id:
            continue

        award = awards_by_id.setdefault(
            award_id,
            {
                "internal_id": row.get("internal_id"),
                "Award ID": award_id,
                "Recipient Name": row.get("Recipient Name"),
                "Recipient UEI": row.get("Recipient UEI"),
                "Award Amount": 0,
                "Start Date": row.get("Action Date"),
                "End Date": None,
                "Awarding Agency": row.get("Awarding Agency"),
                "Awarding Sub Agency": row.get("Awarding Sub Agency"),
                "NAICS Code": row.get("naics_code"),
                "NAICS Description": row.get("naics_description"),
                "PSC Code": row.get("product_or_service_code"),
                "PSC Description": row.get("product_or_service_description"),
                "Primary Place of Performance": row.get("Primary Place of Performance"),
                "Recipient Location": row.get("Recipient Location"),
            },
        )

        transaction_amount = row.get("Transaction Amount") or 0
        award["Award Amount"] += float(transaction_amount)

        action_date = row.get("Action Date")

        if action_date and (not award["Start Date"] or action_date > award["Start Date"]):
            award["Start Date"] = action_date

        if not award.get("Recipient Name") and row.get("Recipient Name"):
            award["Recipient Name"] = row.get("Recipient Name")

        if not award.get("Recipient UEI") and row.get("Recipient UEI"):
            award["Recipient UEI"] = row.get("Recipient UEI")

        if not award.get("Awarding Agency") and row.get("Awarding Agency"):
            award["Awarding Agency"] = row.get("Awarding Agency")

        if not award.get("Awarding Sub Agency") and row.get("Awarding Sub Agency"):
            award["Awarding Sub Agency"] = row.get("Awarding Sub Agency")

        if not award.get("NAICS Code") and row.get("naics_code"):
            award["NAICS Code"] = row.get("naics_code")

        if not award.get("NAICS Description") and row.get("naics_description"):
            award["NAICS Description"] = row.get("naics_description")

        if not award.get("PSC Code") and row.get("product_or_service_code"):
            award["PSC Code"] = row.get("product_or_service_code")

        if not award.get("PSC Description") and row.get("product_or_service_description"):
            award["PSC Description"] = row.get("product_or_service_description")

        if not award.get("Primary Place of Performance") and row.get("Primary Place of Performance"):
            award["Primary Place of Performance"] = row.get("Primary Place of Performance")

        if not award.get("Recipient Location") and row.get("Recipient Location"):
            award["Recipient Location"] = row.get("Recipient Location")

    return list(awards_by_id.values())


def enrich_awards_with_naics(
    rows: list[dict],
    cache_dir: str | Path = "data/raw/usaspending/award_details",
    max_workers: int = 2,
) -> list[dict]:
    """
    Fill in missing NAICS data from the per-award details endpoint.
    """
    cache_dir = Path(cache_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)

    missing_award_ids = sorted(
        {
            row.get("internal_id")
            for row in rows
            if row.get("internal_id") and not row.get("NAICS Code")
        }
    )

    if not missing_award_ids:
        return rows

    naics_by_award_id = {}

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_award_id = {
            executor.submit(_fetch_award_details, award_id, cache_dir): award_id
            for award_id in missing_award_ids
        }

        for future in as_completed(future_to_award_id):
            award_id = future_to_award_id[future]
            try:
                award_details = future.result()
            except Exception:
                continue

            naics_by_award_id[award_id] = _extract_naics_from_award_details(award_details)

    for row in rows:
        award_id = row.get("internal_id")

        if not award_id or row.get("NAICS Code"):
            continue

        naics_code, naics_description = naics_by_award_id.get(award_id, (None, None))

        if naics_code:
            row["NAICS Code"] = naics_code

        if naics_description:
            row["NAICS Description"] = naics_description

    return rows
