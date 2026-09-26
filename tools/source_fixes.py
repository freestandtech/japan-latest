"""Code fixes applied to the English bundle before translation.

Each entry is (description, old, new); `old` must be found in at least one
text unit, so a fix that stops matching fails the build instead of silently
disappearing.
"""

FIXES = [
    (
        # The hub loads analytics pages from a blob URL, so ?c= never arrives
        # and every scenario showed Pedigree's audiences. Use the campaign the
        # page already picked (window.CAMP); lactogrow-b/-c share LACTOGROW's.
        "Saved Audiences / All Claimants follow the page's campaign",
        'function audData(){ return AUD[new URLSearchParams(location.search).get("c")]||AUD.pedigree; }',
        'function audData(){ const C=window.CAMPAIGNS||{}, k=Object.keys(C).find(x=>C[x]===window.CAMP)||""; '
        'return AUD[k]||AUD[k.split("-")[0]]||AUD[new URLSearchParams(location.search).get("c")]||AUD.pedigree; }',
    ),
]


def apply(bundle, html):
    hits = {d: 0 for d, _, _ in FIXES}

    def fn(path, kind, text):
        for desc, old, new in FIXES:
            if old in text:
                hits[desc] += 1
                text = text.replace(old, new)
        return text

    out = bundle.rebuild(html, fn)
    missing = [d for d, n in hits.items() if not n]
    if missing:
        raise SystemExit(f"source fix no longer matches: {missing}")
    return out
