"""Generate the data-driven pages: winning numbers (all games + per game),
scratch-off prizes remaining, the ScratchinLottoTV page, the blog, sitemap and RSS."""
import datetime as dt, html, json, re, shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PUB = ROOT / "public"
SITE = json.loads((PUB / "site.json").read_text())
CFG = json.loads((ROOT / "automation" / "config.json").read_text())
BASE = CFG["site_url"].rstrip("/")
STORE = CFG["store_name"]
TODAY = dt.date.today()

def write(path_no_ext, html_text):
    """Write /foo -> public/foo/index.html so URLs stay clean on GitHub Pages."""
    out = PUB / path_no_ext.strip("/") / "index.html" if path_no_ext.strip("/") else PUB / "index.html"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(html_text)


def load(name, default):
    p = PUB / name
    return json.loads(p.read_text()) if p.exists() else default

def esc(s):
    return html.escape(str(s), quote=True)

def shell(title, desc, body, canonical, extra_head="", active=""):
    nav = [("/#winners", "Winners"), ("/stats", "The Numbers"), ("/numbers", "Winning Numbers"),
           ("/scratch-offs", "Scratch-Offs"), ("/scratchinlottotv", "ScratchinLottoTV"),
           ("/blog", "Blog"), ("/#stores", "Stores")]
    links = "".join(f'<li><a href="{h}"{" style=color:var(--gold)" if h==active else ""}>{t}</a></li>' for h, t in nav)
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{esc(title)}</title>
<meta name="description" content="{esc(desc)}">
<link rel="canonical" href="{BASE}{canonical}">
<meta property="og:title" content="{esc(title)}"><meta property="og:description" content="{esc(desc)}">
<meta property="og:url" content="{BASE}{canonical}"><meta property="og:type" content="website">
<link rel="alternate" type="application/rss+xml" title="{esc(STORE)} blog" href="{BASE}/rss.xml">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Archivo+Black&family=Inter:wght@400;600;700&display=swap" rel="stylesheet">
<link rel="stylesheet" href="/style.css">
{extra_head}
</head>
<body>
<nav><div class="wrap">
  <a class="logo" href="/">@ Your <b>Convenience</b></a>
  <ul>{links}</ul>
  <a class="call" href="tel:+15709747351">📞 (570) 974-7351</a>
</div></nav>
{body}
<footer><div class="wrap">
  <div><b style="color:#fff">{esc(STORE)}</b><br>1900 Riverside Drive, South Williamsport, PA 17702 · (570) 974-7351
    <div class="fine">Winning numbers and prize data are posted here for convenience and are unofficial —
    always confirm with the Pennsylvania Lottery before claiming a prize. Must be 18+ to play; 21+ for tobacco and vape.
    Please play responsibly — if you or someone you know has a gambling problem, call 1-800-GAMBLER.</div></div>
  <div><a href="/blog">Blog</a> · <a href="/scratchinlottotv">ScratchinLottoTV</a> · © {TODAY.year}</div>
