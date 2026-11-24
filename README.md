# 100-App Toolkit Recon

An agent pipeline that researches whether an app can become an agent toolkit (auth method, self-serve vs gated
access, API surface, MCP availability, buildability verdict and main blocker), cites official docs for every
answer, and then verifies itself.

- **Case study page:** `site/index.html` (single self-contained HTML; also published as a live link)
- **Dataset:** `site/dataset.json`, 100 records × 23 fields with evidence URLs and a per-record correction log
- **Schema + definitions:** `agent/prompts/researcher.md`

## What is in here

```
agent/
  research.py            the research agent (Claude API + server-side web search/fetch, optional Composio MCP)
  schema.py              shared enums
  prompts/researcher.md  researcher instructions, output schema, enum definitions (+ v2 precedence rule)
  prompts/verifier.md    adversarial verifier instructions
scripts/                 no API key needed for any of these
  lint.py                merge + schema/consistency lint        (loop 2)
  linkcheck.py           request every evidence URL              (loop 3)
  apply_fixes.py         apply data/fixes.json -> data/final.json, keeping provenance
  score.py               accuracy of each pass vs adjudicated ground truth
  human.py               blind human spot-check: make / ingest
  insights.py            page prose, every number computed from data
  build_site.py          -> site/index.html + site/dataset.json
data/
  apps.csv               the 100 apps
  pass0/closed_book.tsv  baseline: LLM answers from memory, no browsing (written before any grounded result)
  pass1/*.json           grounded researcher output (10 files, one per category)
  pass1.json             merged pass 1
  fixes.json             every correction: field, old -> new, which loop caught it, why
  final.json             pass 1 + fixes
  verify/                samples, verifier outputs, adjudication (ground truth), lint/link reports, scores
```

## How to run the research agent

```bash
pip install -r requirements.txt
export ANTHROPIC_API_KEY=...          # or `ant auth login`

python agent/research.py research --ids 41          # one app  -> data/pass1/app-041.json
python agent/research.py research --ids 1-10,55     # ranges/lists
python agent/research.py verify --sample 30 --seed 42
```

Each app is one agentic turn on `claude-opus-5-5` with the server-side `web_search` and `web_fetch` tools
(the loop resumes on `pause_turn`), followed by a structured-output call that converts the notes into the
JSON schema. Then the **evidence guard** drops confidence to `low` for any cited URL the agent did not
actually retrieve in that run.

**Runnable trigger (no local setup):** add an `ANTHROPIC_API_KEY` repository secret, then
Actions → *Run research agent* → *Run workflow* → enter ids (e.g. `41` or `1-10,55`). The output JSON is
attached to the run as an artifact. The workflow runs the offline test first.

**Composio tools (optional):** pass a Composio MCP server URL (for example a Tool Router URL that exposes
Firecrawl or Exa search) and the agent gets those tools alongside web search/fetch via the Claude API's MCP
connector:

```bash
python agent/research.py research --ids 41 --composio-mcp-url "$COMPOSIO_MCP_URL"
```

## How the published dataset was produced (and verified)

The published run was orchestrated from Claude Code: one orchestrator plus 10 researcher subagents in
parallel (one per category, about 886 web searches and fetches in total), using the **same** `researcher.md`
prompt and schema as `research.py`. Then:

| Loop | What it does | Result |
|---|---|---|
| 0. Closed-book baseline | LLM answers from memory, written before grounded results | 73.3% field accuracy (calibration) |
| 1. Grounded researchers | official docs, cite only pages opened | 98.0% (calibration) |
| 2. Lint v1 → v2 | schema + cross-field rules | 1 → 9 records flagged; 11 field fixes |
| 3. Link check | script + real browser for bot-blocked pages | 359/359 evidence URLs resolve, 0 invented |
| 4. Independent verifiers | 30-app stratified sample, claims only, try to prove wrong | 2/150 disputes, both upheld |
| 5. Definition sweep | one written precedence rule applied to all 100 | 6 records relabelled (human review later reverted 1, Grain) |
| 6. Holdout verifiers | 15 apps never used for fixes, adversarial | headline accuracy (see page) |
| 7. Human spot-check | 12 random fields checked by hand on the cited pages, blind to the agent's answer | 11 matched, 1 not settled by the cited page (Freshdesk), 0 disagreed |
| 8. Human fix review | every logged fix (23 field changes, 14 apps) checked against its reason and page; not blind | 13 accepted (Discord after a better source was cited), 1 rejected and reverted (Grain); review changes logged as source `human` |

Reproduce the scoring and page from the committed data (no API key):

```bash
python scripts/lint.py && python scripts/apply_fixes.py && python scripts/lint.py --final
python scripts/linkcheck.py data/final.json
python scripts/score.py
python scripts/insights.py && python scripts/build_site.py
```

## Human spot-check and redeploy

```bash
python scripts/human.py make     # blind checklist: data/verify/human-checklist.csv
# open each URL, fill human_value from what the page says
python scripts/human.py ingest   # -> data/verify/human.json

# review of every logged fix (not blind: it shows each proposed change)
python scripts/human.py fixes-make     # data/verify/fix-review.csv, one row per corrected app
# fill your_call with accept / reject / unsure
python scripts/human.py fixes-ingest   # -> data/verify/fix-review.json, shown beside each correction

bash scripts/publish.sh "Add human spot-check"
```

## Known limits

Small verification samples (150 + 75 field checks); verifiers share a model family with the researchers;
only five fields are scored; access and pricing terms change often, so this is a dated snapshot. Full list on the page.
