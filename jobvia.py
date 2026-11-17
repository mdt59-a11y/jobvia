"""Jobvia - free automated job board. One file.
Usage:  python jobvia.py fetch   (collect jobs)
        python jobvia.py build   (generate site into dist/)
        python jobvia.py index   (notify Google + IndexNow after deploy)
"""
import os, sys, json, re, html, hashlib, datetime, shutil, urllib.request, urllib.parse
import xml.etree.ElementTree as ET, email.utils

# ======================= CONFIG =======================
SITE = os.environ.get("SITE_URL", "https://jobvia.pages.dev").rstrip("/")
CONTACT_EMAIL = os.environ.get("CONTACT_EMAIL", "mdwnt3959@gmail.com")   # change to your site email
W3F_KEY = os.environ.get("WEB3FORMS_KEY", "PUT_WEB3FORMS_KEY")         # free key from web3forms.com
INDEXNOW_KEY = os.environ.get("INDEXNOW_KEY", "c7a41f0e9b2d4a68b35e1d7f90a2c486")
DAILY_LIMIT = int(os.environ.get("DAILY_LIMIT", "50"))                  # new jobs per day; raise slowly
EXPIRE_DAYS = 30
# section -> (flag, language of the section)
SECTIONS = {"us": ("🇺🇸", "en"), "gb": ("🇬🇧", "en"), "ca": ("🇨🇦", "en"),
            "fr": ("🇫🇷", "fr"), "de": ("🇩🇪", "de"), "remote": ("🌍", "en"), "gov": ("🏛️", "en")}
NAMES = {
 "us": {"en": "United States", "fr": "États-Unis", "de": "USA", "ar": "أمريكا"},
 "gb": {"en": "United Kingdom", "fr": "Royaume-Uni", "de": "Vereinigtes Königreich", "ar": "بريطانيا"},
 "ca": {"en": "Canada", "fr": "Canada", "de": "Kanada", "ar": "كندا"},
 "fr": {"en": "France", "fr": "France", "de": "Frankreich", "ar": "فرنسا"},
 "de": {"en": "Germany", "fr": "Allemagne", "de": "Deutschland", "ar": "ألمانيا"},
 "remote": {"en": "Remote", "fr": "Télétravail", "de": "Remote", "ar": "عن بعد"},
 "gov": {"en": "Government & public sector", "fr": "Secteur public", "de": "Öffentlicher Dienst", "ar": "وظائف حكومية"},
}
T = {
 "en": {"tag": "Real jobs from official sources, updated every day", "search": "Search title, company, city",
        "apply": "Apply on the official site", "latest": "Latest jobs", "browse": "Browse by country",
        "posted": "Posted", "none": "No jobs match your search.", "post": "Post a job", "contact": "Contact",
        "privacy": "Privacy", "about": "About", "company": "Company", "where": "Location", "all": "All jobs in",
        "h1": "Find the job. Skip the fake ones.", "sub": "Every listing links to the employer's or government's own application page."},
 "fr": {"tag": "De vraies offres issues de sources officielles, chaque jour", "search": "Poste, entreprise, ville",
        "apply": "Postuler sur le site officiel", "latest": "Dernières offres", "browse": "Parcourir par pays",
        "posted": "Publié le", "none": "Aucune offre ne correspond.", "post": "Publier une offre", "contact": "Contact",
        "privacy": "Confidentialité", "about": "À propos", "company": "Entreprise", "where": "Lieu", "all": "Toutes les offres :",
        "h1": "Trouvez l'emploi. Évitez les fausses offres.", "sub": "Chaque offre renvoie vers la page de candidature officielle."},
 "de": {"tag": "Echte Jobs aus offiziellen Quellen, täglich aktuell", "search": "Titel, Firma, Stadt",
        "apply": "Auf der offiziellen Seite bewerben", "latest": "Neueste Jobs", "browse": "Nach Land stöbern",
        "posted": "Veröffentlicht", "none": "Keine passenden Jobs gefunden.", "post": "Job veröffentlichen", "contact": "Kontakt",
        "privacy": "Datenschutz", "about": "Über uns", "company": "Unternehmen", "where": "Ort", "all": "Alle Jobs in",
        "h1": "Finde den Job. Ohne Fake-Anzeigen.", "sub": "Jede Anzeige führt zur offiziellen Bewerbungsseite."},
 "ar": {"tag": "وظائف حقيقية من مصادر رسمية، تتحدث يوميا", "search": "ابحث بالمسمى أو الشركة أو المدينة",
        "apply": "قدّم عبر الموقع الرسمي", "latest": "أحدث الوظائف", "browse": "تصفح حسب الدولة",
        "posted": "تاريخ النشر", "none": "لا توجد وظائف مطابقة.", "post": "انشر وظيفة", "contact": "تواصل معنا",
        "privacy": "الخصوصية", "about": "عن الموقع", "company": "الشركة", "where": "المكان", "all": "كل الوظائف في",
        "h1": "لقِ وظيفتك. وتجنّب الوظائف الوهمية.", "sub": "كل إعلان يفتح صفحة التقديم الرسمية عند الجهة صاحبة الوظيفة."},
}
PRICES = [("Standard listing", "$49", "30 days on your country page"),
          ("Featured listing", "$99", "Pinned on top for 14 days + homepage slot"),
          ("Banner", "$149", "Site-wide banner for 30 days")]

