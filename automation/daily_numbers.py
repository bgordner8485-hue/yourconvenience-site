"""One card a day with every PA draw from the previous day, posted to Facebook.

Reads public/numbers.json (already filled by lottery_data.py from the official
feed) so this adds no new source of truth — it only renders and posts.
"""
import datetime as dt, json, os, sys
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import CFG, ROOT, load_json, postiz_upload, postiz_post  # noqa

W, H = 1080, 1350
GOLD, GOLD_D, CREAM = "#f0c000", "#a87c00", "#fff8e1"
RED, BLUE, GREEN, INK = "#c81e1e", "#123f6d", "#1a8a52", "#0d0b08"
FONTS = ROOT / "automation" / "fonts"

# Big-jackpot games first, then the twice-daily number games.
ORDER = ["Powerball", "Powerball Xs & Os", "Mega Millions", "Match 6", "Cash 5",
         "Treasure Hunt", "Millionaire for Life", "PICK 5", "PICK 4", "PICK 3", "PICK 2"]
PAIRED = {"PICK 5", "PICK 4", "PICK 3", "PICK 2"}   # Day + Evening on one row


def font(size, display=False):
    names = ([str(FONTS / "ArchivoBlack-Regular.ttf")] if display else []) + [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
        str(FONTS / "ArchivoBlack-Regular.ttf"),
    ]
    for n in names:
        try:
            return ImageFont.truetype(n, size)
        except Exception:
            continue
    return ImageFont.load_default()


def centred(dr, xy, text, f, fill):
    b = dr.textbbox((0, 0), text, font=f)
    dr.text((xy[0] - (b[2] - b[0]) / 2 - b[0], xy[1] - (b[3] - b[1]) / 2 - b[1]), text, font=f, fill=fill)


def ball(dr, cx, cy, r, text, fill, textcol):
    dr.ellipse([cx - r, cy - r, cx + r, cy + r], fill=fill, outline="#00000055", width=2)
    centred(dr, (cx, cy), text, font(int(r * 1.15)), textcol)


def draws_for(date_str):
    data = load_json(ROOT / "public" / "numbers.json", {"draws": []})
    rows = [d for d in data.get("draws", []) if d.get("date") == date_str]
    out = []
    for game in ORDER:
        hits = [d for d in rows if d.get("game") == game]
        if hits:
            out.append((game, hits))
    return out


