"""English-on-hover for the Japanese build.

Each document (the hub and every embedded demo page) gets a small script plus
its own JA→EN pairs. Hovering Japanese text shows the English source in a
tooltip; on touch devices a long-press does the same. Enabled only when the
hub URL has ?en=1, which also shows an EN on/off button.

Demo pages live in scaled iframes, so they never draw the tooltip themselves:
they post the text and pointer position to their parent, which converts the
coordinates and, at the top document, renders the tooltip at full size.
"""
import html
import json
import re

PH = re.compile(r"⟦\d+⟧")
JA_CHAR = re.compile(r"[぀-ヿ㐀-鿿＀-￯]")


EDGE = " ·—–-:：、。"


def _clean(s):
    s = html.unescape(s.replace("\\n", " "))
    return re.sub(r"\s+", " ", s).strip()


def pairs_for(units):
    """units: iterable of (en_masked, ja_final) as inserted into this document.

    Returns {"k": [[ja, en], ...], "t": [[ja_tpl, en_tpl], ...]}:
    - k: units without placeholders, keyed by their full Japanese text. At
      runtime they also match pieces of text the page glues together
      ("Earn " + n + " points"), with the values in between kept.
    - t: units with ⟦n⟧ placeholders (inline markup, line breaks or ${}
      values). JA and EN share placeholder ids, so the runtime turns the
      Japanese into a pattern, captures the real values and fills them into
      the English.
    """
    keys, tpls = {}, {}
    for en, ja in units:
        if not ja:
            continue
        if PH.search(ja) or PH.search(en):
            lit = PH.sub("", ja)
            if len(JA_CHAR.findall(lit)) >= 2:
                tpls.setdefault(_clean(ja), _clean(en))
            continue
        k = _clean(ja).strip(EDGE)
        if k and JA_CHAR.search(k):
            v = _clean(en)
            if v not in keys.setdefault(k, []):
                keys[k].append(v)
    k = [[j, " / ".join(v)] for j, v in sorted(keys.items(), key=lambda kv: -len(kv[0]))]
    t = sorted(tpls.items(), key=lambda kv: -len(PH.sub("", kv[0])))
    return {"k": k, "t": [list(x) for x in t]}