</div></footer>
</body></html>"""

# ---------------- winning numbers ----------------
BALL_STYLE = {"powerball": "red", "mega_ball": "gold", "cash_ball": "gold", "wild_ball": "gold", "bonus": "gold"}
EXTRA_LABEL = {"wild_ball": "Wild Ball", "powerball": "Powerball", "mega_ball": "Mega Ball",
               "cash_ball": "Cash Ball", "power_play": "Power Play", "megaplier": "Megaplier", "bonus": "Bonus"}

def draw_html(d, show_game=False):
    balls = "".join(f'<span class="ball">{esc(n)}</span>' for n in d["numbers"])
    for k, label in EXTRA_LABEL.items():
        if k in d:
            cls = BALL_STYLE.get(k, "gold")
            mult = k in ("power_play", "megaplier")
            balls += f'<span class="tag">{label}</span>' + (
                f'<span class="ball {cls}">{"x" if mult else ""}{esc(d[k])}</span>')
    head = f'<b>{esc(d["game"])}</b> · ' if show_game else ""
    when = f'{esc(d["date"])}' + (f' · {esc(d["draw"])}' if d.get("draw") else "")
    return f'<div class="drawrow"><div class="meta">{head}{when}</div><div class="balls">{balls}</div></div>'

def numbers_pages(draws):
    by_game = {}
    for d in draws:
        by_game.setdefault(d["game"], []).append(d)
    for lst in by_game.values():
        lst.sort(key=lambda d: (dt.datetime.strptime(d["date"], "%m/%d/%Y"), d.get("draw", "")), reverse=True)
    order = ["PICK 2", "PICK 3", "PICK 4", "PICK 5", "Cash 5", "Match 6", "Treasure Hunt",
             "Millionaire for Life", "Cash4Life", "Powerball", "Mega Millions"]
    games = sorted(by_game, key=lambda g: (order.index(g) if g in order else 99, g))

    cards = ""
    for g in games:
        lst = by_game[g]
        slug = lst[0]["slug"]
        recent = "".join(draw_html(d) for d in lst[:2])
        jack = ""
        nj = next((d for d in lst if d.get("next_jackpot")), None)
        if nj:
            jack = f'<div class="jack">Next drawing {esc(nj["next_draw"])}<b>{esc(nj["next_jackpot"])}</b></div>'
        cards += (f'<div class="game"><h3><a href="/numbers/{slug}">{esc(g)}</a></h3>{recent}{jack}'
                  f'<div style="font-size:13px"><a href="/numbers/{slug}">Past {esc(g)} numbers →</a></div></div>')

    latest = max((d["date"] for d in draws), default="")
    body = f"""<header class="pagehead"><div class="wrap">
  <span class="eyebrow">Updated after every drawing</span>
  <h1>Today's PA Lottery <span>winning numbers</span></h1>
  <p>Every game on one page — PICK 2, 3, 4 and 5, Cash 5, Match 6, Treasure Hunt, Cash4Life, Powerball and Mega Millions.
  Check your ticket here, then see what we've sold at the counter.</p>
</div></header>
<section><div class="wrap">
  <div class="cards">{cards}</div>
  <div class="note">Numbers are pulled straight from the Pennsylvania Lottery's own feed, usually within an hour of each drawing.
  They're posted for convenience and are unofficial — confirm with the Lottery before claiming. Last drawing shown: {esc(latest)}.</div>
  <p><a class="btn" href="/#winners">See the winning tickets we've sold →</a></p>
</div></section>
{videos_section()}"""
    write("numbers", shell(
        "Today's PA Lottery Winning Numbers | @ Your Convenience",
        "Today's Pennsylvania Lottery winning numbers for PICK 2, PICK 3, PICK 4, PICK 5, Cash 5, Match 6, "
        "Treasure Hunt, Cash4Life, Powerball and Mega Millions — plus the winning tickets sold at @ Your Convenience.",
        body, "/numbers", active="/numbers"))

    for g in games:
        lst = by_game[g]
        slug = lst[0]["slug"]
        rows = "".join(draw_html(d) for d in lst[:120])
        nj = next((d for d in lst if d.get("next_jackpot")), None)
        jack = f'<p style="font-size:17px">Next drawing {esc(nj["next_draw"])} — estimated jackpot <b>{esc(nj["next_jackpot"])}</b></p>' if nj else ""
        body = f"""<header class="pagehead"><div class="wrap">
  <span class="eyebrow">PA Lottery</span>
  <h1>{esc(g)} <span>winning numbers</span></h1>
  <p>The latest {esc(g)} results plus the past {min(len(lst),120)} drawings. Tickets sold daily at {esc(STORE)} in South Williamsport.</p>
</div></header>
<section><div class="wrap" style="max-width:760px">
  {jack}
  <div class="game" style="gap:14px">{rows}</div>
  <div class="note">Unofficial — always confirm winning numbers with the Pennsylvania Lottery before claiming a prize.</div>
  <p><a class="btn" href="/numbers">All games →</a></p>
