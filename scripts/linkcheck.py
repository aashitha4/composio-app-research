"""Loop 2b — evidence link check. Requests every evidence URL in a dataset and records the status.
A 404 / DNS failure means the agent cited a page that does not exist (a hallucination signal).
401/403/429 usually mean bot protection, so they are reported separately, not as dead.

  python scripts/linkcheck.py data/pass1.json      # writes data/verify/linkcheck-<name>.json
"""
import json
import sys
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130 Safari/537.36"


def check(url, tries=3):
    for _ in range(tries - 1):  # retry transient network failures before judging a URL
        u, s, k = _check(url)
        if not k.startswith("unreachable"):
            return u, s, k
    return _check(url)


def _check(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "text/html,*/*"})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return url, r.status, "ok"
    except urllib.error.HTTPError as e:
        kind = "blocked" if e.code in (401, 403, 405, 429, 451, 503) else "dead" if e.code in (404, 410) else "error"
        return url, e.code, kind
    except Exception as e:  # DNS, TLS, timeout
        return url, None, f"unreachable: {type(e).__name__}"


def main(path):
    recs = json.loads(Path(path).read_text(encoding="utf-8"))
    urls = sorted({u for r in recs for u in (r.get("evidence") or {}).values() if u})
    with ThreadPoolExecutor(16) as ex:
        results = list(ex.map(check, urls))
    by_url = {u: {"status": s, "kind": k} for u, s, k in results}
    summary = {}
    for v in by_url.values():
        key = v["kind"].split(":")[0]
        summary[key] = summary.get(key, 0) + 1
    out = ROOT / "data" / "verify" / f"linkcheck-{Path(path).stem}.json"
    out.write_text(json.dumps({"summary": summary, "urls": by_url}, indent=2), encoding="utf-8")
    print(f"{len(urls)} unique evidence URLs: {summary}")
    for u, v in by_url.items():
        if v["kind"] != "ok":
            print(f"  {v['kind']:<12} {v['status']}  {u}")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else ROOT / "data" / "pass1.json")