# Keyless public feeds. (url, source name, country code, location). Edit freely: add any employer's public RSS here.
GOV_FEEDS = [
 ("https://careers.who.int/careersection/feed/joblist.rss?lang=en&portal=14105024709&searchtype=3&f=null&s=3|D&a=null&multiline=true", "WHO", "CH", "International"),
 ("https://www.crd.bc.ca/feeds/crd-career-opportunities", "CRD British Columbia", "CA", "British Columbia"),
 ("https://www.jobs.act.gov.au/rss/subscribe?search_page_449671_submit_button=all", "ACT Government", "AU", "Canberra"),
 ("https://www.jobs.ac.uk/feeds/subject-areas/law", "jobs.ac.uk", "GB", "United Kingdom"),
 ("https://www.jobs.ac.uk/feeds/subject-areas/computer-sciences", "jobs.ac.uk", "GB", "United Kingdom"),
]
# sources whose terms ask for a visible, followed link back
ATTR = {"RemoteOK", "WeWorkRemotely", "Himalayas", "Remotive", "Jobicy", "WorkingNomads"}
CC = {"us": "US", "gb": "GB", "ca": "CA", "fr": "FR", "de": "DE"}

DB = "data/jobs.json"
TODAY = datetime.date.today()
TODAY_S = TODAY.isoformat()
E = html.escape
OUT = "dist"
JOBS = []
LANGS = ["en", "fr", "de", "ar"]
HOME = {"en": "/", "fr": "/fr/", "de": "/de/", "ar": "/ar/"}
CSS = r'''
:root{--ink:#0B1530;--paper:#F4F6FB;--card:#fff;--line:#DCE2EE;--amber:#FFB547;--blue:#2F5BFF;--mute:#56627F;--dir:1}
[dir=rtl]{--dir:-1}
@media(prefers-color-scheme:dark){:root{--ink:#E9EDF6;--paper:#0F1726;--card:#172236;--line:#26324A;--mute:#A5B0C8;--blue:#7C9BFF}}
*{box-sizing:border-box}html{scroll-behavior:smooth}
body{margin:0;background:var(--paper);color:var(--ink);font:16px/1.7 Manrope,Cairo,system-ui,sans-serif;-webkit-text-size-adjust:100%}
[dir=rtl] body{font-family:Cairo,Manrope,system-ui,sans-serif}
a{color:inherit;text-decoration:none}
a:focus-visible,input:focus-visible,button:focus-visible,select:focus-visible,textarea:focus-visible{outline:3px solid var(--blue);outline-offset:2px}
.top{display:flex;align-items:center;justify-content:space-between;gap:16px;padding:12px 5vw;background:var(--card);border-bottom:1px solid var(--line);position:sticky;top:0;z-index:10}
.logo{display:flex;align-items:center;gap:10px;font-weight:800;font-size:22px}
.top .desk{display:none}
.sec{gap:4px;flex:1;margin:0 12px}.sec a{padding:6px 11px;border-radius:999px;font-size:14px;font-weight:600;color:var(--mute);white-space:nowrap}.sec a:hover{background:var(--paper);color:var(--ink)}
.lang{gap:2px}.lang a{padding:4px 8px;font-size:13px;font-weight:700;color:var(--mute);border-radius:6px}.lang a:hover{background:var(--paper)}
@media(min-width:1320px){.top .desk{display:flex;align-items:center}.top .burger{display:none}}
.burger{width:44px;height:44px;border:1px solid var(--line);border-radius:12px;background:var(--paper);display:grid;place-content:center;gap:5px;cursor:pointer}
.burger span{display:block;width:20px;height:2px;border-radius:2px;background:var(--ink)}
.scrim{position:fixed;inset:0;background:rgba(5,10,25,.55);opacity:0;pointer-events:none;transition:opacity .25s;z-index:19}
.drawer{position:fixed;top:0;bottom:0;inset-inline-end:0;width:min(86vw,340px);background:var(--card);padding:18px 18px 28px;overflow:auto;z-index:20;transform:translateX(calc(var(--dir)*100%));visibility:hidden;transition:transform .25s,visibility .25s;display:flex;flex-direction:column;gap:6px;box-shadow:0 0 40px rgba(0,0,0,.35)}
body.open .drawer{transform:none;visibility:visible}body.open .scrim{opacity:1;pointer-events:auto}body.open{overflow:hidden}
.dhead{display:flex;align-items:center;justify-content:space-between;margin-bottom:8px;font-weight:800;font-size:20px}
.close{width:40px;height:40px;border:1px solid var(--line);border-radius:10px;background:var(--paper);color:var(--ink);font-size:22px;cursor:pointer}
.dtitle{color:var(--mute);font-size:14px;margin:14px 4px 4px}
.drawer .item{display:flex;align-items:center;gap:12px;padding:13px 12px;border-radius:12px;font-weight:600;font-size:17px}.drawer .item:hover,.drawer .item:active{background:var(--paper)}
.drawer .pills{display:flex;gap:8px;flex-wrap:wrap}.drawer .pills a{padding:8px 16px;border:1px solid var(--line);border-radius:999px;font-weight:700}
.btn{background:var(--amber);color:#0B1530;font-weight:800;padding:10px 18px;border-radius:12px;border:0;cursor:pointer;font:inherit;font-weight:800;transition:transform .15s;display:inline-block;text-align:center}.btn:hover{transform:translateY(-2px)}.btn.big{padding:14px 26px;margin-top:14px}
.drawer .btn{margin-top:18px}
main{max-width:1040px;margin:0 auto;padding:0 5vw 70px}section{margin-top:52px}
.hero{padding-top:44px}.hero h1{font-size:clamp(30px,7vw,60px);line-height:1.25;margin:0 0 16px;font-weight:800;letter-spacing:-.01em;max-width:16em}
.hero p{color:var(--mute);font-size:18px;max-width:34em;margin:0}.hero.small{padding-top:30px}.hero.small h1{font-size:clamp(26px,4.5vw,42px)}
.route{width:100%;height:auto;margin-top:34px;overflow:visible}
.route .line{fill:none;stroke:var(--blue);stroke-width:3;stroke-linecap:round;stroke-dasharray:1;stroke-dashoffset:1;animation:draw 2.4s .2s ease-out forwards}
.route .node circle{fill:var(--card);stroke:var(--amber);stroke-width:3}.route .node text{font-size:17px}
.route .node{opacity:0;transform-box:fill-box;transform-origin:center;animation:pop .5s calc(.3s + var(--i)*.35s) cubic-bezier(.3,1.6,.5,1) forwards}
@keyframes draw{to{stroke-dashoffset:0}}@keyframes pop{from{opacity:0;transform:scale(.3)}to{opacity:1;transform:none}}
h2{font-size:21px;margin:0 0 16px}
.cards{display:grid;grid-template-columns:repeat(auto-fill,minmax(190px,1fr));gap:10px}
.card{display:flex;align-items:center;gap:12px;background:var(--card);border:1px solid var(--line);border-radius:14px;padding:14px 16px;transition:border-color .15s}
.card:hover{border-color:var(--blue)}.card .fl{font-size:24px;line-height:1}.card b{flex:1;font-size:16px}.card i{font-style:normal;color:var(--mute);font-size:14px}
.q{width:100%;padding:14px 16px;border:1px solid var(--line);border-radius:12px;background:var(--card);color:var(--ink);font:inherit;margin-bottom:14px}
.list{display:flex;flex-direction:column;border:1px solid var(--line);border-radius:14px;overflow:hidden;background:var(--card)}
.job{display:flex;flex-wrap:wrap;align-items:center;gap:2px 14px;padding:15px 18px;border-bottom:1px solid var(--line)}
.job:last-child{border-bottom:0}.job:hover{background:var(--paper)}.job[hidden]{display:none}
.jt{font-weight:700;width:100%}.jc,.jl,time{color:var(--mute);font-size:14px}.js{margin-inline-start:auto}
@media(min-width:760px){.job{flex-wrap:nowrap;display:grid;grid-template-columns:2.2fr 1.3fr 1.3fr auto auto;gap:12px}.jt{width:auto}.js{margin:0}}
.post{max-width:720px;padding-top:44px}.post h1{font-size:clamp(26px,4vw,38px);line-height:1.25;margin:12px 0 18px}
.back{color:var(--blue);font-weight:600}dl{display:grid;grid-template-columns:auto 1fr;gap:6px 18px;margin:0 0 22px}dt{color:var(--mute)}dd{margin:0;font-weight:600}
.desc{white-space:pre-line}.srcline{color:var(--mute);font-size:14px}
form{display:grid;gap:14px;margin-top:20px}label{display:grid;gap:6px;font-weight:600}
input,textarea,select{padding:12px 14px;border:1px solid var(--line);border-radius:10px;font:inherit;background:var(--card);color:var(--ink)}
.prices{display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:12px;margin:18px 0}
.price{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:18px;display:grid;gap:4px}.price span{font-size:30px;font-weight:800}.price small{color:var(--mute)}
footer{display:flex;flex-wrap:wrap;justify-content:space-between;gap:12px;padding:26px 5vw;border-top:1px solid var(--line);color:var(--mute);font-size:14px}footer div:last-child{display:flex;gap:18px;flex-wrap:wrap}
@media(prefers-reduced-motion:reduce){*{animation:none!important;transition:none!important}.route .line{stroke-dashoffset:0}.route .node{opacity:1}}
'''
JS = r'''
var b=document.body,t=document.querySelector('.burger');
function setMenu(o){b.classList.toggle('open',o);if(t)t.setAttribute('aria-expanded',o)}
if(t)t.addEventListener('click',function(){setMenu(!b.classList.contains('open'))});
document.querySelectorAll('[data-close]').forEach(function(e){e.addEventListener('click',function(){setMenu(false)})});
document.addEventListener('keydown',function(e){if(e.key==='Escape')setMenu(false)});
document.querySelectorAll('.q').forEach(function(q){
  q.addEventListener('input',function(){
    var v=q.value.trim().toLowerCase();
    q.parentNode.querySelectorAll('.job').forEach(function(r){r.hidden=v&&r.dataset.q.indexOf(v)<0});
  });
});
'''

