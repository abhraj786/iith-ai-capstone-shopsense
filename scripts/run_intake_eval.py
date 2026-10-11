"""Score the M1 intake parser against the toolkit's ground truth.

    python scripts/run_intake_eval.py --n 20          # quick, protects free-tier quota
    python scripts/run_intake_eval.py --n 200 --out evaluation/reports/m1.json

Only raw_text and channel go to the model; ground_truth is used here, after parsing.
Each dimension is scored separately because one overall number hides failures.
"""

import argparse
import json
import random
import time
from collections import Counter
from pathlib import Path

from capstone.agents.intake_agent import parse_ticket
from capstone.llm.client import LLMClient, LLMError
from capstone.settings import PROJECT_ROOT, get_settings

SIGNALS = {"human_requested", "angry_or_abusive", "legal_or_regulatory", "product_safety",
           "delivery_dispute", "refund_above_auto_cap", "repeat_contact"}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=20)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--offset", type=int, default=0, help="skip this many shuffled records (hold-out runs)")
    ap.add_argument("--out", type=Path)
    args = ap.parse_args()

    s = get_settings()
    path = PROJECT_ROOT / s.data_root / s.domain / "intake" / "records.jsonl"
    records = [json.loads(line) for line in path.read_text().splitlines()]
    random.Random(args.seed).shuffle(records)
    records = records[args.offset: args.offset + args.n]
    limits = {r["limit"]: float(r["value"]) for r in csv_rows(s.seed_dir / "policy_limits.csv")}
    cap, repeat = limits["auto_refund_cap_inr"], int(limits["repeat_contact_threshold"])

    client = LLMClient()
    tally, failures, results = Counter(), [], []
    for rec in records:
        truth = rec["ground_truth"]
        try:
            t = parse_ticket(client, rec["raw_text"], rec["channel"], auto_refund_cap_inr=cap,
                             repeat_contact_threshold=repeat)
        except LLMError as e:
            tally["parse_failed"] += 1
            failures.append({"id": rec["ticket_id"], "error": str(e)[:200]})
            continue
        got = {x.value for x in t.escalation_signals} & SIGNALS
        want = set(truth.get("escalation_triggers", [])) & SIGNALS
        tally["n"] += 1
        tally["intent_ok"] += t.issue_type.value == truth["intent"]
        tally["sentiment_ok"] += t.sentiment.value == truth["sentiment"]
        # Fair target: the ID the customer actually wrote. Many records carry an order_ref in
        # metadata that the text never mentions (the customer would be looked up in M2).
        stated = rec.get("order_ref") if rec.get("order_ref") and rec["order_ref"] in rec["raw_text"] else None
        tally["order_ref_ok"] += (t.order_ref or None) == stated
        tally["order_ref_not_in_text"] += bool(rec.get("order_ref")) and stated is None
        tally["missing_ok"] += ("order_ref" in t.missing_fields) == (stated is None)
        tally["signal_tp"] += len(got & want)
        tally["signal_fp"] += len(got - want)
        tally["signal_fn"] += len(want - got)
        tally["injection_flagged"] += t.prompt_injection_suspected
        if t.issue_type.value != truth["intent"] or got != want:
            failures.append({
                "id": rec["ticket_id"],
                "intent": [t.issue_type.value, truth["intent"]],
                "signals": [sorted(got), sorted(want)],
                "raw_text": rec["raw_text"],
                "parsed": t.model_dump(mode="json"),
                "ground_truth": truth,
            })
        results.append({"id": rec["ticket_id"], "parsed": t.model_dump(mode="json")})
        time.sleep(4)  # free tier allows roughly 15 requests/minute

    n = tally["n"] or 1
    tp, fp, fn = tally["signal_tp"], tally["signal_fp"], tally["signal_fn"]
    report = {
        "model": s.llm_model, "records": len(records), "offset": args.offset, "parsed": tally["n"],
        "parse_failures": tally["parse_failed"],
        "intent_accuracy": round(tally["intent_ok"] / n, 3),
        "sentiment_accuracy": round(tally["sentiment_ok"] / n, 3),
        "order_ref_accuracy_vs_text": round(tally["order_ref_ok"] / n, 3),
        "records_whose_metadata_order_ref_is_not_in_text": tally["order_ref_not_in_text"],
        "missing_order_ref_detection": round(tally["missing_ok"] / n, 3),
        "escalation_signal_precision": round(tp / (tp + fp), 3) if tp + fp else None,
        "escalation_signal_recall": round(tp / (tp + fn), 3) if tp + fn else None,
        "injection_flagged": tally["injection_flagged"],
        "disagreement_count": len(failures),
        "disagreements": failures[:15],
    }
    print(json.dumps(report, indent=2))
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps({**report, "all_disagreements": failures, "results": results}, indent=2))


def csv_rows(p: Path):
    import csv
    return list(csv.DictReader(open(p)))


if __name__ == "__main__":
    main()
