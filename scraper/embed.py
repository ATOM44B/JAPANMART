#!/usr/bin/env python3
"""Bake data/products.json into the page so the listings are already there the moment it opens.

    python3 scraper/embed.py index.html data/products.json _site/index.html

The page still checks data/products.json for something newer, so it stays fresh while it is open.
Standard library only.
"""
import json
import re
import sys

src, data, out = sys.argv[1:4]
html = open(src, encoding="utf-8").read()
payload = json.load(open(data, encoding="utf-8"))
blob = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
blob = blob.replace("<", "\\u003c").replace("\u2028", "\\u2028").replace("\u2029", "\\u2029")  # keep it script-safe
pattern = re.compile(r'(<script id="scout-data" type="application/json">).*?(</script>)', re.S)
if not pattern.search(html):
    sys.exit('embed.py: the data block <script id="scout-data"> was not found in ' + src)
html = pattern.sub(lambda m: m.group(1) + blob + m.group(2), html, count=1)
open(out, "w", encoding="utf-8").write(html)
print(f"embedded {len(payload.get('items', []))} listings into {out} ({len(html) // 1024} KB)")
