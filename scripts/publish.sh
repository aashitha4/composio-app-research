#!/usr/bin/env bash
# Rebuild the page from data and redeploy it (GitHub Pages serves the gh-pages branch = the site/ folder).
#   bash scripts/publish.sh "message"
set -euo pipefail
cd "$(dirname "$0")/.."
python scripts/score.py >/dev/null
python scripts/insights.py
python scripts/build_site.py
git add -A
git commit -m "${1:-Rebuild case-study page}" || echo "nothing to commit"
git push origin main
git push origin "$(git subtree split --prefix site main)":gh-pages --force
echo "Deployed: https://aashitha4.github.io/composio-app-research/ (GitHub Pages takes ~1 min)"
