"""Find user-facing English in JS source / HTML templates and rewrite it.

render_js(code, tr) / render_html(html, tr) walk the source and call
tr(unit_text, ctx) -> replacement for every translatable unit. unit_text has
markup and ${} interpolations masked as ⟦n⟧. With tr returning None the unit
is left unchanged (used for listing).
"""
import re

INLINE_TAGS = {"b", "strong", "i", "em", "span", "br", "a", "u", "small", "sup", "sub", "mark", "s", "code", "wbr"}
TAG_RE = re.compile(r"<(/?)([a-zA-Z][a-zA-Z0-9-]*)\b[^<>]*?(/?)>|<!--.*?-->", re.S)
PH_RE = re.compile(r"⟦\d+⟧")
WORD = re.compile(r"[A-Za-z]{2,}")

# ---------------------------------------------------------------- JS tokenizer

def _skip_string(code, i):
    q = code[i]; i += 1
    while i < len(code):
        c = code[i]
        if c == "\\": i += 2; continue
        if c == q: return i + 1
        if c == "\n": return i + 1  # unterminated; bail
        i += 1
    return i

def _parse_template(code, i):
    """code[i]=='`'. Returns (end, parts) where parts alternate str / ('expr', s, e)."""
    i += 1; parts = []; buf_start = i
    while i < len(code):
        c = code[i]
        if c == "\\": i += 2; continue
        if c == "`":
            parts.append(code[buf_start:i]); return i + 1, parts
        if c == "$" and code[i + 1:i + 2] == "{":
            parts.append(code[buf_start:i])
            e = _skip_expr(code, i + 2)
            parts.append(("expr", i + 2, e))
            i = e + 1; buf_start = i; continue
        i += 1
    raise ValueError("unterminated template")

def _skip_expr(code, i):
    """From just inside ${, return index of the matching }."""
    depth = 0
    while i < len(code):
        c = code[i]
        if c in "'\"": i = _skip_string(code, i); continue
        if c == "`": i, _ = _parse_template(code, i); continue
        if c == "/" and code[i + 1:i + 2] == "/": i = code.index("\n", i); continue
        if c == "/" and code[i + 1:i + 2] == "*": i = code.index("*/", i) + 2; continue
        if c == "{": depth += 1
        elif c == "}":
            if depth == 0: return i
            depth -= 1
        i += 1
    raise ValueError("unterminated ${")

REGEX_PREV = set("(,=:[!&|?{};+-*%<>~^") | {""}

def js_tokens(code, base=()):
    """Yield (kind, start, end, extra, path) for string/template literals at top level of `code`.
    path = tuple of object keys / function names enclosing the literal."""
    i = 0; n = len(code); prev = ""; stack = list(base); pending = ""; ident = ""
    def path(): return tuple(x for x in stack if x) + ((pending,) if pending else ())
    while i < n:
        c = code[i]
        if c in " \t\r\n": i += 1; continue
        if c == "/" and code[i + 1:i + 2] == "/":
            j = code.find("\n", i); i = n if j < 0 else j; continue
        if c == "/" and code[i + 1:i + 2] == "*":
            i = code.index("*/", i) + 2; continue
        if c in "'\"":
            e = _skip_string(code, i); yield ("str", i, e, None, path()); ident = ""; i = e; prev = "s"; continue
        if c == "`":
            e, parts = _parse_template(code, i); yield ("tpl", i, e, parts, path()); i = e; prev = "s"; continue
        if c == "/" and (prev in REGEX_PREV or prev in ("return", "typeof")):
            # regex literal
            j = i + 1; cls = False
            while j < n:
                d = code[j]
                if d == "\\": j += 2; continue
                if d == "[": cls = True
                elif d == "]": cls = False
                elif d == "/" and not cls: break
                elif d == "\n": break
                j += 1
            j += 1
            while j < n and code[j].isalpha(): j += 1
            i = j; prev = "r"; continue
        if c.isalnum() or c in "_$":
            j = i
            while j < n and (code[j].isalnum() or code[j] in "_$"): j += 1
            if prev == "function": pending = code[i:j]
            prev = code[i:j]; ident = prev; i = j; continue
        if c in ":=" and code[i+1:i+2] not in "=>" and code[i-1:i] not in "=!<>":
            if c == "=" or ident: pending = ident
        elif c in "{[(":
            stack.append(pending); pending = ""
        elif c in "}])":
            popped = stack.pop() if len(stack) > len(base) else ""
            pending = popped if c == ")" else ""
        elif c in ",;":
            pending = ""
        if c not in " ": ident = "" if c not in ":=" else ident
        prev = c; i += 1

