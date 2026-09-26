"""Recursive unpack/repack for the __bundler HTML format."""
import json,re,base64,gzip

BLOCK=r'(<script type="__bundler/{t}">\n)(.*?)(\n  </script>)'
TEXT_MIMES=('text/','application/javascript','application/json','image/svg')

def _get(h,t):
    m=re.search(BLOCK.format(t=t),h,re.S); return m

def is_bundle(h): return '<script type="__bundler/manifest">' in h

def walk(h,path='root'):
    """Yield (path, kind, text) for every text unit, recursing into nested bundles."""
    man=json.loads(_get(h,'manifest').group(2)); tpl=json.loads(_get(h,'template').group(2))
    yield (path+'/template','template',tpl)
    for u,e in man.items():
        if not e['mime'].startswith(TEXT_MIMES): continue
        b=base64.b64decode(e['data'])
        if e['compressed']: b=gzip.decompress(b)
        t=b.decode('utf-8')
        if is_bundle(t): yield from walk(t,path+'/'+u)
        else: yield (path+'/'+u,e['mime'],t)

def rebuild(h,fn,path='root'):
    """fn(path,kind,text)->new text. Returns rebuilt bundle HTML."""
    mm=_get(h,'manifest'); man=json.loads(mm.group(2))
    tm=_get(h,'template'); tpl=json.loads(tm.group(2))
    changed=False
    for u,e in man.items():
        if not e['mime'].startswith(TEXT_MIMES): continue
        b=base64.b64decode(e['data'])
        if e['compressed']: b=gzip.decompress(b)
        t=b.decode('utf-8')
        nt=rebuild(t,fn,path+'/'+u) if is_bundle(t) else fn(path+'/'+u,e['mime'],t)
        if nt!=t:
            nb=nt.encode('utf-8')
            if e['compressed']: nb=gzip.compress(nb,9,mtime=0)
            e['data']=base64.b64encode(nb).decode(); changed=True
    ntpl=fn(path+'/template','template',tpl)
    # outer shell of this bundle (e.g. <title>, loading text) handled by fn too
    if ntpl==tpl and not changed: return h
    # template JSON: keep the original's escaping style for </ 
    tjson=json.dumps(ntpl,ensure_ascii=False).replace('</','<\\u002F')
    mjson=json.dumps(man,separators=(',',':'))
    h=h[:tm.start(2)]+tjson+h[tm.end(2):]
    mm=_get(h,'manifest')
    h=h[:mm.start(2)]+mjson+h[mm.end(2):]
    return h
