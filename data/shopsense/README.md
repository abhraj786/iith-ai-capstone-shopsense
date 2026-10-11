# ShopSense Generated Data

This directory contains the generated ShopSense data used by the current implementation.

- `intake/records.jsonl` is used by the M1 intake evaluation.
- `mock_api/` contains policy and mock operational tables used by deterministic checks.
- `manifest.json` records generation metadata.
- `eval/golden_set.json` and `corpus/` are retained for later ShopSense milestones.

The files are source data. Runtime mutations should go under `runtime/`, not here.
