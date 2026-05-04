# Phase 2 Explanation

This document explains the Phase 2 code in simple language.

Phase 2 takes the Phase 1 supplier base and turns it into a demo-ready matching
dataset by:

- adding synthetic compliance and risk fields to suppliers
- generating synthetic infrastructure opportunities
- loading both sides into SQLite tables for matching and app use
- keeping the data realistic enough for scoring, filtering, and demo flows


## 1. What Phase 2 Adds

Phase 1 gave us two core assets:

- `data/processed/awards.parquet`
- `data/processed/suppliers.parquet`

Phase 2 builds on top of that and creates:

- `data/processed/suppliers_with_compliance.parquet`
- `data/opportunities.json`
- `inframatch.db`

So the main purpose of Phase 2 is not to fetch more federal data.
It is to make the supplier dataset usable for:

- opportunity-to-supplier matching
- compliance-aware ranking
- application demos
- future UI and API work


## 2. Phase 2 Code Flow

The main Phase 2 flow is:

1. Start with `suppliers.parquet` from Phase 1.
2. Run `scripts/generate_compliance.py`.
3. Create supplier-side synthetic fields such as:
   - `small_business_flag`
   - `local_content_score`
   - `certifications_json`
   - `synthetic_esg_score`
   - `risk_score`
4. Run `scripts/generate_opportunities.py`.
5. Create a small set of synthetic project opportunities with:
   - asset type
   - state and city
   - NAICS and PSC targets
   - budget
   - subagency
   - compliance requirements
6. Run `scripts/load_db.py`.
7. Load suppliers and opportunities into SQLite tables.


## 3. Files Used in Phase 2

### `scripts/generate_compliance.py`

This script enriches Phase 1 suppliers with synthetic compliance-related fields.

Important design choices in this file:

- It uses `SEED = 42` so the output is reproducible.
- It reads `data/processed/suppliers.parquet`.
- It writes `data/processed/suppliers_with_compliance.parquet`.
- It parses JSON string columns from Phase 1 back into Python lists before
  generating new fields.

Main generated fields:

- `small_business_flag`
- `local_content_score`
- `certifications_json`
- `synthetic_esg_score`
- `risk_score`

### `scripts/generate_opportunities.py`

This script creates synthetic opportunities for the matching side.

Important design choices:

- It also uses `SEED = 42` for reproducibility.
- It writes `data/opportunities.json`.
- It keeps opportunities inside the 7-state corridor used in the project:
  `CT`, `DE`, `MA`, `MD`, `NJ`, `NY`, `PA`
- It uses weighted state, city, and subagency selection so the output is not
  uniform random noise.

### `scripts/load_db.py`

This script loads the generated Phase 2 assets into SQLite.

It:

- creates tables using SQLModel metadata
- clears old demo records in dependency-safe order
- loads supplier rows into the `Supplier` table
- loads opportunities into the `Opportunity` table

This is the final step that makes the data usable inside the app.


## 4. Supplier-Side Synthetic Data

The supplier-side overlay is built in `scripts/generate_compliance.py`.
It does not replace Phase 1 procurement history. It adds extra fields on top of
that history.

### 4.1 Small Business Flag

Field:

- `small_business_flag`

How it works:

- The code picks the supplier's primary NAICS code.
- It compares the supplier against an SBA-style revenue threshold map.
- It estimates implied revenue from federal award history.

Important limitation:

- Federal awards are not the same thing as total company revenue.
- The code explicitly treats federal awards as only part of total revenue.
- That means this is a proxy, not a real certification record.

### 4.2 Local Content Score

Field:

- `local_content_score`

How it works:

- Suppliers headquartered in the corridor get a mild advantage.
- Larger firms are slightly penalized because they may rely less on local labor.
- Random noise is added so not every similar supplier gets the exact same score.
- Final values are clipped into a `0-100` range.

This is meant to simulate local staffing or local delivery strength.

### 4.3 Certifications

Field:

- `certifications_json`

Possible certifications include:

- `PE_License`
- `ISO_9001`
- `DBE_Certified`
- `8(a)_Certified`
- `Bridge_Inspection_NHI`
- `OSHA_30`

How it works:

- The code does not assign certifications fully at random.
- It checks NAICS prefixes and, for some credentials, PSC history.
- Example:
  - `Bridge_Inspection_NHI` is only considered if the supplier has bridge-like
    PSC history such as `C1LB`, `Y1LB`, or `Z1LB`
- Small-business related certifications become more likely if
  `small_business_flag` is true.

This makes certifications correlated with supplier history instead of feeling
fake.

### 4.4 ESG Score

Field:

- `synthetic_esg_score`

How it works:

- Starts from a base score.
- Gives a mild uplift to small businesses.
- Gives a mild uplift to firms with `ISO_9001`.
- Adds random variation.
- Clips the result to `0-100`.

This is a synthetic ranking signal, not a third-party ESG measure.

### 4.5 Risk Score

Field:

- `risk_score`

How it works:

- More past awards reduce risk.
- More years since last award increase risk.
- More subagency diversity reduces risk.
- Random variation is added.
- Final values are clipped to `0-100`.

This gives the project a usable demo signal for supplier stability and recency.


## 5. Opportunity-Side Synthetic Data

The opportunity generator creates synthetic projects in
`scripts/generate_opportunities.py`.

Each opportunity includes:

- `title`
- `asset_type`
- `state`
- `city`
- `naics_code`
- `psc_code`
- `awarding_agency`
- `awarding_subagency`
- `budget`
- `required_local_content`
- `requires_small_business`
- `required_certifications`
- `risk_tolerance`

### 5.1 Asset Types

The current generator uses these asset families:

- `bridge_deck`
- `retaining_wall`
- `culvert`
- `pavement`
- `facade`

Each asset type is mapped to:

- likely NAICS codes
- likely PSC codes
- a realistic budget band

That keeps the opportunity side aligned with the supplier-side federal history.

### 5.2 Budgets

Budgets are generated with a log-uniform distribution.

Why that matters:

- infrastructure projects are not evenly distributed by dollar value
- a log-like spread creates many smaller jobs and fewer larger jobs
- this feels more realistic than flat random numbers

### 5.3 Compliance Requirements

Each opportunity also carries synthetic requirements such as:

- minimum local content
- whether small business status is required
- required certifications

The logic is budget-sensitive:

- smaller opportunities are much more likely to require small business
- larger opportunities are less likely to require it

That gives the matching system something concrete to compare against supplier
compliance fields.


## 6. Database Layer

Phase 2 also introduces the app-facing data model in
`inframatch/db/models.py`.

Main tables:

- `Supplier`
- `Opportunity`
- `Match`
- `Inspection`
- `DefectResult`

### `Supplier`

This table stores:

- supplier identity
- award history aggregates
- NAICS, PSC, agency, and subagency history as JSON text
- synthetic compliance and risk fields

### `Opportunity`

This table stores:

- project identity
- geography
- NAICS and PSC target
- agency and subagency
- budget and compliance requirements

### `Match`

This table is prepared for future or external ranking output.
It stores:

- `final_score`
- `rank`
- `score_breakdown_json`
- `top_factors_json`
- `concerns_json`
- `compliance_outcomes_json`

### `Inspection` and `DefectResult`

These support later inspection and computer vision workflows.
They are not the main focus of Phase 2 matching, but the schema is already in
place for the next stage of the product.


## 7. Matching Support Code

The file `inframatch/matching/scoring.py` contains early matching utilities.

### `naics_similarity(...)`

This checks whether supplier NAICS codes overlap with project NAICS prefixes.

Important detail:

- if supplier NAICS data is missing, it returns `None`
- it does not force missing data to look like a bad supplier

That is important because:

- missing signal and zero match are not the same thing

### `agency_familiarity(...)`

This checks whether a supplier has worked with:

- the exact subagency first
- then the top-tier agency as a fallback

That matters because:

- familiarity with the Federal Highway Administration is more specific than
  familiarity with the Department of Transportation in general


## 8. What the Data Contains Right Now

The current generated artifacts in this repo contain:

- `data/processed/awards.parquet`: `1,246` award rows
- `data/processed/suppliers_with_compliance.parquet`: `333` supplier rows
- `data/opportunities.json`: `15` synthetic opportunities

### 8.1 `awards.parquet`

This is still the main historical procurement base from Phase 1.

Important columns include:

- `award_id`
- `recipient_name`
- `recipient_uei`
- `award_amount`
- `start_date`
- `end_date`
- `awarding_agency`
- `awarding_subagency`
- `naics_code`
- `naics_description`
- `psc_code`
- `psc_description`
- `recipient_state`
- `place_of_performance_state`
- `canonical_supplier_id`

This file contains real historical award-derived data, not synthetic rows.

### 8.2 `suppliers_with_compliance.parquet`

This is the main Phase 2 supplier file.

It contains all the Phase 1 supplier aggregates plus the new synthetic overlay:

- `canonical_supplier_id`
- `canonical_name`
- `uei`
- `state`
- `past_awards_count`
- `total_award_value`
- `avg_award_value`
- `last_award_date`
- `naics_codes`
- `psc_codes`
- `agencies_worked_with`
- `subagencies_worked_with`
- `small_business_flag`
- `local_content_score`
- `synthetic_esg_score`
- `risk_score`
- `certifications_json`

