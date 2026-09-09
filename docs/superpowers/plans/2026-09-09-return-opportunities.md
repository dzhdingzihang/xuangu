# Two-week Return Opportunities Implementation Plan

**Goal:** Show the strongest evidence-backed two-week return opportunities across the dynamic A/HK/US pools, while retaining auditable qualification and calibrated model boundaries.

**Architecture:** Add a pure research ranking module evaluated against the full current candidate pools before their compact projection. Publish one bounded contract through the existing immutable snapshot, Worker bootstrap and frontend. Official routine buyback disclosures retain their audit records but cease to imply a new positive catalyst on every reporting day.

**Tech Stack:** Python 3.12, unittest, Cloudflare Worker JavaScript, browser JavaScript, GitHub Actions.

## Implementation and verification

- [ ] Add `return_opportunity.py` with `build_return_opportunities(snapshot, candidate_pools, metadata_by_market)` and deterministic 0–100 evidence scores. Relative momentum, price structure, actual peer-sector strength and event novelty contribute; historical scenario width is risk context, never expected profit. Unknown data remains explicit. Test missing inputs, major negatives, valid high volatility, deterministic ties and no duplicated-event bonus.
- [ ] Update `event_pipeline.py` classification and bounded scan selection. Routine daily buyback filings remain auditable neutral records without materiality evidence. Test repeated filings and distinct substantive events.
- [ ] Wire `server.py` to build opportunity evidence from all scored stocks before `_candidate_pool` removal, with the same snapshot identity and data cutoffs. Reuse known issuer descriptions only as labeled reference metadata, not curated membership or analyst scores.
- [ ] Publish bounded `return_opportunities` through `scripts/build_worker_assets.py` and `src/index.js`; validate the contract in `scripts/validate_snapshot.py` and the deployment verifier. Old snapshots remain reproducible and are not relabeled as new evidence.
- [ ] Update `static/app.js`, `static/styles.css`, `static/index.html` to lead with the return-opportunity research shortlist, followed by rule-qualified candidates. Preserve freshness gating and existing detail navigation.
- [ ] Update `README.md` with the score formula, risk treatment, industry metadata coverage, opportunity/qualification distinctions and cloud update mechanism.
- [ ] Run `python -m unittest discover -s tests`, JavaScript syntax checks, asset build and Wrangler dry run. Replay the current frozen data diagnostically to check candidate ordering without presenting the replay as a backtest.
- [ ] Commit and push isolated changes, await GitHub CI/deploy, trigger cloud generation, and verify current source identity, opportunity counts and actual browser rendering.
