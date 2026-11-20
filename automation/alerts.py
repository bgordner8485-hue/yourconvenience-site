#!/usr/bin/env python3
"""Post the two things that actually sell tickets: a big jackpot, and new scratch-offs.

Both already show on the website (build_site.py renders the NEW badge and the next
jackpot), so this script is only the social half. It runs off the same data files
the site is built from, so there is nothing new to fetch.

State lives under "alerts" in data/state.json so nothing is ever posted twice:
a jackpot tier fires once per run-up and resets when somebody wins, and a new game
is announced once, ever.

  python automation/alerts.py --dry     # show what would post, send nothing
  python automation/alerts.py --seed    # record today as already-posted, send nothing
  python automation/alerts.py           # post anything new
"""
import argparse
import datetime as dt
from pathlib import Path

from PIL import Image, ImageDraw

from common import (CFG, ROOT, STATE_JSON, load_json, save_json,  # noqa: F401
                    postiz_upload, postiz_post)
from daily_numbers import W, H, GOLD, GOLD_D, CREAM, RED, INK, font, centred

OUT = ROOT / "out"

# Only the two games with jackpots big enough to move people off the couch.
JACKPOT_GAMES = ("Powerball", "Mega Millions")

# Dollar milestones, in millions. A post fires the first time a jackpot reaches
# each one; passing several at once posts only the highest.
TIERS = (100, 150, 200, 250, 300, 400, 500, 600, 750, 1000)

# Most new games arrive as a seasonal batch, so they go out as one post, not six.
MAX_GAMES_PER_POST = 6


def dollars(text):
    """'$114,000,000' -> 114000000. Returns 0 for anything unparseable."""
    digits = "".join(c for c in str(text) if c.isdigit())
    return int(digits) if digits else 0


def pretty(amount):
    """114000000 -> '$114 MILLION'. Billions get one decimal place."""
    if amount >= 1_000_000_000:
        billions = amount / 1_000_000_000
        whole = f"{billions:.1f}".rstrip("0").rstrip(".")
        return f"${whole} BILLION"
    return f"${amount // 1_000_000} MILLION"


def tier_reached(amount):
    """Highest milestone this jackpot has reached, or None if it is below them all."""
    millions = amount / 1_000_000
    hit = [t for t in TIERS if millions >= t]
    return max(hit) if hit else None


def clean_game_name(name):
    """The feed suffixes most games with their second-chance status; drop it."""
    for junk in (" Second-Chance Eligible", " Second Chance Eligible"):
        name = name.replace(junk, "")
    return name.strip()


def latest_jackpots(draws):
    """{game: (amount, next_draw)} using the most recent draw row that carries one."""
    out = {}
    for row in draws:
        game = row.get("game")
        if game in JACKPOT_GAMES and game not in out and row.get("next_jackpot"):
            out[game] = (dollars(row["next_jackpot"]), row.get("next_draw", ""))
    return out


def jackpot_alerts(draws, state):
    """One alert per game that has just reached a milestone it has not posted at."""
    alerts = []
    seen = state.setdefault("jackpots", {})
    for game, (amount, next_draw) in latest_jackpots(draws).items():
        rec = seen.setdefault(game, {"tier": 0, "amount": 0})
        if amount < rec.get("amount", 0):
            rec["tier"] = 0          # jackpot fell, so somebody won; the run-up restarts
        rec["amount"] = amount
        tier = tier_reached(amount)
        if tier and tier > rec.get("tier", 0):
            alerts.append({"kind": "jackpot", "game": game, "tier": tier,
                           "amount": amount, "next_draw": next_draw})
    return alerts


def new_game_alerts(games, state):
    """One batched alert for scratch-offs the feed has newly flagged as new."""
    announced = set(state.setdefault("announced_games", []))
    fresh = [g for g in games if g.get("new") and g.get("number") not in announced]
    if not fresh:
        return []
    fresh.sort(key=lambda g: dollars(g.get("price")), reverse=True)
    # The batch rides on the alert and is marked announced only once the post
    # lands, so a seasonal drop goes out as one post rather than six.
    return [{"kind": "new_games", "games": fresh[:MAX_GAMES_PER_POST],
             "total": len(fresh), "numbers": [g["number"] for g in fresh]}]


