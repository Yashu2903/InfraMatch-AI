# Phase 1 Explanation

This document explains the Phase 1 code in simple language.

The goal of Phase 1 is:

- pull real procurement data from USAspending
- keep only infrastructure-relevant contracts
- clean and normalize the data
- deduplicate suppliers
- save two datasets:
  - `data/processed/awards.parquet`
  - `data/processed/suppliers.parquet`


## 0. What Is the Data Source

The main data source for Phase 1 is:

- USAspending.gov

The pipeline now uses this API endpoint:

- `https://api.usaspending.gov/api/v2/search/spending_by_transaction/`

### Why this endpoint is used

We tried more than one USAspending path.

The award-search endpoint looked useful at first, but many rows came back with:

- missing `NAICS Code`
- missing `NAICS Description`

That made the data unreliable for supplier matching.

The transaction-search endpoint worked better because it returned the fields we
needed for Phase 1, including:

- `naics_code`
- `naics_description`
- `product_or_service_code`
- `product_or_service_description`
- awarding agency
- awarding subagency
- place of performance

So the final approach is:

1. pull transaction-level records
2. collapse them into one row per award


## 0.1 What Are Infrastructure-Relevant Contracts in This Project

In this project, infrastructure-relevant contracts mean contracts tied to civil
infrastructure work, not just any engineering work.

That includes work related to:

- highways
- roads
- bridges
- rail corridor work
- dams
- dredging
- sewage and waste facilities
- water supply facilities
- inspection and quality-control work tied to construction
- land surveys
- architect-engineer work that supports infrastructure delivery

### Why this definition matters

A contract can be "engineering" without being useful for InfraMatch.

For example:

- missile engineering
- defense systems integration
- general technical support

Those are engineering-adjacent, but they are not the kind of suppliers we want
for bridge, roadway, water, and inspection matching.

That is why PSC is the main signal in this phase.

### The PSC codes we use now

The current Phase 1 query focuses on PSC codes such as:

- `Y1LB`
  - construction of highways, roads, streets, bridges, and railways
- `Z1LB`
  - maintenance of highways, roads, streets, bridges, and railways
- `Z2LB`
  - repair or alteration of highways, roads, streets, bridges, and railways
- `C1LB`
  - architect-engineering for highways, roads, streets, bridges, and railways
- `Y1KA`
  - construction of dams
- `C1KA`
  - architect-engineering for dams
- `C1KF`
  - architect-engineering for dredging facilities
- `C1ND`
  - architect-engineering for sewage and waste facilities
- `C1NE`
  - architect-engineering for water supply facilities
- `H156`
  - quality control for construction and building materials
- `H356`
  - inspection for construction and building materials
- `C213`
  - general engineering inspection
- `R404`
  - land surveys

We also kept two broader A&E codes to keep the dataset large enough:

- `C211`
- `C219`

These are broader than ideal, but still much cleaner than reopening the door to
generic engineering-service noise.


## 0.2 What Do We Have in `awards.parquet` and `suppliers.parquet`

Phase 1 creates two main outputs:

- `data/processed/awards.parquet`
- `data/processed/suppliers.parquet`

They serve different purposes.

### `awards.parquet`

This is the cleaned award-level dataset.

Think of it as:

- one row per award after collapsing transaction history

This file answers questions like:

- what contract was awarded?
- who received it?
- what agency awarded it?
- what type of work was it?
- where was the work performed?

Typical columns include:

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

Example in plain language:

- supplier: `WSP USA SERVICES INC.`
- agency: `Department of Transportation`
- subagency: `Federal Highway Administration`
- NAICS: `237310`
- PSC: `Y1LB`
- place of performance: `NY`

That is a single award row.

### `suppliers.parquet`

This is the supplier-level summary dataset.

Think of it as:

- one row per deduplicated supplier

This file answers questions like:

- how experienced is this supplier?
- how much total work have they done?
- what kinds of contracts have they done before?
- which agencies and subagencies have they worked with?

Typical columns include:

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

Example in plain language:

- supplier: `Johnson, Mirmiran & Thompson, Inc.`
- state: `MD`
- total history: many awards
- PSC history: road/bridge engineering, inspection, surveys
- agency experience: specific civilian departments and subagencies

This is the file that later matching logic will use the most.


## 0.3 Cleaning and Normalizing the Data

Cleaning and normalizing means:

- taking raw API data
- making field names consistent
- removing bad blanks and duplicates
- converting values into a format we can reliably use later

This is a core part of Phase 1.

### What raw data looks like

The API gives fields like:

- `Award ID`
- `Recipient Name`
- `Awarding Agency`
- `Awarding Sub Agency`
- `naics_code`
- `product_or_service_code`
- `Primary Place of Performance`

