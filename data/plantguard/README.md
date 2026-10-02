# PlantGuard data placeholder

Generate or copy the toolkit output into this directory. No generated data is included.

Expected files after generation:

- `manifest.json`
- `corpus/index.json`
- `corpus/markdown/*.md` and `corpus/pdf/*.pdf`
- `intake/records.jsonl`
- `eval/golden_set.json`
- `mock_api/assets.csv` and `mock_api/assets.json`
- `mock_api/telemetry.csv` and `mock_api/telemetry.json`
- `mock_api/work_orders.csv` and `mock_api/work_orders.json`
- `mock_api/inventory.csv` and `mock_api/inventory.json`

Preserve originals. Use `runtime/mock_api/` for mutable application state.
