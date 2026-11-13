# Five-metric cosmetic care selection

The integrated-v2 rules extend tone candidates with exact-name ascorbic acid
and N-acetyl glucosamine, and blemish-care candidates with exact-name sodium
ascorbyl phosphate. Other vitamin C derivatives are not automatically matched.
Evidence summaries, source URLs, study concentrations and limitations are
recorded in `backend/app/data/cosmetic_rules_integrated_v2.json`.

Brightness and uniformity share a pigmentation concern group. Their outputs
may legitimately overlap. Photo values remain proxy observations, and cannot
establish pigmentation disorders, acne, oiliness or an indication for treatment.

## Context policy

The UI requests `care_context`. Existing API ranking modes remain available.

1. Apply category, ingredient completeness, use-site and exclusion conditions.
2. Match active ingredients only for metrics assessed as needing improvement.
3. Count matched concern groups, with brightness and uniformity counted once.
4. Within equal group coverage, check the combination of low moisture or high
   redness with an exfoliation purpose explicitly written in the product name.
   Those candidates follow candidates without that observed combination.
5. Prefer product-name purpose groups that agree with the actual ingredient
   matches. Count each purpose group once, regardless of word or ingredient count.
6. Apply bundle, hydration support, redness support and optional legacy sensor
   tie handling. Product ID fixes ordering within the remaining ties.

Product-name statements are an unverified source of purpose information.
The response exposes the actual words as `product_name_claims`. Gifts are
excluded from purpose extraction where their naming boundary can be identified.
Missing statements mean unknown. They do not establish inefficacy. An absent
context caution does not establish safety. Ingredient matching is required even
when the name claims suitability for a concern.

The exfoliation interaction is a conservative project selection policy. It
uses product-name purpose, not an inferred disease or a ban on every acid.
AAD's guidance describes irritation and dryness considerations for exfoliation.
https://www.aad.org/public/everyday-care/skin-care-secrets/routine/safely-exfoliate-at-home

Raw ppm/ppb/% observations do not establish formulation concentration. Amount
disclosure, ingredient order and raw ingredient count confer no added ranking
points. Study formulations and commercial products have not been established
as equivalent. Context ordering expresses selection criteria, not comparative
clinical efficacy. The current catalog remains a collected snapshot.

## Local rollout after integrated-v1

No additional schema migration is introduced by this update. Register the new
rule version with `python scripts/seed_cosmetic_rules.py --apply`, then replay
the running service with
`python scripts/verify_cosmetic_personalization.py --api http://localhost:8000`.
The script makes read-only recommendation-preview requests using the current
local product database. Its pass result concerns rule routing and consistency.
