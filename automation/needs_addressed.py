"""Mirror the 'Needs Addressed' Drive folder onto the crew's private punch-list page.

Unlike the winners sync this MIRRORS: a photo deleted from the Drive folder
disappears from the page, so the crew never works a stale list. Clear the folder
and the page empties.

Nothing here is linked from the site, listed in the sitemap, or allowed in
robots.txt (naming a secret path in robots.txt would advertise it). The page
carries <meta name="robots" content="noindex,nofollow"> instead.
"""
import os, re, tempfile
from pathlib import Path
from PIL import Image, ImageOps
try:
    import pillow_heif; pillow_heif.register_heif_opener()   # iPhone .HEIC photos
except Exception:
    pass
from common import *

SLUG = CFG["crew_page"]["slug"]
FOLDER = CFG["crew_page"]["drive_folder_id"]
OUT_JSON = ROOT / "public" / SLUG / "needs.json"   # inside the secret path, not at /needs.json

# What the photo is asking for, read off the file name. Order matters — first hit wins.
TASKS = [
    ("pricing", "Needs pricing", r"\b(pric\w*|tag\w*|label\w*|sign\w*|no\s*price)\b"),
    ("face",    "Pull & face",   r"\b(pull|face|facing|front|fill|restock|stock|empty|gap)\b"),
]

def subfolders(svc, folder_id):
    """Immediate subfolders — their names become the task labels."""
    q = (f"'{folder_id}' in parents and mimeType = 'application/vnd.google-apps.folder' "
         f"and trashed=false")
    r = svc.files().list(q=q, fields="files(id,name)", pageSize=100,
                         supportsAllDrives=True, includeItemsFromAllDrives=True).execute()
    return r.get("files", [])


def classify(name):
    # Underscores are word characters, so "no_price" would hide "price" from \b.
    low = re.sub(r"[_\-]+", " ", re.sub(r"\.[^.]+$", "", name)).lower()
    for key, label, pattern in TASKS:
        if re.search(pattern, low):
            return key, label
    return "other", "Needs a look"

def caption(name):
    """'cooler_door_no_price_2.jpg' -> 'Cooler door no price 2'."""
    t = re.sub(r"\.[^.]+$", "", name)
    t = re.sub(r"(?i)\b(IMG|PXL|DSC|DSCN|PHOTO|SCREENSHOT)[\s_-]*\d+([\s_-]*\d+)*", " ", t)
    t = re.sub(r"\d{4}-\d{2}-\d{2}([T _-]?\d{2}[:.\-]?\d{2}([:.\-]?\d{2})?)?", " ", t)
    t = re.sub(r"[_\-]+", " ", t)
    t = re.sub(r"\b\d{6,}\b", " ", t)                          # leftover date/time runs
    t = re.sub(r"\s+", " ", t).strip()
    return (t[:1].upper() + t[1:]) if t else "Photo"


def main():
    if not os.environ.get("GDRIVE_SERVICE_ACCOUNT_JSON"):
        print("Drive access not set up yet — nothing to do."); return
    if not FOLDER or FOLDER.startswith("PASTE_"):
        print("Crew folder id not set in config.json — nothing to do."); return

    outdir = ROOT / "public" / SLUG / "photos"
    outdir.mkdir(parents=True, exist_ok=True)
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    svc = drive()
    try:
        files = [(f, None) for f in list_images(svc, FOLDER)]
        for sub in subfolders(svc, FOLDER):
            files += [(f, sub["name"]) for f in list_images(svc, sub["id"])]
    except Exception as e:
        print(f"Could not read the Needs Addressed folder: {e}")
        print("Is it shared with the store-bot service account as Viewer?")
        return

    items, keep = [], set()
    for f, folder_label in sorted(files, key=lambda t: t[0]["createdTime"]):
        out = outdir / f"{f['id']}.jpg"
        thumb = outdir / f"{f['id']}_t.jpg"
        keep.update({out.name, thumb.name})
        if not (out.exists() and thumb.exists()):   # only fetch photos we don't have
            try:
                with tempfile.TemporaryDirectory() as td:
                    raw = Path(td) / "raw"
                    download(svc, f["id"], raw)
                    img = ImageOps.exif_transpose(Image.open(raw)).convert("RGB")
                    full = img.copy(); full.thumbnail((1400, 1400))
                    full.save(out, "JPEG", quality=82, optimize=True)
                    # The grid shows these small; serving 1400px there is 10x the bytes.
                    small = img.copy(); small.thumbnail((500, 500))
                    small.save(thumb, "JPEG", quality=72, optimize=True)
                print(f"  + {f['name']}")
            except Exception as e:
                print(f"  skip (could not read photo): {f['name']} — {e}")
                keep.difference_update({out.name, thumb.name})
                continue
        if folder_label:                       # the Drive subfolder is the crew's own label
            key, label = re.sub(r"\W+", "-", folder_label.lower()).strip("-"), folder_label
        else:
            key, label = classify(f["name"])
        items.append({"id": f["id"], "added": f["createdTime"], "task": key,
                      "task_label": label, "caption": caption(f["name"]),
                      "image": f"/{SLUG}/photos/{out.name}",
                      "thumb": f"/{SLUG}/photos/{thumb.name}"})

    # Mirror: drop photos that are no longer in the Drive folder.
    removed = 0
    for old in outdir.glob("*.jpg"):
        if old.name not in keep:
            old.unlink(); removed += 1

    items.sort(key=lambda i: i["added"], reverse=True)
    counts = {}
    for i in items:
        counts[i["task_label"]] = counts.get(i["task_label"], 0) + 1
    save_json(OUT_JSON, {"updated": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
                         "count": len(items), "by_task": counts, "items": items})
    print(f"needs addressed: {len(items)} photo(s)"
          + (f", {removed} cleared" if removed else "")
          + (f" — {', '.join(f'{v} {k.lower()}' for k, v in counts.items())}" if counts else ""))


if __name__ == "__main__":
    main()