# ======================= FETCH =======================
def get(url, headers=None, data=None):
    req = urllib.request.Request(url, headers=headers or {"User-Agent": "JobviaBot/1.0"}, data=data)
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode())

def clean(s, n=900):
    s = re.sub(r"<[^>]+>", " ", html.unescape(s or ""))
    return re.sub(r"\s+", " ", s).strip()[:n]

def day(v):
    if isinstance(v, (int, float)): return datetime.date.fromtimestamp(v).isoformat()
    return (v or TODAY.isoformat())[:10]

def job(src, sid, sec, title, company, loc, url, desc, posted, remote=False):
    if not (title and url): return None
    jid = hashlib.sha1(f"{src}:{sid}".encode()).hexdigest()[:12]
    return {"id": jid, "section": sec, "title": clean(title, 140), "company": clean(company, 90) or "-",
            "location": clean(loc, 90), "url": url, "desc": clean(desc), "posted": day(posted),
            "remote": remote, "source": src, "first_seen": TODAY.isoformat()}

def adzuna():
    i, k = os.environ.get("ADZUNA_APP_ID"), os.environ.get("ADZUNA_APP_KEY")
    if not (i and k): return []
    out = []
    for cc in ["us", "gb", "ca", "de", "fr"]:
        try:
            d = get(f"https://api.adzuna.com/v1/api/jobs/{cc}/search/1?app_id={i}&app_key={k}&results_per_page=50&sort_by=date&content-type=application/json")
            out += [job("adzuna", r["id"], cc, r["title"], r["company"]["display_name"], r["location"]["display_name"],
                        r["redirect_url"], r["description"], r["created"]) for r in d["results"]]
        except Exception as e: print("adzuna", cc, e)
    return out

