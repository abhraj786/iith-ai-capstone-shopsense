# LexOps data placeholder

Generate or copy the toolkit output into this directory. No generated data is included.

Expected files after generation:

- `manifest.json`
- `corpus/index.json`
- `corpus/markdown/*.md` and `corpus/pdf/*.pdf`
- `intake/records.jsonl`
- `eval/golden_set.json`
- `mock_api/counterparties.csv` and `mock_api/counterparties.json`
- `mock_api/contracts.csv` and `mock_api/contracts.json`
- `mock_api/signature_requests.csv` and `mock_api/signature_requests.json`

Preserve originals. Use `runtime/mock_api/` for mutable application state.
