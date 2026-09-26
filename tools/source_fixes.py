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
    (
        # Below 700px the 290px sidebar squeezed the demo to a thumbnail.
        # Collapse it into a top bar with a menu button; the stage gets the
        # full width.
        "Responsive hub: CSS",
        '#hub-label{flex:1;font-size:12.5px;color:#43507a;text-align:center;min-height:16px}\n</style>',
        '#hub-label{flex:1;font-size:12.5px;color:#43507a;text-align:center;min-height:16px}\n'
        '#hub-menu{display:none;background:rgba(255,255,255,0.14);color:#fff;border:1px solid rgba(255,255,255,0.3);'
        'border-radius:8px;padding:8px 12px;font-size:13px;font-weight:600;line-height:1;font-family:inherit;cursor:pointer;white-space:nowrap}\n'
        '@media (max-width:700px){\n'
        '#hub{flex-direction:column;height:100vh;height:100dvh}\n'
        '#hub-side{width:100%;flex:0 0 auto;flex-direction:row;align-items:center;justify-content:space-between;'
        'padding:8px 12px;position:relative;z-index:20}\n'
        '.hub-brand{flex-direction:row;align-items:center;padding:0;gap:10px;min-width:0}\n'
        '.hub-brand .lg{height:34px;padding:0 10px}.hub-brand .lg img{height:20px}\n'
        '.hub-brand .s{white-space:normal;letter-spacing:1px;font-size:9px}\n'
        '#hub-menu{display:block;flex-shrink:0}\n'
        '.hub-foot{display:none}\n'
        '#hub-side-list{display:none;position:absolute;top:100%;left:0;right:0;max-height:70vh;overflow-y:auto;'
        'background:linear-gradient(180deg,#052762,#0A49B7);box-shadow:0 12px 30px rgba(5,39,98,0.35);padding-bottom:12px}\n'
        '#hub-side.open #hub-side-list{display:block}\n'
        '#hub-stage{padding:12px 8px 6px}\n'
        '#hub-bar{padding:6px 10px 14px;gap:8px}\n'
        '#hub-bar button{padding:9px 12px;font-size:12px;white-space:nowrap;flex-shrink:0}\n'
        '#hub-label{font-size:11px;line-height:1.35}\n'
        '#hub-counter{min-width:0;font-size:11px}\n'
        '}\n</style>',
    ),
    (
        "Responsive hub: menu button",
        '<div class="s">Demo of Demos · Japan</div></div>',
        '<div class="s">Demo of Demos · Japan</div></div>'
        '<button id="hub-menu" type="button" aria-expanded="false" aria-controls="hub-side-list">☰ Demos</button>',
    ),
    (
        "Responsive hub: menu toggle",
        '<script src="62849d9e-bce9-4793-bfa0-f434f994b29a"></script>',
        '<script>(function(){var s=document.getElementById("hub-side"),b=document.getElementById("hub-menu");'
        'function set(o){s.classList.toggle("open",o);b.setAttribute("aria-expanded",String(o));}'
        'b.addEventListener("click",function(){set(!s.classList.contains("open"));});'
        'document.getElementById("hub-side-list").addEventListener("click",function(e){if(e.target.closest(".hub-item"))set(false);});'
        '})();</script>\n<script src="62849d9e-bce9-4793-bfa0-f434f994b29a"></script>',
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
