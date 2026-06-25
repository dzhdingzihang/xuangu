# Design QA

source visual truth path: `/Users/dingzihang/.codex/generated_images/019e5f18-25a9-7113-ae80-0495f512f144/ig_0328f119f93b6ee5016a3bec5d28fc819197af3cc2f73e236b.png`
implementation screenshot path: `/tmp/xuangu-local-final-fidelity.png`
full-view comparison evidence: `/tmp/xuangu-design-vs-final-fidelity.png`
viewport: `1440 x 1024`
state: A股 active tab, latest local data snapshot, light theme

## Findings

- [fixed P1] Main decision/chart row was too tall, pushing history and candidates below the first viewport.
  Fix: reduced hero, market tab, chart SVG, and decision row heights so lower modules are visible at 1440x1024.

- [fixed P1] Primary CTA was clipped after compressing the decision card.
  Fix: adjusted card height, CTA height, and internal spacing; verified the button is fully inside the decision panel.

- [fixed P2] Extra live execution block did not exist in the design target and added visual noise.
  Fix: hidden the execution-state block in the visual-target layout while preserving the underlying logic.

- [fixed P2] Market environment section was visible below the designed composition.
  Fix: hidden the extra section for this layout so the page matches the selected visual target structure.

## Required Fidelity Surfaces

- Fonts and typography: close to target with system Chinese UI fonts; display hierarchy now matches the design more closely. Remaining P3 difference: generated mock has slightly more editorial display weight.
- Spacing and layout rhythm: fixed P1 vertical rhythm; main row, reason row, and bottom modules now appear in the same first-viewport order as the design.
- Colors and visual tokens: light pearl/blue/emerald palette matches the target direction. Remaining P3 difference: generated hero image has stronger AI motif than current asset.
- Image quality and asset fidelity: replaced dark header with generated light AI finance header asset; no placeholder hero remains.
- Copy and content: A股 / 美股 / 港股 tabs, recommendation, K-line, reasons, risks, scoring, history, and Top5 match the target information architecture. Live data values differ by design because the product uses real data.

## Patches Made Since QA

- Compressed hero and market tab heights.
- Fixed K-line chart height to avoid pushing content down.
- Hid non-target execution and market environment blocks.
- Reworked CTA and secondary action spacing to avoid clipping.

final result: passed