# ------------------------------------------------------------- unit handling

def js_unescape(s, q):
    # minimal: keep escapes as-is except \' \" \` which we normalise back on write
    return s

def looks_fragment(core):
    t = PH_RE.sub(" ", core).strip()
    if re.search(r"[<>]|=\"|^\"|\"$|^[.\[#{]|[{}]|;\s*$", t): return True
    if re.search(r"[a-z\-]+\([\d.,\s%a-z-]*\)", t) and not re.search(r"[A-Za-z]{3,} [a-z]{3,} [a-z]{3,}", t): return True
    if re.search(r"\b(DOCTYPE|px|rgba|cubic-bezier|onclick|innerHTML|addEventListener)\b", t): return True
    if t.count("_") >= 1 and not " " in t: return True
    return False

CODE_TOKEN = re.compile(r"&\w+;|\S+@\S+|(?:https?://)?[\w\-]+(?:\.[\w\-]+)*\.(?:jp|com|in|co|me|net|org|ai)\b\S*|\S*/\S*|\w+=\S+|\w*_\w+|[A-Z][a-z]+[A-Z]\w*")

def residual(t):
    return CODE_TOKEN.sub(" ", t)

# single lowercase words that are display text, not identifiers
DISPLAY_WORDS = {"claims", "points", "member", "days"}
# lowercase strings that are code even though they look like prose
CODE_STRINGS = {"hub-frame scaled"}
CSS_WORDS = {"top", "left", "right", "bottom", "center", "auto", "none", "both", "inherit"}

def looks_code(s):
    t = s.strip()
    if t in DISPLAY_WORDS: return False
    if t == "DOMContentLoaded" or re.fullmatch(r"\w+\(|[a-z]+ [\d.]+m?s|[a-z]{2}-[A-Z]{2}|[;%].*", t): return True
    r = residual(t)
    if not WORD.search(r): return True
    if CODE_TOKEN.search(t) and re.search(r"\w_\w|=", t) and len(WORD.findall(r)) <= 1: return True
    if not WORD.search(t): return True
    if re.fullmatch(r"[a-z0-9_$.\-]+", t): return True            # ids, keys, event names, classes
    if re.fullmatch(r"[a-z][a-zA-Z0-9]*", t) and not t.islower(): return True  # camelCase ids
    if re.fullmatch(r"[A-Z0-9_]{1,6}", t): return True             # SKU, UTM, OTP ...
    if re.match(r"^(https?:|mailto:|tel:|data:|#|\.\.?/|/)", t): return True
    if re.fullmatch(r"[\w./\-?=&%#:]+\.(png|jpe?g|svg|gif|webp|html|js|css|json|mp4)(\?.*)?", t): return True
    if re.fullmatch(r"[\w\-]+=[\w\-]+", t): return True
    if re.search(r"(^|;)\s*[a-z\-]+\s*:\s*[^;]+;", t) and not re.search(r"[A-Za-z]+ [a-z]+ [a-z]+", t.split(":")[0]): return True  # css
    if re.fullmatch(r"(?:[a-z\-]+:[^;]+;?\s*)+", t): return True
    if re.fullmatch(r"[\d\s.,%+\-×x/:#()]*[A-Za-z]{1,3}[\d\s.,%+\-×x/:()]*", t) and not re.search(r"[A-Za-z]{3}", t): return True
    if t in CODE_STRINGS or all(w in CSS_WORDS for w in t.split()): return True
    # class lists / selectors: need selector punctuation, or be a single token
    if not re.search(r"[A-Z]", t) and (re.search(r"[.#\[>]", t) or " " not in t) and all(re.fullmatch(r"[.#]?[a-z][\w\-]*(?:\[[^\]]*\])?(?::[\w\-()]+)?", w) for w in re.split(r"[\s>,+~]+", t) if w): return True  # selectors / class lists
    if re.fullmatch(r"[MmLlHhVvCcSsQqTtAaZz0-9\s.,\-]+", t) and re.search(r"\d", t): return True  # svg path
    if re.fullmatch(r"(rgba?|hsla?|url|translate\w*|scale|rotate|linear-gradient|calc|var)\(.*\)", t, re.S): return True
    if t in {"en-US", "ja-JP", "Arial", "Poppins", "Lexend Deca", "sans-serif", "monospace"}: return True
    if re.fullmatch(r"(?:[A-Z][a-z]+ )?[A-Z][a-z]+,\s*(?:sans-serif|serif|monospace).*", t): return True
    return False