Some fields use spaces and title case.
Some use snake_case.
Some are nested objects.

That is awkward for downstream code.

### What normalization does

We convert raw values into stable internal keys like:

- `award_id`
- `recipient_name`
- `award_amount`
- `awarding_agency`
- `awarding_subagency`
- `naics_code`
- `psc_code`
- `place_of_performance_state`

### What cleaning does

We also do things like:

- convert amounts into numeric values
- drop rows with missing supplier names
- fill missing award amounts with `0`
- trim whitespace from text
- remove blank codes like `""`
- reduce repeated values into unique lists

### Simple example

Raw values:

```python
{
  "Recipient Name": "  WSP USA SERVICES INC. ",
  "naics_code": "541330",
  "product_or_service_code": "Y1LB"
}
```

After cleaning and normalization:

```python
{
  "recipient_name": "WSP USA SERVICES INC.",
  "naics_code": "541330",
  "psc_code": "Y1LB"
}
```

### Why this matters

If we do not clean and normalize carefully:

- the same supplier can appear in slightly different forms
- numeric calculations become unreliable
- later matching logic becomes harder to explain and debug


## 1. What Phase 1 Produces

At the end of Phase 1 we create two files:

- `awards.parquet`
  - one row per award
  - this is the cleaned procurement history
- `suppliers.parquet`
  - one row per supplier
  - this is the supplier-level summary used later for matching

Example:

- `awards.parquet` might contain one row for a single contract awarded to `WSP USA SERVICES INC.`
- `suppliers.parquet` then combines all WSP award rows into one supplier summary row with:
  - total award value
  - number of past awards
  - NAICS codes seen
  - PSC codes seen
  - agencies and subagencies worked with


## 2. Main Files

The Phase 1 logic is mainly in these files:

- `scripts/build_suppliers.py`
- `inframatch/ingest/usaspending.py`
- `inframatch/ingest/dedup.py`
- `inframatch/ingest/build_features.py`
- `inframatch/matching/scoring.py`


## 3. High-Level Flow

The pipeline works like this:

1. fetch transaction data from USAspending
2. collapse many transaction rows into one award row
3. normalize the fields we care about
4. deduplicate suppliers
5. aggregate supplier-level features
6. save the final parquet files


## 4. `scripts/build_suppliers.py`

This is the main entry point.

When you run:

```powershell
infra\Scripts\python.exe scripts\build_suppliers.py
```

this file controls the whole Phase 1 pipeline.

### What it defines

It defines:

- date window
- allowed states
- allowed top-tier agencies
- allowed PSC codes

These constants are near the top of the file.

### Why this matters

This is where we tell the system:

- only keep work performed in:
  - `NJ`, `NY`, `PA`, `CT`, `MA`, `MD`, `DE`
- only keep awards from civilian agencies like:
  - Department of Transportation
  - General Services Administration
  - Department of the Interior
- only keep infrastructure-like PSC codes such as:
  - `Y1LB`
  - `Z1LB`
  - `Z2LB`
  - `C1LB`
  - `H156`
  - `H356`
  - `C211`
  - `C219`

### What `normalize_award_row()` does

This function takes one raw award row and converts it into the exact structure we want.

For example, if the raw row has:

- `Award ID`
- `Recipient Name`
- `NAICS Code`
- `PSC Code`
- `Primary Place of Performance`

then `normalize_award_row()` turns that into a cleaner Python dictionary with keys like:

- `award_id`
- `recipient_name`
- `naics_code`
- `psc_code`
- `place_of_performance_state`

This is important because the raw API format is awkward and inconsistent for downstream work.

### What `main()` does

`main()` does the full job:

1. calls `fetch_award_transactions(...)`
2. calls `collapse_transactions_to_awards(...)`
3. builds a dataframe
4. removes bad/null rows
5. runs supplier deduplication
6. builds supplier summary features
7. saves both parquet files


## 5. `inframatch/ingest/usaspending.py`

This file handles the USAspending API work.

It is the most important ingestion file.

### `build_filter_payload(...)`

This builds the request body sent to USAspending.

It includes filters like:

- `time_period`
- `place_of_performance_locations`
- `award_type_codes`
- `award_amounts`
- `psc_codes`
- `agencies`
- optional `naics_codes`

Simple example:

If we want only infrastructure work in New York and Pennsylvania from DOT or GSA, this function builds that filter object for the API.

### `fetch_award_transactions(...)`

This fetches pages of transaction data from:

`https://api.usaspending.gov/api/v2/search/spending_by_transaction/`

Why transaction search?

Because this endpoint returned:

- populated `naics_code`
- populated `product_or_service_code`
- place-of-performance data

