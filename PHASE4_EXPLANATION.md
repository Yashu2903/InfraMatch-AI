# Phase 4 Explanation

This document explains the Phase 4 code in simple language.

Phase 4 builds on the Phase 3 matching system.

The main goal of Phase 4 is:

- replace the earlier compliance-policy implementation with the newer one
- integrate that newer compliance engine cleanly into scoring
- make compliance gaps show up clearly in match explanations
- keep ranking, persistence, and CLI output aligned with the new engine

In short:

- Phase 3 built the matching engine
- Phase 4 refines the compliance layer inside that engine


## 1. What Phase 4 Adds

Phase 3 already had:

- supplier scoring
- incumbent and entrant ranking
- score breakdowns
- saved match results
- compliance-aware matching

Phase 4 improves the compliance part specifically by:

- replacing the older matching-layer compliance helper
- moving to the newer compliance engine in `inframatch/compliance/`
- using a rule file with explicit business weights
- normalizing compliance outputs so the rest of the matcher can use them
- surfacing failed compliance rules directly in `concerns`

That means Phase 4 is not a brand-new ranking engine.
It is a cleanup and strengthening of the ranking engine's compliance path.


## 2. Why We Changed the Compliance Layer

At one point the project had two compliance implementations:

- the earlier one in the matching area
- the newer one in `inframatch/compliance/`

That is a problem because:

- two engines can drift apart
- rules can get updated in one place but not the other
- debugging becomes harder
- documentation becomes misleading

So the Phase 4 decision was:

- choose one compliance engine as the source of truth

The newer engine was the better choice because it:

- has clearer rule semantics
- has explicit rule weights
- returns richer per-rule results
- separates compliance logic from scoring code more cleanly


## 3. Files Used in Phase 4

### `inframatch/compliance/engine.py`

This is the main Phase 4 compliance engine.

It is responsible for:

- loading the rule file
- parsing YAML or JSON-compatible YAML
- evaluating rules against supplier and opportunity fields
- returning:
  - one blended compliance score
  - one list of detailed rule outcomes

### `inframatch/compliance/rules.yaml`

This is the active rules file used by the engine.

It currently defines three rules:

- `local_content`
- `small_business`
- `certifications`

It also defines their internal weights:

- `local_content`: `0.4`
- `small_business`: `0.3`
- `certifications`: `0.3`

### `inframatch/matching/scoring.py`

This file uses the compliance engine during supplier scoring.

It now:

- imports `evaluate_rules(...)`
- converts raw rule outcomes into a normalized structure
- uses the blended compliance score as `compliance_fit`
- passes compliance outcomes into explanation logic
- uses failed compliance rules inside `concerns`

### `inframatch/matching/ranker.py`

This file still performs ranking, but now works with the new compliance output.

It:

- ranks suppliers
- saves `compliance_outcomes_json`
- returns saved matches with compliance details intact

### `scripts/rank_supplier.py`

This CLI script shows the ranking output in human-readable form.

It prints:

- top factors
- concerns
- compliance outcomes

### Tests

The most relevant tests for this phase are:

- `tests/test_compliance_policy.py`
- `tests/test_matching_score.py`
- `tests/test_scoring.py`


## 4. Phase 4 Code Flow

The Phase 4 flow for one supplier and one opportunity is:

1. `score_supplier(...)` starts in `inframatch/matching/scoring.py`.
2. It computes normal match factors such as:
   - NAICS similarity
   - PSC similarity
   - past performance
   - location
   - agency familiarity
   - recency
3. It calls the new compliance engine.
4. The compliance engine loads the rules from `inframatch/compliance/rules.yaml`.
5. Each rule is evaluated.
6. The compliance engine returns:
   - one overall compliance score
   - one detailed list of rule outcomes
7. `score_supplier(...)` normalizes those rule outcomes.
8. The final weighted match score is assembled.
9. `top_factors` are selected.
10. `concerns` are built, with failed compliance rules prioritized.
11. `ranker.py` can save the results to the database.
12. `scripts/rank_supplier.py` can print them to the terminal.


## 5. What the New Compliance Engine Does

The new engine in `inframatch/compliance/engine.py` is a rule-evaluation module.

