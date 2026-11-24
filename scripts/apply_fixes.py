"""Apply the audited corrections in data/fixes.json to data/pass1.json -> data/final.json.

Every change keeps its provenance: which loop found it (lint / verifier / adjudication / sweep /
human), the old value, the new value and why. The page renders this log as-is.

  python scripts/apply_fixes.py
"""
import copy
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def get(rec, path):
    for k in path.split(".")[:-1]:
        rec = rec[k]
    return rec, path.split(".")[-1]


def main():
    recs = {r["id"]: copy.deepcopy(r) for r in json.loads((ROOT / "data" / "pass1.json").read_text(encoding="utf-8"))}
    fixes = json.loads((ROOT / "data" / "fixes.json").read_text(encoding="utf-8"))
    for r in recs.values():
        r["corrections"] = []
    applied = 0
    for fx in fixes:
        r = recs[fx["id"]]
        parent, key = get(r, fx["field"])
        old = parent.get(key)
        if old == fx["to"]:
            continue
        parent[key] = fx["to"]
        r["corrections"].append({"field": fx["field"], "from": old, "to": fx["to"],
                                 "source": fx["source"], "reason": fx["reason"],
                                 **({"evidence": fx["evidence"]} if fx.get("evidence") else {})})
        applied += 1
    out = sorted(recs.values(), key=lambda r: r["id"])
    (ROOT / "data" / "final.json").write_text(json.dumps(out, indent=2), encoding="utf-8")
    touched = sum(1 for r in out if r["corrections"])
    print(f"applied {applied} field corrections across {touched} apps -> data/final.json")


if __name__ == "__main__":
    main()
