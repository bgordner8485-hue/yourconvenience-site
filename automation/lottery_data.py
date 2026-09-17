"""Pull PA Lottery winning numbers (official RSS) and scratch-off prizes remaining (official page),
then write public/numbers.json and public/prizes.json.

Sources:
  https://www.palottery.pa.gov/feeds/Games.aspx              (official winning-numbers RSS)
  https://www.palottery.pa.gov/Scratch-Offs/Prizes-Remaining.aspx
"""
import datetime as dt, html, re, sys
from pathlib import Path
import requests
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parent.parent
NUMBERS = ROOT / "public" / "numbers.json"
PRIZES = ROOT / "public" / "prizes.json"
UA = {"User-Agent": "Mozilla/5.0 (+https://www.atyourconveniencestores.com winners board)"}
FEED = "https://www.palottery.pa.gov/feeds/Games.aspx"
PRIZE_URL = "https://www.palottery.pa.gov/Scratch-Offs/Prizes-Remaining.aspx"
KEEP_DAYS = 400

# game slug -> display name, for the per-game pages
GAMES = {
    "pick-2": "PICK 2", "pick-3": "PICK 3", "pick-4": "PICK 4", "pick-5": "PICK 5",
    "cash-pop": "Cash Pop", "treasure-hunt": "Treasure Hunt", "cash-5": "Cash 5",
    "match-6": "Match 6", "millionaire-for-life": "Millionaire for Life",
    "cash4life": "Cash4Life", "mega-millions": "Mega Millions", "powerball": "Powerball",
    "double-play": "Double Play", "pick-2-wild-ball": "PICK 2",
}

def slugify(name):
    s = re.sub(r"[™®]", "", name).strip().lower()
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    return s

def load(p, default):
    import json
    return json.loads(p.read_text()) if p.exists() else default

def save(p, data):
    import json
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, indent=1) + "\n")

def fetch_numbers():
    xml = requests.get(FEED, timeout=45, headers=UA).text
    draws = []
    for item in re.findall(r"<item>(.*?)</item>", xml, re.S):
        def tag(t):
            m = re.search(rf"<{t}>(.*?)</{t}>", item, re.S)
            return html.unescape(m.group(1)).strip() if m else ""
        title, desc = tag("title"), html.unescape(tag("description"))
        m = re.match(r"^(.*?)\s*-\s*(\d{2}/\d{2}/\d{4})\s*$", title)
        if not m:
            continue
        label, date = m.group(1).strip(), m.group(2)
        draw_time = ""
        lm = re.match(r"^(.*?)\s*\((DAY|EVENING|MORNING|.*?)\)$", label)
        if lm:
            label, draw_time = lm.group(1).strip(), lm.group(2).title()
        elif re.match(r"(?i)^pick [2-5]$", label):
            draw_time = "Evening"   # the feed labels only the day draw; the unlabelled one is the evening draw
        nums_m = re.search(r"Winning Numbers?:\s*([0-9 ]+)", desc)
        numbers = nums_m.group(1).split() if nums_m else []
        extras = {}
        for key, pat in (("wild_ball", r"\bWB:\s*(\d+)"),
                         ("powerball", r"\b(?:PB|Powerball):\s*(\d+)"),
                         ("power_play", r"\b(?:PP|Power Play):\s*(\d+)"),
                         ("mega_ball", r"\b(?:MB|Mega Ball):\s*(\d+)"),
                         ("megaplier", r"\b(?:MP|Megaplier):\s*(\d+)"),
                         ("cash_ball", r"\b(?:CB|Cash Ball):\s*(\d+)"),
                         ("bonus", r"\b(?:Mill Ball|Bonus(?: Ball)?|Lucky Ball):\s*(\d+)")):
            mm = re.search(pat, desc, re.I)
            if mm:
                extras[key] = mm.group(1)
        # the feed repeats the extra balls at the end of the main number list — trim them
        tail = [extras[k] for k in ("powerball", "mega_ball", "cash_ball", "bonus") if k in extras]
        tail += [extras[k] for k in ("power_play", "megaplier") if k in extras]
        while tail and numbers and numbers[-len(tail):] == tail:
            numbers = numbers[:-len(tail)]
            break
        for k in ("powerball", "mega_ball", "cash_ball", "bonus"):
            if k in extras and numbers and numbers[-1] == extras[k]:
                numbers = numbers[:-1]
        jack = (re.search(r"jackpot for (\d{2}/\d{2}/\d{4}) is \$([\d,\.]+\s*[\w ]*)", desc, re.I)
                or re.search(r"Est\. Annuity for (\d{2}/\d{2}/\d{4}) is \$([\d,\.]+\s*[\w ]*)", desc, re.I))
        draws.append({
            "game": label, "slug": slugify(label), "date": date, "draw": draw_time,
            "numbers": numbers, **extras,
            **({"next_jackpot": "$" + jack.group(2).strip(), "next_draw": jack.group(1)} if jack else {}),
        })
    return draws