def usajobs():
    k, m = os.environ.get("USAJOBS_API_KEY"), os.environ.get("USAJOBS_EMAIL")
    if not (k and m): return []
    try:
        d = get("https://data.usajobs.gov/api/search?ResultsPerPage=50&DatePosted=3",
                {"Host": "data.usajobs.gov", "User-Agent": m, "Authorization-Key": k})
        res = []
        for it in d["SearchResult"]["SearchResultItems"]:
            o = it["MatchedObjectDescriptor"]
            res.append(job("usajobs", it["MatchedObjectId"], "us", o["PositionTitle"], o["OrganizationName"],
                           o["PositionLocationDisplay"], o["PositionURI"], o.get("QualificationSummary"), o["PublicationStartDate"]))
        return res
    except Exception as e: print("usajobs", e); return []

def francetravail():
    i, s = os.environ.get("FRANCE_TRAVAIL_ID"), os.environ.get("FRANCE_TRAVAIL_SECRET")
    if not (i and s): return []
    try:
        body = urllib.parse.urlencode({"grant_type": "client_credentials", "client_id": i, "client_secret": s,
                                       "scope": "api_offresdemploiv2 o2dsoffre"}).encode()
        t = get("https://entreprise.francetravail.fr/connexion/oauth2/access_token?realm=/partenaire",
                {"Content-Type": "application/x-www-form-urlencoded"}, body)["access_token"]
        d = get("https://api.francetravail.io/partenaire/offresdemploi/v2/offres/search?range=0-49&sort=1",
                {"Authorization": "Bearer " + t})
        return [job("francetravail", r["id"], "fr", r["intitule"], r.get("entreprise", {}).get("nom"),
                    r.get("lieuTravail", {}).get("libelle"),
                    r.get("origineOffre", {}).get("urlOrigine") or f"https://candidat.francetravail.fr/offres/recherche/detail/{r['id']}",
                    r.get("description"), r.get("dateCreation")) for r in d.get("resultats", [])]
    except Exception as e: print("francetravail", e); return []

