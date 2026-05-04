# Phase 6 Explanation

This document explains the Phase 6 backend API in clear language.

Phase 6 is the point where InfraMatch becomes a usable application service
instead of only a collection of pipelines and models.

The main goal of Phase 6 is:

- expose the supplier and opportunity data through HTTP endpoints
- expose the ranking engine through an API
- connect the procurement workflow to the Phase 5 crack-detection model
- persist inspections, match results, and defect-analysis outputs in the
  database
- return clean JSON responses that a frontend or external client can consume

In short:

- Phases 1 to 5 built the data, scoring, and computer-vision pieces
- Phase 6 wraps those pieces in a FastAPI backend so they can be used as a
  product


## 1. What Phase 6 Adds

Phase 6 introduces the API layer under `inframatch/api/` and uses the existing
database, ranking, and computer-vision modules underneath it.

The new backend is responsible for:

- starting a FastAPI application
- validating request bodies and response payloads
- reading and writing rows from SQLite through SQLModel
- running supplier ranking on demand
- creating inspection assignments
- accepting image uploads
- triggering crack-detection inference
- assembling a single report that combines procurement and inspection data


## 2. Files Used in Phase 6

### `inframatch/api/main.py`

This is the core API file.

It contains:

- FastAPI app creation
- CORS middleware setup
- serializer/helper functions
- all route handlers
- file-upload handling
- inspection analysis orchestration

### `inframatch/api/schemas.py`

This file defines the Pydantic models used by FastAPI.

It is responsible for:

- validating JSON request bodies
- documenting expected inputs
- enforcing consistent response shapes

### `inframatch/db/session.py`

This file configures the shared database engine.

It is responsible for:

- building the database URL
- creating the SQLModel engine
- handling SQLite-specific connection settings
- exposing helpers for table creation and session creation

### `inframatch/db/models.py`

This file defines the database tables.

Phase 6 relies heavily on these models:

- `Supplier`
- `Opportunity`
- `Match`
- `Inspection`
- `DefectResult`

### `inframatch/matching/ranker.py`

This file is not part of the API package, but several endpoints call into it.

It is responsible for:

- ranking incumbent suppliers for an opportunity
- ranking emerging entrants
- saving match results into the database
- retrieving saved matches

### `inframatch/cv/inference.py`

This file powers the inspection-analysis endpoint.

It is responsible for:

- loading the trained crack model
- preprocessing a single uploaded image
- generating a crack / no-crack prediction
- estimating crack severity
- producing Grad-CAM output for positive detections


## 3. Backend Stack

Phase 6 uses the following core libraries:

- `fastapi` for the web framework
- `uvicorn` as the ASGI server
- `sqlmodel` for ORM-style database access
- `python-multipart` for file uploads
- `torch`, `torchvision`, `opencv-python`, `pillow`, and `numpy` for the image
  inference path

This stack is listed in `requirements.txt`.


## 4. Application Entry Point

The backend app is created in `inframatch/api/main.py`.

Important lines:

- `app = FastAPI(...)`
- title: `InfraMatch AI API`
- version: `0.6.0`
- description: `Supplier matching, compliance, and inspection analysis API.`

Why this matters:

- FastAPI automatically builds OpenAPI documentation
- the version number signals that this backend is the Phase 6 API layer
- tools like Swagger UI can inspect every route automatically

When the server is running, FastAPI also exposes:

- `/docs` for Swagger UI
- `/redoc` for ReDoc


## 5. CORS Configuration

The backend adds this middleware:

```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

This means:

- requests from any frontend origin are currently allowed
- all HTTP methods are allowed
- all headers are allowed

Why it was done this way:

- it simplifies local development
- it avoids frontend integration issues early in the project

Production note:

- `allow_origins=["*"]` is intentionally permissive
- in a deployed environment, this should be restricted to known frontend
  origins


## 6. How the Database Connection Works

The database connection is configured in `inframatch/db/session.py`.

### Default database path

```python
DEFAULT_DB_PATH = Path(__file__).resolve().parents[2] / "inframatch.db"
```

This means the default database file is:

- `inframatch.db` at the project root

### Environment override

```python
DATABASE_URL = os.getenv("DATABASE_URL", f"sqlite:///{DEFAULT_DB_PATH.as_posix()}")
```

This means:

- if `DATABASE_URL` exists in the environment, the backend will use it
- otherwise it falls back to the local SQLite database file

That design is useful because:

- local development can use SQLite with no extra setup
- deployment can swap to another database URL later without changing code

### SQLite-specific connection settings

```python
if DATABASE_URL.startswith("sqlite"):
    connect_args = {"check_same_thread": False}
```

Why this is needed:

- SQLite normally restricts a connection to the thread that created it
- FastAPI can handle requests across multiple threads
- `check_same_thread=False` prevents thread-related SQLite errors

### Engine creation

```python
engine = create_engine(
    DATABASE_URL,
    echo=False,
    connect_args=connect_args,
)
```

This shared `engine` object is imported by the API routes and other modules.

### Session usage pattern

Most Phase 6 routes use:

```python
with Session(engine) as session:
    ...