def merge(existing, fresh):
    def key(d):
        return (d["game"], d["date"], d.get("draw", ""))
    by = {key(d): d for d in existing}
    added = 0
    for d in fresh:
        if key(d) not in by:
            added += 1
        by[key(d)] = d
    cutoff = dt.date.today() - dt.timedelta(days=KEEP_DAYS)
    out = []
    for d in by.values():
        try:
            if dt.datetime.strptime(d["date"], "%m/%d/%Y").date() >= cutoff:
                out.append(d)
        except ValueError:
            out.append(d)
    out.sort(key=lambda d: (dt.datetime.strptime(d["date"], "%m/%d/%Y"), d["game"]), reverse=True)
    return out, added

def fetch_prizes():
    soup = BeautifulSoup(requests.get(PRIZE_URL, timeout=60, headers=UA).text, "lxml")
    table = soup.find("table")
    if not table:
        return []
    games = []
    for tr in table.find_all("tr"):
        cells = tr.find_all("td")
        if len(cells) < 5:
            continue
        num = cells[0].get_text(" ", strip=True)
        is_new = "NEW" in num.upper()
        num = re.sub(r"(?i)\bnew\b", "", num).strip()
        prizes = [p.get_text(" ", strip=True) for p in cells[3].find_all(["li", "span", "div", "p"])] or \
                 cells[3].get_text("|", strip=True).split("|")
        left = [p.get_text(" ", strip=True) for p in cells[4].find_all(["li", "span", "div", "p"])] or \
               cells[4].get_text("|", strip=True).split("|")
        prizes = [p for p in prizes if p.strip()]
        left = [l for l in left if l.strip()]
        games.append({
            "number": num, "name": cells[1].get_text(" ", strip=True), "price": cells[2].get_text(" ", strip=True),
            "new": is_new,
            "top_prize": prizes[0] if prizes else "",
            "top_prize_left": left[0] if left else "",
            "prizes": [{"prize": p, "left": left[i] if i < len(left) else ""} for i, p in enumerate(prizes)],
        })
    return games

def main():
    now = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    changed = False
    try:
        data = load(NUMBERS, {"draws": []})
        merged, added = merge(data.get("draws", []), fetch_numbers())
        save(NUMBERS, {"updated": now, "draws": merged})
        print(f"numbers: {added} new draw(s), {len(merged)} kept")
        changed = changed or added > 0
    except Exception as e:
        print("numbers FAILED:", e)
    try:
        games = fetch_prizes()
        if games:
            old = load(PRIZES, {}).get("games", [])
            save(PRIZES, {"updated": now, "games": games})
            print(f"prizes: {len(games)} games")
            changed = changed or games != old
    except Exception as e:
        print("prizes FAILED:", e)
    return 0

if __name__ == "__main__":
    sys.exit(main())