Current characteristics of this file:

- supplier headquarters span many states, not just the corridor
- the top supplier headquarters states are currently `NY`, `PA`, `MD`, `VA`,
  `MA`, and `NJ`
- `small_business_flag` is true for most current rows because it is driven by a
  revenue proxy based on federal award history

### 8.3 `opportunities.json`

This is the synthetic project-side dataset used for demo matching.

Each row contains:

- project title
- asset type
- location
- NAICS and PSC target
- awarding agency and subagency
- budget
- compliance requirements
- risk tolerance

Current characteristics of this file:

- all opportunities stay inside the corridor
- the current sample includes `CT`, `DE`, `MD`, `NJ`, `NY`, and `PA`
- common subagencies in the current sample include:
  - `Federal Highway Administration`
  - `Public Buildings Service`
  - `Federal Railroad Administration`
  - `National Park Service`


## 9. Main Issues We Faced While Building Phase 2

These were the main implementation problems Phase 2 had to solve.

### Issue 1: There was no real compliance dataset attached to suppliers

Problem:

- Phase 1 had real procurement history, but not real fields like
  local-content capability, ESG score, or certification inventory.

What we did:

- built a synthetic overlay instead of inventing fields completely at random
- tied certifications to NAICS and PSC history
- tied risk to recency, award count, and agency diversity
- tied local-content scoring partly to geography and firm size

Why this matters:

- the output is still synthetic, but it is structured enough to support ranking
  logic and demos

### Issue 2: JSON-like fields had to move across parquet, Python, and SQLite

Problem:

- supplier history fields such as NAICS lists and subagency lists are naturally
  list-shaped
- parquet, pandas, and SQLite do not all use the same representation cleanly

What we did:

- Phase 1 stores these fields as JSON text
- Phase 2 parses them back into lists when needed
- `load_db.py` normalizes them again into JSON strings before inserting into
  SQLModel tables

Why this matters:

- without that normalization, scoring and database loading would be brittle

### Issue 3: Synthetic opportunities had to match the supplier universe

Problem:

- if the opportunity generator created arbitrary project types, the supplier
  matching side would become unrealistic

What we did:

- constrained opportunities to asset families related to the supplier base
- mapped asset types to realistic NAICS and PSC combinations
- kept geography inside the corridor
- used real-looking civilian subagencies already present in the procurement
  workflow

Why this matters:

- the generated opportunities are actually matchable against the supplier data

### Issue 4: Missing data had to be handled differently from bad matches

Problem:

- a supplier with missing NAICS or agency history should not automatically look
  like a zero-score supplier

What we did:

- matching helpers return `None` for absent signals
- actual mismatches return `0.0`

Why this matters:

- this keeps future ranking logic more honest and easier to debug

### Issue 5: Randomness had to stay reproducible

Problem:

- synthetic demos are hard to debug if every run changes the data completely

What we did:

- fixed the random seed in both generation scripts

Why this matters:

- the team can rerun Phase 2 and get stable results during development

### Issue 6: Synthetic data still needed validation

Problem:

- synthetic data can look fine at a glance but still violate basic logic

What we did:

- added `scripts/validate_synthetic.py`
- added tests for feature building, payload construction, and scoring behavior
- checked range constraints, PSC population, subagency population, corridor
  boundaries, small-business logic, and bridge-certification correlation

Why this matters:

- it reduces the chance of demo data drifting into nonsense


## 10. Known Limitations

Phase 2 is useful, but it is still a synthetic layer on top of real award
history.

Important limitations:

- `small_business_flag` is a proxy, not a verified SBA status
- `synthetic_esg_score` is synthetic and should not be treated as external ESG
  truth
- certifications are probabilistic, even though they are constrained by domain
  logic
- risk scoring depends partly on synthetic assumptions and the current date
- opportunity volume is intentionally small because this is a demo dataset, not
  a production marketplace inventory


## 11. Validation Status

The current automated tests in this repo pass:

- `6 passed`

The tests and validation currently cover:

- USAspending filter payload behavior
- award transaction collapsing
- supplier feature aggregation
- NAICS similarity behavior
- agency familiarity behavior
- synthetic data sanity checks


## 12. Simple Summary

In simple terms, Phase 2 does three things:

1. It turns Phase 1 suppliers into matchable suppliers with compliance-style
   fields.
2. It creates a realistic set of synthetic infrastructure opportunities.
3. It loads both sides into a database structure that the application can use
   for ranking, matching, and later inspection workflows.

That is why Phase 2 is the bridge between raw procurement history and the
product-facing matching system.
