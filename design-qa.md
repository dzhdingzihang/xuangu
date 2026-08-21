# Design QA

Reference target:

- `/Users/dingzihang/Desktop/丁子航的资金理财/xuangu-design-v3.1/01-decision.png`
- `/Users/dingzihang/.codex/generated_images/01a01535-e466-7b12-934b-033ff2fa5605/exec-e67fa99b-551e-4c3f-87aa-acfae964767a.png`

Verified implementation captures (in-app Browser):

- Decision, 1487×1058: `/tmp/xuangu-decision-qa.png`
- Candidates, 1487×1058: `/tmp/xuangu-candidates-qa.png`
- Events, 1487×1058: `/tmp/xuangu-events-qa.png`
- History, 1487×1058: `/tmp/xuangu-history-qa.png`
- Model, 1487×1058: `/tmp/xuangu-model-qa.png`
- Decision, 390×844: `/tmp/xuangu-mobile-qa.png`
- Candidates, 390×844: `/tmp/xuangu-mobile-candidates-qa.png`
- Side-by-side comparison: `/tmp/xuangu-v31-decision-comparison.png`

Checks:

- Five navigation tabs render and switch without console errors.
- Candidate market filter reduces the table to the selected market.
- Decision and history charts use Canvas and resize at the mobile breakpoint.
- The layout follows the reference's white/blue evidence-console hierarchy, 190px rail, compact status bar, dense tables, thin borders and restrained badges.
- Legacy and V2 labels are visually distinct; recommendation degree is not presented as probability.
- Old snapshots show an explicit evidence-gap state rather than fabricated event details.
- Mobile navigation keeps visible and accessible short labels alongside the compact icons.
- Mobile candidates viewport verified at `scrollWidth = clientWidth = 390`; no page-level horizontal overflow.
- Event URLs accept only HTTP(S), unknown directions normalize to the visible neutral filter, and V2 BLOCK overrides client execution advice.

Final result: passed
