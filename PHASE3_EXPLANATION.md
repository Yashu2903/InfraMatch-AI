# Phase 3 Explanation

This document explains the Phase 3 matching engine in simple language.

Phase 3 is the part of the project where InfraMatch becomes a real matching
system instead of only a data pipeline.

The main goal of Phase 3 is:

- take one opportunity
- compare it against many suppliers
- score each supplier across several dimensions
- explain why a supplier scored well or badly
- store the ranked results in the database

Phase 3 also moves compliance logic out of hardcoded scoring code and into a
policy file so rules can be changed more safely later.


## 1. What Phase 3 Adds

Earlier phases prepared the data:

- Phase 1 built the procurement-based supplier base
- Phase 2 added synthetic compliance fields and opportunities
- Phase 3 introduced early scoring logic

Phase 3 adds the full matching layer:

- a multi-factor scoring engine
- ranking functions for incumbents and entrants
- a YAML-based compliance policy engine
- saved match rows in SQLite
- human-readable score explanations
- CLI output for ranked results
- automated tests for matching and compliance behavior


## 2. Files Used in Phase 3

These are the main Phase 3 files.

### `inframatch/matching/scoring.py`

This is the main scoring engine.

It contains:

- factor weights
- NAICS similarity logic
- PSC similarity logic
- past-performance scoring
- location scoring
- agency familiarity scoring
- recency scoring
- final weighted score assembly
- explanation text for each factor

### `inframatch/matching/compliance.py`

This is the compliance policy engine.

It:

- loads the policy file
- validates the policy structure
- evaluates each compliance rule
- returns both:
  - a single compliance score
  - detailed rule outcomes

### `inframatch/matching/policies/phase3_compliance.yaml`

This file defines the compliance rules.

Right now it includes:

- `local_content`
- `small_business`
- `certifications`

Each rule says:

- what kind of rule it is
- which supplier field to read
- which opportunity field to read
- how much that rule should weigh inside compliance
- what message to show

### `inframatch/matching/ranker.py`

This file ranks suppliers against one opportunity.

It provides:

- `rank_suppliers(...)`
- `rank_entrants(...)`
- `save_matches(...)`
- `get_saved_matches(...)`

### `scripts/rank_supplier.py`

This is the CLI helper.

It lets us:

- rank one opportunity from the terminal
- print top factors
- print concerns
- print compliance outcomes
- output JSON if needed

### Tests

Phase 3 is mainly covered by:

- `tests/test_matching_score.py`
- `tests/test_compliance_policy.py`
- `tests/test_scoring.py`


## 3. Core Idea Behind the Matching Engine

The matching engine was designed around one main idea:

- no single field is enough to decide whether a supplier is a good match

That is why the engine does not rank on only:

- lowest risk
- same NAICS
- same state
- or most past awards

Instead, it combines several signals because good supplier matching in this
project depends on more than one thing:

- capability fit
- contract history
- compliance fit
- geography
- agency familiarity
- recency of work

The engine is intentionally simple enough to explain, but structured enough to
be useful.

That balance matters.

If the engine were too simple:

- rankings would be easy to compute
- but they would not reflect how infrastructure supplier selection actually
  works

If the engine were too complex:

- rankings would become hard to debug
- hard to justify
- and hard to improve

So the Phase 3 design is a middle ground:

- enough factors to be realistic
- simple formulas for transparency
- explicit weights so tradeoffs are visible
- explanation text so the result is not a black box


## 4. End-to-End Flow

The Phase 3 flow for one opportunity is:

1. Load the opportunity from the database.
2. Load the supplier pool from the database.
3. Compute supplier-pool maxima for:
   - highest past award count
   - highest total award value
4. Score each supplier.
5. Sort suppliers by `final_score` descending.
6. Assign rank numbers.
7. Save the top results to the `Match` table.

The system also supports a separate entrant ranking path that changes the weight
model for low-history suppliers.


## 5. What Data the Matching Engine Uses

The engine uses supplier data and opportunity data together.

### Supplier-side fields used in scoring

The main supplier inputs are:

- `naics_codes_json`
- `psc_codes_json`
- `agencies_json`
- `subagencies_json`
- `past_awards_count`
- `total_award_value`
- `last_award_date`
- `state`
- `local_content_score`
- `small_business_flag`
- `certifications_json`

### Opportunity-side fields used in scoring

The main opportunity inputs are:

- `naics_code`
- `psc_code`
- `awarding_agency`
- `awarding_subagency`
- `state`
- `required_local_content`
- `requires_small_business`
- `required_certifications_json`


## 6. The Seven Main Scoring Factors

The default ranking model uses seven factors.

### 6.1 `naics_similarity`

