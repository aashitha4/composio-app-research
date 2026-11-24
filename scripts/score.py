"""Score each pass against adjudicated ground truth. No API keys needed.

Ground truth lives in data/verify/adjudication.json: one entry per (app, field) checked, with the
value settled by the independent verifier + doc/browser re-check. The blind human spot-check is
reported separately (data/verify/human.json) and does not feed these scores.

  python scripts/score.py     # prints a table, writes data/verify/scores.json
"""
import csv
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FIELDS = ["auth_primary", "access", "api_style", "official_mcp", "verdict"]


def primary(v):
    return v[0] if isinstance(v, list) and v else v


def load_pass0():
    with open(ROOT / "data" / "pass0" / "closed_book.tsv", encoding="utf-8") as f:
        return {int(r["id"]): r for r in csv.DictReader(f, delimiter="\t")}


def main():
    passes = {
        "pass0_closed_book": load_pass0(),
        "pass1_grounded": {r["id"]: r for r in json.loads((ROOT / "data" / "pass1.json").read_text(encoding="utf-8"))},
        "final": {r["id"]: r for r in json.loads((ROOT / "data" / "final.json").read_text(encoding="utf-8"))},
    }
    truth = json.loads((ROOT / "data" / "verify" / "adjudication.json").read_text(encoding="utf-8"))
    scores = {}
    for sample in ("calibration", "holdout"):
        items = [t for t in truth if t["sample"] == sample]
        if not items:
            continue
        n_uns = sum(bool(t.get("unsettled")) for t in items)
        scores[sample] = {"n_fields": len(items), "n_apps": len({t["id"] for t in items}), "n_unsettled": n_uns}
        for name, data in passes.items():
            # conservative: a check the docs could not settle never counts as a hit
            hits = [(not t.get("unsettled")) and primary(data[t["id"]][t["field"]]) in t["truth_accept"] for t in items]
            settled = [h for h, t in zip(hits, items) if not t.get("unsettled")]
            by_field = {}
            for f in FIELDS:
                fh = [h for h, t in zip(hits, items) if t["field"] == f]
                if fh:
                    by_field[f] = round(100 * sum(fh) / len(fh), 1)
            scores[sample][name] = {"accuracy": round(100 * sum(hits) / len(hits), 1),
                                    "accuracy_settled": round(100 * sum(settled) / len(settled), 1) if settled else None,
                                    "correct": sum(hits), "by_field": by_field}
    (ROOT / "data" / "verify" / "scores.json").write_text(json.dumps(scores, indent=2), encoding="utf-8")
    for sample, s in scores.items():
        print(f"\n{sample}: {s['n_apps']} apps x fields = {s['n_fields']} checks")
        for name in passes:
            if name in s:
                print(f"  {name:<20} {s[name]['accuracy']:>5}%  (settled-only {s[name]['accuracy_settled']}%)   {s[name]['by_field']}")


if __name__ == "__main__":
    main()
