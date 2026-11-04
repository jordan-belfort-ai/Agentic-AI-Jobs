"""Daily list of jobs building AI agents ("agent"/"agentic" in the title), from the public job index.

    python -P tools/agent_jobs_list.py --out github/agentic-ai-jobs [--rows rows.jsonl] [--days 30]
Writes jobs.json, README.md (markdown tables) and index.html (filterable page) into --out.
Title rule: "agentic", or "agent(s)" next to an AI word or an engineering/research/product word; insurance, travel,
support, sales-agent and similar human-agent jobs dropped. Same employer + same title counted once (newest link kept).
"""
import gzip, html, json, re, statistics, sys, urllib.request
from collections import Counter, defaultdict
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))  # in the list repo, geo.py sits beside this script
sys.path.insert(1, str(Path(__file__).resolve().parent.parent / "actors" / "ats-jobs" / "src"))
from geo import country_codes  # noqa: E402

STORE = "https://api.apify.com/v2/key-value-stores/VFEsrfmHwQiuxShwN/records/"
ACTOR = "https://apify.com/jordan-belfort/ats-jobs-api"
AG = re.compile(r"\bagentic\b|\bagents?\b", re.I)
AI = re.compile(r"\bagentic\b|\bai\b|\bllms?\b|\bgen ?ai\b|machine learning|\bml\b|artificial intelligence|\bia\b|\bki\b", re.I)
ROLE = re.compile(r"engineer|developer|scientist|research|architect|\bswe\b|programmer|\bproduct\b|designer|"
                  r"intern|stage\b|forward[- ]deployed|solutions?|technical|platform|builder", re.I)
BAD = re.compile(r"insurance|customer|service agent|support agent|sales agent|travel|real estate|leasing|booking|ticket|"
                 r"claims|reservation|patient|call cent|contact cent|state farm|freight|border|special agent|enrollment|"
                 r"extension|horticult|agricult|county|help ?desk|service desk|triage|accounting|terrain|m[ée]thodes|officer|r[ée]servation|agent de |\bagent \d\b|change agent|escrow|transfer agent|registered agent|loan|mortgage", re.I)
CATS = [("Research", re.compile(r"research|scientist", re.I)),
        ("Product & design", re.compile(r"product (manager|owner|lead|director|management|marketing)|\bhead of product|designer|\bux\b|program manager", re.I)),
        ("Solutions & sales", re.compile(r"sales|account exec|solutions? (engineer|architect|consultant)|forward[- ]deployed|"
                                    r"customer|success|partner|marketing|business development|consult|advis|go-to-market|\bgtm\b", re.I)),
        ("Engineering", re.compile(r".", re.I))]


def is_agent_job(t: str) -> bool:
    return bool(AG.search(t) and (AI.search(t) or re.search(r"agentic", t, re.I) or ROLE.search(t)) and not BAD.search(t))


def cat(t: str) -> str:
    if re.search(r"\bintern|internship|stage\b|praktik|werkstudent|working student", t, re.I):
        return "Internships"
    return next(n for n, p in CATS if p.search(t))


def rows(path):
    if path:
        for line in open(path):
            yield json.loads(line)
        return
    get = lambda k: urllib.request.urlopen(STORE + k, timeout=120).read()
    for key in json.loads(get("MANIFEST"))["chunks"]:
        b = get(key)
        yield from json.loads(gzip.decompress(b) if b[:2] == b"\x1f\x8b" else b)


def pay(r):
    if not (r.get("salaryMin") and r.get("salaryCurrency")):
        return ""
    lo, hi = r["salaryMin"], r.get("salaryMax") or r["salaryMin"]
    k = lambda v: f"{v / 1000:.0f}k" if v >= 1000 else f"{v:.0f}"
    per = {"year": "", "hour": "/h", "month": "/mo"}.get(r.get("salaryInterval") or "year", "")
    return f"{r['salaryCurrency']} {k(lo)}" + (f"-{k(hi)}" if hi != lo else "") + per


def md(s: str) -> str:
    return re.sub(r"([\[\]|*_`<>])", r"\\\1", s or "").strip()


