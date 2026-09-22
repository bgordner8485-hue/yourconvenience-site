"""Build public/stats.json — every winner statistic the site shows.

Two sources, merged:
  * public/winners.json  — the clerk photos (always there)
  * public/portal.json   — the official gemRetailer winners feed, pushed up from
                           the store PC by palottery-pull/publish_stats.py
The portal numbers win wherever they overlap; photos fill in the wall.
Nothing about sales, commissions or inventory is read here — winners only.
"""
import datetime as dt, json
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PUB = ROOT / "public"
TIERS = [(10000, "$10,000+"), (1000, "$1,000–$9,999"), (500, "$500–$999"),
         (100, "$100–$499"), (0, "Under $100")]

def load(name, default):
    p = PUB / name
    try:
        return json.loads(p.read_text()) if p.exists() else default
    except json.JSONDecodeError:
        return default

def iso(d):
    """'09/17/2026', '2026-09-17', '2026-09-17T12:00:00Z' -> date"""
    d = (d or "").strip()
    for fmt in ("%m/%d/%Y", "%Y-%m-%d"):
        try:
            return dt.datetime.strptime(d[:10], fmt).date()
        except ValueError:
            pass
    return None

GAME_FIX = {"pick2": "PICK 2", "pick3": "PICK 3", "pick4": "PICK 4", "pick5": "PICK 5",
            "cash5": "Cash 5", "match6": "Match 6", "treasurehunt": "Treasure Hunt",
            "cash4life": "Cash4Life", "powerball": "Powerball", "megamillions": "Mega Millions",
            "millionaireforlife": "Millionaire for Life", "keno": "Keno", "fastplay": "Fast Play"}


def clean_game(name):
    """Tidy up whatever came off a photo file name or the portal feed."""
    import re
    n = name or ""
    n = re.sub(r"(?<=[a-z])(?=[A-Z])", " ", n)              # winnerPick -> winner Pick
    n = re.sub(r"(?<=[A-Za-z])(?=\d)", " ", n)              # Pick4 -> Pick 4
    n = re.sub(r"(?<=\d)(?=[A-Za-z])", " ", n)              # 6winner -> 6 winner
    n = re.sub(r"[_\-]+", " ", n)
    n = re.sub(r"(?i)\b(winner|winners|winning|ticket)\b", " ", n)
    n = re.sub(r"\s+", " ", n).strip()
    key = re.sub(r"[^a-z0-9]", "", n.lower())
    if key in GAME_FIX:
        return GAME_FIX[key]
    return " ".join(w if w.isupper() else w.capitalize() for w in n.split())


def tier(amount):
    for floor, label in TIERS:
        if amount >= floor:
            return label
    return TIERS[-1][1]

def collect():
    """One list of {date, amount, game, source}. Portal rows are authoritative;
    a photo within a day of a portal row for the same amount is treated as the same win."""
    portal = load("portal.json", {})
    rows = []
    for w in portal.get("winners", []):
        d = iso(w.get("date"))
        if d and w.get("amount"):
            rows.append({"date": d, "amount": float(w["amount"]),
                         "game": clean_game(w.get("game")), "source": "portal"})
    seen = {(r["date"], r["amount"]) for r in rows}
    near = {(r["date"] + dt.timedelta(days=off), r["amount"]) for r in rows for off in (-1, 0, 1)}
    for w in load("winners.json", {}).get("winners", []):
        d = iso(w.get("date"))
        if not d or not w.get("amount"):
            continue
        key = (d, float(w["amount"]))
        if key in seen or key in near:
            continue
        rows.append({"date": d, "amount": float(w["amount"]),
                     "game": clean_game(w.get("game")), "source": "photo"})
    rows.sort(key=lambda r: r["date"], reverse=True)
    return rows, portal

def window(rows, days):
    cutoff = dt.date.today() - dt.timedelta(days=days)
    return [r for r in rows if r["date"] >= cutoff]

def summarise(rows):
    total = sum(r["amount"] for r in rows)
    return {"count": len(rows), "total": round(total, 2),
            "biggest": max((r["amount"] for r in rows), default=0),
            "average": round(total / len(rows), 2) if rows else 0}

def main():
    rows, portal = collect()
    if not rows:
        print("no winner data yet"); return
    today = dt.date.today()
    first = min(r["date"] for r in rows)
    days_live = max((today - first).days, 1)

    by_month = defaultdict(float); month_counts = Counter()
    for r in rows:
        k = r["date"].strftime("%Y-%m")
        by_month[k] += r["amount"]; month_counts[k] += 1
    by_game = defaultdict(lambda: {"count": 0, "total": 0.0})
    for r in rows:
        g = r["game"] or "Scratch-off"
        by_game[g]["count"] += 1; by_game[g]["total"] += r["amount"]
    tiers = Counter(tier(r["amount"]) for r in rows)
    weekday = Counter(r["date"].strftime("%A") for r in rows)
    best_day = max(((d, sum(r["amount"] for r in rows if r["date"] == d))
                    for d in {r["date"] for r in rows}), key=lambda x: x[1])

    week, month, year = window(rows, 7), window(rows, 30), window(rows, 365)
    stats = {
        "updated": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "source": "portal+photos" if any(r["source"] == "portal" for r in rows) else "photos",
        "since": first.isoformat(),
        "all_time": summarise(rows),
        "last_7": summarise(week),
        "last_30": summarise(month),
        "last_365": summarise(year),
        "per_week_average": round(sum(r["amount"] for r in rows) / (days_live / 7), 2),
        "biggest_win": max(rows, key=lambda r: r["amount"]) | {} if rows else None,
        "best_day": {"date": best_day[0].isoformat(), "total": round(best_day[1], 2)},
        "by_tier": [{"tier": label, "count": tiers.get(label, 0)} for _, label in TIERS],
        "by_game": sorted(({"game": g, **v, "total": round(v["total"], 2)}
                           for g, v in by_game.items()), key=lambda x: -x["total"])[:15],
        "by_month": [{"month": m, "total": round(by_month[m], 2), "count": month_counts[m]}
                     for m in sorted(by_month, reverse=True)[:18]],
        "by_weekday": [{"day": d, "count": weekday.get(d, 0)} for d in
                       ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]],
        "portal_through": portal.get("through"),
    }
    b = stats["biggest_win"]
    stats["biggest_win"] = {"date": b["date"].isoformat(), "amount": b["amount"], "game": b["game"]}
    (PUB / "stats.json").write_text(json.dumps(stats, indent=1) + "\n")
    print(f"stats: {stats['all_time']['count']} wins, ${stats['all_time']['total']:,.0f} "
          f"({stats['source']}), week ${stats['last_7']['total']:,.0f}")

if __name__ == "__main__":
    main()