The older award-search path was not reliable enough for Phase 1.

### Cache behavior

The API responses are cached in:

- `data/raw/usaspending_transactions/...`

This means:

- the first run pulls from the internet
- later runs can reuse saved pages if the query is the same

We hash the query inputs into a cache key so different queries do not mix their results.

### `collapse_transactions_to_awards(...)`

USAspending transaction search gives multiple rows for the same award.

Example:

One award might have:

- modification 1
- modification 2
- modification 3

Each comes back as a separate transaction row.

We do not want three rows in `awards.parquet`.

So this function merges them into one award row by:

- grouping by `Award ID`
- summing `Transaction Amount`
- keeping agency, subagency, NAICS, PSC, and location data
- using the latest `Action Date` as the stored `Start Date`

This is how we turn transaction-level data into award-level data.


## 6. `inframatch/ingest/dedup.py`

This file handles supplier deduplication.

The main idea is:

- if a supplier has a UEI, use that first
- if UEI is missing, fall back to normalized name plus state

### Why dedup is needed

The same supplier can appear with small name differences:

- `WSP USA INC`
- `WSP USA SERVICES INC.`
- `WSP USA SOLUTIONS INC.`

Or:

- `Acme LLC`
- `ACME, LLC`

The dedup step tries to create a stable supplier key so downstream matching is supplier-based, not row-based.

### Key function

`dedupe_awards(...)`

It adds:

- cleaned `recipient_name`
- `canonical_supplier_id`

Example:

- supplier with UEI `ABC123` becomes `uei:ABC123`
- supplier with no UEI but normalized name `ACME ENGINEERING` in `NJ` becomes something like:
  - `name_state:ACME ENGINEERING:NJ`


## 7. `inframatch/ingest/build_features.py`

This file converts award rows into supplier rows.

### What it does

It groups all awards by `canonical_supplier_id` and calculates summary features.

Each supplier gets:

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

### Example

Suppose one supplier has three awards:

- award 1 with PSC `Y1LB`
- award 2 with PSC `Z2LB`
- award 3 with PSC `C1LB`

Then the supplier row stores:

```json
["Y1LB", "Z2LB", "C1LB"]
```

for `psc_codes`.

### Empty-value protection

The helper `_unique_non_empty()` removes:

- nulls
- blank strings
- duplicates

This matters because we do not want output like:

```json
["", "541330", ""]
```

We only want:

```json
["541330"]
```


## 8. `inframatch/matching/scoring.py`

This file is a small scoring scaffold added for Phase 1 cleanup.

It is not a full ranking engine yet, but it contains two useful helpers.

### `naics_similarity(...)`

This compares project NAICS prefixes to a supplier's NAICS codes.

Important behavior:

- if the supplier has no NAICS data, it returns `None`
- it does not return `0.0` for missing data

Why that matters:

- `0.0` means "real mismatch"
- `None` means "data unavailable"

That is a big difference when explaining ranking results later.

Example:

```python
naics_similarity(["5413"], ["541330", "237310"])
```

This gives a nonzero match because one supplier code starts with `5413`.

But:

```python
naics_similarity(["5413"], [])
```

returns `None`, because there is no supplier NAICS data to score.

### `agency_familiarity(...)`

This scores agency experience.

It checks:

1. subagency first
2. top-tier agency second

Example:

- project subagency: `Federal Highway Administration`
- supplier subagencies: `["Federal Highway Administration"]`

Result:

- perfect familiarity match

If subagency is missing, it falls back to top-tier, such as:

- `Department of Transportation`


## 9. Main Problems We Faced

Here are the biggest issues we hit while building Phase 1.

### Problem 1: import errors when running the script

At the beginning, running the script failed because Python could not import the local package.

Error:

- `ModuleNotFoundError: No module named 'inframatch'`

### Why it happened

The script was being run from `scripts/`, and Python did not automatically include the project root in `sys.path`.

### Fix

We added the project root to `sys.path` at the top of `scripts/build_suppliers.py`.


### Problem 2: missing dedup module

The script imported:

- `inframatch.ingest.dedup`

but that file did not exist yet.

### Fix

We created `inframatch/ingest/dedup.py` and added the supplier ID logic there.


### Problem 3: invalid NAICS filter format

Early on, the API rejected 3-digit NAICS filters like:

- `541`
- `237`

with an error saying only certain code lengths were supported.

### Fix

We switched to supported 4-digit or 6-digit NAICS forms where relevant.


### Problem 4: raw award-search API returned empty NAICS values

Even after fixing filters, the `spending_by_award` endpoint kept returning:

- `NAICS Code = null`
- `NAICS Description = null`

This made NAICS unusable if we stayed on that endpoint.