</div></section>"""
        write(f"numbers/{slug}", shell(
            f"{g} Winning Numbers & Past Results | @ Your Convenience",
            f"{g} winning numbers for today and the past {min(len(lst),120)} drawings, posted by @ Your Convenience in South Williamsport, PA.",
            body, f"/numbers/{slug}", active="/numbers"))
    return games

# ---------------- scratch-offs ----------------
def prizes_page(games):
    rows = ""
    for g in games:
        badge = '<span class="new">NEW</span>' if g.get("new") else ""
        rows += (f'<tr><td>{badge}{esc(g["number"])}</td><td>{esc(g["name"])}</td><td>{esc(g["price"])}</td>'
                 f'<td>{esc(g["top_prize"])}</td><td><b>{esc(g["top_prize_left"])}</b></td>'
                 f'<td>{esc(", ".join(p["prize"] + " (" + p["left"] + ")" for p in g["prizes"][1:4]))}</td></tr>')
    body = f"""<header class="pagehead"><div class="wrap">
  <span class="eyebrow">Updated daily</span>
  <h1>Scratch-offs: <span>top prizes left</span></h1>
  <p>Before you buy, see how many top prizes are still out there on every active Pennsylvania scratch-off.
  Sort by price, search by name, and buy the ticket at our counter.</p>
</div></header>
<section><div class="wrap">
  <div class="controls">
    <input type="search" id="q" placeholder="Search a game…" style="min-width:240px">
    <select id="price"><option value="">Any price</option></select>
    <label style="display:flex;align-items:center;gap:6px;font-weight:600"><input type="checkbox" id="onlyleft"> Top prize still available</label>
  </div>
  <table id="t"><thead><tr><th data-k="0">Game #</th><th data-k="1">Game</th><th data-k="2">Price</th>
  <th data-k="3">Top prize</th><th data-k="4">Top prizes left</th><th>Next prizes (left)</th></tr></thead>
  <tbody>{rows}</tbody></table>
  <div class="note">Straight from the Pennsylvania Lottery's published prizes-remaining report, refreshed daily. Unofficial — confirm with the Lottery.</div>
</div></section>
<script>
const rows=[...document.querySelectorAll('#t tbody tr')];
const prices=[...new Set(rows.map(r=>r.cells[2].textContent.trim()))].sort((a,b)=>parseFloat(a.replace('$',''))-parseFloat(b.replace('$','')));
price.innerHTML='<option value="">Any price</option>'+prices.map(p=>`<option>${{p}}</option>`).join('');
function filter(){{const s=q.value.toLowerCase(),p=price.value,only=onlyleft.checked;
 rows.forEach(r=>{{const left=parseInt(r.cells[4].textContent.replace(/[^0-9]/g,''))||0;
  r.style.display=(r.cells[1].textContent.toLowerCase().includes(s)&&(!p||r.cells[2].textContent.trim()===p)&&(!only||left>0))?'':'none';}});}}
[q,price,onlyleft].forEach(el=>el.addEventListener('input',filter));
document.querySelectorAll('#t th[data-k]').forEach(th=>{{let asc=false;th.onclick=()=>{{asc=!asc;const k=+th.dataset.k;
 const v=r=>{{const t=r.cells[k].textContent.trim();const n=parseFloat(t.replace(/[^0-9.]/g,''));return isNaN(n)?t.toLowerCase():n;}};
 rows.sort((a,b)=>{{const x=v(a),y=v(b);return (x>y?1:x<y?-1:0)*(asc?1:-1);}}).forEach(r=>r.parentNode.appendChild(r));}};}});