def arbeitnow():   # no key needed, German jobs
    try:
        return [job("arbeitnow", r["slug"], "de", r["title"], r["company_name"], r.get("location"), r["url"],
                    r.get("description"), r.get("created_at"), r.get("remote", False))
                for r in get("https://www.arbeitnow.com/api/job-board-api")["data"][:60]]
    except Exception as e: print("arbeitnow", e); return []

def remotive():    # no key needed; keep the link back to the source
    try:
        return [job("remotive", r["id"], "remote", r["title"], r["company_name"], r.get("candidate_required_location"),
                    r["url"], r.get("description"), r.get("publication_date"), True)
                for r in get("https://remotive.com/api/remote-jobs?limit=60")["jobs"]]
    except Exception as e: print("remotive", e); return []

UA = {"User-Agent": "JobviaBot/1.0 (job aggregator; contact via site)"}
def raw(url):
    return urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=30).read()

def rss(url, sec, src, loc="", remote=False, split=False, cc=None):
    out = []
    try:
        for it in ET.fromstring(raw(url)).iter("item"):
            g = lambda t: (it.findtext(t) or "")
            title, link, comp = g("title"), g("link"), (g("author") or src)
            if split and ": " in title: comp, title = title.split(": ", 1)
            try: d = email.utils.parsedate_to_datetime(g("pubDate")).date().isoformat()
            except Exception: d = None
            j = job(src, link, sec, title, comp, loc, link, g("description"), d, remote)
            if j:
                if cc: j["cc"] = cc
                out.append(j)
    except Exception as e: print("rss", src, e)
    return out

def gov():
    out = []
    for url, name, cc, loc in GOV_FEEDS: out += rss(url, "gov", name, loc, cc=cc)[:40]
    return out

def wwr(): return rss("https://weworkremotely.com/remote-jobs.rss", "remote", "WeWorkRemotely", "Worldwide", True, True)[:60]

def remoteok():
    try:
        return [job("RemoteOK", r["id"], "remote", r["position"], r["company"], r.get("location") or "Worldwide", r["url"],
                    r.get("description"), r.get("date"), True) for r in get("https://remoteok.com/api", UA)[1:]]
    except Exception as e: print("remoteok", e); return []

def jobicy():
    try:
        return [job("Jobicy", r["id"], "remote", r["jobTitle"], r["companyName"], r.get("jobGeo"), r["url"],
                    r.get("jobExcerpt"), r.get("pubDate"), True) for r in get("https://jobicy.com/api/v2/remote-jobs?count=50", UA)["jobs"]]
    except Exception as e: print("jobicy", e); return []

def himalayas():
    try:
        return [job("Himalayas", r.get("guid") or r["title"], "remote", r["title"], r.get("companyName"),
                    ", ".join(r.get("locationRestrictions") or []) or "Worldwide", r.get("applicationLink") or r.get("guid"),
                    r.get("excerpt") or r.get("description"), r.get("pubDate"), True) for r in get("https://himalayas.app/jobs/api?limit=20", UA)["jobs"]]
    except Exception as e: print("himalayas", e); return []

def workingnomads():
    try:
        return [job("WorkingNomads", r["url"], "remote", r["title"], r.get("company_name"), r.get("location") or "Worldwide",
                    r["url"], r.get("description"), r.get("pub_date"), True) for r in get("https://www.workingnomads.com/api/exposed_jobs/", UA)[:50]]
    except Exception as e: print("workingnomads", e); return []

def fetch_main():
    os.makedirs('data', exist_ok=True)
    db = json.load(open(DB)) if os.path.exists(DB) else []
    cutoff = (TODAY - datetime.timedelta(days=EXPIRE_DAYS)).isoformat()
    removed = [j["id"] for j in db if j["first_seen"] < cutoff]
    db = [j for j in db if j["first_seen"] >= cutoff]
    known = {j["id"] for j in db}
    lists = [[j for j in src() if j and j["id"] not in known] for src in (usajobs, francetravail, adzuna, arbeitnow, remotive, gov, wwr, remoteok, jobicy, himalayas, workingnomads)]
    added = []
    while len(added) < DAILY_LIMIT and any(lists):          # round-robin so every source gets a share
        for l in lists:
            if l and len(added) < DAILY_LIMIT: added.append(l.pop(0))
    db = added + db
    json.dump(db, open(DB, "w"), ensure_ascii=False, indent=1)
    json.dump({"added": [j["id"] for j in added], "removed": removed}, open("data/changes.json", "w"))
    print(f"added {len(added)}, removed {len(removed)}, total {len(db)}")


# ======================= BUILD =======================
def slug(j):
    s = re.sub(r"[^a-z0-9]+", "-", j["title"].lower()).strip("-")[:60] or "job"
    return f"{s}-{j['id']}"
