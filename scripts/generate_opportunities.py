import json
import math
import random
from pathlib import Path


SEED = 42
random.seed(SEED)

OUTPUT_PATH = Path("data/opportunities.json")

STATE_WEIGHTS = {
    "NY": 0.25,
    "PA": 0.25,
    "NJ": 0.20,
    "MD": 0.12,
    "MA": 0.10,
    "CT": 0.05,
    "DE": 0.03,
}

STATE_CITIES = {
    "NY": {
        "New York": 0.30,
        "Buffalo": 0.15,
        "Rochester": 0.12,
        "Syracuse": 0.10,
        "Albany": 0.10,
        "Yonkers": 0.08,
        "White Plains": 0.05,
        "Poughkeepsie": 0.05,
        "Binghamton": 0.05,
    },
    "PA": {
        "Philadelphia": 0.30,
        "Pittsburgh": 0.20,
        "Allentown": 0.10,
        "Erie": 0.08,
        "Reading": 0.08,
        "Scranton": 0.07,
        "Harrisburg": 0.07,
        "Lancaster": 0.05,
        "Bethlehem": 0.05,
    },
    "NJ": {
        "Newark": 0.20,
        "Jersey City": 0.15,
        "Paterson": 0.10,
        "Trenton": 0.10,
        "Elizabeth": 0.10,
        "Camden": 0.10,
        "Edison": 0.08,
        "Atlantic City": 0.07,
        "Hoboken": 0.05,
        "Princeton": 0.05,
    },
    "MD": {
        "Baltimore": 0.30,
        "Annapolis": 0.10,
        "Frederick": 0.10,
        "Rockville": 0.10,
        "Silver Spring": 0.10,
        "Gaithersburg": 0.08,
        "Hagerstown": 0.07,
        "College Park": 0.05,
        "Bowie": 0.05,
        "Laurel": 0.05,
    },
    "MA": {
        "Boston": 0.35,
        "Worcester": 0.15,
        "Springfield": 0.12,
        "Cambridge": 0.10,
        "Lowell": 0.08,
        "New Bedford": 0.07,
        "Quincy": 0.05,
        "Somerville": 0.04,
        "Newton": 0.04,
    },
    "CT": {
        "Hartford": 0.30,
        "New Haven": 0.20,
        "Bridgeport": 0.18,
        "Stamford": 0.12,
        "Waterbury": 0.08,
        "Norwalk": 0.06,
        "Danbury": 0.06,
    },
    "DE": {
        "Wilmington": 0.50,
        "Dover": 0.30,
        "Newark DE": 0.15,
        "Middletown": 0.05,
    },
}

ASSET_NAICS = {
    "bridge_deck": ["541330", "541350"],
    "retaining_wall": ["541330", "237310"],
    "culvert": ["237310", "541350"],
    "pavement": ["237310", "541330"],
    "facade": ["541330", "541310"],
}

ASSET_PSC = {
    "bridge_deck": ["C1LB", "C211", "Z1LB"],
    "retaining_wall": ["C211", "C219", "Z1LB"],
    "culvert": ["Z1LB", "C211"],
    "pavement": ["Z1LB", "Y1LB", "C211"],
    "facade": ["C211", "C219"],
}

ASSET_BUDGET_RANGES = {
    "bridge_deck": (150_000, 1_500_000),
    "retaining_wall": (40_000, 250_000),
    "culvert": (25_000, 120_000),
    "pavement": (60_000, 400_000),
    "facade": (80_000, 500_000),
}

SUBAGENCY_WEIGHTS = {
    "Federal Highway Administration": 0.35,
    "Public Buildings Service": 0.25,
    "Federal Transit Administration": 0.10,
    "Veterans Health Administration": 0.10,
    "FEMA": 0.05,
    "Federal Railroad Administration": 0.05,
    "National Park Service": 0.05,
    "Bureau of Reclamation": 0.03,
    "Other": 0.02,
}

