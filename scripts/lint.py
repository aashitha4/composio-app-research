"""Loop 2 — deterministic lint. Merges data/pass1/*.json -> data/pass1.json and flags records whose
fields contradict each other or the schema. No API keys needed.

  python scripts/lint.py            # writes data/pass1.json and data/verify/lint.json
  python scripts/lint.py --final    # lints data/final.json (after fixes)
"""
import json
import sys
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "agent"))
from schema import ENUMS  # noqa: E402

THIRD_PARTY = ("medium.com", "reddit.com", "stackoverflow.com", "zapier.com", "rollout.com",
               "merge.dev", "apitracker.io", "g2.com", "capterra.com", "nango.dev", "pipedream.com")


def lint(r):
    issues = []
    def bad(f, enum):
        v = r.get(f)
        vals = v if isinstance(v, list) else [v]
        if not vals or any(x not in ENUMS[enum] for x in vals):
            issues.append(f"schema: {f}={v!r}")
    for f, e in [("auth_methods", "auth"), ("auth_primary", "auth"), ("access", "access"),
                 ("api_style", "api_style"), ("api_breadth", "breadth"), ("official_mcp", "mcp"),
                 ("verdict", "verdict"), ("blocker_type", "blocker_type"), ("confidence", "confidence")]:
        bad(f, e)
    if r.get("auth_primary") not in (r.get("auth_methods") or []):
        issues.append("auth_primary not in auth_methods")
    v, a, bt = r.get("verdict"), r.get("access"), r.get("blocker_type")
    if v == "ready" and a in ("partner_gated", "no_public_api"):
        issues.append(f"verdict=ready but access={a}")
    if v == "blocked" and a in ("self_serve_free",) and bt not in ("no_api", "local_tool"):
        issues.append("verdict=blocked but access=self_serve_free")
    if v == "ready" and bt != "none":
        issues.append(f"verdict=ready but blocker_type={bt}")
    if v != "ready" and bt == "none":
        issues.append(f"verdict={v} but blocker_type=none")
    # v2 rules (added after v1 flagged only 1/100): access and blocker must tell the same story
    expected = {"approval_required": "app_review", "paid_plan": "paid_plan", "partner_gated": "partnership"}
    if a in expected and v != "blocked" and bt != expected[a]:
        issues.append(f"access={a} but blocker_type={bt} (expected {expected[a]})")
    if a in ("self_serve_free", "self_serve_trial") and bt in ("partnership",):
        issues.append(f"access={a} but blocker_type={bt}")
    if a == "self_serve_free" and bt == "paid_plan":
        issues.append("access=self_serve_free but blocker_type=paid_plan")
    if "cli_only" in (r.get("api_style") or []) and a != "self_serve_free" and "rest" not in r["api_style"]:
        issues.append("local CLI tool: convention is access=self_serve_free + blocker_type=local_tool")
    if r.get("official_mcp") == "official" and r.get("confidence") == "low":
        issues.append("official MCP claimed on a low-confidence record")
    if a == "no_public_api" and "none" not in (r.get("api_style") or []) and "cli_only" not in (r.get("api_style") or []):
        issues.append("access=no_public_api but api_style lists an API")
    ev = r.get("evidence") or {}
    if r.get("official_mcp") == "official" and not ev.get("mcp"):
        issues.append("official_mcp=official without mcp evidence URL")
    for k in ("docs", "auth", "access"):
        if not ev.get(k):
            issues.append(f"missing evidence.{k}")
    for k, u in ev.items():
        if u and urlparse(u).netloc.removeprefix("www.").endswith(THIRD_PARTY):
            issues.append(f"evidence.{k} is third-party ({urlparse(u).netloc})")
    return issues


def main():
    if "--final" in sys.argv:  # lint the corrected dataset instead of re-merging pass 1
        recs = json.loads((ROOT / "data" / "final.json").read_text(encoding="utf-8"))
        report = {r["id"]: {"app": r["app"], "issues": lint(r)} for r in recs}
        flagged = {k: v for k, v in report.items() if v["issues"]}
        (ROOT / "data" / "verify" / "lint-final.json").write_text(json.dumps(flagged, indent=2), encoding="utf-8")
        print(f"{len(recs)} final records, {len(flagged)} flagged")
        for k, v in flagged.items():
            print(f"  #{k} {v['app']}: {'; '.join(v['issues'])}")
        return
    recs = []
    for f in sorted((ROOT / "data" / "pass1").glob("*.json")):
        data = json.loads(f.read_text(encoding="utf-8"))
        recs.extend(data if isinstance(data, list) else [data])
    recs.sort(key=lambda r: r["id"])
    ids = [r["id"] for r in recs]
    assert ids == list(range(1, 101)), f"expected ids 1..100, got {len(ids)} records"
    (ROOT / "data" / "pass1.json").write_text(json.dumps(recs, indent=2), encoding="utf-8")
    report = {r["id"]: {"app": r["app"], "issues": lint(r)} for r in recs}
    flagged = {k: v for k, v in report.items() if v["issues"]}
    (ROOT / "data" / "verify" / "lint.json").write_text(json.dumps(flagged, indent=2), encoding="utf-8")
    print(f"{len(recs)} records, {len(flagged)} flagged")
    for k, v in flagged.items():
        print(f"  #{k} {v['app']}: {'; '.join(v['issues'])}")


if __name__ == "__main__":
    main()