def jurl(j): return f"/jobs/{j['section']}/{slug(j)}.html"
def write(path, content):
    p = os.path.join(OUT, path.lstrip("/"))
    os.makedirs(os.path.dirname(p), exist_ok=True)
    open(p, "w", encoding="utf-8").write(content)

LANGL = {"en": "Language", "fr": "Langue", "de": "Sprache", "ar": "اللغة"}
MENU = {"en": "Menu", "fr": "Menu", "de": "Menü", "ar": "القائمة"}

def layout(lang, title, desc, body, path, ld="", alts=None):
    t = T[lang]; d = "rtl" if lang == "ar" else "ltr"
    nav = "".join(f'<a href="/jobs/{s}/">{SECTIONS[s][0]} {E(NAMES[s][lang])}</a>' for s in SECTIONS)
    dnav = "".join(f'<a class="item" href="/jobs/{s}/"><span>{SECTIONS[s][0]}</span>{E(NAMES[s][lang])}</a>' for s in SECTIONS)
    sw = "".join(f'<a href="{HOME[l]}" hreflang="{l}">{l.upper()}</a>' for l in LANGS)
    hl = "".join(f'<link rel="alternate" hreflang="{l}" href="{SITE}{u}">' for l, u in (alts or {}).items())
    return f'''<!doctype html><html lang="{lang}" dir="{d}"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{E(title)}</title><meta name="description" content="{E(desc[:158])}">
<link rel="canonical" href="{SITE}{path}">{hl}
<meta property="og:title" content="{E(title)}"><meta property="og:description" content="{E(desc[:158])}"><meta property="og:type" content="website">
<link rel="icon" href="data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 32 32'%3E%3Crect width='32' height='32' rx='8' fill='%230B1530'/%3E%3Cpath d='M7 22 16 9l9 13' fill='none' stroke='%23FFB547' stroke-width='3'/%3E%3C/svg%3E">
<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Manrope:wght@400;600;800&family=Cairo:wght@400;700;900&display=swap" rel="stylesheet">
<link rel="stylesheet" href="/style.css">{ld}</head><body>
<header class="top"><a class="logo" href="{HOME[lang]}"><svg width="28" height="28" viewBox="0 0 32 32" aria-hidden="true"><rect width="32" height="32" rx="8" fill="#FFB547"/><path d="M7 22 16 9l9 13" fill="none" stroke="#0B1530" stroke-width="3"/></svg>Jobvia</a>
<nav class="sec desk">{nav}</nav><div class="lang desk">{sw}</div><a class="btn desk" href="/advertise.html">{E(t["post"])}</a>
<button class="burger" type="button" aria-label="{MENU[lang]}" aria-expanded="false" aria-controls="drawer"><span></span><span></span><span></span></button></header>
<div class="scrim" data-close></div>
<aside class="drawer" id="drawer" aria-label="{MENU[lang]}"><div class="dhead"><span>Jobvia</span><button class="close" type="button" data-close aria-label="Close">×</button></div>
<div class="dtitle">{E(t["browse"])}</div>{dnav}
<div class="dtitle">{LANGL[lang]}</div><div class="pills">{sw}</div>
<a class="btn" href="/advertise.html">{E(t["post"])}</a></aside>
<main>{body}</main>
<footer><div>© {TODAY_S[:4]} Jobvia</div><div><a href="/about.html">{t["about"]}</a><a href="/contact.html">{t["contact"]}</a><a href="/advertise.html">{t["post"]}</a><a href="/privacy.html">{t["privacy"]}</a></div></footer>
<script src="/app.js" defer></script></body></html>'''

def rows(jobs, lang):
    t = T[lang]
    return "".join(f'''<a class="job" href="{jurl(j)}" data-q="{E((j["title"]+" "+j["company"]+" "+j["location"]).lower())}">
<span class="jt">{E(j["title"])}</span><span class="jc">{E(j["company"])}</span><span class="jl">{E(j["location"])}</span>
<span class="js">{SECTIONS[j["section"]][0]}</span><time>{j["posted"]}</time></a>''' for j in jobs)

def route_svg():
    pts = [("🇺🇸", 40, 110), ("🇬🇧", 190, 50), ("🇫🇷", 330, 120), ("🇩🇪", 470, 60), ("🌍", 610, 130), ("🇨🇦", 740, 70)]
    d = "M40 110 C110 10 130 60 190 50 S290 160 330 120 S430 -10 470 60 S560 190 610 130 S700 10 740 70"
    n = "".join(f'<g class="node" style="--i:{i}"><circle cx="{x}" cy="{y}" r="17"/><text x="{x}" y="{y+6}" text-anchor="middle">{f}</text></g>' for i, (f, x, y) in enumerate(pts))
    return f'<svg class="route" viewBox="0 0 780 200" aria-hidden="true"><path class="line" d="{d}" pathLength="1"/>{n}</svg>'