It does not know about ranking weights like:

- `naics_similarity`
- `past_performance`
- `recency`

Its job is narrower:

- evaluate only compliance requirements

That separation is good engineering because:

- ranking logic and business-rule logic are different concerns


## 6. Rule Loading

The function `load_rules(...)` reads the rules file.

Important design details:

- it reads from `rules.yaml`
- it accepts YAML if `PyYAML` is available
- it can also parse JSON-compatible YAML if `PyYAML` is unavailable

Why this matters:

- the repo remains usable in environments where YAML dependencies are not fully
  installed yet
- the rule file can still stay external and editable


## 7. Rule Types in Phase 4

The current engine supports three rule types.

### 7.1 `numeric_threshold`

Used for:

- `local_content`

How it works:

- reads a numeric supplier field
- reads a numeric opportunity requirement
- compares them with an operator such as `>=`
- gives:
  - pass/fail
  - partial score
  - weighted score

Why partial score is useful:

- a supplier with `50` against a requirement of `100` is not the same as a
  supplier with `0`

### 7.2 `boolean_match`

Used for:

- `small_business`

How it works:

- activates only when the opportunity requires the condition
- if the opportunity does not require it, the supplier gets full credit
- if the requirement is active, the result is essentially pass/fail

Why this makes sense:

- this is a binary procurement condition
- partial credit does not make much sense here

### 7.3 `set_subset`

Used for:

- `certifications`

How it works:

- compares required certifications against supplier certifications
- finds:
  - matched items
  - missing items
- gives partial credit if some certifications are present but not all

Why this matters:

- certification requirements are often multi-item requirements
- missing one required certification should show up clearly


## 8. Current Rule Weights

Inside `inframatch/compliance/rules.yaml`, the current weights are:

- `local_content`: `0.4`
- `small_business`: `0.3`
- `certifications`: `0.3`

These weights apply only inside compliance scoring.

That means they decide:

- how much each compliance rule contributes to the final compliance score

They do not replace the outer match weight:

- `compliance_fit = 0.20`

So there are two layers of weighting:

1. inner compliance-rule weights
2. outer match-factor weights


## 9. Why These Compliance Weights Make Sense

### `local_content = 0.4`

This gets the highest internal weight because:

- it is a direct delivery constraint
- it reflects ability to meet a concrete project participation requirement
- it is often more operational than a paperwork-style signal

### `small_business = 0.3`

This is important because:

- some opportunities explicitly require it
- it can be a hard procurement requirement

It is slightly below local content because:

- it only matters when the opportunity activates that condition

### `certifications = 0.3`

This is important because:

- missing required certifications can block or weaken supplier suitability

It sits at the same weight as small business because:

- both are meaningful gating signals
- but local content was chosen as the slightly stronger operational signal in
  the current rule set


## 10. How Compliance Is Integrated Into `scoring.py`

The main integration point is:

- `compliance_fit(supplier, opportunity)`

This function now:

1. calls `evaluate_rules(...)`
2. gets:
   - a blended compliance score
   - raw rule outcomes
3. converts those raw rule outcomes into a normalized format used by the
   matching engine

The normalized output includes fields such as:

- `rule`
- `name`
- `rule_type`
- `passed`
- `score`
- `weight`
- `weighted_score`
- `note`
- `supplier_value`
- `required_value`
- `missing`

Why normalization is important:

- the compliance engine and the ranking engine should stay loosely coupled
- the ranking layer should get a stable structure even if the raw engine format
  changes later


## 11. What Changed in `concerns`

This is one of the most important Phase 4 improvements.

Earlier, `concerns` came mainly from:

- the lowest-scoring top-level factors

That could hide an important compliance failure.

For example:

- a supplier might fail small-business requirements
- but the concern list could still show only generic low-scoring factors like
  location or agency familiarity

That is not ideal.

So in Phase 4, `build_concerns(...)` was changed to:

- prioritize failed compliance rules first
- then fill the rest from low-scoring generic factors

Now a failing supplier can surface concerns like:

- `compliance:small_business`
- `compliance:local_content`
- `compliance:certifications`