### Fix

We tested the transaction search endpoint and found it returned:

- `naics_code`
- `naics_description`
- `product_or_service_code`

So we changed the pipeline to use:

- `spending_by_transaction`

and then collapse transactions back into awards.

That was one of the biggest improvements in Phase 1.


### Problem 5: the early dataset was defense-heavy

Even when NAICS was populated, the first dataset was full of firms like:

- Lockheed Martin
- Northrop Grumman
- Boeing

That did not match the InfraMatch story.

### Why it happened

NAICS tells us the vendor's industry, not what service the government bought.

So `541330` pulled in defense engineering as well as infrastructure engineering.

### Fix

We changed the query strategy:

- use PSC as the main filter
- use civilian agencies only
- use place of performance instead of recipient location

This moved the slice toward infrastructure work rather than defense work.


### Problem 6: wrong location signal

We initially filtered using recipient location.

That means:

- where the vendor is based

But for infrastructure matching, what matters more is:

- where the work happened

### Fix

We changed to:

- `place_of_performance_locations`

This made the geographic slice more meaningful.


### Problem 7: date leakage

Earlier pulls included older rows than expected.

### Why it happened

USAspending has multiple date fields, and using the wrong interpretation can let older awards through.

### Fix

We used:

- `date_type = "new_awards_only"`

and also kept a final dataframe guard:

- `awards_df["start_date"] >= START_DATE`


### Problem 8: cache contamination

When a query changed, old cached pages could still exist and make it look like the new query had run.

### Fix

We:

- hashed query inputs into cache directories
- deleted stale cache folders before major reruns


### Problem 9: one fallback got blocked by the USAspending detail endpoint

We briefly tried enriching missing NAICS by calling the per-award detail endpoint.

That approach ran into:

- intermittent `500` errors
- web application firewall blocks under heavier request volume

### Fix

We abandoned that path once transaction search proved to be cleaner and more reliable.

This simplified the final pipeline a lot.


## 10. Why the Current Version Is Better

The current Phase 1 pipeline is better because:

- it has `100%` NAICS fill
- it has `100%` PSC fill
- it uses place of performance
- it excludes DoD completely
- it captures subagency history for future matching
- it produces a cleaner supplier mix for infrastructure work


## 11. Example of One Row Moving Through the Pipeline

Imagine the API gives us a transaction row like this:

- Recipient Name: `WSP USA ENVIRONMENT & INFRASTRUCTURE INC.`
- Awarding Agency: `Department of Transportation`
- Awarding Sub Agency: `Federal Highway Administration`
- PSC: `Y1LB`
- NAICS: `237310`
- Transaction Amount: `500000`

### Step 1: transaction fetch

The row is fetched from USAspending.

### Step 2: collapse to award

If this award has multiple transactions, they are merged into one award row.

### Step 3: normalization

The row becomes something like:

```python
{
  "award_id": "...",
  "recipient_name": "WSP USA ENVIRONMENT & INFRASTRUCTURE INC.",
  "award_amount": 500000,
  "awarding_agency": "Department of Transportation",
  "awarding_subagency": "Federal Highway Administration",
  "naics_code": "237310",
  "psc_code": "Y1LB"
}
```

### Step 4: deduplication

We attach a stable supplier ID, usually based on UEI.

### Step 5: supplier aggregation

If WSP has many award rows, they get combined into one supplier row with:

- total award value
- number of awards
- list of PSC codes
- list of NAICS codes
- list of subagencies worked with


## 12. Final Output After This Phase

After the latest rebuild:

- `awards.parquet` has `1246` rows
- `suppliers.parquet` has `333` rows

This means:

- we now have a manageable infrastructure-focused award table
- and a deduplicated supplier table ready for later matching work


## 13. Remaining Trade-Off

The dataset is much cleaner than before, but it is not perfect.

The biggest trade-off is:

- we had to include broader PSCs like `C211` and `C219`

Why?

Because the stricter bridge/water-only slice was too small.

So the final dataset is:

- clearly infrastructure-oriented
- clearly better than the defense-heavy version
- but still broader than a pure bridge-inspection-only dataset

That trade-off is documented and intentional.


## 14. Short Summary

Phase 1 now works like this:

- query USAspending transaction data
- filter to infrastructure-style PSCs
- restrict to civilian agencies
- restrict by place of performance in the Northeast corridor
- collapse transactions into awards
- normalize and deduplicate suppliers
- build supplier-level features for matching

The hardest part of Phase 1 was not deduplication.

The hardest part was finding the right procurement query so the data actually matched the InfraMatch story.

That is why most of the work in this phase ended up being:

- API debugging
- filter design
- data-quality validation

instead of just dataframe cleaning.