def commit(alert, state):
    """Record an alert as posted. Only ever called once the post has landed."""
    if alert["kind"] == "jackpot":
        state.setdefault("jackpots", {}).setdefault(alert["game"], {})["tier"] = alert["tier"]
    else:
        done = set(state.setdefault("announced_games", []))
        state["announced_games"] = sorted(done | set(alert["numbers"]))


def fitted(dr, text, max_width, start, display=True, floor=24):
    """Largest font at or below `start` that keeps `text` inside `max_width`."""
    size = start
    while size > floor:
        f = font(size, display=display)
        if dr.textlength(text, font=f) <= max_width:
            return f
        size -= 4
    return font(floor, display=display)


def _frame(dr):
    """Shared furniture: gold rule top and bottom, store name in the footer."""
    dr.rectangle([0, 0, W, 14], fill=GOLD)
    dr.rectangle([0, H - 14, W, H], fill=GOLD)
    centred(dr, (W // 2, H - 104), CFG["store_name"].upper(), font(40, True), GOLD)
    centred(dr, (W // 2, H - 56), CFG.get("store_address", ""), font(27), CREAM)


def render_jackpot(alert, path):
    im = Image.new("RGB", (W, H), INK)
    dr = ImageDraw.Draw(im)
    _frame(dr)
    centred(dr, (W // 2, 150), "JACKPOT ALERT", font(54, True), RED)
    game = alert["game"].upper()
    centred(dr, (W // 2, 300), game, fitted(dr, game, W - 120, 92), CREAM)

    amount = pretty(alert["amount"])
    head, _, unit = amount.rpartition(" ")
    centred(dr, (W // 2, 545), head, fitted(dr, head, W - 90, 230), GOLD)
    centred(dr, (W // 2, 745), unit, fitted(dr, unit, W - 160, 104), GOLD_D)

    if alert.get("next_draw"):
        centred(dr, (W // 2, 900), f"NEXT DRAWING  {alert['next_draw']}", font(44, True), CREAM)
    centred(dr, (W // 2, 1030), "GET YOUR TICKETS HERE", font(56, True), GOLD)
    im.save(path, "JPEG", quality=88, optimize=True)
    return path


def render_new_games(alert, path):
    im = Image.new("RGB", (W, H), INK)
    dr = ImageDraw.Draw(im)
    _frame(dr)
    centred(dr, (W // 2, 140), "JUST IN", font(50, True), RED)
    centred(dr, (W // 2, 240), "NEW SCRATCH-OFFS", fitted(dr, "NEW SCRATCH-OFFS", W - 110, 92), GOLD)

    rows = alert["games"]
    top, bottom = 390, 1140
    step = (bottom - top) // max(len(rows), 1)
    y = top + step // 2
    for g in rows:
        name = clean_game_name(g.get("name", ""))
        price = str(g.get("price", "")).strip()
        dr.rounded_rectangle([70, y - 34, 214, y + 34], radius=16, fill=GOLD)
        centred(dr, (142, y), price, font(46, True), INK)
        f = fitted(dr, name, W - 300, 54, display=False, floor=26)
        dr.text((248, y - f.size - 2), name, font=f, fill=CREAM)
        prize = str(g.get("top_prize", "")).strip()
        if prize:
            dr.text((250, y + 14), f"top prize {prize}", font=font(28), fill=GOLD_D)
        y += step
    im.save(path, "JPEG", quality=88, optimize=True)
    return path


def captions(alert):
    """(facebook text, google text). Google gets no link and no hashtags: it
    rejects post text carrying a URL, and its button is the link instead."""
    store = CFG["store_name"]
    if alert["kind"] == "jackpot":
        amount, game = pretty(alert["amount"]), alert["game"]
        when = f" Next drawing {alert['next_draw']}." if alert.get("next_draw") else ""
        fb = (f"{game.upper()} IS AT {amount}!{when}\n\n"
              f"Somebody has to win it. Might as well be someone from around here.\n"
              f"Tickets at {store} - play here, win here.\n\n"
              f"{CFG['site_url']}/#numbers\n{CFG['hashtags']}")
        spoken = amount.replace("MILLION", "million").replace("BILLION", "billion")
        gmb = (f"{game} has climbed to {spoken}.{when} "
               f"Stop in and get your tickets before the cutoff.")
        return fb, gmb

    rows = alert["games"]
    names = [f"{str(g.get('price','')).strip()} {clean_game_name(g.get('name',''))}" for g in rows]
    listed = "\n".join(f"- {n}" for n in names)
    extra = alert["total"] - len(rows)
    more = f"\n...and {extra} more on the rack." if extra > 0 else ""
    fb = (f"NEW SCRATCH-OFFS JUST LANDED at {store}!\n\n{listed}{more}\n\n"
          f"Fresh tickets mean every top prize is still out there. Come pick your lucky one.\n\n"
          f"{CFG['site_url']}/scratch-offs\n{CFG['hashtags']}")
    gmb = (f"New scratch-offs have just landed at {store}: "
           + ", ".join(names) + f".{more.replace(chr(10), ' ')} "
           "Every top prize is still unclaimed on a brand new game. Come in and pick yours.")
    return fb, gmb


def send(alert, image, dry):
    chans = {k: v for k, v in CFG["postiz"].get("alert_channels", {}).items()
             if v and not v.startswith("PASTE_")}
    fb, gmb = captions(alert)
    if dry:
        print(f"\n--- WOULD POST [{alert['kind']}] to {', '.join(chans) or '(no channels)'}")
        print(f"    image: {image}")
        print("    facebook:\n      " + fb.replace("\n", "\n      "))
        print("    google:\n      " + gmb.replace("\n", "\n      "))
        return
    if not chans:
        print("  no alert channels configured - image built, not posted"); return
    postiz_post(chans, postiz_upload(image), fb, captions={"gmb": gmb})
    print(f"  posted [{alert['kind']}] to {', '.join(chans)}")


def in_posting_window(start=7, end=21):
    """Eastern-time guard. An alert posted at 3am is spent for nothing."""
    try:
        from zoneinfo import ZoneInfo
        now = dt.datetime.now(ZoneInfo("America/New_York"))
    except Exception:                       # no tz database available
        now = dt.datetime.now(dt.timezone.utc) - dt.timedelta(hours=5)
    return start <= now.hour < end


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dry", action="store_true",
                    help="build the cards and show the captions, post nothing, save no state")
    ap.add_argument("--seed", action="store_true",
                    help="mark today's jackpots and new games as already posted, send nothing")
    ap.add_argument("--max", type=int, default=1, metavar="N",
                    help="most alerts to post in one run (default 1, so a busy hour "
                         "spreads out instead of arriving as a burst)")
    a = ap.parse_args()

    numbers = load_json(ROOT / "public" / "numbers.json", {"draws": []})
    prizes = load_json(ROOT / "public" / "prizes.json", {"games": []})
    state = load_json(STATE_JSON, {})
    alerts_state = state.setdefault("alerts", {})

    found = (jackpot_alerts(numbers.get("draws", []), alerts_state)
             + new_game_alerts(prizes.get("games", []), alerts_state))

    if a.seed:
        for alert in found:
            commit(alert, alerts_state)
        save_json(STATE_JSON, state)
        jp = alerts_state.get("jackpots", {})
        print(f"seeded: {len(alerts_state.get('announced_games', []))} games marked announced, "
              f"jackpot tiers {({g: v['tier'] for g, v in jp.items()})} - nothing posted")
        return

    if not found:
        print("nothing new: no jackpot milestone crossed and no new scratch-offs")
        return

    if not a.dry and not in_posting_window():
        print(f"{len(found)} alert(s) ready, holding until morning - "
              f"nothing is gained posting these overnight")
        return

    # Biggest jackpot first, new scratch-offs after it.
    found.sort(key=lambda al: (al["kind"] != "jackpot", -al.get("amount", 0)))
    holding = found[a.max:]
    found = found[:a.max]

    OUT.mkdir(exist_ok=True)
    for alert in found:
        if alert["kind"] == "jackpot":
            name = alert["game"].lower().replace(" ", "-")
            image = render_jackpot(alert, OUT / f"alert-jackpot-{name}.jpg")
            print(f"{alert['game']}: {pretty(alert['amount'])}")
        else:
            image = render_new_games(alert, OUT / "alert-new-games.jpg")
            print(f"new scratch-offs: {alert['total']} game(s)")
        send(alert, image, a.dry)
        if not a.dry:
            commit(alert, alerts_state)

    for alert in holding:
        what = alert["game"] if alert["kind"] == "jackpot" else "new scratch-offs"
        print(f"  holding for a later run: {what}")

    if a.dry:
        print("\ndry run - no state saved, nothing posted")
    else:
        save_json(STATE_JSON, state)


if __name__ == "__main__":
    main()