SUBAGENCY_TO_AGENCY = {
    "Federal Highway Administration": "Department of Transportation",
    "Federal Transit Administration": "Department of Transportation",
    "Federal Railroad Administration": "Department of Transportation",
    "Public Buildings Service": "General Services Administration",
    "Veterans Health Administration": "Department of Veterans Affairs",
    "FEMA": "Department of Homeland Security",
    "National Park Service": "Department of the Interior",
    "Bureau of Reclamation": "Department of the Interior",
    "Other": "Other",
}

ASSET_TITLE_LABELS = {
    "bridge_deck": "Bridge Deck Inspection",
    "retaining_wall": "Retaining Wall Condition Assessment",
    "culvert": "Culvert Inspection and Repair",
    "pavement": "Pavement Rehabilitation Assessment",
    "facade": "Facade Structural Inspection",
}

RISK_TOLERANCES = ["low", "medium", "high"]


def weighted_choice(weight_dict):
    items = list(weight_dict.keys())
    weights = list(weight_dict.values())
    return random.choices(items, weights=weights, k=1)[0]


def log_uniform(low, high):
    return math.exp(random.uniform(math.log(low), math.log(high)))


def compliance_from_budget(budget):
    if budget < 250_000:
        requires_small_business = random.random() < 0.70
        required_local_content = random.uniform(40, 80)
    elif budget < 1_000_000:
        requires_small_business = random.random() < 0.30
        required_local_content = random.uniform(20, 60)
    else:
        requires_small_business = random.random() < 0.05
        required_local_content = random.uniform(0, 40)

    return requires_small_business, round(required_local_content, 2)


def required_certifications(asset_type, naics_code, psc_code):
    certs = []

    if naics_code.startswith("541"):
        certs.append("PE_License")

    if naics_code.startswith("237"):
        certs.append("OSHA_30")

    if asset_type == "bridge_deck" or psc_code in {"C1LB", "Y1LB", "Z1LB"}:
        certs.append("Bridge_Inspection_NHI")

    if random.random() < 0.35:
        certs.append("ISO_9001")

    return sorted(set(certs))


def generate_opportunity(index):
    state = weighted_choice(STATE_WEIGHTS)
    city = weighted_choice(STATE_CITIES[state])

    asset_type = random.choice(list(ASSET_NAICS.keys()))
    naics_code = random.choice(ASSET_NAICS[asset_type])
    psc_code = random.choice(ASSET_PSC[asset_type])

    low, high = ASSET_BUDGET_RANGES[asset_type]
    budget = round(log_uniform(low, high), 2)

    requires_small_business, required_local_content = compliance_from_budget(budget)

    awarding_subagency = weighted_choice(SUBAGENCY_WEIGHTS)
    awarding_agency = SUBAGENCY_TO_AGENCY[awarding_subagency]

    certs = required_certifications(asset_type, naics_code, psc_code)

    title = f"{city} {ASSET_TITLE_LABELS[asset_type]}"

    return {
        "title": title,
        "asset_type": asset_type,
        "state": state,
        "city": city,
        "naics_code": naics_code,
        "psc_code": psc_code,
        "awarding_agency": awarding_agency,
        "awarding_subagency": awarding_subagency,
        "budget": budget,
        "required_local_content": required_local_content,
        "requires_small_business": requires_small_business,
        "required_certifications": certs,
        "risk_tolerance": random.choice(RISK_TOLERANCES),
    }


def main():
    opportunities = [generate_opportunity(i) for i in range(15)]

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)

    with OUTPUT_PATH.open("w", encoding="utf-8") as f:
        json.dump(opportunities, f, indent=2)

    print(f"Saved {len(opportunities)} opportunities to {OUTPUT_PATH}")

    print("\nGenerated opportunities:")
    for i, opp in enumerate(opportunities, start=1):
        print(
            f"{i}. {opp['title']} | {opp['state']} | "
            f"NAICS {opp['naics_code']} | PSC {opp['psc_code']} | "
            f"{opp['awarding_subagency']} | ${opp['budget']:,.0f}"
        )


if __name__ == "__main__":
    main()