</script>"""
    write("scratch-offs", shell(
        "PA Scratch-Off Top Prizes Remaining | @ Your Convenience",
        "How many top prizes are left on every active Pennsylvania Lottery scratch-off, updated daily by "
        "@ Your Convenience in South Williamsport, PA.",
        body, "/scratch-offs", active="/scratch-offs"))


# ---------------- winner stats ----------------
def money(n, cents=False):
    return f"${n:,.2f}" if cents else f"${n:,.0f}"


def stats_page():
    st = load("stats.json", {})
    if not st:
        return
    at, w7, w30, w365 = st["all_time"], st["last_7"], st["last_30"], st["last_365"]
    since = dt.date.fromisoformat(st["since"]).strftime("%B %Y")
    big = st["biggest_win"]
    bigdate = dt.date.fromisoformat(big["date"]).strftime("%b %-d, %Y")
    bestday = dt.date.fromisoformat(st["best_day"]["date"]).strftime("%b %-d, %Y")

    def tile(value, label, sub=""):
        return (f'<div class="tile"><div class="tilev">{esc(value)}</div>'
                f'<div class="tilel">{esc(label)}</div>'
                + (f'<div class="tiles">{esc(sub)}</div>' if sub else '') + '</div>')

    tiles = "".join([
        tile(money(at["total"]), "paid out to our customers", f"since {since}"),
        tile(f'{at["count"]:,}', "winning tickets sold", f'{money(at["average"])} average win'),
        tile(money(st["per_week_average"]), "paid out in an average week"),
        tile(money(at["biggest"]), "biggest single win", f'{big["game"] or "Scratch-off"} · {bigdate}'),
    ])
    recent = "".join([
        tile(money(w7["total"]), "last 7 days", f'{w7["count"]} winners'),
        tile(money(w30["total"]), "last 30 days", f'{w30["count"]} winners'),
        tile(money(w365["total"]), "last 12 months", f'{w365["count"]} winners'),
        tile(money(st["best_day"]["total"]), "best single day", bestday),
    ])
    tier_rows = "".join(f'<tr><td>{esc(t["tier"])}</td><td><b>{t["count"]:,}</b></td></tr>'
                        for t in st["by_tier"] if t["count"])
    month_rows = "".join(
        f'<tr><td>{dt.date.fromisoformat(m["month"] + "-01").strftime("%B %Y")}</td>'
        f'<td>{m["count"]}</td><td><b>{money(m["total"])}</b></td></tr>' for m in st["by_month"])
    game_rows = "".join(f'<tr><td>{esc(g["game"])}</td><td>{g["count"]}</td>'
                        f'<td><b>{money(g["total"])}</b></td></tr>' for g in st["by_game"])
    days = st["by_weekday"]; peak = max(d["count"] for d in days) or 1
    day_rows = "".join(
        f'<tr><td>{esc(d["day"])}</td><td style="width:60%"><span class="bar" style="width:'
        f'{round(100 * d["count"] / peak)}%"></span></td><td><b>{d["count"]}</b></td></tr>' for d in days)
    source = ("Figures come from the Pennsylvania Lottery's own retailer records plus the "
              "winning tickets we photograph at the counter, updated daily."
              if st.get("source") == "portal+photos" else
              "Figures are counted from the winning tickets we've photographed at the counter.")
    full_since = st.get("full_since")
    month_note = ""
    if full_since and full_since[:7] > st["since"][:7]:
        fs = dt.date.fromisoformat(full_since).strftime("%B %Y")
        month_note = (f'<p class="note">Ticket-by-ticket records start in {esc(fs)}. '
                      f'Before that we can only count the large prizes the Lottery reports, '
                      f'so those months are left out of this table — they are still in the '
                      f'totals above.</p>')

    body = f"""<header class="pagehead"><div class="wrap">
  <span class="eyebrow">The numbers</span>
  <h1>{esc(money(at["total"]))} <span>paid out</span></h1>
  <p>Every winning ticket sold at {esc(STORE)} since {esc(since)} — counted, totalled and kept honest.
  {esc(source)}</p>
</div></header>
<section><div class="wrap">
  <div class="tiles">{tiles}</div>
  <h2 style="font-size:28px;margin:38px 0 14px">Lately</h2>
  <div class="tiles">{recent}</div>

  <div class="two-col">
    <div><h2 style="font-size:24px;margin:34px 0 12px">How the wins break down</h2>
      <table><thead><tr><th>Prize range</th><th>Tickets</th></tr></thead><tbody>{tier_rows}</tbody></table></div>
    <div><h2 style="font-size:24px;margin:34px 0 12px">Which day hits most</h2>
      <table><thead><tr><th>Day</th><th></th><th>Wins</th></tr></thead><tbody>{day_rows}</tbody></table></div>
  </div>

  <h2 style="font-size:24px;margin:34px 0 12px">Month by month</h2>
  <table><thead><tr><th>Month</th><th>Winners</th><th>Paid out</th></tr></thead><tbody>{month_rows}</tbody></table>
  {month_note}

  <h2 style="font-size:24px;margin:34px 0 12px">By game</h2>
  <table><thead><tr><th>Game</th><th>Winners</th><th>Paid out</th></tr></thead><tbody>{game_rows}</tbody></table>

  <div class="note">Every figure on this page is a ticket actually sold and paid at our counter. It says nothing
  about your odds on the next one — the Lottery's odds are the Lottery's odds. Play for fun, spend what you can
  afford to lose, and if it stops being fun, call 1-800-GAMBLER.</div>
  <p><a class="btn" href="/#winners">See the tickets →</a></p>
