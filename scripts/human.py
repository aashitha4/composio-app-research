"""Human spot-check, the one loop an agent cannot do for you.

  python scripts/human.py make      # draws 12 random (app, field) pairs -> data/verify/human-checklist.csv
  (open each URL, read the page yourself, fill the `human_value` column; add a note if useful)
  python scripts/human.py ingest    # -> data/verify/human.json, rendered on the page

The checklist is blind (it does not show the agent's answer). `match` is computed at ingest time.
"""
import csv
import json
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CSV = ROOT / "data" / "verify" / "human-checklist.csv"
OUT = ROOT / "data" / "verify" / "human.json"
FIELDS = {"auth_primary": "auth", "access": "access", "official_mcp": "mcp", "verdict": "access"}
COLS = ["app", "field", "url_to_check", "allowed_values", "human_value", "note"]  # blind: no agent value
ALLOWED = {
    "auth_primary": "oauth2 | api_key | bearer_token | basic | jwt | hmac_signature | none | other",
    "access": "self_serve_free | self_serve_trial | paid_plan | approval_required | partner_gated | no_public_api",
    "official_mcp": "official | community_only | none_found",
    "verdict": "ready | ready_with_caveats | blocked",
}


def make(n=12, seed=2026):
    recs = json.loads((ROOT / "data" / "final.json").read_text(encoding="utf-8"))
    rng = random.Random(seed)
    picks, seen = [], set()
    while len(picks) < n:
        r = rng.choice(recs)
        f = rng.choice(list(FIELDS))
        url = r["evidence"].get(FIELDS[f]) or r["evidence"].get("docs")
        if (r["id"], f) in seen or not url:
            continue
        seen.add((r["id"], f))
        picks.append({"app": r["app"], "field": f, "url_to_check": url,
                      "allowed_values": ALLOWED[f], "human_value": "", "note": ""})
    with open(CSV, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=COLS)
        w.writeheader()
        w.writerows(picks)
    print(f"wrote {CSV} ({n} rows, seed {seed})")


def ingest():
    with open(CSV, newline="", encoding="utf-8") as fh:
        rows = [r for r in csv.DictReader(fh)]
    todo = [r for r in rows if not r["human_value"].strip()]
    if todo:
        sys.exit(f"{len(todo)} rows still have no human_value; fill them first")
    final = {r["app"]: r for r in json.loads((ROOT / "data" / "final.json").read_text(encoding="utf-8"))}
    out = []
    for r in rows:
        agent = final[r["app"]][r["field"]]
        human = r["human_value"].strip()
        out.append({"app": r["app"], "field": r["field"], "agent": agent, "human": human,
                    "match": human == agent, "url": r["url_to_check"], "note": r["note"]})
    hits = sum(o["match"] for o in out)
    lede = (f"I opened each page myself and recorded what it says, without looking at the agent's value first. "
            f"{hits} of {len(out)} fields matched the agent. Rows are a seeded random draw (seed 2026) from all 100 apps.")
    OUT.write_text(json.dumps({"status": "done", "lede": lede, "hits": hits, "n": len(out), "rows": out}, indent=1), encoding="utf-8")
    print(lede)


if __name__ == "__main__":
    {"make": make, "ingest": ingest}[sys.argv[1] if len(sys.argv) > 1 else "make"]()
