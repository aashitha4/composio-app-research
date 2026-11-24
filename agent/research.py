"""App-research agent: researcher -> evidence guard -> lint -> independent verifier.

Usage
  python agent/research.py research --ids 1-100            # writes data/pass1/app-XXX.json
  python agent/research.py research --ids 7 --composio-mcp-url "$COMPOSIO_MCP_URL"
  python agent/research.py verify --sample 30 --seed 42      # writes data/verify/agent-verifier.json

Requires ANTHROPIC_API_KEY (or an `ant auth login` profile). Lint, scoring and the site
build need no keys: see scripts/.
"""
from __future__ import annotations

import argparse
import csv
import json
import random
import sys
from pathlib import Path
from urllib.parse import urldefrag

import anthropic

from schema import ENUMS

ROOT = Path(__file__).resolve().parents[1]
PROMPTS = ROOT / "agent" / "prompts"
MODEL = "claude-opus-5-5"
BETAS = ["server-side-fallback-2026-07-01"]  # re-run a refused request on a fallback model

WEB_TOOLS = [
    {"type": "web_search_20260209", "name": "web_search", "max_uses": 8},
    {"type": "web_fetch_20260209", "name": "web_fetch", "max_uses": 10},
]



def _s(enum=None):
    return {"type": "string", **({"enum": enum} if enum else {})}


URL_OR_NULL = {"anyOf": [{"type": "string"}, {"type": "null"}]}
RECORD_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["id", "app", "category", "one_liner", "auth_methods", "auth_primary", "auth_notes",
                 "access", "access_notes", "api_style", "api_breadth", "api_breadth_notes",
                 "official_mcp", "mcp_notes", "webhooks", "sandbox", "verdict", "blocker",
                 "blocker_type", "evidence", "confidence", "uncertain_fields", "notes"],
    "properties": {
        "id": {"type": "integer"}, "app": _s(), "category": _s(), "one_liner": _s(),
        "auth_methods": {"type": "array", "items": _s(ENUMS["auth"])},
        "auth_primary": _s(ENUMS["auth"]), "auth_notes": _s(),
        "access": _s(ENUMS["access"]), "access_notes": _s(),
        "api_style": {"type": "array", "items": _s(ENUMS["api_style"])},
        "api_breadth": _s(ENUMS["breadth"]), "api_breadth_notes": _s(),
        "official_mcp": _s(ENUMS["mcp"]), "mcp_notes": _s(),
        "webhooks": _s(ENUMS["yn"]), "sandbox": _s(ENUMS["yn"]),
        "verdict": _s(ENUMS["verdict"]), "blocker": _s(), "blocker_type": _s(ENUMS["blocker_type"]),
        "evidence": {
            "type": "object", "additionalProperties": False,
            "required": ["docs", "auth", "access", "mcp"],
            "properties": {"docs": URL_OR_NULL, "auth": URL_OR_NULL, "access": URL_OR_NULL,
                           "mcp": URL_OR_NULL},
        },
        "confidence": _s(ENUMS["confidence"]),
        "uncertain_fields": {"type": "array", "items": _s()},
        "notes": _s(),
    },
}

VERIFY_FIELDS = ["auth_primary", "access", "api_style", "official_mcp", "verdict"]
VERDICT_SCHEMA = {
    "type": "object", "additionalProperties": False,
    "required": ["id", "app", "checks"],
    "properties": {
        "id": {"type": "integer"}, "app": _s(),
        "checks": {"type": "array", "items": {
            "type": "object", "additionalProperties": False,
            "required": ["field", "claimed", "agree", "correct_value", "evidence_url", "reason"],
            "properties": {"field": _s(VERIFY_FIELDS), "claimed": _s(), "agree": {"type": "boolean"},
                           "correct_value": _s(), "evidence_url": URL_OR_NULL, "reason": _s()},
        }},
    },
}


def load_apps():
    with open(ROOT / "data" / "apps.csv", newline="", encoding="utf-8") as f:
        return [{**r, "id": int(r["id"])} for r in csv.DictReader(f)]


def parse_ids(spec: str):
    out = set()
    for part in spec.split(","):
        a, _, b = part.partition("-")
        out.update(range(int(a), int(b or a) + 1))
    return out


def norm(url: str) -> str:
    return urldefrag(url)[0].rstrip("/").lower()