def render(date_str, groups, path):
    im = Image.new("RGB", (W, H), INK)
    dr = ImageDraw.Draw(im)
    for y in range(H):                                   # subtle warm gradient
        v = int(9 + 12 * (1 - abs(y - H * 0.35) / H))
        dr.line([(0, y), (W, y)], fill=(v + 4, v + 2, max(v - 4, 0)))
    dr.rectangle([6, 6, W - 7, H - 7], outline=GOLD_D, width=6)

    centred(dr, (W / 2, 76), "WINNING NUMBERS", font(64, True), GOLD)
    d = dt.datetime.strptime(date_str, "%m/%d/%Y").date()
    centred(dr, (W / 2, 132), d.strftime("%A, %B %-d, %Y").upper(), font(26), CREAM)

    top, bottom = 178, H - 160
    n = max(len(groups), 1)
    rowh = min(104, (bottom - top) / n)
    # When the rows do not fill the space, centre the block instead of
    # leaving a dead gap above the footer.
    y = top + ((bottom - top) - rowh * n) / 2 + rowh / 2
    for game, hits in groups:
        dr.rounded_rectangle([34, y - rowh / 2 + 5, W - 34, y + rowh / 2 - 5], 13,
                             fill="#161208", outline="#2e2718", width=1)
        gf = font(25, True)
        b = dr.textbbox((0, 0), game, font=gf)
        while b[2] - b[0] > 250 and gf.size > 15:
            gf = font(gf.size - 2, True)
            b = dr.textbbox((0, 0), game, font=gf)
        dr.text((58, y - (b[3] - b[1]) / 2 - b[1]), game, font=gf, fill=GOLD)

        if game in PAIRED:
            x = 330
            for tag in ("Day", "Evening"):
                hit = next((h for h in hits if h.get("draw") == tag), None)
                if not hit:
                    continue
                centred(dr, (x + 22, y - rowh * 0.26), tag.upper()[:3], font(15), "#8a7f66")
                r = 20
                for i, num in enumerate(hit["numbers"]):
                    ball(dr, x + 8 + i * (r * 2 + 6), y + rowh * 0.06, r, str(num), CREAM, INK)
                x += 8 + len(hit["numbers"]) * (r * 2 + 6) + 60
        else:
            hit = hits[0]
            r = 26
            x = 350
            for num in hit["numbers"]:
                ball(dr, x, y, r, str(num), CREAM, INK)
                x += r * 2 + 10
            if hit.get("powerball"):
                ball(dr, x, y, r, str(hit["powerball"]), RED, "#fff")
                x += r * 2 + 10
            if hit.get("mega_ball"):
                ball(dr, x, y, r, str(hit["mega_ball"]), GOLD, INK)
                x += r * 2 + 10
            jp = hit.get("next_jackpot")
            if jp:
                jf = font(21, True)
                bb = dr.textbbox((0, 0), jp, font=jf)
                dr.text((W - 60 - (bb[2] - bb[0]), y - (bb[3] - bb[1]) / 2 - bb[1]), jp, font=jf, fill=GREEN)
        y += rowh

    fy = H - 142
    dr.rounded_rectangle([34, fy, W - 34, H - 30], 13, fill="#000000", outline=GOLD, width=3)
    centred(dr, (W / 2, fy + 30), "PLAY HERE.   WIN HERE.   GET PAID HERE.", font(27, True), GOLD)
    centred(dr, (W / 2, fy + 62), CFG["store_name"], font(21), CREAM)
    centred(dr, (W / 2, fy + 90), "Must be 18 or older.  Please play responsibly.", font(16), "#8a7f66")
    im.save(path, "JPEG", quality=90, optimize=True)
    return path


def caption(date_str, groups):
    d = dt.datetime.strptime(date_str, "%m/%d/%Y").date()
    jackpots = []
    for game, hits in groups:
        jp = hits[0].get("next_jackpot")
        if jp and game in ("Powerball", "Mega Millions", "Match 6", "Cash 5", "Treasure Hunt"):
            jackpots.append(f"{game} {jp}")
    lines = [f"PA Lottery winning numbers for {d.strftime('%A, %B %-d')} \U0001f340",
             "", "Check your tickets — all of yesterday's draws are on the board."]
    if jackpots:
        lines += ["", "Coming up: " + "  •  ".join(jackpots[:4])]
    lines += ["", f"Tickets sold daily at {CFG['store_name']}.", CFG["hashtags"]]
    return "\n".join(lines)


def main():
    day = (dt.date.today() - dt.timedelta(days=1))
    if len(sys.argv) > 1 and sys.argv[1] not in ("--dry",):
        day = dt.datetime.strptime(sys.argv[1], "%Y-%m-%d").date()
    date_str = day.strftime("%m/%d/%Y")
    groups = draws_for(date_str)
    if not groups:
        print(f"no draws recorded for {date_str} — nothing to post"); return
    out = ROOT / "out"; out.mkdir(exist_ok=True)
    img = render(date_str, groups, out / "daily-numbers.jpg")
    text = caption(date_str, groups)
    print(f"{len(groups)} games for {date_str} -> {img}")
    print("-" * 60); print(text); print("-" * 60)
    if "--dry" in sys.argv:
        print("dry run — not posting"); return
    if not os.environ.get("POSTIZ_API_KEY"):
        print("POSTIZ_API_KEY not set — image built, not posted"); return
    media = postiz_upload(img)
    postiz_post({"facebook": CFG["postiz"]["winner_channels"]["facebook"]}, media, text)


if __name__ == "__main__":
    main()