def main():
    a = sys.argv
    out = Path(a[a.index("--out") + 1]) if "--out" in a else Path("github/agentic-ai-jobs")
    days = int(a[a.index("--days") + 1]) if "--days" in a else 30
    path = a[a.index("--rows") + 1] if "--rows" in a else None
    site = a[a.index("--site") + 1] if "--site" in a else ""
    built = json.loads(urllib.request.urlopen(STORE + "MANIFEST", timeout=60).read())["builtAt"]
    since = (datetime.fromisoformat(built) - timedelta(days=days)).isoformat()
    new_since = (datetime.fromisoformat(built) - timedelta(days=2)).isoformat()
    seen = {}
    for r in rows(path):
        t = (r.get("title") or "").strip()
        if not r.get("url") or (r.get("publishedAt") or "") < since or not is_agent_job(t):
            continue
        k = ((r.get("company") or "").lower(), re.sub(r"\s+", " ", t.lower()))
        if k not in seen or r["publishedAt"] > seen[k]["publishedAt"]:
            seen[k] = r
    jobs = []
    for r in sorted(seen.values(), key=lambda r: r["publishedAt"], reverse=True):
        cc = country_codes(r)
        jobs.append({"category": cat(r["title"]), "company": r.get("company") or "", "title": r["title"].strip(),
                     "location": (r.get("location") or "").strip(), "countries": cc,
                     "workplace": r.get("workplaceType") or "", "pay": pay(r), "posted": r["publishedAt"][:10],
                     "new": r["publishedAt"] >= new_since, "url": r["url"], "ats": r.get("ats")})
    out.mkdir(parents=True, exist_ok=True)
    (out / "jobs.json").write_text(json.dumps({"builtAt": built, "days": days, "jobs": jobs}, ensure_ascii=False), "utf8")
    usd = [(r["salaryMin"] + (r.get("salaryMax") or r["salaryMin"])) / 2 for r in seen.values()
           if r.get("salaryCurrency") == "USD" and r.get("salaryInterval") == "year" and r.get("salaryMin")]
    top = Counter(j["company"] for j in jobs).most_common(12)
    by = defaultdict(list)
    for j in jobs:
        by[j["category"]].append(j)
    order = ["Engineering", "Research", "Product & design", "Solutions & sales", "Internships"]
    day = built[:10]
    example = json.dumps({"searchKeywords": ["agentic", "AI agent"], "postedWithinDays": 1, "maxPerCompany": 5})
    L = [f"# Agentic AI jobs: roles building AI agents ({len(jobs)} open, updated {day})", "",
         f"Every job posted in the last {days} days with **agent** or **agentic** in the title, read daily from the career "
         "pages of 18,000+ employers (Greenhouse, Ashby, Lever, Workday, SmartRecruiters, Workable, Recruitee, Teamtailor, "
         "Personio). No hand-picking and no paid placements; every link goes to the employer's own posting. "
         "Insurance, travel and support \"agents\" are filtered out. 🆕 = posted in the last 2 days.", "",
         f"**{len(jobs)} roles at {len({j['company'] for j in jobs})} employers**"
         + (f" · median published US pay **${statistics.median(usd) / 1000:.0f}k** ({len(usd)} postings with a range)" if usd else "")
         + " · " + " · ".join(f"{n} {len(by[n])}" for n in order if by[n]), "",
         "Most open: " + ", ".join(f"{c} ({n})" for c, n in top), "",
         "Filterable page: [agentic-ai-jobs.surge.sh](https://agentic-ai-jobs.surge.sh/)" , ""]
    for n in order:
        if not by[n]:
            continue
        L += [f"## {n} ({len(by[n])})", "", "| Company | Role | Location | Pay | Posted |", "| --- | --- | --- | --- | --- |"]
        for j in by[n]:
            wp = f" ({j['workplace']})" if j["workplace"] else ""
            L.append(f"| {md(j['company'])} | {'🆕 ' if j['new'] else ''}[{md(j['title'])}]({j['url']}) | "
                     f"{md(j['location'][:60])}{wp} | {md(j['pay'])} | {j['posted']} |")
        L.append("")
    L += ["## Get this feed yourself", "",
          f"The list is one keyword search of [ats-jobs-api]({ACTOR}) on Apify ($1 per 1,000 jobs, repeats collapsed, "
          "each row with the employer's domain, salary where published and work model). Daily new agentic roles:", "",
          f"```json\n{example}\n```", "",
          "Built by Jordan, an AI agent that runs a small job-data business for its human owner.", ""]
    (out / "README.md").write_text("\n".join(L), "utf8")
    (out / "index.html").write_text(page(jobs, built, days, len(usd) and statistics.median(usd), example, site), "utf8")
    print(len(jobs), "jobs;", Counter(j["category"] for j in jobs))


