#!/usr/bin/env python3
"""Build the Japanese index.html from the English bundle.

    git show main:index.html > /tmp/index.en-src.html  # original English bundle
    python tools/apply_ja.py --src /tmp/index.en-src.html --out index.html \
        --en-out index.en.html --list tools/strings_tagged.tsv

Options: --dry (list strings only), --partial (cache only, no API calls).
Needs SAKANA_API_KEY unless every string is already in translate_cache.json.

Walks every nested bundle, extracts user-facing strings, tags each B2B or
consumer (tools/tagging.py), translates through translate.py (cached), and
repacks. Also sets lang="ja" and adds a Noto Sans JP font fallback. Code fixes
in tools/source_fixes.py are applied first; --en-out writes the fixed English
build.
"""
import argparse
import collections
import csv
import hashlib
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.dirname(HERE))

import bundle
import extract_strings as extract
import source_fixes
import tagging

KINDS = [
    ("Stepped journey page", "journey"), ("APPI (Japan) privacy layer", "appi"),
    ("Popups over the blurred", "popups"), ("Shared LINE phone", "line"),
    ("0: auto-enrollment popup", "reengage"), ("Loyalty & re-engagement — per-brand data", "redata"),
    ("Standalone-bundle asset resolver", "resolver"), ("FreeStand Demo Hub (Japan) — demo registry", "hubreg"),
    ("FreeStand Demo Hub — shell", "hubshell"), ("Per-tab insight popup", "ana-insights"),
    ("Audience:", "ana-audience"), ("Campaign Performance Overview", "ana-perf"),
    ("Statistical Analysis", "ana-stats"), ("inline SVG icon set", "ana-icons"),
    ("Campaign data for FreeStand Analytics", "ana-data"), ("Sources screen", "sources-js"),
]

# India campaigns: present in the analytics data but never reachable from the
# Japan hub (pages hard-code lactogrow / lactogrow-b / lactogrow-c).
INDIA_AUD = {"bournvita", "cadbury", "biscoff"}


def kind_of(kind, text):
    if kind == "template":
        m = re.search(r"<title>(.*?)</title>", text)
        return "tpl:" + (m.group(1) if m else "?")
    for key, name in KINDS:
        if key in text[:200]:
            return name
    return "js:" + text[:40]


def india_ranges(kind, text):
    if kind != "ana-data":
        return []
    a, b = text.index('C["bournvita"]='), text.index('C["lactogrow-b"]=')
    c, d = text.index('C["cadbury"]='), text.index("return C;")
    return [(a, b), (c, d)]


def skipped(kind, path, pos, ranges):
    if kind == "ana-audience" and set(path.split("/")) & INDIA_AUD:
        return True
    return any(a <= pos < b for a, b in ranges)


FONT_LINK = ('<link rel="stylesheet" href="https://fonts.googleapis.com/css2?'
             'family=Noto+Sans+JP:wght@300;400;500;600;700&amp;display=swap">')
# phrase-aware Japanese line breaking (Chrome 119+; ignored elsewhere)
JA_CSS = "<style>:lang(ja){line-break:strict;word-break:auto-phrase}</style>"
JP_STACK = "Noto Sans JP,Hiragino Sans,Hiragino Kaku Gothic ProN,Yu Gothic,Meiryo,"


def add_jp_fonts(text):
    # unquoted family names are valid CSS and safe inside any JS/HTML quoting
    return re.sub(r"(?<!Meiryo,)\bsans-serif\b", JP_STACK + "sans-serif", text)


def localize_template(tpl):
    tpl = re.sub(r'<html lang="en"', '<html lang="ja"', tpl, count=1)
    if "family=Noto+Sans+JP" not in tpl:
        tpl = re.sub(r"(<head[^>]*>)", lambda m: m.group(1) + "\n" + FONT_LINK + JA_CSS, tpl, count=1)
    return tpl