def run_tool_loop(client, system: str, user: str, mcp_url: str | None):
    """Run one web-grounded turn. Returns (final_text, fetched_urls)."""
    tools, extra, betas = list(WEB_TOOLS), {}, list(BETAS)
    if mcp_url:  # Composio MCP server (e.g. a Tool Router URL exposing Firecrawl / Exa search)
        betas.append("mcp-client-2025-11-20")
        extra["mcp_servers"] = [{"type": "url", "url": mcp_url, "name": "composio"}]
        tools.append({"type": "mcp_toolset", "mcp_server_name": "composio"})
    messages = [{"role": "user", "content": user}]
    fetched: set[str] = set()
    for _ in range(8):  # pause_turn resumes
        resp = client.beta.messages.create(
            model=MODEL, max_tokens=16000, system=system, messages=messages, tools=tools,
            betas=betas, fallbacks="default", output_config={"effort": "high"}, **extra)
        for block in resp.content:
            if block.type == "web_fetch_tool_result" and getattr(block.content, "url", None):
                fetched.add(norm(block.content.url))
            elif block.type == "web_search_tool_result" and isinstance(block.content, list):
                fetched.update(norm(r.url) for r in block.content if getattr(r, "url", None))
        if resp.stop_reason == "pause_turn":
            messages.append({"role": "assistant", "content": resp.content})
            continue
        if resp.stop_reason == "refusal":
            raise RuntimeError("model declined the request")
        text = "\n".join(b.text for b in resp.content if b.type == "text")
        return text, fetched
    raise RuntimeError("tool loop did not finish")


def to_json(client, notes: str, schema: dict, instruction: str):
    resp = client.messages.create(
        model=MODEL, max_tokens=8000,
        messages=[{"role": "user", "content": f"{instruction}\n\n<notes>\n{notes}\n</notes>"}],
        output_config={"format": {"type": "json_schema", "schema": schema}, "effort": "low"})
    return json.loads(next(b.text for b in resp.content if b.type == "text"))


def evidence_guard(rec: dict, fetched: set[str]) -> dict:
    """Loop 1: every cited URL must be one the agent actually retrieved this run."""
    bad = [k for k, u in rec["evidence"].items() if u and norm(u) not in fetched]
    if bad:
        rec["evidence_unverified"] = bad
        rec["confidence"] = "low"
        rec["uncertain_fields"] = sorted(set(rec["uncertain_fields"]) | {f"evidence.{k}" for k in bad})
    return rec


def cmd_research(args):
    client = anthropic.Anthropic()
    system = (PROMPTS / "researcher.md").read_text(encoding="utf-8")
    out_dir = ROOT / "data" / "pass1"
    out_dir.mkdir(parents=True, exist_ok=True)
    for app in [a for a in load_apps() if a["id"] in parse_ids(args.ids)]:
        user = (f"Research app #{app['id']}: {app['app']} (category: {app['category']}; "
                f"hint: {app['hint']}). Fetch the official docs, then write your findings with URLs.")
        try:
            notes, fetched = run_tool_loop(client, system, user, args.composio_mcp_url)
            rec = to_json(client, notes, RECORD_SCHEMA,
                          "Convert these research notes into the record schema. Copy URLs exactly. "
                          f"Use id={app['id']}, app={app['app']!r}, category={app['category']!r}.")
            rec = evidence_guard(rec, fetched)
        except Exception as e:  # keep going; a failed app is a finding, not a crash
            rec = {"id": app["id"], "app": app["app"], "error": str(e)}
        (out_dir / f"app-{app['id']:03d}.json").write_text(json.dumps(rec, indent=2), encoding="utf-8")
        print(f"[{app['id']:>3}] {app['app']}: {rec.get('verdict', rec.get('error'))}")


def cmd_verify(args):
    """Loop 3: independent verifier re-derives key fields from docs for a random sample."""
    client = anthropic.Anthropic()
    system = (PROMPTS / "verifier.md").read_text(encoding="utf-8")
    final = {r["id"]: r for r in json.loads((ROOT / "data" / "pass1.json").read_text(encoding="utf-8"))}
    ids = sorted(random.Random(args.seed).sample(sorted(final), args.sample))
    results = []
    for i in ids:
        claim = {k: final[i][k] for k in ["id", "app", *VERIFY_FIELDS]}
        notes, _ = run_tool_loop(client, system, "Verify this record:\n" + json.dumps(claim), None)
        results.append(to_json(client, notes, VERDICT_SCHEMA, "Convert the verification notes to JSON."))
        print(f"[{i:>3}] verified")
    out = ROOT / "data" / "verify" / "agent-verifier.json"
    out.write_text(json.dumps({"seed": args.seed, "ids": ids, "results": results}, indent=2), encoding="utf-8")


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("research")
    r.add_argument("--ids", default="1-100")
    r.add_argument("--composio-mcp-url", default=None)
    v = sub.add_parser("verify")
    v.add_argument("--sample", type=int, default=30)
    v.add_argument("--seed", type=int, default=42)
    args = p.parse_args(argv)
    {"research": cmd_research, "verify": cmd_verify}[args.cmd](args)


if __name__ == "__main__":
    sys.exit(main())