</div></section>
{videos_section()}"""
    write("stats", shell(
        f'{money(at["total"])} in Lottery Winners Sold | @ Your Convenience',
        f'@ Your Convenience in South Williamsport has sold {at["count"]:,} winning Pennsylvania Lottery '
        f'tickets worth {money(at["total"])} since {since}. Full breakdown by month, game and prize size.',
        body, "/stats", active="/stats"))


# ---------------- ScratchinLottoTV ----------------
def videos_section(limit=3):
    vids = load("videos.json", {}).get("videos", [])[:limit]
    if not vids:
        return ""
    cards = "".join(f'<a class="vid" href="{esc(v["url"])}" target="_blank" rel="noopener">'
                    f'<img loading="lazy" src="{esc(v["thumb"])}" alt=""><div>{esc(v["title"])}</div></a>' for v in vids)
    return f"""<section style="background:#fff;border-top:1px solid var(--line)"><div class="wrap">
  <h2 style="font-size:30px">Watch us scratch on ScratchinLottoTV</h2>
  <p style="color:var(--muted)">We scratch tickets from our own counter and write a lucky song for every winner.</p>
  <div class="vids" style="margin-top:18px">{cards}</div>
  <p style="margin-top:18px"><a class="btn" href="/scratchinlottotv">More episodes →</a></p>
</div></section>"""

def channel_page():
    data = load("videos.json", {})
    vids = data.get("videos", [])
    url = SITE.get("youtube_url") or data.get("channel_url") or ""
    cards = "".join(f'<a class="vid" href="{esc(v["url"])}" target="_blank" rel="noopener">'
                    f'<img loading="lazy" src="{esc(v["thumb"])}" alt=""><div>{esc(v["title"])}</div></a>' for v in vids[:24])
    if not cards:
        cards = '<div class="note">Episodes will appear here as soon as the channel link is set in site.json.</div>'
    sub = f'<p><a class="btn" href="{esc(url)}" target="_blank" rel="noopener">Subscribe on YouTube →</a></p>' if url else ""
    body = f"""<header class="pagehead"><div class="wrap">
  <span class="eyebrow">Our channel</span>
  <h1>Scratchin<span>LottoTV</span></h1>
  <p>We buy tickets off our own counter, scratch them on camera, and turn the wins into original songs.
  Real tickets, real reactions, and the same games you'll find in the rack at {esc(STORE)}.</p>
  {sub}
</div></header>
<section><div class="wrap"><div class="vids">{cards}</div></div></section>
<section style="background:#fff;border-top:1px solid var(--line)"><div class="wrap" style="max-width:760px">
  <h2 style="font-size:28px">Want to be on the show?</h2>
  <p style="color:var(--muted)">Hit a winner at our counter and we'll put your ticket on the wall — and the week's winners
  get their own montage set to one of our songs. Stop in and ask.</p>
  <p><a class="btn" href="/#winners">See this week's winners →</a></p>
</div></section>"""
    write("scratchinlottotv", shell(
        "ScratchinLottoTV — Scratch-Off Videos & Lucky Songs | @ Your Convenience",
        "ScratchinLottoTV: scratch-off sessions filmed at @ Your Convenience in South Williamsport, PA, "
        "with an original song for every big win.",
        body, "/scratchinlottotv", active="/scratchinlottotv"))

# ---------------- blog ----------------
def md_to_html(md):
    try:
        import markdown
        return markdown.markdown(md, extensions=["extra", "toc"])
    except ImportError:
        return "".join(f"<p>{html.escape(p)}</p>" for p in md.split("\n\n"))

def read_posts():
    posts = []
    for f in sorted((ROOT / "content" / "posts").glob("*.md")):
        raw = f.read_text()
        meta = {}
        if raw.startswith("---"):
            fm, raw = raw.split("---", 2)[1:]
            for line in fm.strip().splitlines():
                if ":" in line:
                    k, v = line.split(":", 1)
                    meta[k.strip()] = v.strip().strip('"')
        posts.append({"slug": meta.get("slug", f.stem), "title": meta.get("title", f.stem),
                      "date": meta.get("date", ""), "description": meta.get("description", ""),
                      "body": md_to_html(raw.strip())})
    posts.sort(key=lambda p: p["date"], reverse=True)
    return posts

def blog_pages(posts):
    for p in posts:
        ld = json.dumps({"@context": "https://schema.org", "@type": "BlogPosting", "headline": p["title"],
                         "datePublished": p["date"], "description": p["description"],
                         "mainEntityOfPage": f'{BASE}/blog/{p["slug"]}',
                         "author": {"@type": "Organization", "name": STORE},
                         "publisher": {"@type": "Organization", "name": STORE}})
        body = f"""<header class="pagehead"><div class="wrap">
  <span class="eyebrow">{esc(p["date"])}</span>
  <h1>{esc(p["title"])}</h1>
