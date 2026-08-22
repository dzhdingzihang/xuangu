# Design QA

## Source and comparison setup

- Figma file: `https://www.figma.com/design/9Wgimyl5jMk2BX0TCHtrwB`
- Frames: Today `11:37`, Candidate `11:40`, Evidence `11:43`, History `11:46`, Model `11:49`, Health `11:52`.
- Reference captures: `docs/design-qa/reference/{decision,candidates,events,history,model,health}.png`.
- Implementation captures: `docs/design-qa/implementation/{decision,candidates,events,history,model,health}.png`.
- Responsive captures: `docs/design-qa/implementation/mobile-{decision,candidates,events,history,model,health}.png`.
- Desktop viewport: `1512 × 982`, CSS pixel ratio `1`. Reference and implementation were captured at the same viewport and page state.
- Full-view comparisons: `docs/design-qa/comparison/{decision,candidates,events,history,model,health}.png`. Each file is `3026 × 1010`: two `1512 × 982` viewports plus labels and divider.
- Focus comparisons: `docs/design-qa/comparison/focus-{decision,candidates,events}.png`, covering the decision cards, candidate master/detail area and evidence feed/detail area at readable scale.

Implementation pages use the live local snapshot. Dynamic company names and counts therefore differ from the Figma fixture; the comparison evaluates hierarchy, state semantics, surfaces and interaction structure rather than forcing mock values into production.

## Visual fidelity

- Layout and spacing: the 192px navigation rail, compact top status bar, six-tab information architecture, KPI rows, master/detail layouts, thin dividers and evidence-console hierarchy match the reference direction. Long candidate/model pages extend below the first viewport because production exposes full score and gate evidence.
- Typography: Noto Sans SC plus the mono data face preserve the reference hierarchy. Production density is intentionally tighter than the illustrative Figma rows so complete market evidence remains scannable without hiding fields; headings, labels and numerical data remain visually distinct.
- Color and surfaces: white and cool-gray surfaces, navy text, blue primary actions, and restrained positive/warning/negative states use shared tokens. No gradients, decorative blobs, CSS illustrations or placeholder imagery were introduced.
- Icons: Phosphor icons are used consistently for navigation, health states and actions; no hand-drawn SVG substitutes are present.
- Copy: `NO_VALID_PICK`, `RESEARCH_ONLY`, `EXECUTABLE_REVIEW`, automatic evidence, manual evidence and model signals are explicitly separated. Recommendation scores are never labelled as probabilities.

## State and interaction checks

- All six tabs switch to exactly one visible `tabpanel`; hash, title and selected navigation state stay synchronized.
- Today → “查看阻断原因” opens Data Health; Today → research/executable CTA opens the matching market and candidate detail.
- Candidate market, risk, route and search controls update the list; single-market order remains the snapshot order while the all-market view uses the documented research-priority sort.
- Event type/market/direction/search filters keep the detail pane inside the filtered result set. `model_signal` without a URL renders a disabled “没有可验证原文链接” button instead of a fabricated homepage link.
- Automatic official evidence is shown before manual pending-ingestion evidence and model signals. Manual evidence never contributes to the automatic evidence count.
- History archive remains collapsed by default and exposes immutable snapshots on demand.
- READY and NO_VALID branches were checked against the strict contract. READY resolves and displays the executable candidate plus calibrated probability, net utility, costs, tail risk and matching automatic evidence; malformed or incomplete contracts fail closed to `NO_VALID_PICK`.
- Browser console: no warnings or errors on the final local pass.

## Responsive and accessibility checks

- At `390 × 844`, all six tabs are reachable from the horizontally scrollable tab rail and every page reports `document.scrollWidth === 390`.
- At `320 × 760`, Candidate, Model and Evidence report `document.scrollWidth === 320`; the long dual-low badge and model definition list wrap without page-level overflow.
- Buttons and filters use semantic controls, tab/panel ARIA relationships are present, inputs have labels, selected states are exposed, and reduced-motion preferences are respected.
- Disabled evidence actions are actual disabled buttons. Status is communicated with text in addition to color.

## Iteration history

1. Initial six-tab pass matched the reference structure but mixed market-level risk with single-stock risk, allowed a filtered event detail to remain outside the active result set, and overflowed the Model page at mobile widths.
2. Market-aware execution states, strict event selection, narrow-grid `minmax(0, 1fr)`, wrapping dual-low headers, automatic-evidence date/HTTPS checks and the server-authoritative evidence count resolved those issues.
3. Final READY/NO_VALID audit added fail-closed contract checks, executable-candidate rendering, READY-aware History/Model copy, automatic evidence prominence and correct empty-link handling. Desktop, 390px and 320px browser passes then completed without P1/P2 findings.

The remaining visible differences are production data density and dynamic content, not broken layout or false decision semantics.

final result: passed
