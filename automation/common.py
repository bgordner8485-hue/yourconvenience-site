"""Shared helpers: config, Google Drive access, Postiz posting."""
import io, json, os, re, datetime as dt
from pathlib import Path
import requests

ROOT = Path(__file__).resolve().parent.parent
CFG = json.loads((ROOT / "automation" / "config.json").read_text())
WINNERS_JSON = ROOT / "public" / "winners.json"
STATE_JSON = ROOT / "data" / "state.json"

def load_json(p, default):
    return json.loads(p.read_text()) if p.exists() else default

def save_json(p, data):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, indent=2) + "\n")

# ---------- Google Drive (service account) ----------
def drive():
    from google.oauth2 import service_account
    from googleapiclient.discovery import build
    info = json.loads(os.environ["GDRIVE_SERVICE_ACCOUNT_JSON"])
    creds = service_account.Credentials.from_service_account_info(
        info, scopes=["https://www.googleapis.com/auth/drive.readonly"])
    return build("drive", "v3", credentials=creds, cache_discovery=False)

def list_files_any(svc, folder_id, since_iso=None):
    """Every non-trashed file in a folder (reports: CSV, XLSX, PDF...)."""
    q = f"'{folder_id}' in parents and trashed=false"
    if since_iso:
        q += f" and createdTime > '{since_iso}'"
    out, token = [], None
    while True:
        r = svc.files().list(q=q, fields="nextPageToken, files(id,name,createdTime,mimeType)",
                             orderBy="createdTime", pageSize=200, pageToken=token,
                             supportsAllDrives=True, includeItemsFromAllDrives=True).execute()
        out += r.get("files", [])
        token = r.get("nextPageToken")
        if not token:
            return out


def list_images(svc, folder_id, since_iso=None):
    q = f"'{folder_id}' in parents and mimeType contains 'image/' and trashed=false"
    if since_iso:
        q += f" and createdTime > '{since_iso}'"
    out, token = [], None
    while True:
        r = svc.files().list(q=q, fields="nextPageToken, files(id,name,createdTime,mimeType)",
                             orderBy="createdTime", pageSize=200, pageToken=token,
                             supportsAllDrives=True, includeItemsFromAllDrives=True).execute()
        out += r.get("files", [])
        token = r.get("nextPageToken")
        if not token:
            return out

def download(svc, file_id, dest):
    from googleapiclient.http import MediaIoBaseDownload
    buf = io.FileIO(dest, "wb")
    dl = MediaIoBaseDownload(buf, svc.files().get_media(fileId=file_id, supportsAllDrives=True))
    done = False
    while not done:
        _, done = dl.next_chunk()
    buf.close()

# ---------- Filename parsing ----------
AMOUNT_RE = re.compile(r"\$\s*([\d,]+(?:\.\d{1,2})?)")
def parse_name(name, default_store):
    """'$500 winner', '041826 $400 winner', '$1,000 Linden Cash 5' -> dict."""
    m = AMOUNT_RE.search(name)
    if not m:
        return None  # no dollar amount -> skip (not a winner photo)
    amount = float(m.group(1).replace(",", ""))
    low = name.lower()
    store = "Linden" if "linden" in low else default_store
    rest = AMOUNT_RE.sub("", name)
    rest = re.sub(r"(?i)\b(winner|winning|ticket|linden|south|williamsport|\d{6})\b", "", rest)
    rest = re.sub(r"\.(jpe?g|png|heic)$", "", rest, flags=re.I)
    game = re.sub(r"[\s_\-]+", " ", rest).strip() or None
    return {"amount": amount, "store": store, "game": game}

def money(n):
    return f"${n:,.0f}" if n == int(n) else f"${n:,.2f}"

# ---------- Postiz ----------
def _hdr():
    return {"Authorization": os.environ["POSTIZ_API_KEY"]}

def postiz_upload(path):
    with open(path, "rb") as f:
        r = requests.post(f"{CFG['postiz']['api_base']}/upload", headers=_hdr(),
                          files={"file": (Path(path).name, f)}, timeout=300)
    r.raise_for_status()
    j = r.json()
    return {"id": j["id"], "path": j["path"]}

SETTINGS = {
    "facebook":  lambda t: {"__type": "facebook"},
    "instagram": lambda t: {"__type": "instagram-standalone", "post_type": "post"},
    "gmb":       lambda t: {"__type": "gmb", "topicType": "STANDARD",
                            "callToActionType": "LEARN_MORE", "callToActionUrl": CFG["site_url"]},
    "tiktok":    lambda t: {"__type": "tiktok-business", "title": t[:90], "privacy_level": "PUBLIC_TO_EVERYONE",
                            "duet": False, "stitch": False, "comment": True, "autoAddMusic": "no",
                            "brand_content_toggle": False, "brand_organic_toggle": True,
                            "video_made_with_ai": False, "content_posting_method": "DIRECT_POST"},
    "youtube":   lambda t: {"__type": "youtube", "title": t[:100], "type": "public",
                            "selfDeclaredMadeForKids": "no"},
}

def postiz_post(channels, media, content, title="", captions=None):
    """channels: {platform: integration_id}. captions: optional per-platform text."""
    posts = []
    for plat, iid in channels.items():
        if not iid or iid.startswith("PASTE_"):
            print(f"  skip {plat}: channel id not set")
            continue
        text = (captions or {}).get(plat, content)
        posts.append({"integration": {"id": iid},
                      "value": [{"content": text, "image": [media]}],
                      "settings": SETTINGS[plat](title)})
    if not posts:
        return None
    if os.environ.get("DRY_RUN") == "1":
        print("  DRY_RUN:", json.dumps(posts, indent=1)[:800]); return None
    body = {"type": "now", "date": dt.datetime.now(dt.timezone.utc).isoformat(),
            "shortLink": False, "tags": [], "posts": posts}
    r = requests.post(f"{CFG['postiz']['api_base']}/posts", headers=_hdr(), json=body, timeout=120)
    print("  postiz:", r.status_code, r.text[:300])
    r.raise_for_status()
    return r.json()
