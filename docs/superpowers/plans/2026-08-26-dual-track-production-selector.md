# Dual-Track Production Selector Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Publish auditable candidates through either the existing event-catalyst gate or a stricter quality-technical gate, without presenting either rule score as an上涨概率.

**Architecture:** Keep `production-rule-10d-v1` as the stable envelope and add the paired model contract `dual_track_candidate_qualification_v3` / `ten-day-audited-rule-ensemble-v3`. Every evaluated row contains both track audits; an overall candidate qualifies when either track passes, while market/data/negative-event blockers remain fail-closed for both tracks. The browser and Worker only display server-published results and expose the chosen track explicitly.

**Tech Stack:** Python 3.12, standard-library `unittest`, vanilla JavaScript, Cloudflare Worker, GitHub Actions.

---

### Task 1: Lock the dual-track rule behavior with failing tests

**Files:**
- Modify: `tests/test_production_rule_model.py`

- [ ] **Step 1: Add a quality-track fixture and assertions**

```python
def test_quality_technical_track_can_qualify_without_positive_event(self):
    row = candidate(
        market="us",
        code="VZ",
        name="Verizon",
        legacy_recommendation_degree=71,
        v2_rank=7,
        v2_rank_universe_size=299,
        verified_positive_event_ids=[],
        estimated_10d_range={"low_pct": -4.2, "high_pct": 7.3},
        blocker_codes=["TEN_DAY_MODEL_NOT_READY", "VERIFIED_POSITIVE_EVENT_MISSING"],
    )
    decision = build_production_decision(snapshot(row))
    self.assertEqual(decision["action"], "QUALIFIED_PICK")
    self.assertEqual(decision["primary"]["qualification_track"], "quality_technical")
    self.assertEqual(decision["primary"]["verified_positive_event_ids"], [])
```

- [ ] **Step 2: Add strict quality-track rejection cases**

```python
def test_quality_technical_track_has_stricter_non_event_gates(self):
    cases = {
        "legacy": (67.99, 7, -4.2, 7.3, "QUALITY_LEGACY_BELOW_THRESHOLD"),
        "rank": (71, 31, -4.2, 7.3, "QUALITY_V2_TOP_DECILE_REQUIRED"),
        "ratio": (71, 7, -5.0, 7.0, "QUALITY_RISK_REWARD_BELOW_THRESHOLD"),
    }
    for label, (legacy, rank, low, high, blocker) in cases.items():
        with self.subTest(label=label):
            row = candidate(
                market="us", code=f"{label}.US", name=label,
                legacy_recommendation_degree=legacy,
                v2_rank=rank, v2_rank_universe_size=299,
                verified_positive_event_ids=[],
                estimated_10d_range={"low_pct": low, "high_pct": high},
                blocker_codes=["VERIFIED_POSITIVE_EVENT_MISSING"],
            )
            evaluated = build_production_decision(snapshot(row))["evaluated_candidates"][0]
            self.assertEqual(evaluated["status"], "REJECTED")
            self.assertIn(blocker, evaluated["blocker_codes"])
```

- [ ] **Step 3: Prove shared safety gates cannot be bypassed**

```python
def test_quality_track_cannot_bypass_market_data_or_negative_event_blockers(self):
    for blocker in ("POOL_COVERAGE_INCOMPLETE", "MATERIAL_NEGATIVE_EVENT", "EVENT_CANDIDATE_NOT_SCANNED"):
        row = candidate(
            market="us", code="SAFE.US", name="Safe",
            legacy_recommendation_degree=75, v2_rank=1, v2_rank_universe_size=299,
            verified_positive_event_ids=[],
            blocker_codes=["VERIFIED_POSITIVE_EVENT_MISSING", blocker],
        )
        evaluated = build_production_decision(snapshot(row))["evaluated_candidates"][0]
        self.assertEqual(evaluated["status"], "REJECTED")
        self.assertIn(blocker, evaluated["blocker_codes"])
```

- [ ] **Step 4: Run the model tests and verify the new cases fail**

Run: `/tmp/xuangu-py312.EeOtnx/bin/python -m unittest tests.test_production_rule_model -v`