def home(lang):
    t = T[lang]; by = sorted(JOBS, key=lambda j: j["posted"], reverse=True)
    cards = "".join(f'<a class="card" href="/jobs/{s}/"><span class="fl">{SECTIONS[s][0]}</span><b>{E(NAMES[s][lang])}</b><i>{sum(1 for j in JOBS if j["section"]==s) or ""}</i></a>' for s in SECTIONS)
    body = f'''<section class="hero"><h1>{t["h1"]}</h1><p>{t["sub"]}</p>{route_svg()}</section>
<section><h2>{t["browse"]}</h2><div class="cards">{cards}</div></section>
<section><h2>{t["latest"]}</h2><input class="q" type="search" placeholder="{t["search"]}" aria-label="{t["search"]}">
<div class="list">{rows(by[:60], lang) or f'<p>{t["none"]}</p>'}</div></section>'''
    write(HOME[lang] + "index.html", layout(lang, f"Jobvia - {t['tag']}", t["sub"] + " " + t["tag"], body, HOME[lang],
          alts={l: HOME[l] for l in LANGS}))

def jobld(j):
    cc = j.get("cc") or CC.get(j["section"], "US")
    ld = {"@context": "https://schema.org", "@type": "JobPosting", "title": j["title"],
          "description": j["desc"] or j["title"], "datePosted": j["posted"],
          "validThrough": (datetime.date.fromisoformat(j["first_seen"]) + datetime.timedelta(days=EXPIRE_DAYS)).isoformat() + "T23:59:59",
          "hiringOrganization": {"@type": "Organization", "name": j["company"]},
          "directApply": False, "url": SITE + jurl(j)}
    if j["remote"] or j["section"] == "remote":
        ld["jobLocationType"] = "TELECOMMUTE"; ld["applicantLocationRequirements"] = {"@type": "Country", "name": j["location"] or "Worldwide"}
    else:
        ld["jobLocation"] = {"@type": "Place", "address": {"@type": "PostalAddress", "addressLocality": j["location"], "addressCountry": cc}}
    return '<script type="application/ld+json">' + json.dumps(ld, ensure_ascii=False) + "</script>"

def sections():
    for s, (flag, lang) in SECTIONS.items():
        t = T[lang]; js = sorted([j for j in JOBS if j["section"] == s], key=lambda j: j["posted"], reverse=True)
        name = NAMES[s][lang]
        body = f'''<section class="hero small"><h1>{flag} {t["all"]} {E(name)}</h1><p>{t["sub"]}</p></section>
<section><input class="q" type="search" placeholder="{t["search"]}" aria-label="{t["search"]}"><div class="list">{rows(js[:400], lang) or f'<p>{t["none"]}</p>'}</div></section>'''
        write(f"/jobs/{s}/index.html", layout(lang, f"{t['all']} {name} - Jobvia", f"{t['all']} {name}. {t['tag']}", body, f"/jobs/{s}/"))
        for j in js:
            rel = "noopener" if j["source"] in ATTR else "nofollow noopener"
            src = f'<p class="srcline">Source: <a href="{E(j["url"])}" target="_blank" rel="noopener">{E(j["source"])}</a></p>' if j["source"] in ATTR else ""
            b = f'''<article class="post"><a class="back" href="/jobs/{s}/">← {E(name)}</a><h1>{E(j["title"])}</h1>
<dl><dt>{t["company"]}</dt><dd>{E(j["company"])}</dd><dt>{t["where"]}</dt><dd>{E(j["location"])}</dd><dt>{t["posted"]}</dt><dd>{j["posted"]}</dd></dl>
<p class="desc">{E(j["desc"])}</p>{src}<a class="btn big" rel="{rel}" target="_blank" href="{E(j["url"])}">{t["apply"]}</a></article>'''
            write(jurl(j), layout(lang, f'{j["title"]} - {j["company"]} | Jobvia', j["desc"] or j["title"], b, jurl(j), ld=jobld(j)))