This measures industry-code similarity.

Logic:

- exact 6-digit NAICS match: `1.00`
- same 4-digit family: `0.66`
- same 2-digit sector: `0.33`
- no match: `0.00`
- no supplier NAICS history: `None`

Why it exists:

- NAICS gives a fast capability signal
- it helps tell whether the supplier operates in the same industry space as the
  opportunity

Why it is not enough by itself:

- NAICS can be broad
- many engineering firms share similar NAICS codes
- it does not tell us enough about the exact kind of government work performed

### 6.2 `psc_similarity`

This measures service-code similarity.

Logic:

- exact PSC match: `1.00`
- same PSC family, first two characters: `0.50`
- same broad PSC category, first character: `0.25`
- no match: `0.00`
- no supplier PSC history: `None`

Why it exists:

- PSC is often more specific to what the government bought
- it gives a better signal for infrastructure work type than NAICS alone

Why it matters in this project:

- InfraMatch is trying to match contract type and work history, not just vendor
  industry labels

### 6.3 `past_performance`

This measures how much prior federal award history the supplier has.

Logic:

- uses both:
  - `past_awards_count`
  - `total_award_value`
- both values are log-scaled relative to the strongest supplier in the pool
- final past-performance score is:
  - `0.5 * count_score + 0.5 * value_score`

Why log scaling is used:

- supplier histories are very uneven
- one very large incumbent should not crush every smaller supplier too hard
- log scaling compresses extreme values while still rewarding proven experience

Why count and value are split evenly:

- award count captures repeat delivery
- total value captures scale
- using both avoids over-rewarding either:
  - many tiny awards
  - or one very large award

### 6.4 `compliance_fit`

This measures how well the supplier satisfies opportunity requirements.

In Phase 3 this is evaluated through the policy engine, not hardcoded scoring.

The current policy includes:

- `local_content`
- `small_business`
- `certifications`

Why this factor exists:

- a supplier can look strong historically but still fail project requirements
- compliance fit is a practical filter, not just a nice-to-have

### 6.5 `location_score`

This measures geographic closeness.

Logic:

- same state: `1.00`
- adjacent state: `0.70`
- inside Northeast corridor but not adjacent: `0.40`
- outside corridor: `0.10`

Why it exists:

- infrastructure work is geographically grounded
- local presence often affects mobilization, staffing, responsiveness, and
  familiarity with regional delivery conditions

Why it is not weighted too heavily:

- strong suppliers can still perform across state lines
- geography matters, but should not dominate capability and compliance

### 6.6 `agency_familiarity`

This measures whether the supplier has worked with the same agency before.

Logic:

- exact subagency match: `1.00`
- top-tier agency match only: `0.50`
- no match: `0.00`

Why subagency is stronger than agency:

- working with the Federal Highway Administration is more specific than working
  with the Department of Transportation in general

Why it exists:

- procurement familiarity is real
- agencies and subagencies often have specific delivery habits, expectations,
  and contracting patterns

### 6.7 `recency`

This measures how recent the supplier's last award was.

Logic:

- uses exponential decay on years since last award
- very recent work stays near `1.0`
- older history gradually decays toward `0`

Why it exists:

- recent activity is a stronger signal than very old activity
- it helps reduce the score of suppliers whose history is real but stale

Why its weight is kept small:

- recency should influence ranking
- but it should not wipe out strong capability, compliance, or historical fit


## 7. Default Weight Model

The default weight model is:

- `naics_similarity`: `0.20`
- `psc_similarity`: `0.15`
- `past_performance`: `0.20`
- `compliance_fit`: `0.20`
- `location_score`: `0.10`
- `agency_familiarity`: `0.10`
- `recency`: `0.05`

These weights sum to `1.00`.


## 8. Why Each Weight Was Chosen

This is the core reasoning behind the current weights.

### `naics_similarity = 0.20`

Why it is important:

- NAICS is one of the main capability signals
- it helps determine whether the supplier lives in the right technical domain

Why it is not higher than `0.20`:

- NAICS is too broad to dominate alone
- a pure NAICS-driven engine would overrate generic engineering overlap

Why `0.20` makes sense:

- it is strong enough to matter
- but not strong enough to overrule more specific evidence

### `psc_similarity = 0.15`

Why it is important:

- PSC is often closer to actual purchased work than NAICS

Why it is slightly below NAICS:

- the current project still uses both together as complementary classification
  signals
- PSC is powerful, but the dataset can still contain broad families and mixed
  codes

Why `0.15` makes sense:

- it gives material credit to work-type alignment
- but still keeps room for experience and compliance

### `past_performance = 0.20`

Why it is important:

- delivery history matters
- it gives confidence that the supplier can actually perform

Why it is not larger:

- too much past-performance weight would make the system overly incumbent-heavy
- the project needs to reward history without turning into a "largest incumbent
  always wins" engine

Why `0.20` makes sense:

- it keeps history in the top tier of importance
- but balances it against current fit and compliance

### `compliance_fit = 0.20`

Why it is important:

- if a supplier cannot satisfy project constraints, historical strength alone is
  not enough

Why it deserves top-tier weight:

- compliance is operationally important
- it is closer to a go/no-go dimension than some of the softer ranking signals

Why `0.20` makes sense:

- it puts compliance on equal footing with capability and experience
- that matches the project goal of procurement-aware ranking, not just history
  scoring

### `location_score = 0.10`

Why it is important:

- regional proximity can matter in infrastructure delivery

Why it is moderate:

- good suppliers may still work effectively outside their home state
- geography should influence, not dominate

Why `0.10` makes sense:

- it rewards regional fit
- but avoids making the model a simple local-only filter

### `agency_familiarity = 0.10`

Why it is important:

- prior agency experience can reduce execution friction

Why it is moderate:

- the project should not over-favor incumbents or repeat agency contractors
- some suppliers can still be excellent even without direct prior agency history

Why `0.10` makes sense:

- enough to recognize useful procurement familiarity
- not enough to make prior relationship the main driver

### `recency = 0.05`

Why it is important:

- active suppliers should get some credit over dormant ones

Why it is the smallest:

- recency is a supporting signal
- it should not override deeper evidence like classification fit, compliance,
  or meaningful past performance

Why `0.05` makes sense:

- it sharpens the ranking slightly
- without making the system unstable or overly time-sensitive


## 9. Why the Engine Uses Weighted Addition

The final score is a weighted sum of factor scores.

In simple terms:

- each factor produces a `0-1` style signal
- each factor is multiplied by its weight
- the weighted parts are added together

Why this design was chosen:

- easy to explain
- easy to debug
- easy to tune
- easy to compare between suppliers

This is important for InfraMatch because the product needs explainability.

If a user asks:

- why did Supplier A beat Supplier B?

we can point to:

- exact factor scores
- weighted contributions
- top factors
- concern factors
- compliance outcomes


## 10. Why Missing Data Is Not Treated the Same as Failure

This is an important design choice.

For some factors:

- missing supplier history returns `None`
- actual mismatch returns `0.0`

Example:

- no NAICS history is not the same as "bad NAICS match"
- no agency history is not the same as "proven agency mismatch"

Why this matters:

- it preserves honesty in the engine
- it avoids hiding data-quality issues inside the score
- it makes future tuning easier

At final-score time:

- `None` is treated as `0.0` for calculation
- but the explanation text still says the historical signal is missing


## 11. Compliance Engine Design

Phase 3 moves compliance logic into a policy engine.

This was done for a few reasons:

- compliance rules change more often than scoring structure
- hardcoded rules are harder to audit
- policy files are easier to inspect and revise
- it separates business rules from ranking math

### How the policy engine works

1. Load the YAML policy file.
2. Validate its structure.
3. Read enabled rules.
4. Evaluate each rule against supplier and opportunity fields.
5. Return:
   - one compliance score
   - one detailed list of rule outcomes

### Why the engine supports multiple rule types

The current rule types are:

- `threshold_ratio`
- `boolean_requirement`
- `subset_ratio`

These were chosen because they match the current project needs well.

#### `threshold_ratio`

Used for:

- `local_content`

Why:

- the requirement is numeric
- the supplier can partially satisfy it
- partial credit makes sense

Example:

- required local content = `60`
- supplier local content = `30`
- score = `0.5`

#### `boolean_requirement`

Used for:

- `small_business`

Why:

- this is a true or false requirement
- partial credit does not make sense here

#### `subset_ratio`

Used for:

- `certifications`

Why:

- opportunities can require multiple certifications
- suppliers can match some but not all
- partial credit is useful


## 12. Why the Compliance Rules Currently Have Equal Weights

Inside the policy file, the three rules currently use weight `1.0` each.

That means compliance currently behaves like an equal-weight average of:

- local content
- small business
- certifications

Why this was done:

- simple and interpretable baseline
- avoids pretending we already know a more precise business hierarchy
- keeps the first policy version easy to tune

Why equal weighting makes sense for now:

- all three requirements are meaningful
- the project is still at a stage where transparency matters more than overfit
  precision

What this means practically:

- if a supplier passes two rules and fails one, compliance still remains partly
  positive
- if later business logic says one rule is much more important, we can change
  only the policy file


## 13. Why We Added a Separate Entrant Model