</div></header>
<section><div class="wrap"><article class="prose">{p["body"]}</article>
<p style="margin-top:30px"><a class="btn" href="/blog">More posts →</a></p></div></section>"""
        write(f'blog/{p["slug"]}', shell(
            f'{p["title"]} | @ Your Convenience', p["description"], body, f'/blog/{p["slug"]}',
            extra_head=f'<script type="application/ld+json">{ld}</script>', active="/blog"))
    items = "".join(f'<div class="post"><time>{esc(p["date"])}</time>'
                    f'<h3><a href="/blog/{p["slug"]}">{esc(p["title"])}</a></h3>'
                    f'<p style="color:var(--muted);margin:0">{esc(p["description"])}</p></div>' for p in posts)
    body = f"""<header class="pagehead"><div class="wrap">
  <span class="eyebrow">From the counter</span>
  <h1>The <span>lucky</span> blog</h1>
  <p>Scratch-off strategy, what's hot in the rack, winners from our stores, and what we learn filming ScratchinLottoTV.</p>
</div></header>
<section><div class="wrap"><div class="postlist">{items or '<div class="note">First posts coming soon.</div>'}</div></div></section>"""
    write("blog", shell(
        "Lottery Tips, Winners & Scratch-Off News | @ Your Convenience",
        "Scratch-off tips, PA Lottery news and winner stories from @ Your Convenience in South Williamsport, PA.",
        body, "/blog", active="/blog"))
    return posts

def feeds(posts, games):
    urls = ["/", "/stats", "/numbers", "/scratch-offs", "/scratchinlottotv", "/blog"]
    urls += [f"/numbers/{g}" for g in games]
    urls += [f'/blog/{p["slug"]}' for p in posts]
    body = "".join(f"<url><loc>{BASE}{u}</loc><lastmod>{TODAY}</lastmod></url>" for u in urls)
    (PUB / "sitemap.xml").write_text(
        f'<?xml version="1.0" encoding="UTF-8"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">{body}</urlset>')
    (PUB / "robots.txt").write_text(f"User-agent: *\nAllow: /\nSitemap: {BASE}/sitemap.xml\n")
    items = "".join(
        f'<item><title>{esc(p["title"])}</title><link>{BASE}/blog/{p["slug"]}</link>'
        f'<guid>{BASE}/blog/{p["slug"]}</guid><description>{esc(p["description"])}</description></item>' for p in posts)
    (PUB / "rss.xml").write_text(
        f'<?xml version="1.0" encoding="UTF-8"?><rss version="2.0"><channel>'
        f'<title>{esc(STORE)} — Blog</title><link>{BASE}/blog</link>'
        f'<description>Lottery tips, winners and scratch-off news from {esc(STORE)}.</description>{items}</channel></rss>')

def main():
    draws = load("numbers.json", {}).get("draws", [])
    games = numbers_pages(draws) if draws else []
    slugs = sorted({d["slug"] for d in draws})
    prizes = load("prizes.json", {}).get("games", [])
    if prizes:
        prizes_page(prizes)
    stats_page()
    channel_page()
    posts = blog_pages(read_posts())
    feeds(posts, slugs)
    print(f"built: {len(games)} game pages, {len(prizes)} scratch-offs, {len(posts)} posts")

if __name__ == "__main__":
    main()