Expected: the new quality-track tests fail because V2 still requires a positive event and does not publish `qualification_track`.

### Task 2: Implement auditable event-catalyst and quality-technical tracks

**Files:**
- Modify: `production_rule_model.py`

- [ ] **Step 1: Introduce the V3 contract pair and strict quality policy**

```python
ACTION_BASIS = "dual_track_candidate_qualification_v3"
RULE_MODEL_ID = "ten-day-audited-rule-ensemble-v3"
TRACK_EVENT_CATALYST = "event_catalyst"
TRACK_QUALITY_TECHNICAL = "quality_technical"
QUALITY_POLICY = {
    "a_share": {"minimum_legacy": 66.0, "maximum_downside": 6.0, "minimum_upside": 6.0},
    "hk": {"minimum_legacy": 67.0, "maximum_downside": 6.0, "minimum_upside": 6.0},
    "us": {"minimum_legacy": 68.0, "maximum_downside": 7.5, "minimum_upside": 6.5},
}
QUALITY_MAX_V2_RANK_FRACTION = 0.10
QUALITY_MIN_DATA_QUALITY = 95.0
QUALITY_MIN_RISK_REWARD_RATIO = 1.50
QUALITY_MIN_QUALIFICATION_SCORE = 72.0
```

- [ ] **Step 2: Evaluate both tracks independently**

```python
track_evaluations = [
    {
        "track": TRACK_EVENT_CATALYST,
        "status": "PASS" if not catalyst_blockers else "FAIL",
        "blocker_codes": _dedupe(catalyst_blockers),
    },
    {
        "track": TRACK_QUALITY_TECHNICAL,
        "status": "PASS" if not quality_blockers else "FAIL",
        "blocker_codes": _dedupe(quality_blockers),
    },
]
qualification_track = next(
    (item["track"] for item in track_evaluations if item["status"] == "PASS"),
    None,
)
```

The quality path ignores only `VERIFIED_POSITIVE_EVENT_MISSING`. It still requires a completed event scan and preserves pool, quote, data, negative-event, non-positive-utility, and unknown source blockers. It uses the same score weights as the catalyst path so scores remain comparable; the missing event retains a zero event contribution.

- [ ] **Step 3: Publish track metadata and policy**

```python
result["qualification_track"] = qualification_track
result["track_evaluations"] = track_evaluations
decision["policy"]["tracks"] = {
    "event_catalyst": {"verified_positive_event_required": True},
    "quality_technical": {
        "verified_positive_event_required": False,
        "event_scan_required": True,
        "maximum_v2_rank_fraction": 0.10,
        "minimum_data_quality": 95.0,
        "minimum_risk_reward_ratio": 1.50,
        "minimum_qualification_score": 72.0,
    },
}
```

- [ ] **Step 4: Run the model tests**

Run: `/tmp/xuangu-py312.EeOtnx/bin/python -m unittest tests.test_production_rule_model -v`

Expected: all production-rule model tests pass; VZ-like and PFE-like fixtures qualify only through `quality_technical`.

### Task 3: Validate and preserve the new contract through snapshots and Worker summaries

**Files:**
- Modify: `server.py`
- Modify: `scripts/validate_snapshot.py`
- Modify: `src/index.js`
- Modify: `scripts/build_worker_assets.py`
- Modify: `tests/test_snapshot_contract.py`
- Modify: `tests/test_worker_contract.py`
- Modify: `tests/test_build_worker_assets.py`

- [ ] **Step 1: Advance the snapshot model version**

```python
MODEL_VERSION = "smart-selector-2026-08-26.2-dual-track-rule"
```

- [ ] **Step 2: Accept archives from V1/V2 and require V3 for the new model version**

```python
SUPPORTED_PRODUCTION_RULE_CONTRACTS = {
    ("strict_rule_qualification_v1", "ten-day-audited-rule-ensemble-v1"),
    ("candidate_level_rule_qualification_v2", "ten-day-audited-rule-ensemble-v2"),
    ("dual_track_candidate_qualification_v3", "ten-day-audited-rule-ensemble-v3"),
}
```

