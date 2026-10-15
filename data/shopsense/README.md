# ShopSense Generated Data

This directory contains the generated ShopSense data used by the current implementation.

- `intake/records.jsonl` is used by the M1 intake evaluation.
- `mock_api/` contains the policy and mock operational tables (CSV) read by the deterministic tools.
- `manifest.json` records generation metadata.
- `eval/` holds the M8 golden tickets and component items; `corpus/` holds the policy documents (markdown is indexed, the PDFs are the original sources).

The files are source data. Runtime mutations should go under `runtime/`, not here.