This is a better behavior because:

- compliance failures are often more actionable than generic score weakness


## 12. Top Factors vs Concerns

The engine now separates:

- strengths
- risks

### `top_factors`

These are the strongest weighted contributors to the final score.

They help answer:

- why is this supplier ranking well?

### `concerns`

These are the weakest or most problematic areas, with compliance failures
prioritized first.

They help answer:

- what should I worry about for this supplier?

This makes the output more decision-friendly.


## 13. Is `ranker.py` Updated

Yes.

`inframatch/matching/ranker.py` is aligned with the current compliance engine.

It already:

- uses `score_supplier(...)`
- receives the new normalized `compliance_outcomes`
- saves `compliance_outcomes_json`
- returns those outcomes when reading saved matches

So ranking persistence stays in sync with the new compliance path.


## 14. Is `scripts/rank_supplier.py` Updated

Yes.

The CLI output is aligned with the current structure.

It prints:

- supplier rank
- final score
- top factors
- concerns
- compliance outcomes

That means the current command-line view is not hiding compliance details.


## 15. Backward Compatibility and Stability

The rest of the matcher still keeps earlier compatibility behavior where
possible.

Examples:

- `naics_similarity(...)` still supports older-style usage
- `agency_familiarity(...)` still supports older signature patterns

That matters because this phase was not meant to break the rest of the
matching stack.


## 16. Main Problems Phase 4 Solved

### Problem 1: Two compliance engines existed

Why it was bad:

- duplicate logic
- possible drift
- harder debugging

What Phase 4 did:

- selected the new `inframatch/compliance/` engine as the active one
- removed the older matching-layer compliance module from active use

### Problem 2: Compliance gaps were not visible enough in concerns

Why it was bad:

- actionable failures could be buried

What Phase 4 did:

- made failed compliance rules appear first in `concerns`

### Problem 3: External rules needed better runtime safety

Why it was bad:

- YAML dependencies may not always be installed

What Phase 4 did:

- added a fallback parser path for JSON-compatible YAML

### Problem 4: Ranking output had to stay aligned with the new compliance shape

Why it mattered:

- persistence and CLI output should not lag behind scoring changes

What Phase 4 did:

- kept `ranker.py` and `rank_supplier.py` aligned with the current structure


## 17. What the Data Looks Like Now in Match Output

For each scored supplier, the match output now includes:

- `final_score`
- `score_breakdown`
- `top_factors`
- `concerns`
- `compliance_outcomes`

The compliance outcomes now carry richer detail than before, including:

- rule id
- rule name
- rule type
- whether the rule passed
- partial score
- rule weight
- weighted score
- explanatory message
- supplier-side value
- required value
- missing items when applicable


## 18. Example of Why This Design Is Better

Suppose an opportunity requires:

- small-business participation
- `60%` local content
- two certifications

And a supplier has:

- no small-business flag
- only `20%` local content
- only one of the two certifications

The new system can now show that clearly.

Instead of only saying:

- low compliance score

it can now show concerns such as:

- `compliance:small_business`
- `compliance:local_content`
- `compliance:certifications`

That makes the result easier to interpret and easier to act on.


## 19. Validation Status

The current test suite still passes.

At the time of writing:

- `25 passed`

The tests cover:

- scoring behavior
- compliance rule loading
- compliance rule evaluation
- failed compliance surfacing
- ranking integration behavior


## 20. Known Limitations

Phase 4 is stronger than the earlier version, but it still has limits.

Important ones:

- the rule set is still small
- the compliance engine is still rule-based, not learned
- messages are still handcrafted
- outer scoring weights are still manually chosen
- opportunity and supplier compliance data still come from earlier synthetic
  data generation

These are acceptable for the current stage because explainability is still more
important than model complexity.


## 21. Simple Summary

In simple terms, Phase 4 did four important things:

1. It replaced the old compliance implementation with the newer one.
2. It integrated that engine properly into supplier scoring.
3. It made compliance failures show up clearly in concerns.
4. It kept ranking, saved matches, and CLI output aligned with the new engine.

That is why this phase matters.

It made the matching system more consistent, more explainable, and more useful
for real ranking decisions.
