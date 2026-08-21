# Third-Party Notices

Stock Scoring Kit contains a portable JavaScript implementation adapted from
the stock-screening factor and risk model integrated into
`daily_stock_analysis`.

## AlphaSift

- Project: AlphaSift
- Source: <https://github.com/ZhuLinsen/alphasift>
- Referenced revision: `9f522747caafd3c0b1ddb7e14d5cf44c8580b6cf`
- License: Apache License 2.0

The relevant `daily_stock_analysis` screening implementation identifies itself
as derived from this AlphaSift revision and licensed under Apache-2.0.

## daily_stock_analysis screening integration

- Project: daily_stock_analysis
- Source: <https://github.com/ZhuLinsen/daily_stock_analysis>
- Referenced revision: `cfd6b0a5fb9c57685dc2b02ca059fa88d8eff8ec`
- Relevant source scope: `src/services/screening/**/*.py` and
  `src/services/screening/strategies/*.yaml`
- License for that source scope: Apache License 2.0

The implementation in this package has been rewritten in JavaScript, reduced
to a deterministic and browser-portable API, and modified for embedding in
other projects. Generated files in `dist/` retain an attribution banner.

A copy of the applicable license is included at
`LICENSES/Apache-2.0-AlphaSift.txt`.