```

This pattern is important because it:

- opens a unit of work for one request
- safely closes the session when the block ends
- keeps database lifecycle management simple

### Table creation helper

`create_db_and_tables()` calls:

```python
SQLModel.metadata.create_all(engine)
```

This creates all declared SQLModel tables if they do not already exist.


## 7. Database Tables Used by the API

The API depends on five SQLModel tables from `inframatch/db/models.py`.

### `Supplier`

This table stores normalized supplier profiles.

Important fields:

- `id`
- `canonical_supplier_id`
- `canonical_name`
- `uei`
- `state`
- `past_awards_count`
- `total_award_value`
- `avg_award_value`
- `last_award_date`
- `naics_codes_json`
- `psc_codes_json`
- `agencies_json`
- `subagencies_json`
- `local_content_score`
- `small_business_flag`
- `certifications_json`
- `synthetic_esg_score`
- `risk_score`

Why some fields end with `_json`:

- SQLite is being used in a lightweight demo-style setup
- lists such as NAICS codes or certifications are stored as JSON text
- the API converts them back to Python lists before returning responses

### `Opportunity`

This table stores contract or infrastructure opportunities.

Important fields:

- `id`
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
- `required_certifications_json`
- `risk_tolerance`

### `Match`

This table stores ranked supplier results for a specific opportunity.

Important fields:

- `opportunity_id`
- `supplier_id`
- `final_score`
- `rank`
- `score_breakdown_json`
- `top_factors_json`
- `concerns_json`
- `compliance_outcomes_json`
- `created_at`

This table is what allows ranking to be computed once and later retrieved by
the report endpoint.

### `Inspection`

This table tracks the field-inspection workflow.

Important fields:

- `opportunity_id`
- `supplier_id`
- `status`
- `uploaded_image_path`
- `created_at`

The `status` field acts like a simple workflow marker:

- `assigned`
- `image_uploaded`
- `analyzed`

### `DefectResult`

This table stores the output of the Phase 5 crack model for one inspection.

Important fields:

- `inspection_id`
- `prediction`
- `confidence`
- `severity`
- `crack_ratio`
- `gradcam_path`
- `created_at`


## 8. Why the API Uses Response Conversion Helpers

`main.py` contains four helper functions:

- `parse_json_list`
- `supplier_to_response`
- `opportunity_to_response`
- `inspection_to_response`
- `defect_result_to_response`

### `parse_json_list(value)`

This helper turns database JSON text back into Python lists.

It handles:

- `None`
- an already-valid list
- a JSON-encoded string
- invalid JSON safely

Why this matters:

- the DB stores several list-like fields as strings
- clients should receive clean JSON arrays instead of raw text blobs

### `*_to_response(...)` helpers

These helpers convert SQLModel rows into the response schemas defined in
`schemas.py`.

Benefits:

- route handlers stay shorter
- date formatting is centralized
- JSON string parsing is centralized
- the API response shape stays stable


## 9. Request and Response Schemas

`inframatch/api/schemas.py` defines the API contracts.

### Request models

#### `OpportunityCreate`

Used by:

- `POST /opportunities`

This validates all fields required to create a new opportunity.

#### `AssignSupplierRequest`

Used by:

- `POST /opportunities/{opportunity_id}/assign`

This currently contains:

- `supplier_id: int`

#### `RankRequest`

Used by:

- `POST /opportunities/{opportunity_id}/rank`

This currently contains:

- `top_n: int = 10`

### Response models

#### `SupplierResponse`

Returned by:

- `GET /suppliers`
- `GET /suppliers/{supplier_id}`
- nested supplier payloads in match-reporting responses

#### `OpportunityResponse`

Returned by:

- `POST /opportunities`
- `GET /opportunities`
- `GET /opportunities/{id}`

#### `InspectionResponse`

Returned by:

- `POST /opportunities/{id}/assign`
- `POST /inspections/{id}/upload`

#### `DefectResultResponse`

Returned by:

- `POST /inspections/{id}/analyze`

#### `ReportResponse`

Returned by:

- `GET /inspections/{id}/report`

This response is intentionally flexible and contains nested dictionaries for:

- inspection
- opportunity
- supplier
- match
- defect_result


## 10. Endpoint-by-Endpoint Explanation

Phase 6 exposes 13 routes.


### 10.1 `GET /health`

Purpose:

- confirm the API is running
- show the configured database URL
- confirm whether the trained crack model file exists

Return shape:

```json
{
  "status": "ok",
  "database": "sqlite:///.../inframatch.db",
  "model_exists": true
}
```

Why this endpoint is useful:

- quick smoke test
- frontend boot-time health check
- easy debugging for missing-model issues


### 10.2 `POST /opportunities`

Purpose:

- create a brand-new opportunity row

Input:

- request body validated by `OpportunityCreate`

What the code does:

1. receives JSON payload
2. constructs an `Opportunity` SQLModel object
3. converts `required_certifications` list into JSON text with `json.dumps(...)`
4. adds the row to the database session
5. commits the transaction
6. refreshes the object so the generated `id` is available
7. returns the normalized response

Why `session.refresh(...)` is used:

- after commit, it reloads the row from the DB
- this ensures auto-generated fields like `id` are populated in Python


### 10.3 `GET /opportunities`

Purpose:

- list all opportunities
- optionally filter by `state`
- optionally filter by `asset_type`

Query parameters:

- `state`
- `asset_type`

What the code does:

1. starts with `select(Opportunity)`
2. conditionally adds `.where(...)` filters
3. executes the query
4. maps every row through `opportunity_to_response`

Design note:

- filtering is done directly in SQLModel for scalar fields such as state and
  asset type


### 10.4 `GET /opportunities/{opportunity_id}`

Purpose:

- retrieve one opportunity by primary key

What the code does:

1. calls `session.get(Opportunity, opportunity_id)`
2. if no row is found, raises `HTTPException(status_code=404, ...)`
3. otherwise returns a clean response model

Why `session.get(...)` is used:

- it is the simplest and most direct way to fetch one row by primary key


### 10.5 `POST /opportunities/{opportunity_id}/rank`

Purpose:

- run the supplier-ranking engine for a specific opportunity
- optionally limit how many results are returned
- save the ranking output into the `Match` table

Input:

- request body validated by `RankRequest`
- default `top_n` is `10`

What the code does:

1. calls `rank_suppliers(opportunity_id=..., top_n=..., save=True)`
2. `rank_suppliers(...)` loads the opportunity and supplier pool
3. it computes normalized maxima for past performance features
4. it scores every supplier using the Phase 3 scoring function
5. it sorts results descending by `final_score`
6. it assigns rank positions
7. it persists the top results via `save_matches(...)`
8. it returns JSON containing the ranked results

Why matches are saved:

- later endpoints, especially `/matches` and `/report`, can reuse the result
- it prevents the report workflow from depending only on transient in-memory
  ranking output

Error handling:

- if the opportunity does not exist, `rank_suppliers(...)` raises `ValueError`
- the route converts that into an HTTP `404`


### 10.6 `GET /opportunities/{opportunity_id}/matches`

Purpose:

- fetch previously saved ranking results for one opportunity
- enrich each match with full supplier information

What the code does:

1. validates that the opportunity exists
2. calls `get_saved_matches(opportunity_id)`
3. `get_saved_matches(...)` reads `Match` rows ordered by rank
4. JSON text columns are converted back into lists/dicts
5. the route loops through each match and fetches its supplier
6. it attaches nested supplier data to each match record

Why enrichment is useful:

- a frontend can render both score details and supplier profile details from one
  response
- the client does not need to make a separate `/suppliers/{id}` call for each
  ranked row


### 10.7 `GET /opportunities/{opportunity_id}/entrants`

Purpose:

- rank emerging or low-history suppliers using a cold-start weighting strategy

Query parameters:

- `top_n`, constrained to `1 <= top_n <= 50`

What the code does:

1. calls `rank_entrants(opportunity_id=..., top_n=...)`
2. `rank_entrants(...)` filters suppliers to those with low award history
3. it uses `ENTRANT_WEIGHTS` instead of the default incumbent weights
4. it scores and sorts those entrants
5. it returns the top results without saving them to the `Match` table

Why this endpoint exists separately:

- established firms and emerging entrants should not always be judged by the
  same weight mix
- this route offers a fairer view of newer suppliers


### 10.8 `GET /suppliers`

Purpose:

- list suppliers with optional filtering and pagination

Query parameters:

- `state`
- `naics`
- `psc`
- `limit`
- `offset`

What the code does:

1. loads supplier rows, optionally filtered by `state` in SQL
2. filters by `naics` in Python
3. filters by `psc` in Python
4. applies slicing for `offset` and `limit`
5. returns normalized supplier responses

Why `naics` and `psc` filtering happen in Python:

- those fields are stored as JSON text arrays in SQLite
- for this project scale, Python-side filtering is simpler and safer than
  relying on SQLite JSON expressions

Tradeoff:

- this is acceptable for demo or moderate local data sizes
- for large-scale production workloads, normalized relation tables or richer
  DB-native JSON indexing would scale better


### 10.9 `GET /suppliers/{supplier_id}`

Purpose:

- fetch one supplier profile by primary key

What the code does:

1. loads one row via `session.get(Supplier, supplier_id)`
2. raises `404` if the row does not exist
3. returns a structured `SupplierResponse`


### 10.10 `POST /opportunities/{opportunity_id}/assign`

Purpose:

- assign a supplier to an opportunity for inspection follow-up
- create a new inspection workflow record

Input:

- request body with `supplier_id`

What the code does:

1. validates that the opportunity exists
2. validates that the supplier exists
3. creates an `Inspection` row
4. sets initial status to `assigned`
5. commits and refreshes the row
6. returns `InspectionResponse`

Why this endpoint matters:

- it creates the bridge between procurement matching and the field-inspection
  process


### 10.11 `POST /inspections/{inspection_id}/upload`

Purpose:

- upload an inspection image for a previously created inspection

Input:

- multipart form upload
- required file field name: `file`

Accepted suffixes:

- `.jpg`
- `.jpeg`
- `.png`

What the code does:

1. checks the file extension
2. loads the `Inspection` row
3. creates `uploads/inspections/` if necessary
4. writes the uploaded bytes to disk as
   `uploads/inspections/inspection_{inspection_id}.{suffix}`
5. stores that relative path in `inspection.uploaded_image_path`
6. updates inspection status to `image_uploaded`
7. commits the updated row

Why the file path is persisted:

- the analysis endpoint needs a deterministic image location
- the report endpoint can expose where the source image came from

Error handling:

- `400` for unsupported file types
- `404` if the inspection record does not exist


### 10.12 `POST /inspections/{inspection_id}/analyze`

Purpose:

- run the Phase 5 crack-detection model on the uploaded image
- store the defect-analysis result in the database

Query parameters:

- `threshold`
- allowed range: `0.01` to `0.99`
- default: `0.5`

What the code does:

1. checks that `models/crack_resnet18.pt` exists
2. loads the inspection record
3. verifies that an image path is present
4. verifies that the image file still exists on disk
5. calls `predict(...)` from `inframatch/cv/inference.py`
6. builds a `DefectResult` row from the returned prediction
7. updates the inspection status to `analyzed`
8. commits both the defect result and the inspection update
9. returns a `DefectResultResponse`

What `predict(...)` does internally:

- loads the trained model checkpoint
- loads and transforms the image
- computes softmax probabilities
- applies the threshold to decide `crack` vs `no_crack`
- if prediction is `no_crack`, returns early with no severity map
- if prediction is `crack`, generates Grad-CAM, estimates crack ratio, bins
  severity, and saves an overlay image

Severity logic:

- `low` if crack ratio is below `0.005`
- `medium` if crack ratio is below `0.02`
- otherwise `high`

Error handling:

- `500` if the trained model file is missing
- `404` if the inspection does not exist
- `400` if no image has been uploaded
- `404` if the stored image path does not exist on disk


### 10.13 `GET /inspections/{inspection_id}/report`

Purpose:

- assemble a single full report for an inspection

This is the most product-like Phase 6 endpoint.

It combines:

- inspection assignment data
- the opportunity record
- the supplier record
- the saved procurement match, if one exists
- the latest defect-analysis result, if one exists

What the code does:

1. loads the `Inspection`
2. loads the linked `Opportunity`
3. loads the linked `Supplier`
4. validates that all three exist
5. queries the `Match` table for the inspection's supplier-opportunity pair
6. queries the `DefectResult` table for the newest result for that inspection
7. converts DB rows into response-safe dictionaries
8. returns a `ReportResponse`

Why it queries the latest defect result:

- an inspection might be analyzed more than once
- ordering by `created_at.desc()` ensures the newest result is returned

Why this endpoint is important:

- it gives the frontend a single payload for final review
- it is the endpoint that best demonstrates the value of combining Phases 3, 4,
  5, and 6


## 11. End-to-End Workflow in Phase 6

A normal request flow looks like this:

1. `GET /opportunities` or `GET /suppliers`
2. `POST /opportunities/{id}/rank`
3. `GET /opportunities/{id}/matches`
4. `POST /opportunities/{id}/assign`
5. `POST /inspections/{id}/upload`
6. `POST /inspections/{id}/analyze`
7. `GET /inspections/{id}/report`

Conceptually, this workflow does the following:

- discover an infrastructure opportunity
- score suppliers for that opportunity
- select a supplier for follow-up
- create an inspection task
- upload field imagery
- run defect detection
- combine business and engineering signals into one report


## 12. How Ranking Connects to the API

The ranking endpoints do not implement scoring logic themselves.

Instead, they delegate to `inframatch/matching/ranker.py`.

### `rank_suppliers(...)`

This function:

- loads the target opportunity
- loads the supplier pool
- computes maxima used for score normalization
- scores every supplier through `score_supplier(...)`
- sorts descending by final score
- adds rank numbers
- optionally saves those results into `Match`

### `save_matches(...)`

This function:

- deletes old saved matches for the opportunity
- inserts the latest ranked results

Why old rows are deleted first:

- the saved match list should reflect the latest ranking run
- this prevents stale rows from accumulating for the same opportunity

### `get_saved_matches(...)`

This function:

- reads match rows back from the DB
- orders them by rank
- decodes JSON text fields into real Python data structures


## 13. How Computer Vision Connects to the API

The analysis endpoint calls `predict(...)` from
`inframatch/cv/inference.py`.

That function does several important things:

- detects whether CUDA is available
- loads the checkpointed ResNet18 model
- applies the evaluation image transform
- computes class probabilities
- applies a configurable classification threshold
- generates Grad-CAM for crack-positive cases
- estimates crack severity with a heuristic based on edge density inside the
  Grad-CAM mask

This means the API layer does not need to know low-level PyTorch details.

That separation is good design because:

- API code stays focused on HTTP and persistence
- CV code stays focused on model inference
- each layer can evolve more independently


## 14. Validation and Error Handling

Phase 6 uses two main validation layers.

### FastAPI / Pydantic validation

This handles:

- request body typing
- missing required JSON fields
- query parameter constraints such as `top_n >= 1`
- query parameter bounds like analysis threshold between `0.01` and `0.99`

If validation fails, FastAPI automatically returns a `422 Unprocessable Entity`
response.

### Manual business validation inside routes

This handles:

- missing database rows
- unsupported file extensions
- missing uploaded images
- missing model checkpoint files

These produce deliberate `HTTPException(...)` responses such as:

- `400`
- `404`
- `500`


## 15. Why Some Data Is Stored as JSON Text

Several database columns store lists as strings:

- `required_certifications_json`
- `naics_codes_json`
- `psc_codes_json`
- `agencies_json`
- `subagencies_json`
- `certifications_json`
- match explanation fields such as `score_breakdown_json`

Why this approach was used:

- the project uses SQLite for simplicity
- these values are naturally list-shaped
- storing them as JSON text avoids creating many extra join tables during the
  prototype stage

Tradeoff:

- it is simple and practical for a prototype
- filtering and analytics over those fields become less efficient
- a more production-heavy design would likely normalize some of those fields


## 16. Running the Backend

Phase 6 is intended to be run with Uvicorn.

A typical local command is:

```bash
uvicorn inframatch.api.main:app --reload
```

By default:

- the app serves on `http://127.0.0.1:8000`
- Swagger docs are available at `http://127.0.0.1:8000/docs`

