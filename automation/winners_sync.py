"""Every run: find new photos in the Drive win folder -> add to website -> post to FB / IG / Google Business."""
import datetime as dt, os, sys, tempfile
from pathlib import Path
from PIL import Image, ImageOps
try:
    import pillow_heif; pillow_heif.register_heif_opener()   # iPhone .HEIC photos
except Exception:
    pass
from common import *

def save_all(data, state, files, since):
    data["winners"].sort(key=lambda w: w["date"], reverse=True)
    save_json(WINNERS_JSON, data)
    stamps = [f["createdTime"] for f in files] + [state.get("since") or since or ""]
    state["since"] = max(stamps)
    state["seen"] = state["seen"][-5000:]
    save_json(STATE_JSON, state)


def main():
    if not os.environ.get("GDRIVE_SERVICE_ACCOUNT_JSON"):
        print("Drive access not set up yet (GDRIVE_SERVICE_ACCOUNT_JSON missing) — nothing to do."); return
    state = load_json(STATE_JSON, {"seen": [], "since": None})
    data = load_json(WINNERS_JSON, {"winners": []})
    svc = drive()
    # First run: only look back 14 days so we don't blast a year of old photos to social.
    since = state["since"] or (dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=14)).isoformat()
    backfill_site_only = "--backfill" in sys.argv or os.environ.get("BACKFILL") == "true"
    if backfill_site_only:
        since = None
    files = []
    try:
        files = [f for f in list_images(svc, CFG["drive_winners_folder_id"], since) if f["id"] not in state["seen"]]
        print(f"{len(files)} new photo(s)")
        outdir = ROOT / "public" / "winners"; outdir.mkdir(parents=True, exist_ok=True)
        for f in files:
            info = parse_name(f["name"], CFG["default_store"])
            state["seen"].append(f["id"])
            if not info:
                print(f"  skip (no $ amount in name): {f['name']}"); continue
            try:
                with tempfile.TemporaryDirectory() as td:
                    raw = Path(td) / "raw"
                    download(svc, f["id"], raw)
                    img = ImageOps.exif_transpose(Image.open(raw)).convert("RGB")
                    img.thumbnail((1080, 1350))
                    out = outdir / f"{f['id']}.jpg"
                    img.save(out, "JPEG", quality=85, optimize=True)
            except Exception as e:
                print(f"  skip (could not read photo): {f['name']} — {e}"); continue
            entry = {"id": f["id"], "date": f["createdTime"], "image": f"/winners/{out.name}", **info}
            data["winners"].append(entry)
            print(f"  added {money(info['amount'])} ({info['store']})")
            if backfill_site_only:
                continue
            amt = money(info["amount"])
            game = f" on {info['game']}" if info["game"] else ""
            text = (f"🎉 WINNER ALERT! 🎉\nAnother {amt} winner{game} sold at {CFG['store_name']} — {info['store']}! "
                    f"Congratulations to our lucky customer! 🍀\n\nYour next ticket could be the one. Play here. Win here.\n"
                    f"{CFG['hashtags']}")
            gmb = (f"Another {amt} winning ticket{game} sold at our {info['store']} store! Congratulations! "
                   f"See all our recent winners on our website.")
            try:
                if not os.environ.get("POSTIZ_API_KEY"):
                    print("  (Postiz not set up yet — website only)"); continue
                media = postiz_upload(out)
                postiz_post(CFG["postiz"]["winner_channels"], media, text, captions={"gmb": gmb})
            except Exception as e:  # keep the website update even if social fails
                print("  POSTING FAILED:", e)
    finally:
        save_all(data, state, files, since)

if __name__ == "__main__":
    main()
