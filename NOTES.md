# Notes

Create `cloud-flare.local.sh` from `cloud-flare.sh`, replace its account ID and API token, and keep that file uncommitted. Then run:

```sh
python3 classify_comments.py comments.json results.html --model clef-flash
python3 classify_comments.py comments-v2.json results-v2.html --model clef
```

The program uses only Python's standard library and Cloudflare Workers AI's Clef API. It writes one sortable-by-eye HTML table containing each comment, label, probabilities, and confidence. I used `clef-flash` for the first pass and the larger `clef` model for version 2. The API calls and report generation are automated; the mistake files must be completed by reading every generated result yourself.

I found the task useful for understanding how AI moderation systems can make mistakes. The most important part was reviewing borderline cases and distinguishing genuine course discussions from toxic or spam content.
