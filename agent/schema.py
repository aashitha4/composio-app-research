"""Shared enums (imported by the agent and by the key-free scripts)."""

ENUMS = {
    "auth": ["oauth2", "api_key", "bearer_token", "basic", "jwt", "hmac_signature", "none", "other"],
    "access": ["self_serve_free", "self_serve_trial", "paid_plan", "approval_required",
               "partner_gated", "no_public_api"],
    "api_style": ["rest", "graphql", "soap", "websocket", "grpc", "sdk_only", "cli_only", "none"],
    "breadth": ["broad", "moderate", "narrow", "none"],
    "mcp": ["official", "community_only", "none_found"],
    "yn": ["yes", "no", "unknown"],
    "verdict": ["ready", "ready_with_caveats", "blocked"],
    "blocker_type": ["none", "app_review", "paid_plan", "partnership", "no_api", "self_hosted_only",
                     "per_tenant_setup", "local_tool", "other"],
    "confidence": ["high", "medium", "low"],
}