def collect(h):
    rows = []
    seen = set()
    for path, kind, text in bundle.walk(h):
        digest = hashlib.md5(text.encode()).hexdigest()
        if digest in seen:
            continue
        seen.add(digest)
        kd = kind_of(kind, text)
        ranges = india_ranges(kd, text)

        def tr(u, ctx):
            p = "/".join(ctx.get("path", ()))
            if not skipped(kd, p, ctx.get("pos", -1), ranges):
                rows.append((kd, p, u))
            return None

        (extract.render_html if kind == "template" else extract.render_js)(text, tr, {"file": kd})
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", default="index.html")
    ap.add_argument("--out", default="index.html")
    ap.add_argument("--en-out", help="also write the fixed English build here")
    ap.add_argument("--list", help="write the tagged string list (TSV) here")
    ap.add_argument("--dry", action="store_true", help="list strings only, no API calls")
    ap.add_argument("--partial", action="store_true", help="cache only: no API calls, untranslated strings stay English")
    a = ap.parse_args()

    h = source_fixes.apply(bundle, open(a.src, encoding="utf-8").read())
    if a.en_out:
        with open(a.en_out, "w", encoding="utf-8") as f:
            f.write(h)
    rows = collect(h)
    occ = collections.OrderedDict()
    for kd, p, u in rows:
        occ.setdefault(u, []).append((kd, p, tagging.tag(kd, p)))
    # one translation per English string, so code comparisons stay consistent;
    # anything a consumer sees gets the consumer register
    reg = {u: ("consumer" if any(t == "consumer" for *_, t in v) else "b2b") for u, v in occ.items()}
    print(f"{len(reg)} unique strings: {collections.Counter(reg.values())}", file=sys.stderr)
    if a.list:
        with open(a.list, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f, delimiter="\t")
            w.writerow(["register", "file", "path", "english"])
            for u, v in occ.items():
                w.writerow([reg[u], v[0][0], v[0][1], u])
    if a.dry:
        return

    from translate import Translator
    t = Translator(workers=4)
    items = list(reg.items())
    if a.partial:
        out = [t.cached(u, r) for u, r in items]
    else:
        out = t.translate_many([(u, r) for u, r in items])
    ja = {u: j for (u, _), j in zip(items, out) if j is not None}
    missing = [u for u, _ in items if u not in ja]
    if missing and not a.partial:
        print(f"{len(missing)} strings failed; rerun to retry (cached ones are free)", file=sys.stderr)
        sys.exit(1)

    def fn(path, kind, text):
        kd = kind_of(kind, text)
        ranges = india_ranges(kd, text)

        def tr(u, ctx):
            p = "/".join(ctx.get("path", ()))
            if skipped(kd, p, ctx.get("pos", -1), ranges):
                return None
            return ja.get(u)

        if kind == "template":
            new = extract.render_html(text, tr, {"file": kd})
            new = localize_template(new)
        else:
            new = extract.render_js(text, tr, {"file": kd})
        return add_jp_fonts(new)

    h2 = bundle.rebuild(h, fn)
    # outer loader shell of the root document
    h2 = h2.replace("<html>", '<html lang="ja">', 1)
    h2 = h2.replace("<title>FreeStand — Japan Demo Hub</title>", "<title>" + ja.get("FreeStand — Japan Demo Hub", "FreeStand — Japan Demo Hub") + "</title>", 1)
    h2 = h2.replace("This page requires JavaScript to display.", "このページを表示するにはJavaScriptを有効にしてください。", 1)
    h2 = h2.replace(">DEMO OF DEMOS</text>", ">デモ一覧</text>", 1)
    head_end = h2.index("</head>")
    h2 = h2[:head_end].replace("sans-serif", JP_STACK + "sans-serif") + h2[head_end:head_end + 2000].replace("Arial,Helvetica,sans-serif", "Arial,Helvetica," + JP_STACK + "sans-serif") + h2[head_end + 2000:]
    with open(a.out, "w", encoding="utf-8") as f:
        f.write(h2)
    print(f"wrote {a.out}", file=sys.stderr)


if __name__ == "__main__":
    main()