def segment_markup(text, placeholders_in=None):
    """Split masked markup into (start,end) unit spans. placeholders already
    present (⟦n⟧ for ${}) count as inline. Returns list of (s,e)."""
    spans = []; seg_start = 0
    for m in TAG_RE.finditer(text):
        name = (m.group(2) or "").lower()
        if m.group(0).startswith("<!--") or name not in INLINE_TAGS:
            spans.append((seg_start, m.start())); seg_start = m.end()
    spans.append((seg_start, len(text)))
    return spans

def mask_unit(u, existing):
    """Mask inline tags in unit text u; existing is list of original strings for ⟦n⟧ already present.
    Returns (masked, table) where table maps placeholder -> original."""
    table = {}
    # re-number: collect in order of appearance, both existing placeholders and tags
    out = []; k = 0; pos = 0
    pat = re.compile(r"⟦(\d+)⟧|(?:\\n)+|\||" + TAG_RE.pattern, re.S)
    for m in pat.finditer(u):
        out.append(u[pos:m.start()])
        orig = existing[int(m.group(1))] if m.group(1) is not None else m.group(0)
        ph = f"⟦{k}⟧"; table[ph] = orig; out.append(ph); k += 1; pos = m.end()
    out.append(u[pos:])
    return "".join(out), table

def translatable_core(masked):
    """Trim leading/trailing whitespace, placeholders and punctuation-only edges.
    Returns (lead, core, trail) or None."""
    m = re.match(r"^((?:\s|⟦\d+⟧|&nbsp;|[·•→←↑↓✓✕×|:\-–—])*)(.*?)((?:\s|⟦\d+⟧|&nbsp;|[·•→←↑↓✓✕×|:\-–—])*)$", masked, re.S)
    lead, core, trail = m.group(1), m.group(2), m.group(3)
    # keep placeholders inside core balanced to what is actually in core
    if not WORD.search(PH_RE.sub("", core)): return None
    return lead, core, trail

