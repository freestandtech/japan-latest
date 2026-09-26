import re
CONSUMER_FILES={"line"}
CONSUMER_KEYS={
 "reengage":{"MTABS","phone","FIRST","WHEEL","STK","TANZ","tier","MA_TITLE","MA_MENU","MA_TOAST","maTier","maBody","maSheet","miniApp","dl","wd","del","openViewer","tickPts","spin","wishFlow",""},
 "journey":{"igFrame","webScreen","siteNav","leftHtml"},
 "appi":{"notice","consent","fields","formPrev"},
 "popups":{"track"},
 "tpl":{"groups","friend","track","ig","media2","heroT","formTitle","formCta","fields","pages","trackLabel","web"},
}
B2B_IN_CONSUMER={"redata":{"profile","cohorts","captured","opps","brand","program"}}
def tag(kind,path):
    parts=path.split('/') if path else []
    if kind in CONSUMER_FILES: return "consumer"
    if kind=="redata": return "b2b" if set(parts)&B2B_IN_CONSUMER["redata"] else "consumer"
    if kind=="reengage":
        top=parts[0] if parts else ""
        return "consumer" if top in CONSUMER_KEYS["reengage"] else "b2b"
    if kind.startswith("tpl:Nestlé LACTOGROW") and set(parts)&CONSUMER_KEYS["tpl"]: return "consumer"
    if kind in CONSUMER_KEYS and set(parts)&CONSUMER_KEYS[kind]: return "consumer"
    return "b2b"
