#!/usr/bin/env python3
"""Which bins are holding games whose top prize is already gone.

Crosses the store's live bin map against the PA Lottery's prizes-remaining feed.
A game with no top prize left still sells at full price, and customers who check
before buying can see that - so those bins are the ones to turn over first.

Sources, all read-only:
  bins   https://yc-lottery.vercel.app/api/lottery?doc=state/bins
  games  https://yc-lottery.vercel.app/api/lottery?doc=config/games
  prizes public/prizes.json  (already pulled hourly by lottery_data.py)

Writes data/rack-report.md and data/rack-report.json.

  python automation/rack_report.py            # write the report
  python automation/rack_report.py --print    # ...and print it
"""
import argparse
import datetime as dt
import json
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PRIZES = ROOT / "public" / "prizes.json"
OUT_MD = ROOT / "data" / "rack-report.md"
OUT_JSON = ROOT / "data" / "rack-report.json"
API = "https://yc-lottery.vercel.app/api/lottery?doc="


def fetch(doc):
    with urllib.request.urlopen(API + doc, timeout=30) as r:
        return json.loads(r.read().decode("utf-8")).get("data") or {}


def num(value):
    digits = "".join(c for c in str(value) if c.isdigit())
    return int(digits) if digits else 0


def build():
    bins = (fetch("state/bins") or {}).get("bins") or {}
    catalog = (fetch("config/games") or {}).get("games") or {}
    prizes = json.loads(PRIZES.read_text(encoding="utf-8"))
    feed = {g["number"]: g for g in prizes.get("games", [])}

    dead, thin, unchecked = [], [], []
    for bin_no, slot in sorted(bins.items(), key=lambda kv: num(kv[0])):
        game_no = str((slot or {}).get("g", "")).strip()
        if not game_no:
            continue
        left_in_bin = num((slot or {}).get("t"))
        info = catalog.get(game_no, {})
        price = num(info.get("price"))
        name = info.get("name") or f"game {game_no}"

        game = feed.get(game_no)
        if not game:
            # x-prefixed slots are the store's own vending/special entries, and a
            # retired game drops out of the feed entirely. Either way: not checkable.
            unchecked.append({"bin": bin_no, "game": game_no, "name": name,
                              "price": price, "tickets": left_in_bin})
            continue

        row = {"bin": bin_no, "game": game_no,
               "name": game.get("name") or name,
               "price": num(game.get("price")) or price,
               "top_prize": game.get("top_prize", ""),
               "top_left": num(game.get("top_prize_left")),
               "tickets": left_in_bin}
        row["tied_up"] = row["price"] * left_in_bin
        if row["top_left"] == 0:
            dead.append(row)
        elif row["top_left"] <= 2:
            thin.append(row)

    dead.sort(key=lambda r: -r["tied_up"])
    thin.sort(key=lambda r: (r["top_left"], -num(r["top_prize"])))
    return bins, dead, thin, unchecked


def render(bins, dead, thin, unchecked):
    today = dt.date.today().isoformat()
    L = [f"# Rack report - {today}", "",
         f"{len(bins)} bins checked against the PA Lottery prizes-remaining feed.", ""]

    if dead:
        tied = sum(r["tied_up"] for r in dead)
        L += [f"## Pull these - top prize already gone ({len(dead)})", "",
              f"Roughly **${tied:,}** of ticket value sitting in bins whose headline "
              f"prize is already claimed.", "",
              "| bin | price | game | top prize | tickets left | on the pegs |",
              "|----:|------:|------|-----------|-------------:|------------:|"]
        for r in dead:
            L.append(f"| {r['bin']} | ${r['price']} | {r['name']} | {r['top_prize']} - none left "
                     f"| {r['tickets']} | ${r['tied_up']:,} |")
        L.append("")

    if thin:
        L += [f"## Nearly gone - one or two top prizes left ({len(thin)})", "",
              "Worth knowing before you reorder, and worth a post while the prize is "
              "still out there.", "",
              "| bin | price | game | top prize | left |",
              "|----:|------:|------|-----------|-----:|"]
        for r in thin:
            L.append(f"| {r['bin']} | ${r['price']} | {r['name']} | {r['top_prize']} | {r['top_left']} |")
        L.append("")

    if unchecked:
        pegs = ", ".join(r["bin"] for r in unchecked)
        L += [f"## Not in the feed - not checked ({len(unchecked)})", "",
              f"Bins {pegs}. These are the store's own vending and special entries, "
              f"or games the Lottery has retired out of the feed.", ""]

    if not dead and not thin:
        L += ["Nothing to pull and nothing nearly gone. Rack is clean.", ""]
    return "\n".join(L)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--print", dest="show", action="store_true", help="print the report too")
    a = ap.parse_args()

    bins, dead, thin, unchecked = build()
    md = render(bins, dead, thin, unchecked)
    OUT_MD.parent.mkdir(parents=True, exist_ok=True)
    OUT_MD.write_text(md, encoding="utf-8", newline="")
    OUT_JSON.write_text(json.dumps(
        {"generated": dt.datetime.now(dt.timezone.utc).isoformat(), "bins": len(bins),
         "dead": dead, "thin": thin, "unchecked": unchecked}, indent=1), encoding="utf-8", newline="")
    print(f"{len(bins)} bins | {len(dead)} to pull | {len(thin)} nearly gone | "
          f"{len(unchecked)} not checked -> {OUT_MD.relative_to(ROOT)}")
    if a.show:
        print()
        print(md)


if __name__ == "__main__":
    main()
