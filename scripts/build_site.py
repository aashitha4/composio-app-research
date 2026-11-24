"""Build site/index.html (the case-study page) from the data files. No API keys needed.

  python scripts/build_site.py

Everything numeric on the page is computed here or in the page's JS from data/final.json and
data/verify/*, so the prose cannot drift from the data.
"""
import csv
import json
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
D = ROOT / "data"


def jload(p, default=None):
    p = D / p
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else default


def main():
    final = jload("final.json")
    pass1 = {r["id"]: r for r in jload("pass1.json")}
    with open(D / "pass0" / "closed_book.tsv", encoding="utf-8") as f:
        pass0 = {int(r["id"]): r for r in csv.DictReader(f, delimiter="\t")}

    n = len(final)
    c = lambda k: Counter((r[k][0] if isinstance(r[k], list) else r[k]) for r in final)
    auth, access, verdict, blocker, mcp = c("auth_primary"), c("access"), c("verdict"), c("blocker_type"), c("official_mcp")
    bycat = defaultdict(list)
    for r in final:
        bycat[r["category"]].append(r)
    free_share = {k: sum(r["access"] == "self_serve_free" for r in v) for k, v in bycat.items()}
    best = sorted(free_share.items(), key=lambda kv: -kv[1])
    worst = sorted(free_share.items(), key=lambda kv: kv[1])
    oauth_any = sum("oauth2" in r["auth_methods"] for r in final)
    keyish = ("api_key", "bearer_token", "basic", "hmac_signature")
    dual = sum("oauth2" in r["auth_methods"] and any(m in r["auth_methods"] for m in keyish) for r in final)
    nonoauth_cats = [k for k, v in bycat.items() if sum(r["auth_primary"] == "oauth2" for r in v) <= 2]

    stats = dict(
        n=n, oauth_primary=auth["oauth2"], oauth_any=oauth_any, apikey_primary=auth["api_key"], dual=dual,
        ready=verdict["ready"], caveats=verdict["ready_with_caveats"], blocked=verdict["blocked"],
        free=access["self_serve_free"], trial=access["self_serve_trial"], approval=access["approval_required"],
        paid=access["paid_plan"], partner=access["partner_gated"], nopublic=access.get("no_public_api", 0),
        app_review=blocker["app_review"], paid_blk=blocker["paid_plan"], partnership=blocker["partnership"],
        mcp_official=mcp["official"], mcp_comm=mcp["community_only"], mcp_none=mcp["none_found"],
        best_cats=best[:3], worst_cats=worst[:3], nonoauth_cats=nonoauth_cats,
    )

    corrections = [{"id": r["id"], "app": r["app"], **cx} for r in final for cx in r.get("corrections", [])]
    payload = {
        "records": final,
        "pass0": {i: {k: v for k, v in r.items() if k != "id"} for i, r in pass0.items()},
        "pass1_changed": {r["id"]: [cx["field"] for cx in r.get("corrections", [])] for r in final},
        "stats": stats,
        "insights": jload("insights.json", {}),
        "scores": jload("verify/scores.json", {}),
        "samples": jload("verify/samples.json", {}),
        "adjudication": jload("verify/adjudication.json", []),
        "corrections": corrections,
        "lint_history": jload("verify/lint_history.json", []),
        "linkcheck": (jload("verify/linkcheck-final.json") or jload("verify/linkcheck-pass1.json") or {}).get("summary", {}),
        "browser": jload("verify/browser-linkcheck.json", {}),
        "human": jload("verify/human.json", {"status": "pending", "rows": [], "lede": "Not done yet. Run <code>python scripts/human.py make</code>, check each page by hand, then <code>python scripts/human.py ingest</code>."}),
        "agent_run": jload("verify/agent_run.json", {}),
    }
    tpl = (ROOT / "site" / "template.html").read_text(encoding="utf-8")
    blob = json.dumps(payload, ensure_ascii=False).replace("</", "<\\/")
    html = tpl.replace("/*__DATA__*/{}", blob)
    (ROOT / "site" / "index.html").write_text(html, encoding="utf-8")
    (ROOT / "site" / "dataset.json").write_text(json.dumps(final, indent=1, ensure_ascii=False), encoding="utf-8")
    print(f"site/index.html written ({len(html)//1024} KB); stats: { {k: v for k, v in stats.items() if not isinstance(v, list)} }")


if __name__ == "__main__":
    main()
