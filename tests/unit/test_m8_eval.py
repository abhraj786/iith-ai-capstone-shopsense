"""M8 golden eval runner tests."""

import json

from scripts.run_m8_golden_eval import main


def test_m8_golden_eval_passes(tmp_path, monkeypatch):
    out = tmp_path / "m8_report.json"
    monkeypatch.setattr("sys.argv", ["run_m8_golden_eval.py", "--out", str(out)])

    main()

    report = json.loads(out.read_text())
    assert report["total"] == 20
    assert report["passed"] == 20
    assert report["accuracy"] == 1.0
