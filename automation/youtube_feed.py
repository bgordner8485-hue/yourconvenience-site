"""Pull the latest ScratchinLottoTV episodes from YouTube's public channel feed into public/videos.json.
Set "youtube_channel_id" (UC...) or "youtube_url" in public/site.json. No API key needed."""
import json, re
from pathlib import Path
import requests

ROOT = Path(__file__).resolve().parent.parent
SITE = ROOT / "public" / "site.json"
OUT = ROOT / "public" / "videos.json"
UA = {"User-Agent": "Mozilla/5.0 (+atyourconveniencestores.com)"}

def channel_id(site):
    cid = (site.get("youtube_channel_id") or "").strip()
    if cid.startswith("UC"):
        return cid
    url = (site.get("youtube_url") or "").strip()
    if not url:
        return None
    html = requests.get(url, timeout=30, headers=UA).text
    m = re.search(r'"channelId":"(UC[\w-]{20,})"', html) or re.search(r'channel/(UC[\w-]{20,})', html)
    return m.group(1) if m else None

def main():
    site = json.loads(SITE.read_text())
    cid = channel_id(site)
    if not cid:
        print("No YouTube channel set in site.json — skipping."); return
    xml = requests.get(f"https://www.youtube.com/feeds/videos.xml?channel_id={cid}", timeout=30, headers=UA).text
    vids = []
    for entry in re.findall(r"<entry>(.*?)</entry>", xml, re.S):
        vid = re.search(r"<yt:videoId>(.*?)</yt:videoId>", entry)
        title = re.search(r"<title>(.*?)</title>", entry)
        pub = re.search(r"<published>(.*?)</published>", entry)
        if vid and title:
            vids.append({"id": vid.group(1), "title": title.group(1),
                         "url": f"https://www.youtube.com/watch?v={vid.group(1)}",
                         "thumb": f"https://i.ytimg.com/vi/{vid.group(1)}/hqdefault.jpg",
                         "published": pub.group(1) if pub else ""})
    OUT.write_text(json.dumps({"channel_id": cid, "channel_url": f"https://www.youtube.com/channel/{cid}",
                               "videos": vids}, indent=1) + "\n")
    print(f"videos: {len(vids)}")

if __name__ == "__main__":
    main()