def process_text(raw, tr, ctx, existing=None, is_markup=None):
    """raw: literal text (placeholders ⟦n⟧ refer to existing). Returns new text."""
    existing = existing or []
    if is_markup is None:
        is_markup = bool(TAG_RE.search(raw))
    if not is_markup:
        plain = PH_RE.sub("", raw)
        if looks_code(plain) and not existing: return raw
        if looks_code(plain) and existing and not re.search(r"[A-Za-z]+ [A-Za-z]+", plain): return raw
        spans = [(0, len(raw))]
    else:
        spans = segment_markup(raw)
    out = []; pos = 0
    for s, e in spans:
        out.append(raw[pos:s]); pos = e
        u = raw[s:e]
        masked, table = mask_unit(u, existing)
        tc = translatable_core(masked)
        if not tc: out.append(u); continue
        lead, core, trail = tc
        if looks_code(PH_RE.sub(" ", core)) or looks_fragment(core): out.append(u); continue
        # renumber core placeholders from 0
        order = PH_RE.findall(core); ren = {}; core2 = core
        for j, ph in enumerate(order): ren[f"⟦{j}⟧"] = table[ph]
        it = iter(range(len(order)))
        core2 = PH_RE.sub(lambda m: f"⟦{next(it)}⟧", core)
        res = tr(core2, ctx)
        if res is None: out.append(u); continue
        res = PH_RE.sub(lambda m: ren[m.group(0)], res)
        unmask = lambda x: PH_RE.sub(lambda m: table[m.group(0)], x)
        out.append(unmask(lead) + res + unmask(trail))
    out.append(raw[pos:])
    return "".join(out)

# --------------------------------------------------------------- renderers

def decode_esc(s):
    return re.sub(r"\\u([0-9a-fA-F]{4})|\\x([0-9a-fA-F]{2})", lambda m: chr(int(m.group(1) or m.group(2), 16)), s)

def _fix_quotes(s, q):
    # escape the literal's own quote char and newlines if the translation introduced them
    s = s.replace("\\", "\\\\") if False else s
    if q in "'\"":
        s = re.sub(r"(?<!\\)" + re.escape(q), "\\" + q, s).replace("\n", "\\n")
    else:
        s = re.sub(r"(?<!\\)`", "\\`", s)
    return s

def render_js(code, tr, ctx):
    out = []; pos = 0
    for kind, s, e, parts, pth in js_tokens(code, ctx.get("path", ())):
        out.append(code[pos:s]); pos = e
        lit = code[s:e]
        c2 = dict(ctx, pos=s, path=pth)
        if kind == "str":
            q = lit[0]; body = lit[1:-1]; bu = decode_esc(body.replace("\\" + q, q))
            nb = process_text(bu, tr, c2)
            out.append(q + (body if nb == bu else _fix_quotes(nb, q)) + q)
        else:
            existing = []; masked = []
            for p in parts:
                if isinstance(p, tuple):
                    inner = render_js(code[p[1]:p[2]], tr, c2)
                    masked.append(f"⟦{len(existing)}⟧"); existing.append("${" + inner + "}")
                else:
                    masked.append(decode_esc(p))
            raw = "".join(masked)
            nb = process_text(raw, tr, c2, existing)
            if nb == raw:
                nb = code[s + 1:e - 1]
            else:
                nb = _fix_quotes(nb, "`")
            out.append("`" + nb + "`")
    out.append(code[pos:])
    return "".join(out)

ATTR_RE = re.compile(r'\b(title|alt|placeholder|aria-label)="([^"]*)"')

def render_html(html, tr, ctx):
    """Translate text nodes & a few attributes in an HTML doc; inline <script> via render_js."""
    out = []; pos = 0
    for m in re.finditer(r"(<script\b[^>]*>)(.*?)(</script>)|(<style\b[^>]*>.*?</style>)|(<title>)(.*?)(</title>)", html, re.S):
        out.append(_html_body(html[pos:m.start()], tr, ctx)); pos = m.end()
        if m.group(1):
            out.append(m.group(1) + render_js(m.group(2), tr, ctx) + m.group(3))
        elif m.group(5):
            out.append(m.group(5) + process_text(m.group(6), tr, ctx, is_markup=False) + m.group(7))
        else:
            out.append(m.group(0))
    out.append(_html_body(html[pos:], tr, ctx))
    return "".join(out)

def _html_body(chunk, tr, ctx):
    chunk = process_text(chunk, tr, ctx, is_markup=True)
    return ATTR_RE.sub(lambda m: f'{m.group(1)}="{process_text(m.group(2), tr, ctx, is_markup=False)}"', chunk)
