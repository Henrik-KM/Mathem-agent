# Mathem Agent roadmap

This backlog extends the existing personal meal-planning and basket-building
prototype. The estimates are planning ranges for proposed work, totaling
approximately 24-32 hours. The items below remain to be implemented.

Development and regression checks use fictional product catalogs, temporary
state and mocked retailer responses. Live accounts, customer information and
real shopping activity are outside the review workflow.

## 1. Enforce selection constraints and the basket budget

Estimated effort: 8-10 hours.

The current planner selects products heuristically and warns when the result
exceeds the budget. Product scoring heavily penalizes exclusions, but selecting
the highest score can still return an unsuitable item when every candidate is
excluded.

Planned work:

- Separate hard eligibility filters from preference scoring and return a clear
  unavailable result when no product satisfies the constraints.
- Choose or substitute products across the complete basket to meet the budget,
  and explain an infeasible budget without silently violating preferences.
- Handle missing prices explicitly and preserve reproducibility for a fixed
  catalog and seed.

Acceptance checks:

- An excluded product is never selected, including an all-excluded catalog.
- A feasible fixture stays within its specified basket budget.
- An infeasible fixture produces an explicit diagnostic.
- Tests cover empty search results, unknown prices and deterministic reruns.

## 2. Calculate portions, pack sizes and shared ingredients

Estimated effort: 6-8 hours.

The current quantity rule is a coarse people-and-price heuristic. The planner
also tends to avoid reusing a selected product across recipes.

Planned work:

- Normalize supported package sizes and comparable units.
- Calculate ingredient amounts and required package counts from servings.
- Aggregate shared ingredients across meals and account for optional pantry
  stock, while retaining each recipe's contribution to the basket.

Acceptance checks:

- Two- and four-person fixtures produce consistent required amounts.
- Shared ingredients produce one aggregated basket line.
- Incompatible or missing units produce a visible warning.
- Basket estimates include whole-package purchase costs.

## 3. Extend connector and weekly-recovery regression coverage

Estimated effort: 6-8 hours.

The repository already has basic weekly idempotency and retry tests. Extend
those protections around retailer changes and interrupted runs.

Planned work:

- Add offline response fixtures for changed product markup, missing fields,
  unavailable products, rate limits and expired sessions.
- Test interruption at each weekly-run boundary and recovery from partial
  progress.
- Cover daylight-saving transitions, a missed scheduled run and repeated
  execution in the same weekly period.
- Preserve the existing rule that an ambiguous basket-write result requires
  review rather than an automatic retry.

Acceptance checks:

- Regression tests make no real retailer requests and use no live credentials.
- Previously confirmed basket lines are not added again during recovery.
- Ambiguous writes and expired sessions surface an actionable status.
- Weekly period selection remains stable around timezone changes.

## 4. Improve plan comparison and review in the local interface

Estimated effort: 4-6 hours.

Planned work:

- Show the requested budget, estimated basket total and remaining headroom
  consistently across the CLI and Streamlit interface.
- Let the user inspect alternatives and adjust quantities before authorizing a
  basket update.
- Explain substitutions, unavailable ingredients and unresolved quantities.
- Document the offline demo, contribution workflow and updated behavior as
  each work item is completed.

Acceptance checks:

- Fictional review scenarios show the same totals in both interfaces.
- Adjustments produce an inspectable basket preview.
- Reviewing or comparing plans does not create an order or payment.