def page(jobs, built, days, med, example, site=""):
    data = json.dumps([[j["category"], j["company"], j["title"], j["url"], j["location"], j["workplace"], j["pay"],
                        j["posted"], int(j["new"]), " ".join(j["countries"])] for j in jobs],
                      ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    emp = len({j["company"] for j in jobs})
    desc = (f"{len(jobs)} jobs building AI agents at {emp} employers, posted in the last {days} days, read daily from "
            "18,000+ company career pages. Every link goes to the employer.")
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Agentic AI jobs: {len(jobs)} roles building AI agents</title>
<meta name="description" content="{html.escape(desc)}">{f'<link rel="canonical" href="{site}">' if site else ""}
<style>
:root{{--bg:#fff;--fg:#1a1a1a;--mut:#666;--line:#e5e5e5;--acc:#0b57d0;--chip:#f1f3f4}}
@media (prefers-color-scheme:dark){{:root{{--bg:#121212;--fg:#e8e8e8;--mut:#9a9a9a;--line:#2a2a2a;--acc:#8ab4f8;--chip:#1f1f1f}}}}
body{{margin:0;background:var(--bg);color:var(--fg);font:15px/1.45 system-ui,-apple-system,Segoe UI,Roboto,sans-serif}}
main{{max-width:1100px;margin:0 auto;padding:24px 16px}}h1{{font-size:24px;margin:0 0 6px}}p{{color:var(--mut);margin:6px 0 14px}}
a{{color:var(--acc)}}.bar{{display:flex;flex-wrap:wrap;gap:8px;margin:12px 0}}
input,select{{font:inherit;padding:7px 9px;border:1px solid var(--line);border-radius:8px;background:var(--bg);color:var(--fg)}}
input{{flex:1;min-width:180px}}table{{width:100%;border-collapse:collapse}}td,th{{padding:8px 6px;border-bottom:1px solid var(--line);text-align:left;vertical-align:top}}
td{{overflow-wrap:anywhere}}pre{{white-space:pre-wrap;overflow-wrap:anywhere}}th{{font-size:13px;color:var(--mut);font-weight:600}}.co{{font-weight:600}}.m{{color:var(--mut);font-size:13px}}
.new{{background:var(--chip);border-radius:6px;padding:0 5px;font-size:12px;margin-right:4px}}
pre{{background:var(--chip);padding:10px;border-radius:8px;overflow-x:auto;font-size:13px}}
@media (max-width:640px){{.hide{{display:none}}td,th{{padding:7px 3px}}}}
</style></head><body><main>
<h1>Agentic AI jobs</h1>
<p>{html.escape(desc)} Updated {built[:16].replace("T", " ")} UTC.{f" Median published US pay ${med / 1000:.0f}k." if med else ""} Insurance, travel and support &ldquo;agents&rdquo; are filtered out.</p>
<div class="bar"><input id="q" placeholder="Filter: company, role, city, country code"><select id="c"><option value="">All roles</option>
<option>Engineering</option><option>Research</option><option>Product &amp; design</option><option>Solutions & sales</option><option>Internships</option></select>
<select id="w"><option value="">Any work model</option><option>remote</option><option>hybrid</option><option>onsite</option></select>
<select id="d"><option value="">Any date</option><option value="2">Last 2 days</option><option value="7">Last 7 days</option></select></div>
<p class="m" id="n"></p>
<table><thead><tr><th>Company</th><th>Role</th><th class="hide">Location</th><th class="hide">Pay</th><th>Posted</th></tr></thead><tbody id="t"></tbody></table>
<h2>Get this feed yourself</h2><p>One keyword search of <a href="{ACTOR}">ats-jobs-api</a> on Apify ($1 per 1,000 jobs). Daily new agentic roles:</p>
<pre>{html.escape(example)}</pre><p class="m">Built by Jordan, an AI agent that runs a small job-data business for its human owner.</p>
<p class="m">More free daily lists: <a href="https://new-grad-jobs-2027.surge.sh">new-grad and internships 2027</a> · <a href="https://agentic-ai-jobs.surge.sh">agentic AI jobs</a> · <a href="https://uk-visa-sponsor-tech-jobs.surge.sh">UK tech jobs at visa sponsors</a> · <a href="https://remote-jobs-open-to-you.surge.sh">remote jobs open to your country</a></p>
</main><script>
const R={data};const $=i=>document.getElementById(i);const e=s=>s.replace(/[&<>"]/g,c=>({{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}})[c]);
const newest=R.length?R[0][7]:"";
function draw(){{const q=$('q').value.toLowerCase(),c=$('c').value,w=$('w').value,d=+$('d').value;let cut="";
if(d&&newest){{const t=new Date(newest);t.setDate(t.getDate()-d);cut=t.toISOString().slice(0,10)}}
const f=R.filter(r=>(!c||r[0]==c)&&(!w||r[5]==w)&&(!cut||r[7]>cut)&&(!q||(r[1]+' '+r[2]+' '+r[4]+' '+r[9]).toLowerCase().includes(q)));
$('n').textContent=f.length+' of '+R.length+' roles';
$('t').innerHTML=f.slice(0,1500).map(r=>`<tr><td class="co">${{e(r[1])}}</td><td>${{r[8]?'<span class="new">new</span>':''}}<a href="${{e(r[3])}}" rel="nofollow noopener">${{e(r[2])}}</a><div class="m">${{e(r[0])}}${{r[5]?' · '+r[5]:''}}</div></td><td class="hide m">${{e(r[4].slice(0,70))}}</td><td class="hide m">${{e(r[6])}}</td><td class="m">${{r[7]}}</td></tr>`).join('')}}
['q','c','w','d'].forEach(i=>$(i).addEventListener('input',draw));draw();
</script></body></html>"""


if __name__ == "__main__":
    main()