For a V3 qualified row, require `qualification_track` in `{"event_catalyst", "quality_technical"}` and require a matching `PASS` entry in `track_evaluations`. Require positive event IDs only for `event_catalyst`; require `event_candidate_scanned is True` for both tracks.

- [ ] **Step 3: Preserve audit fields in public summaries**

```javascript
const fields = [
  "qualification_id", "qualification_track", "track_evaluations", "status",
  "market", "code", "name", "rule_model_id", "score_kind",
  "qualification_score", "score_components"
];
```

- [ ] **Step 4: Run contract tests**

Run: `/tmp/xuangu-py312.EeOtnx/bin/python -m unittest tests.test_snapshot_contract tests.test_worker_contract tests.test_build_worker_assets -v`

Expected: old archived pairs remain accepted; the current model requires V3; Worker summaries retain track metadata without embedding full candidate snapshots.

### Task 4: Make the selected track clear in every relevant tab

**Files:**
- Modify: `static/app.js`
- Modify: `tests/test_frontend_contract.py`

- [ ] **Step 1: Accept the V3 pair in the browser contract guard**

```javascript
|| (decision.action_basis === "dual_track_candidate_qualification_v3"
  && decision.rule_model_id === "ten-day-audited-rule-ensemble-v3")
```

- [ ] **Step 2: Add explicit track labels**

```javascript
function qualificationTrackLabel(track) {
  return ({
    event_catalyst: "事件催化合格",
    quality_technical: "质量趋势合格",
  })[track] || "规则合格";
}
```

Use this label in the decision card, candidate badge, event tab, and history detail. For a quality-track primary with no positive event IDs, display “已完成事件扫描且未发现重大负面；本通道不要求正向催化”，instead of claiming that an event ID was required.

- [ ] **Step 3: Update the model tab to V3 dual-track thresholds**

The model card must display:

```text
事件催化：Legacy A/H/US 64/63/64，V2 Top 20%，正向事件至少 1 条，风险收益至少 1.20
质量趋势：Legacy A/H/US 66/67/68，V2 Top 10%，数据质量至少 95，风险收益至少 1.50，资格分至少 72
```

- [ ] **Step 4: Run frontend contract tests and syntax checks**

Run: `/tmp/xuangu-py312.EeOtnx/bin/python -m unittest tests.test_frontend_contract -v`

Run: `node --check static/app.js && node --check src/index.js`

Expected: tests and syntax checks pass, and no browser code derives a qualification locally.

### Task 5: Document, regress, generate, deploy, and verify

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Document both tracks and their safety boundary**

Add a table that states the event requirement, Legacy threshold, V2 percentile, data quality, risk/reward, and range limits for each track. State that both tracks remain deterministic qualification rules, not probabilities or guaranteed returns.

- [ ] **Step 2: Run the full regression suite**

Run: `git diff --check && node --check static/app.js && node --check src/index.js && /tmp/xuangu-py312.EeOtnx/bin/python -m unittest discover -s tests -q`

Expected: all tests pass with no diff whitespace errors or JavaScript syntax failures.

- [ ] **Step 3: Commit and push to GitHub main**

Run: `git add production_rule_model.py server.py scripts/validate_snapshot.py scripts/build_worker_assets.py src/index.js static/app.js README.md tests docs/superpowers/plans/2026-08-26-dual-track-production-selector.md && git commit -m "feat: add dual-track qualified candidates"`

Run: `git push git@github.com:dzhdingzihang/xuangu.git HEAD:main`

Expected: the Cloudflare deploy workflow completes successfully.

- [ ] **Step 4: Trigger a full data generation and verify the live contract**

Run: `gh workflow run deploy-worker.yml --ref main`

Expected live checks:

```text
/api/status: ok=true, model_version=smart-selector-2026-08-26.2-dual-track-rule
/api/latest: rule_model_id=ten-day-audited-rule-ensemble-v3
/api/latest: VZ and PFE qualify via quality_technical when the same audited inputs remain present
/api/history: the new qualified snapshot is archived with qualification_track
```

- [ ] **Step 5: Verify the rendered site**

Open `https://xuangu.alixjd.com/`, confirm the candidate tab shows each qualified stock with its track badge, the model tab explains both tracks, and the history tab opens the immutable V3 snapshot without a blank state.
