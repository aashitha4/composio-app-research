"""Human spot-check, the one loop an agent cannot do for you.

  python scripts/human.py make      # draws 12 random (app, field) pairs -> data/verify/human-checklist.csv
  (open each URL, read the page yourself, fill the `human_value` column; add a note if useful)
  python scripts/human.py ingest    # -> data/verify/human.json, rendered on the page

  python scripts/human.py fixes-make     # one row per corrected app -> data/verify/fix-review.csv
  (read each change, open the page, fill `your_call` with accept / reject / unsure)
  python scripts/human.py fixes-ingest   # -> data/verify/fix-review.json, shown next to each correction

The spot-check is blind (it does not show the agent's answer); `match` is computed at ingest time.
The fix review cannot be blind: it asks whether each proposed change is right.
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
                    "match": None if human == "unsure" else human == agent, "url": r["url_to_check"], "note": r["note"]})
    hits = sum(o["match"] is True for o in out)
    unsure = sum(o["match"] is None for o in out)
    lede = (f"I opened each page myself and recorded what it says, without seeing the agent's answer first. "
            f"{hits} of {len(out)} fields matched the agent"
            + (f"; {unsure} I could not settle from the page" if unsure else "")
            + ". Rows are a seeded random draw (seed 2026) from all 100 apps.")
    OUT.write_text(json.dumps({"status": "done", "lede": lede, "hits": hits, "n": len(out), "rows": out}, indent=1), encoding="utf-8")
    print(lede)


# ---------- review of the logged fixes (not blind: the reviewer sees the proposed change) ----------
FIX_CSV = ROOT / "data" / "verify" / "fix-review.csv"
FIX_OUT = ROOT / "data" / "verify" / "fix-review.json"
FIX_COLS = ["n", "app", "what_changed", "open_this", "search_for", "question", "your_call", "note"]
CALLS = ("accept", "reject", "unsure")
SWEEP_Q = "Rule: if other customers can't install the app until the vendor reviews it (or installs are capped), access = approval_required, even with a free sandbox. Does this page show such a cap or review step?"
# One review row per app, in walkthrough order. Search phrases were checked against each page on 24 Nov 2026.
FIX_GUIDE = [
    ("HubSpot", "https://developers.hubspot.com/docs/apps/developer-platform/build-apps/manage-apps-in-hubspot", "25", SWEEP_Q + " (Your spot-check note already found the 25-install cap.)"),
    ("Attio", "https://docs.attio.com/rest-api/guides/authentication", "up to 25 workspaces", SWEEP_Q + " (The page says to go past 25 you publish the app; it does not spell out the approval step.)"),
    ("Copper", "https://developer.copper.com/introduction/oauth/index.html", "To register your application", SWEEP_Q + " (Here: are OAuth credentials issued by Copper on request rather than self-serve?)"),
    ("Discord", "https://docs.discord.com/developers/events/gateway", "100+ guilds", SWEEP_Q),
    ("BigCommerce", "https://docs.bigcommerce.com/docs/integrations/apps/guide/types", "Not available to other stores", SWEEP_Q),
    ("Grain", "https://developers.grain.com/authentication.html", "only available to clients", SWEEP_Q),
    ("Twenty", "https://docs.twenty.com/developers/extend/oauth", "External app acting", "Is OAuth the documented method for an external app acting on behalf of a user (so oauth2 is the right primary auth for a toolkit)? The citation and note were updated to match."),
    ("Coda", "https://coda.io/developers/apis/v1", "free of charge", "The API is free and self-serve; users paste a token instead of doing OAuth. Under the definitions, token auth is not a gate (Telegram is 'ready' on the same basis). Do you agree 'ready' fits?"),
    ("GoHighLevel", "https://marketplace.gohighlevel.com/docs/oauth/SandboxAccount.md", "Create App Test Account", "Judgement: HighLevel has no free customer plan, so every customer already pays for HighLevel; developers get sandbox test accounts (the page does not say 'free'). Should 'customers pay for the product' count as a blocker for building the toolkit? Agent says no, so 'ready'."),
    ("fanbasis", "https://commas.com", "Enterprise & APIs", "fanbasis is now Commas. Is there any link to public API docs or MCP setup instructions? If none: accept (API style none, MCP none_found, Zapier citation removed)."),
    ("Sherlock", "https://github.com/sherlock-project/sherlock", "MIT", "It's a free open-source tool you install and run yourself, with no keys. Label: access self_serve_free with blocker 'local tool' (instead of 'no public API'). Does that convention make sense?"),
    ("Binance", "https://developers.binance.com/docs/login/introduction", "close ecosystem partners", "Only the OAuth 'Binance Login' is partner-only; normal API keys are self-serve. So the main blocker is not a partnership (it's 'other': users hand over signed trading keys). Agree?"),
    ("Paygent Connect", "", "", "No page needed. Access was already approval_required (live keys need an approved merchant account); this only makes blocker_type match (app_review). Consistent?"),
    ("Otter AI", "https://otter.ai/pricing", "Otter API", "Is the API only on the Enterprise tier (custom pricing / book a demo)? That's a sales gate, so blocker = partnership rather than paid plan. Check the comparison-table row too."),
]
LONG_TEXT = {"blocker", "auth_notes", "access_notes", "notes"}


def _short(v):
    return json.dumps(v, ensure_ascii=False) if not isinstance(v, str) else v


def fixes_make():
    final = {r["app"]: r for r in json.loads((ROOT / "data" / "final.json").read_text(encoding="utf-8"))}
    apps_with_fixes = {a for a, r in final.items() if r.get("corrections")}
    assert apps_with_fixes == {g[0] for g in FIX_GUIDE}, apps_with_fixes ^ {g[0] for g in FIX_GUIDE}
    rows = []
    for i, (app, url, phrase, q) in enumerate(FIX_GUIDE, 1):
        cx = [c for c in final[app]["corrections"] if c["source"] != "human"]
        short = [f"{c['field']}: {_short(c['from'])} -> {_short(c['to'])}" for c in cx if c["field"] not in LONG_TEXT]
        text = [c["field"] for c in cx if c["field"] in LONG_TEXT]
        rows.append({"n": i, "app": app, "what_changed": "; ".join(short) + (f" (+ {', '.join(text)} text updated)" if text else ""),
                     "open_this": url, "search_for": phrase, "question": q, "your_call": "", "note": ""})
    with open(FIX_CSV, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=FIX_COLS)
        w.writeheader()
        w.writerows(rows)
    print(f"wrote {FIX_CSV} ({len(rows)} apps, {sum(1 for g in FIX_GUIDE for c in final[g[0]]['corrections'] if c['source'] != 'human')} field fixes)")


def fixes_ingest():
    with open(FIX_CSV, newline="", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    bad = [r["app"] for r in rows if r["your_call"].strip() not in CALLS]
    if bad:
        sys.exit(f"your_call must be one of {CALLS}; fix rows: {bad}")
    final = {r["app"]: r for r in json.loads((ROOT / "data" / "final.json").read_text(encoding="utf-8"))}
    agent_fx = lambda app: [c for c in final[app]["corrections"] if c["source"] != "human"]  # what was reviewed
    human_fx = lambda app: [c for c in final[app]["corrections"] if c["source"] == "human"]  # what the review changed
    out = [{"app": r["app"], "call": r["your_call"].strip(), "note": r["note"], "n_fields": len(agent_fx(r["app"])),
            "review_changes": [c["field"] for c in human_fx(r["app"])]} for r in rows]
    k = {c: sum(o["call"] == c for o in out) for c in CALLS}
    nf = sum(o["n_fields"] for o in out)
    nh = sum(len(o["review_changes"]) for o in out)
    reverted = [o["app"] for o in out if o["call"] == "reject" and o["review_changes"]]
    lede = (f"I reviewed every logged fix ({nf} field changes across {len(out)} apps) against its reason and source page. "
            f"This review is not blind, since it shows the proposed change. Accepted {k['accept']} of {len(out)} apps"
            + (f", rejected {k['reject']}" if k["reject"] else "") + (f", unsure about {k['unsure']}" if k["unsure"] else "") + "."
            + (f" Rejected fixes were reverted ({', '.join(reverted)})." if reverted else "")
            + (f" Changes made because of the review are logged with source 'human' ({nh} field changes)." if nh else ""))
    FIX_OUT.write_text(json.dumps({"status": "done", "lede": lede, "counts": k, "n_apps": len(out), "n_fields": nf, "n_review_changes": nh,
                                   "reverted": reverted, "rows": out}, indent=1), encoding="utf-8")
    print(lede)
    pending = [o["app"] for o in out if o["call"] == "reject" and not o["review_changes"]]
    if pending:
        print(f"NOTE: rejected fixes for {pending} are still applied in data/final.json; revert them in data/fixes.json (source 'human').")


if __name__ == "__main__":
    {"make": make, "ingest": ingest, "fixes-make": fixes_make, "fixes-ingest": fixes_ingest}[sys.argv[1] if len(sys.argv) > 1 else "make"]()
