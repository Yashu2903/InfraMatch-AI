import hashlib
import json
import time
from datetime import date
from pathlib import Path
from typing import Iterable

import requests
from requests import HTTPError
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


BASE_URL = "https://api.usaspending.gov/api/v2/search/spending_by_transaction/"


DEFAULT_FIELDS = [
    "Award ID",
    "Recipient Name",
    "Recipient UEI",
    "Action Date",
    "Transaction Amount",
    "Awarding Agency",
    "Awarding Sub Agency",
    "Recipient Location",
    "Primary Place of Performance",
    "NAICS Code",
    "NAICS Description",
    "PSC Code",
    "PSC Description",
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


def _supports_api_naics_filter(naics_prefixes: list[str]) -> bool:
    return all(len(str(code).strip()) in {2, 4, 6} for code in naics_prefixes)


def _format_api_naics_filter(naics_prefixes: list[str] | None) -> list[str] | None:
    if not naics_prefixes:
        return None

    if _supports_api_naics_filter(naics_prefixes):
        return [str(code).strip() for code in naics_prefixes if str(code).strip()]

    coarse_prefixes = []

    for prefix in naics_prefixes:
        cleaned = str(prefix).strip()

        if len(cleaned) >= 2:
            coarse_prefix = cleaned[:2]

            if coarse_prefix not in coarse_prefixes:
                coarse_prefixes.append(coarse_prefix)

    return coarse_prefixes or None


def _matches_naics_prefixes(row: dict, naics_prefixes: list[str]) -> bool:
    if not naics_prefixes:
        return True

    naics_code = str(
        row.get("NAICS Code")
        or row.get("naics_code")
        or ""
    ).strip()

    return any(naics_code.startswith(prefix) for prefix in naics_prefixes)


def _needs_client_side_naics_filter(
    requested_naics_prefixes: list[str], api_naics_prefixes: list[str] | None
) -> bool:
    return bool(requested_naics_prefixes) and requested_naics_prefixes != (api_naics_prefixes or [])


def _legacy_cache_dir(cache_dir: Path) -> Path | None:
    candidates = [
        path
        for path in cache_dir.iterdir()
        if path.is_dir() and (path / "page_1.json").exists()
    ]

    if len(candidates) == 1:
        return candidates[0]

    return None


def _first_present(row: dict, *keys: str):
    for key in keys:
        value = row.get(key)

        if value is not None and value != "":
            return value

    return None


def _coerce_amount(value) -> float:
    if value is None or value == "":
        return 0.0

    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


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
    Build USAspending transaction-search payload for the bounded infrastructure slice.
    """
    filters = {
        "time_period": [
            {
                "start_date": start_date,
                "end_date": end_date,
                "date_type": "new_awards_only",
            }
        ],
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

    if psc_codes:
        filters["psc_codes"] = {
            "require": [str(code).strip() for code in psc_codes if str(code).strip()],
        }

    if agency_names:
        filters["agencies"] = [
            {
                "type": "awarding",
                "tier": "toptier",
                "name": agency_name,
            }
            for agency_name in agency_names
            if str(agency_name).strip()
        ]

    if naics_prefixes:
        filters["naics_codes"] = {
            "require": naics_prefixes,
        }

    return {
        "filters": filters,
        "fields": DEFAULT_FIELDS,
        "page": page,
        "limit": limit,
        "sort": "Transaction Amount",
        "order": "desc",
    }


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
    Fetch paginated USAspending transaction records with cache reuse.
    """
    states = states or ["NJ", "NY", "PA"]
    psc_codes = psc_codes or []
    agency_names = agency_names or []
    end_date = end_date or date.today().isoformat()

    requested_naics_prefixes = naics_prefixes or []
    api_naics_prefixes = _format_api_naics_filter(requested_naics_prefixes)
    needs_client_side_naics_filter = _needs_client_side_naics_filter(
        requested_naics_prefixes,
        api_naics_prefixes,
    )

    cache_root = Path(cache_dir)
    cache_root.mkdir(parents=True, exist_ok=True)

    cache_key_payload = {
        "states": states,
        "naics_prefixes": requested_naics_prefixes,
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
    request_cache_dir = cache_root / cache_key
    legacy_cache_dir = _legacy_cache_dir(cache_root)

    if request_cache_dir.exists():
        active_cache_dir = request_cache_dir
    elif legacy_cache_dir is not None:
        active_cache_dir = legacy_cache_dir
    else:
        request_cache_dir.mkdir(parents=True, exist_ok=True)
        active_cache_dir = request_cache_dir

    session = _build_session()
    page = 1

    while True:
        if max_pages is not None and page > max_pages:
            break

        cache_path = active_cache_dir / f"page_{page}.json"

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
            request_cache_dir.mkdir(parents=True, exist_ok=True)

            with (request_cache_dir / f"page_{page}.json").open("w", encoding="utf-8") as f:
                json.dump(response_json, f, indent=2)

            active_cache_dir = request_cache_dir
            time.sleep(sleep_seconds)

        results = response_json.get("results", [])

        if not results:
            break

        for row in results:
            if needs_client_side_naics_filter and not _matches_naics_prefixes(
                row,
                requested_naics_prefixes,
            ):
                continue

            yield row

        page_metadata = response_json.get("page_metadata", {})
        has_next_page = page_metadata.get("hasNext") or page_metadata.get("has_next_page")

        if not has_next_page:
            break

        page += 1


def collapse_transactions_to_awards(rows: list[dict]) -> list[dict]:
    """
    Collapse transaction-level rows into one row per award.
    """
    awards: dict[str, dict] = {}

    for row in rows:
        award_id = _first_present(row, "Award ID")

        if award_id is None:
            continue

        award_id = str(award_id).strip()

        if not award_id:
            continue

        award = awards.setdefault(
            award_id,
            {
                "Award ID": award_id,
                "Recipient Name": _first_present(row, "Recipient Name"),
                "Recipient UEI": _first_present(row, "Recipient UEI"),
                "Award Amount": 0.0,
                "Start Date": None,
                "End Date": _first_present(row, "End Date"),
                "Awarding Agency": _first_present(row, "Awarding Agency"),
                "Awarding Sub Agency": _first_present(row, "Awarding Sub Agency"),
                "NAICS Code": _first_present(row, "NAICS Code", "naics_code"),
                "NAICS Description": _first_present(
                    row,
                    "NAICS Description",
                    "naics_description",
                ),
                "PSC Code": _first_present(row, "PSC Code", "product_or_service_code"),
                "PSC Description": _first_present(
                    row,
                    "PSC Description",
                    "product_or_service_description",
                ),
                "Recipient Location": _first_present(row, "Recipient Location"),
                "Primary Place of Performance": _first_present(
                    row,
                    "Primary Place of Performance",
                ),
                "internal_id": _first_present(row, "internal_id"),
            },
        )

        award["Award Amount"] += _coerce_amount(
            _first_present(row, "Transaction Amount", "Award Amount")
        )

        action_date = _first_present(row, "Action Date", "Start Date")

        if action_date and (
            award["Start Date"] is None or str(action_date) > str(award["Start Date"])
        ):
            award["Start Date"] = action_date

        for target_key, source_keys in [
            ("Recipient Name", ("Recipient Name",)),
            ("Recipient UEI", ("Recipient UEI",)),
            ("End Date", ("End Date",)),
            ("Awarding Agency", ("Awarding Agency",)),
            ("Awarding Sub Agency", ("Awarding Sub Agency",)),
            ("NAICS Code", ("NAICS Code", "naics_code")),
            ("NAICS Description", ("NAICS Description", "naics_description")),
            ("PSC Code", ("PSC Code", "product_or_service_code")),
            (
                "PSC Description",
                ("PSC Description", "product_or_service_description"),
            ),
            ("Recipient Location", ("Recipient Location",)),
            ("Primary Place of Performance", ("Primary Place of Performance",)),
            ("internal_id", ("internal_id",)),
        ]:
            if award[target_key] is None or award[target_key] == "":
                replacement = _first_present(row, *source_keys)

                if replacement is not None and replacement != "":
                    award[target_key] = replacement

    return list(awards.values())


def fetch_awards(
    states: list[str] | None = None,
    naics_prefixes: list[str] | None = None,
    start_date: str = "2020-01-01",
    end_date: str | None = None,
    min_amount: float = 25_000,
    cache_dir: str | Path = "data/raw/usaspending_transactions",
    limit: int = 100,
    max_pages: int | None = None,
    sleep_seconds: float = 0.2,
) -> Iterable[dict]:
    """
    Backward-compatible alias retained for older callers.
    """
    yield from fetch_award_transactions(
        states=states,
        naics_prefixes=naics_prefixes,
        start_date=start_date,
        end_date=end_date,
        min_amount=min_amount,
        cache_dir=cache_dir,
        limit=limit,
        max_pages=max_pages,
        sleep_seconds=sleep_seconds,
    )
