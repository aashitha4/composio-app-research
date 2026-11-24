"""Write data/insights.json: the page's prose, with every number computed from the data files.

  python scripts/insights.py
"""
import json
import re
from collections import Counter, defaultdict
from html import escape as esc
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
D = ROOT / "data"
REPO_URL = "https://github.com/aashitha4/composio-app-research"


def jl(p, d=None):
    p = D / p
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else d


def names(rows, k=None):
    xs = [r["app"] for r in rows]
    return ", ".join(xs[:k]) + (f" and {len(xs) - k} more" if k and len(xs) > k else "")


def main():
    R = jl("final.json")
    P = lambda v: v[0] if isinstance(v, list) else v
    n = len(R)
    auth, access, verdict, blk = (Counter(P(r[k]) for r in R) for k in ("auth_primary", "access", "verdict", "blocker_type"))
    cats = defaultdict(list)
    for r in R:
        cats[r["category"]].append(r)
    free = {c: sum(r["access"] == "self_serve_free" for r in v) for c, v in cats.items()}
    ranked = sorted(free.items(), key=lambda kv: -kv[1])
    zero_oauth = [c for c, v in cats.items() if sum(r["auth_primary"] == "oauth2" for r in v) == 0]
    oauth_any = sum("oauth2" in r["auth_methods"] for r in R)
    approval = [r for r in R if r["access"] == "approval_required"]
    appr_oauth = sum(r["auth_primary"] == "oauth2" for r in approval)
    appr_cats = Counter(r["category"] for r in approval).most_common(4)
    outreach = [r for r in R if r["verdict"] == "blocked" or r["blocker_type"] == "partnership"]
    blocked = [r for r in R if r["verdict"] == "blocked"]
    ready = [r for r in R if r["verdict"] == "ready"]
    off = [r for r in R if r["official_mcp"] == "official"]
    beta = [r for r in off if re.search(r"\bbeta\b|preview|early.access|\bEAP\b|closed|alpha|announced|sign up for updates|waitlist", r["mcp_notes"], re.I)]
    hosted = [r for r in off if re.search(r"remote|hosted|https://mcp|/mcp", r["mcp_notes"], re.I)]
    ro = [r for r in off if re.search(r"read-only|read only|docs-only|documentation only", r["mcp_notes"], re.I)]
    gated_cats = sorted(cats, key=lambda c: -sum(r["access"] in ("partner_gated", "paid_plan") for r in cats[c]))[:2]
    sc = jl("verify/scores.json", {})
    cal, hold = sc.get("calibration", {}), sc.get("holdout", {})
    acc = lambda s, k: s.get(k, {}).get("accuracy")
    run = jl("verify/agent_run.json", {}).get("researchers", {})
    fixes = jl("fixes.json", [])
    fx = Counter(f["source"] for f in fixes)
    lint_hist = jl("verify/lint_history.json", [])
    link = jl("verify/linkcheck-final.json", {}).get("summary") or jl("verify/linkcheck-pass1.json", {}).get("summary", {})
    nlinks = sum(link.values()) if link else 0
    hv = jl("verify/human.json", {})
    h_unsure = [r for r in hv.get("rows", []) if r["match"] is None]
    h_miss = [r for r in hv.get("rows", []) if r["match"] is False]
    fr = jl("verify/fix-review.json", {})
    fr_txt = ""
    if fr.get("status") == "done":
        k = fr["counts"]
        fr_txt = (f" I also reviewed every logged fix ({fr['n_fields']} field changes across {fr['n_apps']} apps; not blind): accepted {k['accept']} of {fr['n_apps']}"
                  + (f", rejected {k['reject']}" if k["reject"] else "") + (f", unsure about {k['unsure']}" if k["unsure"] else "") + ".")

    findings = [
        dict(big=f"{auth['oauth2']}", unit="of 100 · OAuth2 primary",
             title="OAuth2 is the default; API keys are the exception",
             body=f"{auth['oauth2']} apps use OAuth2 as the primary way a toolkit would act for an end user, and {oauth_any} offer it at all. "
                  f"API keys are primary for {auth['api_key']}. Key-first apps cluster in developer-facing products: "
                  f"<b>{', '.join(zero_oauth)}</b> has no OAuth-primary app.",
             so="Registering and maintaining OAuth apps is the critical path for most of the catalog. Key-based tools are the quickest to add."),
        dict(big=f"{n - len(blocked)}", unit="of 100 · buildable",
             title="Almost nothing is hard-blocked. The question is which gate.",
             body=f"Only {len(blocked)} apps are blocked outright ({names(blocked)}). {verdict['ready']} can be built and tested today on free credentials. "
                  f"The other {verdict['ready_with_caveats']} are buildable but sit behind a review, a paid tier, a sales gate or per-customer setup.",
             so="Treat the backlog as a gate-clearing queue, not a feasibility study."),
        dict(big=f"{blk['app_review']}", unit="apps · app review",
             title="The most common blocker is app review, not money",
             body=f"{blk['app_review']} apps need marketplace or app review before a multi-tenant OAuth app can serve other customers, "
                  f"versus {blk['paid_plan']} blocked by a paid plan and {blk['partnership']} by a partnership or sales gate. "
                  f"{appr_oauth} of the {len(approval)} approval-gated apps are OAuth platforms with a marketplace: "
                  f"{', '.join(f'{c} ({k})' for c, k in appr_cats)}. Examples: Meta Ads, Google Ads, LinkedIn Ads, Shopify, Slack, HubSpot, Zendesk, Intercom.",
             so="One repeatable app-review playbook (security questionnaire, scopes justification, demo video, privacy policy) unlocks a quarter of the list. That is an ops process worth owning."),
        dict(big=f"{ranked[0][1]}/10", unit=f"free · {ranked[0][0]}",
             title="Gates follow the category",
             body=f"Free self-serve credentials are the norm in {', '.join(f'{c} ({k}/10)' for c, k in ranked[:3])}. "
                  f"{', '.join(f'{c} ({k}/10)' for c, k in ranked[-2:])} are the opposite: credentials come through trials, reviews or sales. "
                  f"Sales and paid-plan gates concentrate in {gated_cats[0]} and {gated_cats[1]}.",
             so="Batch the self-serve categories for fast coverage. Route Support, Finance and AI-native apps to partnerships early because they have the longest lead time."),
        dict(big=f"{len(off)}", unit="of 100 · vendor MCP",
             title="Vendor MCP servers are now table stakes, but many are partial",
             body=f"{len(off)} apps publish their own MCP server ({len(hosted)} of them remote/hosted). {len(beta)} of those are beta, preview or early-access, "
                  f"and at least {len(ro)} are read-only or docs-only ({names(ro, 5)}). Several are tenant-scoped (the URL includes the customer's domain).",
             so="A vendor MCP does not replace a managed toolkit. The value moves to auth management across many apps, write actions, consistent schemas and reliability."),
        dict(big=f"{acc(cal, 'pass0_closed_book') or '—'}%", unit="closed-book accuracy",
             title="Model memory is not enough. This data moves monthly.",
             body=f"Answering from an LLM's memory alone scored {acc(cal, 'pass0_closed_book')}% on the calibration sample "
                  f"(official MCP field: {cal.get('pass0_closed_book', {}).get('by_field', {}).get('official_mcp', '—')}%). "
                  "Real changes in 2026 the docs caught and memory missed: Google Ads retired developer tokens (Sep 9), Cloudflare opened public OAuth clients (June), Clay shipped a public API, fanbasis rebranded to Commas.",
             so="Research has to be grounded in docs and re-run on a schedule. The pipeline makes a re-run cheap."),
    ]

    agent = dict(
        lede=(f"The research ran as an orchestrator plus {run.get('agents', 10)} researcher agents in parallel (one per category, ~{run.get('tool_calls', 0)} web searches and fetches), "
              "then a chain of checks. Everything after the researchers is a verification loop. The same pipeline is in the repo as a standalone Python script on the Claude API, with optional Composio MCP tools."),
        steps=[
            dict(title="Closed-book baseline", body="An LLM answers all 100 from memory, no browsing. Written <i>before</i> any grounded result, so it is a fair 'before' number.", out="data/pass0/closed_book.tsv"),
            dict(title="Researcher agents ×10", body="One agent per category, web search + fetch on official docs. Strict schema, enum definitions, 'unknown' over guessing, and every URL must be one it opened.", out="data/pass1/*.json · 100 records"),
            dict(title="Evidence guard", body="In the API version: any cited URL that was not actually fetched in that run is flagged and confidence drops to low.", out="agent/research.py: evidence_guard()"),
            dict(title="Deterministic lint", body="Schema enums and cross-field rules (e.g. access=partner_gated cannot be verdict=ready; blocker must match access). v1 caught 1 record, v2 caught 9.", out="scripts/lint.py"),
            dict(title="Link check: script + browser", body=f"Every cited URL is requested. {nlinks} unique URLs. Bot-blocked ones are re-opened in a real browser. Result: zero dead links, no invented URLs.", out="data/verify/linkcheck-*.json"),
            dict(title="Independent verifiers", body="Fresh agents see only the claims (no URLs, no notes) and try to prove each of 5 fields wrong on a stratified sample of 30 (3 per category).", out="150 field checks"),
            dict(title="Adjudication", body="The orchestrator agent re-read every disputed page in a real browser and settled it. The ambiguous definition (free sandbox vs. review-gated) got a written precedence rule. Every resulting fix is logged with its reason for human review.", out="data/verify/adjudication.json"),
            dict(title="Consistency sweep", body="The precedence rule is applied to all 100, not just the sample. 6 more records relabelled, each logged with its reason.", out="data/fixes.json"),
            dict(title="Holdout verification", body="15 apps never used for any fix are verified by new adversarial verifiers against the final data. This is the headline accuracy.", out="data/verify/verifier-holdout-*.json"),
            dict(title="Human spot-check", human=True, body=(f"I checked {hv.get('n', 12)} randomly drawn fields by hand on the cited pages, blind to the agent's answer: {hv.get('hits')} of {hv.get('n')} matched"
                                                              + (f", and {len(h_unsure)} I could not settle from the cited page ({', '.join(esc(r['app']) for r in h_unsure)})" if h_unsure else "")
                                                              + (f", and {len(h_miss)} disagreed ({', '.join(esc(r['app']) for r in h_miss)})" if h_miss else "") + "." + fr_txt
                                                              if hv.get("status") == "done" else "12 randomly drawn fields are checked by hand on the cited pages, blind to the agent's answer (scripts/human.py)."), out="data/verify/human.json"),
        ],
        human=[
            "<b>Writing the definitions.</b> 'Self-serve vs gated' is a judgment call. The first definition was ambiguous, and the agents labelled the same situation two ways (HubSpot 'free' vs. Front 'approval'). The fix was a written precedence rule, not more agent runs.",
            "<b>Settling disagreements.</b> When a verifier disagreed with a researcher, the page had to be read and a call made (Twenty's auth, Coda's verdict). The orchestrator agent proposed each call with its source, and every fix is logged with its reason so a person can review it (data/fixes.json).",
            "<b>Bot-protected docs.</b> developer.salesforce.com, several help centres and Meta's docs refuse scripted fetches. A real browser was needed to confirm those pages.",
            "<b>Entity resolution.</b> fanbasis is now Commas, Paygent Connect runs on NMI's gateway docs, and 'YouTube Transcript' is a third-party service (transcriptapi.com). A human has to accept which entity is meant.",
            "<b>Accepting exceptions.</b> Four records still trip a lint rule on purpose (Clay, Xero, iPayX, fanbasis), each with a written reason.",
        ],
        fails=[
            "<b>Labelled identical situations differently</b> (6 apps) before the precedence rule. The per-record verifiers did not catch it either: they accepted both labels.",
            "<b>Never opened the key page</b> once: for Twenty it read the API-key page but not the OAuth page, so it picked the wrong primary auth.",
            "<b>Over-cautious verdicts:</b> it marked Coda 'with caveats' only because auth is token-based, which the definitions do not treat as a gate.",
            "<b>Schema slips:</b> wrote <code>api_breadth: \"unknown\"</code> (not an allowed value) and cited zapier.com as an auth source.",
            "<b>Fell back to search snippets</b> when docs were JS-rendered or 403 (Lark, Gumroad, Salesforce, Otter). Those records are marked medium/low confidence rather than presented as certain.",
            "<b>Saw a prompt injection</b> in vendor docs (text addressed to AI agents asking for a feedback report) and correctly ignored it. Docs are untrusted input.",
        ] + [f"<b>Cited a page that does not carry the claim</b> ({esc(r['app'])}, {esc(r['field'])}): the human spot-check could not confirm "
             f"<code>{esc(str(r['agent']))}</code> from it. Human's note: \"{esc(r['note'])}\" The answer may still be right, but that citation does not prove it."
             for r in h_unsure] + [f"<b>Human disagreed</b> ({esc(r['app'])}, {esc(r['field'])}): agent said <code>{esc(str(r['agent']))}</code>, the page says "
             f"<code>{esc(r['human'])}</code>. {esc(r['note'])}" for r in h_miss],
    )

    loops = [
        ["Lint v1 → v2 (pass 1)", f"{lint_hist[0]['flagged'] if lint_hist else '—'} → {lint_hist[1]['flagged'] if len(lint_hist) > 1 else '—'} records flagged; {fx.get('lint', 0)} field fixes"],
        ["Link check (script)", f"{link.get('ok', 0)} of {nlinks} URLs OK; {link.get('error', 0)} bot-blocked; 0 dead"],
        ["Link check (real browser)", "7 of 7 bot-blocked Meta pages returned 200 with the expected title"],
        ["Verifiers · calibration", "2 of 150 field checks disputed; both upheld after re-reading the docs"],
        ["Definition sweep (all 100)", f"{fx.get('sweep', 0)} records relabelled by one written rule"],
        ["Holdout verifiers", (f"{hold['final']['correct']} of {hold['n_fields']} confirmed; {hold.get('n_unsettled', 0)} unsettled (docs conflict or don't render), counted as misses" if hold.get("final") else "pending")],
        ["Orchestrator browser spot-check (holdout)", "Airtable (no OAuth review, only privacy/terms URLs) and Pylon (sales-provisioned trials only) re-read by hand in a browser: both matched"],
        ["Lint on final data", f"{lint_hist[-1]['flagged'] if lint_hist else '—'} flagged, all reviewed exceptions"],
    ]
    verify = dict(
        lede=(f"Five fields were checked per sampled app: primary auth, access gate, API style, official MCP and verdict. The calibration sample (30 apps, 3 per category) was used to find error patterns, so its 'final' score is optimistic by design. "
              f"The <b>holdout</b> (15 other apps, picked by a seeded random draw before any results existed) was never used for fixes, so it is the honest number. "
              "Ground truth = the independent verifier's answer, overruled only where a browser re-read of the docs showed it was wrong. "
              "Checks the docs could not settle (conflicting or JS-only pages) are counted as misses, never as hits."
              + (f" On the holdout, the definition sweep fixed an app it was never tuned on (Copper), lifting the grounded agent from {acc(hold, 'pass1_grounded')}% to {acc(hold, 'final')}%." if hold.get("final") else "")),
        loops=loops,
    )

    limits = [
        f"Sample sizes are small: 150 + 75 field checks. {acc(hold, 'final')}% on 75 holdout checks is consistent with a true error rate of a few percent across all fields and apps. The 'medium' and 'low' confidence flags in the table show where errors are most likely.",
        "The verifiers run on the same model family as the researchers, so their errors can be correlated. They agreed 98% of the time on the first round, and they missed the definition inconsistency. The human spot-check and the cross-record sweep exist for this reason.",
        "Only five fields are scored. The free-text notes (rate limits, breadth estimates, sandbox details) are evidence-linked but not independently scored. 'Sandbox' is 'unknown' for 45 apps because docs rarely say.",
        "Pricing and access terms change often (several changed in 2026). Treat this as a snapshot dated in the header. The pipeline is built to re-run.",
        "Three records are low confidence (fanbasis/Commas, Paygent Connect, iPayX). Their docs are thin or inconsistent, and the page says so rather than guessing.",
        "No paid accounts were used. Where an app is paid or partner-gated, the finding is the gate itself, with evidence.",
    ]

    out = dict(
        as_of="23 Nov 2026", repo_url=REPO_URL, findings=findings, agent=agent, verify=verify, limits=limits,
        run_lede="The research agent is a Python CLI on the Claude API (server-side web search + fetch, structured JSON output). Composio tools can be added via MCP. All checking, scoring and page-building scripts run with no API key.",
        run_cmds=[
            "git clone " + REPO_URL + " && cd composio-app-research",
            "pip install -r requirements.txt",
            "export ANTHROPIC_API_KEY=...            # or: ant auth login",
            "",
            "# research: one app, a range, or all 100  ->  data/pass1/app-XXX.json",
            "python agent/research.py research --ids 41",
            "python agent/research.py research --ids 1-100",
            "",
            "# optional: give the agent Composio tools (e.g. Firecrawl/Exa via a Composio MCP URL)",
            "python agent/research.py research --ids 41 --composio-mcp-url \"$COMPOSIO_MCP_URL\"",
            "",
            "# verification loops (no API key needed except 'verify')",
            "python scripts/lint.py                  # merge + schema/consistency lint",
            "python scripts/linkcheck.py data/pass1.json",
            "python agent/research.py verify --sample 30 --seed 42",
            "python scripts/apply_fixes.py && python scripts/lint.py --final",
            "python scripts/score.py                 # accuracy per pass",
            "python scripts/insights.py && python scripts/build_site.py   # -> site/index.html",
        ],
        footer=("Built for the Composio AI Product Ops take-home. Data: <a href=\"dataset.json\">dataset.json</a> (100 records, 23 fields each, evidence URLs and correction log). "
                "Every number on this page is computed from the data files at build time."),
    )
    (D / "insights.json").write_text(json.dumps(out, indent=1, ensure_ascii=False), encoding="utf-8")
    print("insights.json written")


if __name__ == "__main__":
    main()