def pages():
    en = "en"
    write("/about.html", layout(en, "About Jobvia", "How Jobvia collects and checks job listings.", f'''<article class="post"><h1>About Jobvia</h1>
<p>Jobvia lists jobs from government job boards and established job APIs. We link every listing to the original application page and remove listings after {EXPIRE_DAYS} days. We never ask candidates for money.</p></article>''', "/about.html"))
    write("/contact.html", layout(en, "Contact Jobvia", "Contact Jobvia.", f'''<article class="post"><h1>Contact</h1>
<p>Email: <a href="mailto:{E(CONTACT_EMAIL)}">{E(CONTACT_EMAIL)}</a></p>
<form action="https://api.web3forms.com/submit" method="POST"><input type="hidden" name="access_key" value="{E(W3F_KEY)}"><input type="hidden" name="subject" value="Jobvia contact"><input type="checkbox" name="botcheck" style="display:none">
<label>Name<input name="name" required></label><label>Email<input type="email" name="email" required></label><label>Message<textarea name="message" rows="5" required></textarea></label><button class="btn big">Send message</button></form></article>''', "/contact.html"))
    pr = "".join(f'<div class="price"><b>{n}</b><span>{p}</span><small>{d}</small></div>' for n, p, d in PRICES)
    opts = "".join(f"<option>{n}</option>" for n, _, _ in PRICES)
    write("/advertise.html", layout(en, "Post a job or advertise on Jobvia", "Prices and request form for employers.", f'''<article class="post"><h1>Post a job or advertise</h1><div class="prices">{pr}</div>
<form action="https://api.web3forms.com/submit" method="POST"><input type="hidden" name="access_key" value="{E(W3F_KEY)}"><input type="hidden" name="subject" value="Jobvia posting request"><input type="checkbox" name="botcheck" style="display:none">
<label>Company Name<input name="company" required></label><label>Work Email<input type="email" name="email" required></label>
<label>Country<input name="country" required></label><label>Service Required<select name="service">{opts}</select></label>
<label>Message<textarea name="message" rows="5"></textarea></label><button class="btn big">Send request</button></form></article>''', "/advertise.html"))
    write("/privacy.html", layout(en, "Privacy Policy - Jobvia", "How Jobvia handles data, cookies and ads.", f'''<article class="post"><h1>Privacy Policy</h1>
<p>Jobvia does not require an account. We do not collect personal data except what you send through our forms, which we use only to reply to you.</p>
<p>Job listings link to third-party sites with their own privacy policies. Third-party vendors, including Google, may use cookies to serve ads based on your visits to this and other sites. You can opt out of personalised ads in Google Ads Settings.</p>
<p>Contact: {E(CONTACT_EMAIL)}</p></article>''', "/privacy.html"))
    write("/404.html", layout(en, "Page not found - Jobvia", "Page not found.", '<article class="post"><h1>This job is gone</h1><p>Listings expire. <a href="/">Browse current jobs</a>.</p></article>', "/404.html"))

def seo():
    urls = [h for h in HOME.values()] + [f"/jobs/{s}/" for s in SECTIONS] + ["/about.html", "/contact.html", "/advertise.html", "/privacy.html"] + [jurl(j) for j in JOBS]
    write("/sitemap.xml", '<?xml version="1.0" encoding="UTF-8"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">' +
          "".join(f"<url><loc>{SITE}{u}</loc><lastmod>{TODAY_S}</lastmod></url>" for u in urls) + "</urlset>")
    write("/robots.txt", f"User-agent: *\nAllow: /\nSitemap: {SITE}/sitemap.xml\n")
    write(f"/{INDEXNOW_KEY}.txt", INDEXNOW_KEY)


def build_main():
    global JOBS
    os.makedirs("data", exist_ok=True)
    if not os.path.exists(DB): json.dump([], open(DB, "w"))
    JOBS = json.load(open(os.environ.get("JOBS_FILE", DB)))
    shutil.rmtree(OUT, ignore_errors=True); os.makedirs(OUT)
    write("/style.css", CSS); write("/app.js", JS)
    for l in LANGS: home(l)
    sections(); pages(); seo()
    print("built", len(JOBS), "jobs")

# ======================= INDEXING =======================
def index_main():
    global JOBS
    ch = json.load(open("data/changes.json")); JOBS = json.load(open(DB))
    jobs = {j["id"]: j for j in JOBS}
    add = [SITE + jurl(jobs[i]) for i in ch["added"] if i in jobs]
    print("new urls:", len(add), "removed ids:", len(ch["removed"]))
    sa = os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON")
    if sa:
        from google.oauth2 import service_account
        from google.auth.transport.requests import AuthorizedSession
        cr = service_account.Credentials.from_service_account_info(json.loads(sa), scopes=["https://www.googleapis.com/auth/indexing"])
        s = AuthorizedSession(cr)
        for u in add[:190]:
            if s.post("https://indexing.googleapis.com/v3/urlNotifications:publish", json={"url": u, "type": "URL_UPDATED"}).status_code == 429: break
        print("google done")
    if add:
        body = json.dumps({"host": SITE.split("//")[1], "key": INDEXNOW_KEY, "keyLocation": f"{SITE}/{INDEXNOW_KEY}.txt", "urlList": add[:9000]}).encode()
        try:
            urllib.request.urlopen(urllib.request.Request("https://api.indexnow.org/indexnow", body, {"Content-Type": "application/json"}), timeout=30)
            print("indexnow done")
        except Exception as e: print("indexnow", e)

if __name__ == "__main__":
    {"fetch": fetch_main, "build": build_main, "index": index_main}[sys.argv[1]]()
