"""Weekly + monthly: build a vertical 1080x1920 montage of the last 7 days of winners, set to a Rust & Rail track,
and post it to Facebook, Instagram (Reel), TikTok and YouTube Shorts.

  python weekly_montage.py                   # weekly: last 7 days, build + post
  python weekly_montage.py --period month    # monthly: all of last month (run on the 1st)
  python weekly_montage.py --no-post         # build only (writes out/montage-<period>.mp4)
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

def build(winners, music, music_start, out_mp4, work, period="week", label="", shown_total=None, shown_count=None):
    """shown_total/shown_count: whole-period numbers for the title card when the video had to be trimmed."""
    total = sum(w["amount"] for w in winners)
    card_total = shown_total if shown_total is not None else total
    card_count = shown_count if shown_count is not None else len(winners)
    p = period_cfg(period)
    per = min(p["seconds_per_winner"], (p["max_seconds"] - 6) / max(len(winners), 1))
    per = max(per, p["min_seconds_per_winner"])
    xf = 0.35
    slides = []
    head = "THIS WEEK'S" if period == "week" else "THIS MONTH'S"
    lines = [(head, 90, WHITE), ("WINNERS", 130, GOLD), (f"{money(card_total)} WON", 100, WHITE)]
    if period == "month":
        lines.append((f"{card_count} WINNING TICKETS", 56, WHITE))
    lines.append((label or CFG["store_name"], 56, GOLD))
    card(lines, work / "intro.png")
    slides.append((work / "intro.png", 3.0))
    for i, w in enumerate(winners):
        p = work / f"w{i}.png"; winner_slide(w["_path"], w, p); slides.append((p, per))
    card([("PLAY HERE.", 110, WHITE), ("WIN HERE.", 110, GOLD), ("", 40, WHITE),
          (CFG["store_address"], 40, WHITE), ("Music: Rust & Rail", 40, (200, 210, 225))], work / "outro.png")
    slides.append((work / "outro.png", 3.0))
    clips = []
    for i, (png, secs) in enumerate(slides):
        c = work / f"c{i}.mp4"; clip(png, secs + xf, c, zoom_in=i % 2 == 0); clips.append((c, secs + xf))
    # Chain crossfades. ffmpeg holds every input open at once, so a monthly montage (150+ clips)
    # would run out of memory in one pass — join in chunks of 20, then crossfade the chunks.
    def chain(parts, out, salt=0):
        inputs, filt, last, offset = [], [], "[0:v]", 0.0
        for c, _ in parts: inputs += ["-i", str(c)]
        for i in range(1, len(parts)):
            offset += parts[i - 1][1] - xf
            k = i + salt
            trans = "fade" if (salt == 0 and i in (1, len(parts) - 1)) else ["slideleft", "slideup", "circleopen", "smoothleft"][k % 4]
            filt.append(f"{last}[{i}:v]xfade=transition={trans}:duration={xf}:offset={offset:.3f}[v{i}]")
            last = f"[v{i}]"
        dur = offset + parts[-1][1]
        if len(parts) == 1:
            filt, last = ["[0:v]null[v0]"], "[v0]"
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", *inputs, "-filter_complex", ";".join(filt), "-map", last,
                        "-c:v", "libx264", "-preset", "veryfast", "-crf", "18", "-pix_fmt", "yuv420p", "-r", str(FPS),
                        str(out)], check=True)
        return dur

    CHUNK = 20
    if len(clips) > CHUNK + 4:
        segs = []
        for n, i in enumerate(range(0, len(clips), CHUNK)):
            seg = work / f"seg{n}.mp4"
            segs.append((seg, chain(clips[i:i + CHUNK], seg, salt=i)))
        clips = segs
    silent = work / "silent.mp4"
    duration = chain(clips, silent)
    af = (f"atrim=start={music_start}:duration={duration:.3f},asetpts=PTS-STARTPTS,"
          f"afade=t=in:d=0.5,afade=t=out:st={duration-2:.3f}:d=2,loudnorm=I=-14:TP=-1.5")
    # long montages loop the song if it is shorter than the video
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(silent), "-stream_loop", "-1", "-i", str(music),
                    "-map", "0:v", "-map", "1:a", "-af", af, "-c:v", "libx264", "-preset", "medium", "-crf", "20",
                    "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k", "-t", f"{duration:.3f}",
                    "-movflags", "+faststart", str(out_mp4)], check=True)
    return total, duration

def clean_song_title(filename):
    """'03_After_Everyone_Goes_Home_2026-07-23T215433.mp3' -> 'After Everyone Goes Home'."""
    t = re.sub(r"\.[^.]+$", "", filename)                       # drop the extension
    t = re.sub(r"\d{4}-\d{2}-\d{2}[T _-]?\d{0,6}", " ", t)      # export timestamps
    t = re.sub(r"[_]+", " ", t)
    t = re.sub(r"(?i)\b(final|master|mastered|mixdown|mix|v\d+|take\s*\d+|"
               r"wav|mp3|export|render|copy|\d{1,3}kbps)\b", " ", t)
    t = re.sub(r"^\s*\d{1,2}[\s.\-]+(?=\D)", "", t)            # leading track number
    t = re.sub(r"\(\s*\d+\s*\)", " ", t)                       # '(1)' duplicate marker
    t = re.sub(r"[\s\-]+$", "", re.sub(r"\s+", " ", t)).strip(" -_")
    if t and t == t.lower():
        t = " ".join(w.capitalize() for w in t.split())
    return t or filename


AUDIO_EXT = (".mp3", ".wav", ".m4a", ".aac", ".flac", ".ogg", ".aiff", ".wma")

def song_catalog(svc):
    """Every Rust & Rail track in the configured Drive song folders (one level of subfolders)."""
    folders = list(CFG["montage"].get("music_folder_ids") or [])
    start = CFG["montage"].get("music_start", 30)
    seen_folders, songs, seen = set(), [], set()
    while folders:
        fid = folders.pop(0)
        if fid in seen_folders:
            continue
        seen_folders.add(fid)
        try:
            files = list_files_any(svc, fid)
        except Exception as e:
            print(f"  song folder {fid}: {e}")
            continue
        for f in files:
            if f.get("mimeType") == "application/vnd.google-apps.folder":
                if len(seen_folders) < 25:
                    folders.append(f["id"])
                continue
            name = f["name"]
            if not (name.lower().endswith(AUDIO_EXT) or str(f.get("mimeType", "")).startswith("audio/")):
                continue
            title = clean_song_title(name)
            key = title.lower()
            if key in seen:
                continue
            seen.add(key)
            songs.append({"title": title, "drive_id": f["id"], "start": start})
    songs.sort(key=lambda s: s["title"].lower())
    return songs


PERIOD_DEFAULTS = {
    "week":  {"min_winners": 2, "seconds_per_winner": 2.6, "min_seconds_per_winner": 1.2, "max_seconds": 58},
    "month": {"min_winners": 4, "seconds_per_winner": 2.0, "min_seconds_per_winner": 0.9, "max_seconds": 150},
}

def period_cfg(period):
    """Weekly settings come from config 'montage' (unchanged); monthly from 'montage.monthly'."""
    m = CFG["montage"]
    base = dict(PERIOD_DEFAULTS[period])
    src = m if period == "week" else m.get("monthly", {})
    base.update({k: src[k] for k in base if k in src})
    return base


def period_window(period, today=None):
    """week  -> the last 7 days (what it has always done)
       month -> the whole previous calendar month (built on the 1st)."""
    now = dt.datetime.now(dt.timezone.utc)
    if period == "week":
        return now - dt.timedelta(days=7), now, ""
    today = today or dt.date.today()
    first_this = today.replace(day=1)
    last_prev = first_this - dt.timedelta(days=1)
    start = dt.datetime(last_prev.year, last_prev.month, 1, tzinfo=dt.timezone.utc)
    end = dt.datetime(first_this.year, first_this.month, 1, tzinfo=dt.timezone.utc)
    return start, end, last_prev.strftime("%B %Y").upper()


VIDEOS_JSON = ROOT / "public" / "videos" / "montages.json"

def record_for_website(period, label, count, total, dur, song, release_tag):
    """public/videos/montages.json tells the website + TV page what the latest montages are.
    The .mp4 itself lives as a GitHub Release asset (keeps the repo small) and is copied into the
    site at deploy time as /videos/<period>-latest.mp4."""
    data = load_json(VIDEOS_JSON, {"latest": {}, "archive": []})
    entry = {
        "period": period, "label": label, "built": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "count": count, "total": total, "seconds": round(dur, 1), "song": song["title"],
        "src": f"/videos/{period}-latest.mp4",
        "archive_file": f"{period}-{dt.date.today().isoformat()}.mp4",
        "release_tag": release_tag,
    }
    data["latest"][period] = entry
    data["archive"] = ([entry] + [a for a in data.get("archive", []) if a.get("archive_file") != entry["archive_file"]])[:120]
    save_json(VIDEOS_JSON, data)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-post", action="store_true")
    ap.add_argument("--local", action="store_true", help="use public/winners images instead of Drive")
    ap.add_argument("--music", help="local audio file (skips Drive download)")
    ap.add_argument("--period", choices=["week", "month"], default="week")
    a = ap.parse_args()
    pcfg = period_cfg(a.period)
    if not a.local and not os.environ.get("GDRIVE_SERVICE_ACCOUNT_JSON"):
        print("Drive access not set up yet — skipping."); return

    start, end, label = period_window(a.period)
    data = load_json(WINNERS_JSON, {"winners": []})
    def when(w): return dt.datetime.fromisoformat(w["date"].replace("Z", "+00:00"))
    winners = [w for w in data["winners"] if start <= when(w) < end]
    winners.sort(key=lambda w: w["date"])
    full_count, full_total = len(winners), sum(w["amount"] for w in winners)
    if len(winners) < pcfg["min_winners"]:
        print(f"Only {len(winners)} winner(s) this {a.period} — skipping montage."); return
    # biggest winners first if we have to trim
    max_n = int((pcfg["max_seconds"] - 6) / pcfg["min_seconds_per_winner"])
    if len(winners) > max_n:
        winners = sorted(sorted(winners, key=lambda w: -w["amount"])[:max_n], key=lambda w: w["date"])

    state = load_json(STATE_JSON, {})
    out_dir = ROOT / "out"; out_dir.mkdir(exist_ok=True)
    out_mp4 = out_dir / f"montage-{a.period}.mp4"
    with tempfile.TemporaryDirectory() as td:
        work = Path(td)
        svc = None if (a.local and a.music) else drive()
        songs = song_catalog(svc) if svc else []
        if not songs:
            songs = CFG["montage"]["music"]          # fallback: the hand-listed tracks
        print(f"{len(songs)} Rust & Rail track(s) available")
        # monthly picks from the other end of the list so it rarely repeats the weekly song
        if a.period == "week":
            song = songs[state.get("montage_count", 0) % len(songs)]
        else:
            song = songs[-1 - (state.get("monthly_count", 0) % len(songs))]
        for w in winners:  # use the full-res originals when we can
            if a.local:
                w["_path"] = ROOT / "public" / w["image"].lstrip("/")
            else:
                w["_path"] = work / f"{w['id']}.img"; download(svc, w["id"], w["_path"])
        music = Path(a.music) if a.music else work / "song"
        if not a.music:
            download(svc, song["drive_id"], music)
        total, dur = build(winners, music, song.get("start", 0) if not a.music else 0, out_mp4, work,
                           period=a.period, label=label, shown_total=full_total, shown_count=full_count)
    total = full_total  # captions always show the whole period, even if the video was trimmed
    print(f"Built {out_mp4} — {len(winners)} winners, {money(total)}, {dur:.1f}s, song: {song['title']}")
    key = "montage_count" if a.period == "week" else "monthly_count"
    state[key] = state.get(key, 0) + 1   # rotate the song, posted or not
    save_json(STATE_JSON, state)
    record_for_website(a.period, label, full_count, total, dur, song, os.environ.get("MONTAGE_RELEASE_TAG", "montages"))
    if a.no_post:
        return
    channels = {k: v for k, v in CFG["postiz"]["montage_channels"].items() if v and not v.startswith("PASTE_")}
    if not os.environ.get("POSTIZ_API_KEY") or not channels:
        print("Postiz not set up yet (API key or channel ids missing) — video built but not posted."); return
    if a.period == "week":
        week = dt.date.today().strftime("%b %d")
        title = f"{money(total)} in Winners This Week! @ Your Convenience 🎉 #Shorts"
        text = (f"🍀 This week's winners at {CFG['store_name']}! {full_count} winning tickets, {money(total)} total "
                f"(week of {week}). Congratulations to everyone who cashed in! 🎉\n\n")
    else:
        month = label.title()
        title = f"{money(total)} in Winners in {month}! @ Your Convenience 🎉"
        text = (f"🏆 {month} at {CFG['store_name']}: {full_count} winning tickets and {money(total)} paid out "
                f"right here at our counter! Thank you for playing with us — next month could be yours. 🍀\n\n")
    text += f"🎵 Music: \"{song['title']}\" by Rust & Rail\n📍 {CFG['store_address']}\n🎬 Watch every winner: {CFG['site_url']}/#videos\n{CFG['hashtags']}"
    media = postiz_upload(out_mp4)
    postiz_post(channels, media, text, title=title)

if __name__ == "__main__":
    main()