The file `inframatch/matching/ranker.py` includes `rank_entrants(...)`.

This exists because a single weight model can unfairly punish emerging
suppliers.

If we scored entrants with the full incumbent model:

- low award count would hurt them
- lower total award value would hurt them
- missing agency familiarity would hurt them

That would create a built-in incumbency bias.

So the entrant path removes:

- `past_performance`
- `agency_familiarity`

and keeps:

- `naics_similarity`
- `psc_similarity`
- `compliance_fit`
- `location_score`
- `recency`

### Raw entrant weights

The entrant profile uses:

- `naics_similarity`: `0.20`
- `psc_similarity`: `0.15`
- `compliance_fit`: `0.20`
- `location_score`: `0.10`
- `recency`: `0.05`

These do not sum to `1.00`, and that is intentional because the code
re-normalizes weights before scoring.

### Effective entrant weights after normalization

After normalization, the effective weights are approximately:

- `naics_similarity`: `0.2857`
- `psc_similarity`: `0.2143`
- `compliance_fit`: `0.2857`
- `location_score`: `0.1429`
- `recency`: `0.0714`

Why this makes sense:

- capability and compliance become the dominant signals
- the model stops over-rewarding incumbency
- geography and recency still matter, but less


## 14. Explanation Output and Why It Matters

Each ranked result does not just return a score.
It also returns:

- `score_breakdown`
- `top_factors`
- `concerns`
- `compliance_outcomes`

### `score_breakdown`

This contains, for each factor:

- factor name
- raw value
- weight
- weighted contribution
- explanation note

### `top_factors`

This surfaces the strongest weighted contributors.

Why it matters:

- users can quickly understand why a supplier looks strong

### `concerns`

This surfaces the weakest factors.

Why it matters:

- users can quickly understand the main risks or gaps

### `compliance_outcomes`

This shows detailed policy results such as:

- which rule passed
- which rule failed
- what score the rule contributed
- what exact gap exists

Why it matters:

- compliance should not be hidden inside one blended number


## 15. Persistence Design

The `Match` table stores the Phase 3 ranking output.

Saved fields include:

- `final_score`
- `rank`
- `score_breakdown_json`
- `top_factors_json`
- `concerns_json`
- `compliance_outcomes_json`

Why we save this:

- ranking can be reused without recomputing immediately
- UI or API layers can read match details directly
- explanations stay attached to the saved result


## 16. Backward Compatibility Work

Phase 3 changed the matching layer, but we still kept compatibility with older
tests and earlier helper usage.

Examples:

- `naics_similarity(...)` still supports older list-prefix style behavior
- `agency_familiarity(...)` still supports the older keyword-based calling
  style

Why this was important:

- the codebase already had earlier tests and expectations
- improving the engine should not silently break previously working behavior


## 17. Why the Policy File Is Written the Way It Is

The policy file is currently JSON-compatible YAML.

Why:

- YAML is the intended long-term format
- but the current repo also supports environments where `PyYAML` is not
  installed yet
- JSON is a valid subset of YAML

So the current design gives both:

- external policy configuration
- practical runtime safety in the current environment


## 18. Current Validation Coverage

Phase 3 is backed by tests that check:

- NAICS similarity behavior
- PSC similarity behavior
- location scoring behavior
- agency familiarity behavior
- past-performance bounds
- recency behavior
- full supplier score output
- failed compliance surfacing
- policy loading
- policy evaluation math

At the time of writing, the test suite passes with:

- `25 passed`


## 19. Known Limitations

Phase 3 is strong for the current project scope, but it still has limits.

Important ones:

- weights are manually chosen, not statistically trained
- compliance policy is still small and rule-based
- agency familiarity is binary/partial rather than nuanced
- opportunity and compliance data still contain synthetic elements from earlier
  phases
- no learning-to-rank model is being used yet

These are acceptable limits for the current stage because explainability and
control were more important than model complexity.


## 20. Simple Summary

In simple terms, Phase 3 does this:

1. It checks whether a supplier looks capable for the project.
2. It checks whether the supplier has relevant work history.
3. It checks whether the supplier meets the opportunity's compliance
   requirements.
4. It checks whether the supplier is geographically close and agency-relevant.
5. It blends those signals with explicit weights.
6. It returns both a score and a human-readable explanation.

The reason the matching engine was coded this way is simple:

- the system needed to be realistic enough to rank suppliers well
- but transparent enough that a person can understand and trust the result

That is why Phase 3 uses:

- simple formulas
- visible weights
- policy-driven compliance
- saved explanations

It is not just a ranking engine.
It is a ranking engine that is meant to be explainable, tunable, and usable in
the product.
