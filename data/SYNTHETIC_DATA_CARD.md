# Phase 1 Data Card

## Summary

This Phase 1 procurement slice is designed to approximate a Northeast civil
infrastructure supplier universe for InfraMatch. The dataset is intentionally
filtered to contracts that look like transportation, water, dam, survey, and
inspection work rather than general engineering services.

## Why PSC Is Primary

NAICS classifies the vendor's industry, not the service the government bought.
That distinction matters here because `541330` (Engineering Services) includes
both bridge-focused firms and defense engineering contractors. To avoid a
defense-heavy dataset, the slice uses PSC as the primary filter and treats
NAICS as secondary context.

The ingester filters primarily on infrastructure-oriented PSC codes, including:

- `Y1LB`, `Z1LB`, `Z2LB`, `C1LB` for highway, road, bridge, and railway work
- `Y1KA`, `C1KA`, `C1KF`, `C1ND`, `C1NE` for dams, dredging, sewage, and water
- `H156`, `H356`, `C213`, `R404` for inspection, quality control, and surveys
- `C211`, `C219` as a controlled expansion to keep the supplier pool large
  enough for Phase 1 while staying inside architect-engineer work

## Agency Scope

The slice explicitly includes only civilian top-tier awarding agencies:

- Department of Transportation
- General Services Administration
- Department of the Interior
- Department of Veterans Affairs
- Department of Homeland Security
- Department of Agriculture
- Environmental Protection Agency

Department of Defense is excluded on purpose to keep defense engineering
contracts from overwhelming the infrastructure signal. A side effect is that
Army Corps of Engineers Civil Works contracts are also excluded because they sit
administratively under DoD in USAspending. This is a deliberate trade-off for
dataset coherence.

## Geographic and Date Scope

The final slice uses place-of-performance rather than recipient location,
because where the work happened is more relevant to infrastructure matching than
where the vendor is headquartered.

The final production query uses:

- Place of performance: `NJ`, `NY`, `PA`, `CT`, `MA`, `MD`, `DE`
- Award types: `C`, `D`
- Minimum award amount: `$25,000`
- Date window: January 1, 2018 through December 31, 2025
- Date mode: `new_awards_only`

The initial stricter Northeast slice using only `NJ`, `NY`, and `PA` and only
high-signal PSC families was cleaner but too small for the supplier-volume goal.
The final slice is the smallest tested expansion that reached a workable number
of suppliers without opening the floodgates to generic `R425` engineering
services.

## Known Trade-Offs

- The final PSC list is broader than a pure bridge-only dataset because the
  stricter slice produced too few suppliers.
- `C211` and `C219` introduce some architecture and general A&E work, but they
  were materially cleaner than adding `R425`, which quickly reintroduced
  generic technical-services firms.
- The dataset is suitable for an infrastructure-oriented Phase 1 supplier base,
  but later phases should still expose score breakdowns so users can tell the
  difference between transportation, water, inspection, and general A&E history.
