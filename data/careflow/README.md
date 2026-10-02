# CareFlow data placeholder

Generate or copy the toolkit output into this directory. No generated data is included.

Expected files after generation:

- `manifest.json`
- `corpus/index.json`
- `corpus/markdown/*.md` and `corpus/pdf/*.pdf`
- `intake/records.jsonl`
- `eval/golden_set.json`
- `mock_api/plans.csv` and `mock_api/plans.json`
- `mock_api/patients.csv` and `mock_api/patients.json`
- `mock_api/appointments.csv` and `mock_api/appointments.json`
- `mock_api/referrals.csv` and `mock_api/referrals.json`

Preserve originals. Use `runtime/mock_api/` for mutable application state.
