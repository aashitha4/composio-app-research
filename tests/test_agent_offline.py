"""Offline test of agent/research.py: a fake Claude client checks the tool loop (pause_turn resume),
Composio MCP passthrough, structured-output conversion and the evidence guard. No network, no API key.

  python tests/test_agent_offline.py
"""
import json, sys, types, shutil
from pathlib import Path
from types import SimpleNamespace as NS
ROOT = Path(__file__).resolve().parents[1]; sys.path.insert(0, str(ROOT / "agent"))
import research
calls = []
REC = {"id": 41, "app": "Shopify", "category": "Ecommerce", "one_liner": "x", "auth_methods": ["oauth2"], "auth_primary": "oauth2",
       "auth_notes": "", "access": "approval_required", "access_notes": "", "api_style": ["graphql"], "api_breadth": "broad",
       "api_breadth_notes": "", "official_mcp": "official", "mcp_notes": "", "webhooks": "yes", "sandbox": "yes", "verdict": "ready_with_caveats",
       "blocker": "App Store review", "blocker_type": "app_review",
       "evidence": {"docs": "https://shopify.dev/docs/api", "auth": "https://shopify.dev/docs/apps/auth/", "access": "https://never-fetched.example/x", "mcp": None},
       "confidence": "high", "uncertain_fields": [], "notes": ""}
class Beta:
    def __init__(s): s.n = 0
    def create(s, **kw):
        calls.append(("beta", sorted(kw))); s.n += 1
        fetch = NS(type="web_fetch_tool_result", content=NS(url="https://shopify.dev/docs/api"))
        search = NS(type="web_search_tool_result", content=[NS(url="https://shopify.dev/docs/apps/auth")])
        if s.n == 1: return NS(stop_reason="pause_turn", content=[search])
        return NS(stop_reason="end_turn", content=[fetch, NS(type="text", text="notes...")])
class Msgs:
    def create(s, **kw):
        calls.append(("msg", sorted(kw))); assert kw["output_config"]["format"]["type"] == "json_schema"
        return NS(content=[NS(type="text", text=json.dumps(REC))])
class Client:
    def __init__(s): s.beta = NS(messages=Beta()); s.messages = Msgs()
research.anthropic = types.SimpleNamespace(Anthropic=Client)
out = ROOT / "data" / "pass1" / "app-041.json"
research.main(["research", "--ids", "41", "--composio-mcp-url", "https://example.invalid/mcp"])
rec = json.loads(out.read_text(encoding="utf-8")); out.unlink()
assert [c[0] for c in calls] == ["beta", "beta", "msg"], calls
assert "mcp_servers" in calls[0][1] and "fallbacks" in calls[0][1]
assert rec["evidence_unverified"] == ["access"] and rec["confidence"] == "low"
print("calls:", [c[0] for c in calls])
print("beta kwargs:", calls[0][1])
print("unverified evidence:", rec.get("evidence_unverified"), "| confidence:", rec["confidence"])
print("OK")
