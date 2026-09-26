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


def _clean(s):
    s = html.unescape(s.replace("\\n", " "))
    return re.sub(r"\s+", " ", s).strip()


def pairs_for(units):
    """units: iterable of (en_masked, ja_final). Returns [[ja_segment, en], ...].

    Inline markup and ${} values were masked as ⟦n⟧, so on the page a unit can
    be split across several text nodes; every Japanese piece between
    placeholders becomes a key pointing at the whole English unit.
    """
    out = {}
    for en, ja in units:
        if not ja:
            continue
        en_txt = _clean(PH.sub(" ", en))
        for seg in PH.split(ja):
            seg = _clean(seg).strip(" ·—–-:：、。")
            if len(seg) >= 2 and JA_CHAR.search(seg):
                out.setdefault(seg, [])
                if en_txt not in out[seg]:
                    out[seg].append(en_txt)
    return [[k, " / ".join(v)] for k, v in sorted(out.items(), key=lambda kv: -len(kv[0]))]


SCRIPT = r"""
(function(){
if(window.__enTips)return;window.__enTips=1;
var MAP=__MAP__,EX={},KEYS=[],i;
for(i=0;i<MAP.length;i++){EX[MAP[i][0]]=MAP[i][1];KEYS.push(MAP[i][0]);}
var top_=window.parent===window, on=false, avail=false;
try{avail=top_&&/[?&]en=1(&|$)/.test(location.search);}catch(e){}
var JA=/[぀-ヿ㐀-鿿＀-￯]/;
function post(w,m){try{m.__entip=1;w.postMessage(m,"*");}catch(e){}}
function frames(){return Array.prototype.slice.call(document.querySelectorAll("iframe"));}
function broadcast(){frames().forEach(function(f){post(f.contentWindow,{t:"state",on:on});});}
function lookup(t){
  t=t.replace(/\s+/g," ").trim().replace(/^[\s·—–:：、。-]+|[\s·—–:：、。-]+$/g,"");
  if(t.length<2||!JA.test(t))return "";
  if(EX[t])return EX[t];
  var hits=[],used=[],k,p,j,ok;
  for(k=0;k<KEYS.length&&hits.length<4;k++){
    p=t.indexOf(KEYS[k]);if(p<0)continue;
    ok=true;for(j=0;j<used.length;j++)if(p<used[j][1]&&p+KEYS[k].length>used[j][0])ok=false;
    if(ok){used.push([p,p+KEYS[k].length]);hits.push([p,EX[KEYS[k]]]);}
  }
  hits.sort(function(a,b){return a[0]-b[0];});
  return hits.map(function(h){return h[1];}).join(" … ");
}
function textAt(x,y){
  var r=document.caretRangeFromPoint?document.caretRangeFromPoint(x,y):null,n;
  if(!r&&document.caretPositionFromPoint){var c=document.caretPositionFromPoint(x,y);n=c&&c.offsetNode;}
  else n=r&&r.startContainer;
  if(!n||n.nodeType!==3)return "";
  var rr=document.createRange();rr.selectNodeContents(n);
  var rs=rr.getClientRects(),hit=false;
  for(var q=0;q<rs.length;q++){var b=rs[q];if(x>=b.left-2&&x<=b.right+2&&y>=b.top-2&&y<=b.bottom+2){hit=true;break;}}
  return hit?lookup(n.textContent):"";
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