The backend expects:

- `inframatch.db` to exist or be creatable
- `models/crack_resnet18.pt` to exist if the analysis endpoint will be used
- write access to `uploads/inspections/`
- write access to `outputs/gradcam/` for positive crack detections


## 17. Design Strengths of Phase 6

Phase 6 is strong because it:

- cleanly separates API, database, ranking, and vision logic
- uses explicit schemas for input and output contracts
- keeps request handlers readable
- stores enough workflow state to support real user flows
- unifies procurement analytics and infrastructure inspection in one backend


## 18. Current Limitations and Practical Next Steps

The current Phase 6 implementation is a strong prototype, but it is not yet a
full production backend.

Current limitations:

- no authentication or authorization
- no delete or update endpoints for most resources
- permissive CORS settings
- SQLite JSON-text storage for list-like fields
- no background job queue for long-running analysis tasks
- no object storage abstraction for uploaded files
- no pagination metadata wrapper around list endpoints
- no dedicated migration system shown in this phase

Reasonable next steps:

- add authentication
- add update/delete routes where appropriate
- add Alembic-style migrations
- move uploads to managed storage
- add async task processing for model inference
- normalize some multi-value database fields
- add integration tests for all API flows


## 19. Final Summary

Phase 6 turns InfraMatch into a backend application.

It does that by connecting four layers:

- FastAPI for HTTP access
- SQLModel and SQLite for persistence
- the ranking engine for procurement intelligence
- the Phase 5 vision model for inspection analysis

The most important outcome is not any single endpoint.

The real outcome is the full workflow:

- create or fetch an opportunity
- rank candidate suppliers
- assign a supplier to an inspection
- upload an image
- analyze the image
- retrieve one combined report

That end-to-end workflow is the clearest expression of what Phase 6 adds to the
project.
