"""Weekly: build a vertical 1080x1920 montage of the last 7 days of winners, set to a Rust & Rail track,
and post it to Facebook, Instagram (Reel), TikTok and YouTube Shorts.

  python weekly_montage.py              # build + post
  python weekly_montage.py --no-post    # build only (writes out/montage.mp4)
  python weekly_montage.py --music x.wav --local   # offline test using public/winners + a local song
"""
import argparse, datetime as dt, os, subprocess, tempfile
from pathlib import Path
from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageOps
from common import *

W, H, FPS = 1080, 1920, 30
FONT_B = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
NAVY, GOLD, WHITE = (16, 35, 61), (255, 200, 61), (255, 255, 255)

def font(size, path=None):
    for p in [path, str(ROOT / "automation" / "fonts" / "ArchivoBlack-Regular.ttf"), FONT_B]:
        try:
            if p: return ImageFont.truetype(p, size)
        except OSError: pass
    return ImageFont.load_default()

def center(d, y, text, f, fill, stroke=0):
    w = d.textlength(text, font=f)
    d.text(((W - w) / 2, y), text, font=f, fill=fill, stroke_width=stroke, stroke_fill=(0, 0, 0))

def pill(d, cy, text, f):
    w = d.textlength(text, font=f); pad = 40
    box = [(W - w) / 2 - pad, cy - 20, (W + w) / 2 + pad, cy + f.size + 40]
    d.rounded_rectangle(box, radius=36, fill=GOLD)
    d.text(((W - w) / 2, cy), text, font=f, fill=NAVY)

def winner_slide(photo, w, out):
    img = ImageOps.exif_transpose(Image.open(photo)).convert("RGB")
    bg = ImageOps.fit(img, (W, H)).filter(ImageFilter.GaussianBlur(40))
    bg = Image.blend(bg, Image.new("RGB", (W, H), NAVY), 0.45)
    fg = img.copy(); fg.thumbnail((W - 160, 1150))
    bg.paste(fg, ((W - fg.width) // 2, 330 + (1150 - fg.height) // 2))
    d = ImageDraw.Draw(bg)
    center(d, 170, "WINNER!", font(110), GOLD, stroke=4)
    pill(d, 1520, money(w["amount"]), font(130))
    sub = w.get("game") or w.get("store") or ""
    if sub: center(d, 1720, sub.upper(), font(48), WHITE, stroke=2)
    bg.save(out)

def card(lines, out):
    im = Image.new("RGB", (W, H), NAVY); d = ImageDraw.Draw(im)
    for i in range(0, W + H, 90):  # subtle stripes
        d.line([(i, 0), (i - H, H)], fill=(20, 42, 72), width=30)
    y = 560
    for text, size, color in lines:
        center(d, y, text, font(size), color, stroke=2); y += int(size * 1.35)
    im.save(out)

def clip(png, secs, out, zoom_in=True):
    frames = int(secs * FPS)
    z = f"min(1+0.0006*on,1.08)" if zoom_in else f"max(1.08-0.0006*on,1)"
    vf = (f"scale={W*2}:{H*2},zoompan=z='{z}':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)'"
          f":d={frames}:s={W}x{H}:fps={FPS},format=yuv420p")
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-loop", "1", "-i", str(png), "-vf", vf,
                    "-frames:v", str(frames), "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", str(out)], check=True)

