#!/usr/bin/env python3
"""Classify course-forum comments with Cloudflare Clef and make a scan-friendly HTML report."""

import argparse
import html
import json
import re
import time
import urllib.error
import urllib.request
from pathlib import Path


LABELS = {
    "acceptable": "Relevant, ordinary course discussion, questions, answers, feedback, or disagreement without abuse or promotion.",
    "toxic": "Insults, harassment, threats, hate or degrading attacks aimed at a person or group. Criticism stated without abuse is acceptable.",
    "spam": "Unsolicited advertising, scams, paid assignment services, referral promotions, mass marketing, or suspicious links unrelated to course discussion.",
}


def read_credentials(path: Path):
    if not path.exists():
        raise RuntimeError(f"Credentials file not found: {path}. Copy cloud-flare.sh to this path and fill in real values.")
    text = path.read_text(encoding="utf-8")
    values = dict(re.findall(r'^export\s+(CLOUDFLARE_ACCOUNT_ID|CLOUDFLARE_API_TOKEN)="([^"]*)"\s*$', text, re.MULTILINE))
    missing = [key for key in ("CLOUDFLARE_ACCOUNT_ID", "CLOUDFLARE_API_TOKEN") if not values.get(key)]
    if missing:
        raise RuntimeError(f"Missing {', '.join(missing)} in {path}")
    if values["CLOUDFLARE_API_TOKEN"] == "your-cloudflare-api-token-goes-here":
        raise RuntimeError(f"Replace the placeholder API token in {path}")
    return values["CLOUDFLARE_ACCOUNT_ID"], values["CLOUDFLARE_API_TOKEN"]


def classify(comment, account, token, model):
    payload = {
        "state": {"comment": comment["comment"]},
        "questions": {
            "moderation": {
                "type": "choice",
                "instructions": (
                    "Classify this college-course forum comment. Choose exactly one label. "
                    "Use toxic only for abusive targeting, threats, harassment, hate, or degrading insults. "
                    "Use spam for unsolicited promotion, scams, paid services, referral marketing, or suspicious advertising. "
                    "Ordinary criticism, disagreement, and course-related help are acceptable."
                ),
                "criteria": LABELS,
            }
        },
    }
    request = urllib.request.Request(
        f"https://api.cloudflare.com/client/v4/accounts/{account}/ai/run/@cf/cloudflare/{model}",
        data=json.dumps(payload).encode("utf-8"),
        method="POST",
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
    )
    for attempt in range(4):
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                result = json.load(response)
            if not result.get("success"):
                raise RuntimeError(result.get("errors") or "Cloudflare returned an unsuccessful response")
            answer = result["result"]["answers"]["moderation"]
            return {"label": answer["choice"], "probabilities": answer.get("probabilities", {}), "confidence": answer.get("confidence")}
        except urllib.error.HTTPError as error:
            if error.code not in (429, 500, 502, 503, 504) or attempt == 3:
                body = error.read().decode("utf-8", errors="replace")
                raise RuntimeError(f"Cloudflare HTTP {error.code}: {body[:500]}") from error
            time.sleep(2 ** attempt)


def render(data, model):
    rows = []
    for item in data["comments"]:
        result = item["result"]
        label = html.escape(result["label"])
        confidence = result.get("confidence")
        confidence_text = "—" if confidence is None else f"{confidence:.3f}"
        probs = " ".join(f"{html.escape(k)}: {v:.3f}" for k, v in result.get("probabilities", {}).items())
        rows.append(
            f'<tr class="{label}"><td>{item["id"]}</td><td>{html.escape(item["author"])}</td>'
            f'<td>{html.escape(item["thread"])}</td><td>{html.escape(item["comment"])}</td>'
            f'<td><strong>{label}</strong><br><small>confidence {confidence_text}<br>{probs}</small></td></tr>'
        )
    return f'''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width">
<title>Clef moderation results ({html.escape(model)})</title>
<style>
body {{ font: 15px system-ui, sans-serif; margin: 2rem; color: #17202a }}
table {{ border-collapse: collapse; width: 100%; }} th {{ position: sticky; top: 0; background: #17202a; color: white; }}
th, td {{ border: 1px solid #d8dee4; padding: .65rem; text-align: left; vertical-align: top; }}
td:nth-child(1) {{ width: 3rem; }} td:nth-child(4) {{ min-width: 28rem; }}
tr.acceptable {{ background: #f0fff4; }} tr.toxic {{ background: #fff5f5; }} tr.spam {{ background: #fffaf0; }}
small {{ color: #586069; }}
</style></head><body><h1>Clef moderation results</h1>
<p>Model: <code>{html.escape(model)}</code> · {len(data["comments"])} comments</p>
<table><thead><tr><th>ID</th><th>Author</th><th>Thread</th><th>Comment</th><th>Clef result</th></tr></thead>
<tbody>{''.join(rows)}</tbody></table></body></html>'''


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--model", choices=("clef-flash", "clef"), default="clef-flash")
    parser.add_argument("--credentials", type=Path, default=Path("cloud-flare.local.sh"))
    args = parser.parse_args()
    try:
        account, token = read_credentials(args.credentials)
    except RuntimeError as error:
        parser.error(str(error))
    source = json.loads(args.input.read_text(encoding="utf-8"))
    results = []
    for number, comment in enumerate(source["comments"], 1):
        print(f"[{number}/{len(source['comments'])}] comment {comment['id']}")
        result = classify(comment, account, token, args.model)
        results.append({**comment, "result": result})
    args.output.write_text(render({**source, "comments": results}, args.model), encoding="utf-8")
    print(f"Wrote {args.output}")


if __name__ == "__main__":
    main()