SCRIPT = r"""
(function(){
if(window.__enTips)return;window.__enTips=1;
var MAP=__MAP__,EX={},KEYS=[],TPL=[],i;
for(i=0;i<MAP.k.length;i++){EX[MAP.k[i][0]]=MAP.k[i][1];KEYS.push(MAP.k[i][0]);}
var top_=window.parent===window, on=false, avail=false;
try{avail=top_&&/[?&]en=1(&|$)/.test(location.search);}catch(e){}
var JA=/[぀-ヿ㐀-鿿＀-￯]/, PH=/⟦(\d+)⟧/g, EDGE=/^[\s·—–:：、。-]+|[\s·—–:：、。-]+$/g;
function post(w,m){try{m.__entip=1;w.postMessage(m,"*");}catch(e){}}
function frames(){return Array.prototype.slice.call(document.querySelectorAll("iframe"));}
function broadcast(){frames().forEach(function(f){post(f.contentWindow,{t:"state",on:on});});}
function norm(t){return t.replace(/\s+/g," ").trim();}
function esc(s){return s.replace(/[.*+?^${}()|[\]\\]/g,"\\$&");}
var TRIM=/^[\s·•✓✔☐☑①-⑳—–:：、。\-]+|[\s·•✓✔☐☑—–:：、。\-]+$/g;
function trim(t){return norm(t).replace(TRIM,"");}
function tpls(){
  if(TPL.length||!MAP.t.length)return TPL;
  MAP.t.forEach(function(p){
    var ids=[],lit=0,src=trim(p[0]).split(/(⟦\d+⟧)/).map(function(part){
      var m=/^⟦(\d+)⟧$/.exec(part);
      if(m){ids.push(m[1]);return "([\\s\\S]*?)";}
      lit+=(part.match(/[぀-ヿ㐀-鿿]/g)||[]).length;
      return part.split(/\s+/).filter(Boolean).map(esc).join("\\s*");
    }).join("\\s*");
    var fl="";try{new RegExp("","d");fl="d";}catch(e){}
    var BR=/(?:\s*⟦\d+⟧){2,}\s*/,
        items=function(x){return trim(x).split(BR).map(function(y){return trim(y.replace(PH," "));});},
        seq=function(x){return (x.match(/⟦\d+⟧/g)||[]).join("");},
        ji=items(p[0]),ei=items(p[1]),same=ji.length>1&&ji.length===ei.length&&seq(p[0])===seq(p[1]);
    try{TPL.push({re:new RegExp("^"+src+"$",fl),loose:lit>=6?new RegExp(src,fl):null,ids:ids,en:p[1],items:same?[ji,ei]:null});}catch(e){}
  });
  return TPL;
}
function value(v){ /* a captured value may itself be translated text */
  v=norm(v);if(!v||!JA.test(v))return v;
  var k=trim(v);return EX[k]||compose(v)||v;
}
function apply(T,m){
  var got={};T.ids.forEach(function(id,j){got[id]=m[j+1];});
  return norm(T.en.replace(PH,function(_,id){return got[id]!=null?" "+value(got[id])+" ":" ";}))
    .replace(/\s+([,.!?;:)])/g,"$1").replace(/([(])\s+/g,"$1");
}
/* does the hovered text [off,off+len) land on the template's own words,
   not only inside a ${}-style capture? (stops a big container template
   from claiming unrelated text that happens to sit in one of its slots) */
function onLiteral(m,off,len){
  if(!m.indices)return true;
  var s0=m.indices[0][0],s1=m.indices[0][1],caps=m.indices.slice(1);
  for(var p=Math.max(off,s0);p<Math.min(off+len,s1);p++){
    var inCap=false;
    for(var j=0;j<caps.length;j++)if(caps[j]&&p>=caps[j][0]&&p<caps[j][1]){inCap=true;break;}
    if(!inCap&&!/\s/.test(c_[p]))return true;
  }
  return false;
}
var c_="";
/* match the text of container c (the hovered node itself, or an ancestor) */
function item(T,node){
  if(!T.items)return "";var i=T.items[0].indexOf(node);
  return i>=0&&T.items[1][i]&&!/⟦/.test(T.items[0][i])?T.items[1][i]:"";
}
function fill(c,node,edges){
  var L=tpls(),k,m,off;c_=c=trim(c);if(!c)return "";
  node=node==null?c:node;off=c.indexOf(node);if(off<0)return "";
  for(k=0;k<L.length;k++){m=L[k].re.exec(c);if(m&&onLiteral(m,off,node.length))return item(L[k],node)||apply(L[k],m);}
  for(k=0;k<L.length;k++){
    if(!L[k].loose)continue;m=L[k].loose.exec(c);if(!m||!onLiteral(m,off,node.length))continue;
    if(!edges)return item(L[k],node)||apply(L[k],m);
    /* the sentence sits next to other text in the same node */
    var pre=trim(c.slice(0,m.index)),post=trim(c.slice(m.index+m[0].length)),out=[];
    if(pre){pre=value(pre);if(JA.test(pre))pre="";}
    if(post){post=value(post);if(JA.test(post))post="";}
    [pre,apply(L[k],m),post].forEach(function(x){if(x)out.push(x);});
    return out.join(" · ");
  }
  return "";
}
function compose(t){ /* known pieces in order; anything between them (numbers, names) is kept */
  var used=[],k,key,p,j,ok,any=false;
  for(k=0;k<KEYS.length;k++){
    key=KEYS[k];p=t.indexOf(key);
    while(p>=0){
      ok=true;for(j=0;j<used.length;j++)if(p<used[j][1]&&p+key.length>used[j][0]){ok=false;break;}
      if(ok&&key.length===1&&(JA.test(t.charAt(p-1)||"")||JA.test(t.charAt(p+1)||"")))ok=false;
      if(ok){used.push([p,p+key.length,EX[key]]);any=true;}
      p=t.indexOf(key,p+key.length);
    }
  }
  if(!any)return "";
  used.sort(function(a,b){return a[0]-b[0];});
  var out=[],pos=0,gap;
  var keep=function(g){g=norm(g);return /^[\s·・、。：:,，;；]*$/.test(g)?"":g;};
  used.forEach(function(u){gap=keep(t.slice(pos,u[0]));if(gap)out.push(gap);out.push(u[2]);pos=u[1];});
  gap=keep(t.slice(pos));if(gap)out.push(gap);
  var s=norm(out.join(" ")).replace(/\s+([,.!?;:)])/g,"$1");
  return JA.test(s)?"":s;
}
var memo={};
function lookup(t){
  t=norm(t);var k=trim(t);
  if(k.length<1||!JA.test(k))return "";
  if(k in memo)return memo[k];
  return memo[k]=EX[k]||fill(t,null,true)||compose(t)||"";
}
function lookupNode(n){
  var t=norm(n.textContent);if(!JA.test(t))return "";
  var k=trim(t);if(!k)return "";if(EX[k])return EX[k];
  /* the node itself, then enclosing elements: inline markup splits a
     sentence across text nodes */
  var r=fill(t,null,true),el=n.parentElement;
  for(var d=0;!r&&el&&d<3;d++,el=el.parentElement){
    var c=norm(el.textContent);if(c.length>400)break;
    r=fill(c,k,false);
  }
  return r||compose(t)||"";
}
window.__enTipsLookup=lookupNode;
function textAt(x,y){
  var r=document.caretRangeFromPoint?document.caretRangeFromPoint(x,y):null,n;
  if(!r&&document.caretPositionFromPoint){var c=document.caretPositionFromPoint(x,y);n=c&&c.offsetNode;}
  else n=r&&r.startContainer;
  if(!n||n.nodeType!==3)return "";
  var rr=document.createRange();rr.selectNodeContents(n);
  var rs=rr.getClientRects(),hit=false;
  for(var q=0;q<rs.length;q++){var b=rs[q];if(x>=b.left-2&&x<=b.right+2&&y>=b.top-2&&y<=b.bottom+2){hit=true;break;}}
  return hit?lookupNode(n):"";
}
/* ---- rendering (top document only) ---- */
var tip=null,hideT=0;
function ensureTip(){
  if(tip)return tip;
  tip=document.createElement("div");tip.id="en-tip";tip.setAttribute("role","tooltip");
  tip.style.cssText="position:fixed;left:0;top:0;z-index:2147483647;pointer-events:none;max-width:300px;"+
    "padding:5px 8px;border-radius:6px;background:rgba(17,22,33,0.92);color:#fff;font:500 11.5px/1.4 -apple-system,BlinkMacSystemFont,Segoe UI,Arial,sans-serif;"+
    "letter-spacing:0;box-shadow:0 4px 14px rgba(0,0,0,0.25);opacity:0;transition:opacity .12s;white-space:normal;word-break:normal;overflow-wrap:anywhere";
  (document.body||document.documentElement).appendChild(tip);return tip;
}
function render(text,x,y){
  var t=ensureTip();t.textContent=text;t.style.opacity="0";t.style.display="block";
  var w=t.offsetWidth,h=t.offsetHeight,W=innerWidth,H=innerHeight,
      l=Math.min(Math.max(6,x+12),W-w-6),tp=y+18;
  if(tp+h>H-6)tp=y-h-12;
  t.style.transform="translate("+Math.round(l)+"px,"+Math.round(Math.max(6,tp))+"px)";
  t.style.opacity="1";
}
function unrender(){if(tip){tip.style.opacity="0";}}
function show(text,x,y){if(top_)render(text,x,y);else post(window.parent,{t:"show",text:text,x:x,y:y});}
function hide(){if(top_)unrender();else post(window.parent,{t:"hide"});}
/* ---- hover ---- */
var cur="",timer=0,lx=0,ly=0,raf=0;
function onMove(e){
  if(!on||e.pointerType==="touch")return;lx=e.clientX;ly=e.clientY;
  if(raf)return;raf=requestAnimationFrame(function(){raf=0;
    var t=textAt(lx,ly);
    if(t!==cur){cur=t;clearTimeout(timer);hide();if(t)timer=setTimeout(function(){show(cur,lx,ly);},350);}
  });
}
document.addEventListener("pointermove",onMove,true);
document.addEventListener("pointerdown",function(e){if(e.pointerType!=="touch"){clearTimeout(timer);cur="";hide();}},true);
document.addEventListener("mouseout",function(e){if(!e.relatedTarget){clearTimeout(timer);cur="";hide();}},true);
/* ---- long-press on touch ---- */
var lp=0,sx=0,sy=0,shownByTouch=0;
document.addEventListener("touchstart",function(e){
  if(!on||e.touches.length!==1)return;var p=e.touches[0];sx=p.clientX;sy=p.clientY;clearTimeout(lp);
  lp=setTimeout(function(){var t=textAt(sx,sy);if(t){show(t,sx,sy);shownByTouch=Date.now();clearTimeout(hideT);hideT=setTimeout(hide,3000);}},450);
},{passive:true,capture:true});
document.addEventListener("touchmove",function(e){var p=e.touches[0];if(p&&Math.abs(p.clientX-sx)+Math.abs(p.clientY-sy)>10)clearTimeout(lp);},{passive:true,capture:true});
document.addEventListener("touchend",function(){clearTimeout(lp);},{passive:true,capture:true});
document.addEventListener("contextmenu",function(e){if(on&&Date.now()-shownByTouch<1500)e.preventDefault();},true);
/* ---- messages between frames ---- */
function frameOf(src){var f=frames();for(var k=0;k<f.length;k++)if(f[k].contentWindow===src)return f[k];return null;}
window.addEventListener("message",function(e){
  var d=e.data;if(!d||d.__entip!==1)return;
  if(d.t==="ask"){if(frameOf(e.source))post(e.source,{t:"state",on:on});return;}
  if(d.t==="state"&&e.source===window.parent&&!top_){on=!!d.on;if(!on){cur="";clearTimeout(timer);}broadcast();return;}
  var f=frameOf(e.source);if(!f)return;
  if(d.t==="hide"){hide();return;}
  if(d.t==="show"&&on){
    var r=f.getBoundingClientRect(),s=f.clientWidth?r.width/f.clientWidth:1;
    show(d.text,r.left+f.clientLeft*s+d.x*s,r.top+f.clientTop*s+d.y*s);
  }
});
document.addEventListener("load",function(e){if(e.target&&e.target.tagName==="IFRAME")post(e.target.contentWindow,{t:"state",on:on});},true);
if(!top_)post(window.parent,{t:"ask"});
/* ---- EN switch (top document, only with ?en=1) ---- */
if(avail){
  on=true;
  var st=document.createElement("style");
  st.textContent="#en-switch{position:fixed;top:10px;right:12px;z-index:2147483646;height:26px;padding:0 10px;border-radius:13px;"+
    "border:1px solid rgba(5,39,98,0.25);background:#fff;color:#052762;font:700 11px/24px -apple-system,BlinkMacSystemFont,Arial,sans-serif;"+
    "letter-spacing:1px;cursor:pointer;box-shadow:0 2px 8px rgba(5,39,98,0.15);opacity:.9}"+
    "#en-switch[aria-pressed=false]{background:#EDF1F8;color:#8a94ab}"+
    "#en-switch:hover{opacity:1}"+
    "@media (max-width:700px){#en-switch{top:auto;bottom:78px;right:10px}}";
  document.head.appendChild(st);
  var b=document.createElement("button");b.id="en-switch";b.type="button";b.textContent="EN";
  b.setAttribute("aria-pressed","true");b.title="English on hover";
  b.addEventListener("click",function(){on=!on;b.setAttribute("aria-pressed",String(on));if(!on){cur="";clearTimeout(timer);unrender();}broadcast();});
  (document.body||document.documentElement).appendChild(b);
  broadcast();
}
})();
"""


def script_tag(pairs):
    data = json.dumps(pairs, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    return "<script>" + SCRIPT.replace("__MAP__", data) + "</script>"


def inject(template, pairs):
    i = template.rfind("</body>")
    tag = script_tag(pairs)
    return template[:i] + tag + template[i:] if i >= 0 else template + tag