def build(winners, music, music_start, out_mp4, work):
    total = sum(w["amount"] for w in winners)
    mcfg = CFG["montage"]
    per = min(mcfg["seconds_per_winner"], (mcfg["max_seconds"] - 6) / max(len(winners), 1))
    per = max(per, 1.2)
    xf = 0.35
    slides = []
    card([("THIS WEEK'S", 90, WHITE), ("WINNERS", 130, GOLD), (f"{money(total)} WON", 100, WHITE),
          (CFG["store_name"], 56, GOLD)], work / "intro.png")
    slides.append((work / "intro.png", 3.0))
    for i, w in enumerate(winners):
        p = work / f"w{i}.png"; winner_slide(w["_path"], w, p); slides.append((p, per))
    card([("PLAY HERE.", 110, WHITE), ("WIN HERE.", 110, GOLD), ("", 40, WHITE),
          (CFG["store_address"], 40, WHITE), ("Music: Rust & Rail", 40, (200, 210, 225))], work / "outro.png")
    slides.append((work / "outro.png", 3.0))
    clips = []
    for i, (png, secs) in enumerate(slides):
        c = work / f"c{i}.mp4"; clip(png, secs + xf, c, zoom_in=i % 2 == 0); clips.append((c, secs + xf))
    # chain xfades
    inputs, filt, last, offset = [], [], "[0:v]", 0.0
    for c, _ in clips: inputs += ["-i", str(c)]
    for i in range(1, len(clips)):
        offset += clips[i - 1][1] - xf
        trans = "fade" if i in (1, len(clips) - 1) else ["slideleft", "slideup", "circleopen", "smoothleft"][i % 4]
        filt.append(f"{last}[{i}:v]xfade=transition={trans}:duration={xf}:offset={offset:.3f}[v{i}]")
        last = f"[v{i}]"
    duration = offset + clips[-1][1]
    ai = len(clips)
    filt.append(f"[{ai}:a]atrim=start={music_start}:duration={duration:.3f},asetpts=PTS-STARTPTS,"
                f"afade=t=in:d=0.5,afade=t=out:st={duration-2:.3f}:d=2,loudnorm=I=-14:TP=-1.5[a]")
    cmd = ["ffmpeg", "-y", "-loglevel", "error", *inputs, "-i", str(music), "-filter_complex", ";".join(filt),
           "-map", last, "-map", "[a]", "-c:v", "libx264", "-preset", "medium", "-crf", "20", "-pix_fmt", "yuv420p",
           "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", "-r", str(FPS), str(out_mp4)]
    subprocess.run(cmd, check=True)
    return total, duration

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-post", action="store_true")
    ap.add_argument("--local", action="store_true", help="use public/winners images instead of Drive")
    ap.add_argument("--music", help="local audio file (skips Drive download)")
    ap.add_argument("--days", type=int, default=7)
    a = ap.parse_args()
    if not a.local and not os.environ.get("GDRIVE_SERVICE_ACCOUNT_JSON"):
        print("Drive access not set up yet — skipping."); return

    cutoff = dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=a.days)
    data = load_json(WINNERS_JSON, {"winners": []})
    winners = [w for w in data["winners"] if dt.datetime.fromisoformat(w["date"].replace("Z", "+00:00")) >= cutoff]
    winners.sort(key=lambda w: w["date"])
    if len(winners) < CFG["montage"]["min_winners"]:
        print(f"Only {len(winners)} winner(s) this week — skipping montage."); return
    # biggest winners first if we have to trim
    max_n = int((CFG["montage"]["max_seconds"] - 6) / 1.2)
    if len(winners) > max_n:
        winners = sorted(sorted(winners, key=lambda w: -w["amount"])[:max_n], key=lambda w: w["date"])

    state = load_json(STATE_JSON, {})
    songs = CFG["montage"]["music"]
    song = songs[state.get("montage_count", 0) % len(songs)]
    out_dir = ROOT / "out"; out_dir.mkdir(exist_ok=True)
    out_mp4 = out_dir / "montage.mp4"
    with tempfile.TemporaryDirectory() as td:
        work = Path(td)
        svc = None if (a.local and a.music) else drive()
        for w in winners:  # use the full-res originals when we can
            if a.local:
                w["_path"] = ROOT / "public" / w["image"].lstrip("/")
            else:
                w["_path"] = work / f"{w['id']}.img"; download(svc, w["id"], w["_path"])
        music = Path(a.music) if a.music else work / "song"
        if not a.music:
            download(svc, song["drive_id"], music)
        total, dur = build(winners, music, song.get("start", 0) if not a.music else 0, out_mp4, work)
    print(f"Built {out_mp4} — {len(winners)} winners, {money(total)}, {dur:.1f}s, song: {song['title']}")
    if a.no_post:
        return
    week = dt.date.today().strftime("%b %d")
    title = f"{money(total)} in Winners This Week! @ Your Convenience 🎉 #Shorts"
    text = (f"🍀 This week's winners at {CFG['store_name']}! {len(winners)} winning tickets, {money(total)} total "
            f"(week of {week}). Congratulations to everyone who cashed in! 🎉\n\n"
            f"🎵 Music: \"{song['title']}\" by Rust & Rail\n📍 {CFG['store_address']}\n{CFG['hashtags']}")
    media = postiz_upload(out_mp4)
    postiz_post(CFG["postiz"]["montage_channels"], media, text, title=title)
    state["montage_count"] = state.get("montage_count", 0) + 1
    save_json(STATE_JSON, state)

if __name__ == "__main__":
    main()
