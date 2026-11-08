"""Read PA Lottery report files that land in a Drive folder (filed there by the Gmail script)
and turn them into site data: public/payouts.json (daily payouts) and any future report types.

Each report type gets a parser below, matched on the file name. Until we have a real sample,
parsers raise NotImplementedError and the file is left in place for inspection — nothing breaks.
"""
import datetime as dt, json, os, re, sys, tempfile
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import CFG, ROOT, drive, list_files_any, download, load_json, save_json  # noqa

PAYOUTS = ROOT / "public" / "payouts.json"

def parse_daily_pays(path, name):
    """Daily Pays / payouts report -> [{'date': 'YYYY-MM-DD', 'amount': float, 'tickets': int|None}]"""
    text = Path(path).read_text(errors="ignore") if path.suffix.lower() in (".csv", ".txt") else ""
    if not text:
        raise NotImplementedError(f"no parser yet for {name} (not a text/CSV report)")
    rows = []
    for line in text.splitlines():
        m = re.search(r"(\d{1,2}[/-]\d{1,2}[/-]\d{2,4}).*?\$?\s*([\d,]+\.\d{2})", line)
        if m:
            d = dt.datetime.strptime(re.sub(r"-", "/", m.group(1)), "%m/%d/%Y" if len(m.group(1)) > 8 else "%m/%d/%y")
            rows.append({"date": d.date().isoformat(), "amount": float(m.group(2).replace(",", ""))})
    if not rows:
        raise NotImplementedError(f"no rows recognised in {name}")
    return rows

PARSERS = [
    (re.compile(r"(daily.?pay|payout)", re.I), "payouts", parse_daily_pays),
]

DRAWER_FEED = "https://yc-drawer.vercel.app/api/payouts?days=400"

def from_drawer():
    """The true payouts (Brad 11/9): each night's Daily Pays "Total Pay" off the lottery terminal, as confirmed on
    the drawer app's closing sheet. Written straight into public/payouts.json. Photos are only the winners someone
    took a picture of, so they never stand in for this number."""
    import urllib.request
    try:
        with urllib.request.urlopen(urllib.request.Request(DRAWER_FEED, headers={"User-Agent": "store-bot"}), timeout=30) as r:
            feed = json.load(r)
    except Exception as e:
        print("Daily Pays feed not reachable:", e); return
    rows = [d for d in feed.get("days", []) if re.match(r"^\d{4}-\d{2}-\d{2}$", str(d.get("date", ""))) and isinstance(d.get("amount"), (int, float))]
    payouts = load_json(PAYOUTS, {"days": []})
    by_date = {d["date"]: d for d in payouts.get("days", [])}
    for d in rows:
        by_date[d["date"]] = {"date": d["date"], "amount": round(float(d["amount"]), 2), "count": d.get("count"), "source": "daily-pays"}
    days = sorted(by_date.values(), key=lambda d: d["date"], reverse=True)[:400]
    save_json(PAYOUTS, {"updated": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"), "source": "Daily Pays", "days": days})
    print(f"Daily Pays feed: {len(rows)} day(s)")

def main():
    from_drawer()
    folder = CFG.get("drive_reports_folder_id", "")
    if not folder or folder.startswith("PASTE_") or not os.environ.get("GDRIVE_SERVICE_ACCOUNT_JSON"):
        print("Reports folder not set up yet — nothing to do."); return
    state = load_json(ROOT / "data" / "reports_state.json", {"seen": []})
    svc = drive()
    files = [f for f in list_files_any(svc, folder) if f["id"] not in state["seen"]]
    print(f"{len(files)} new report file(s)")
    payouts = load_json(PAYOUTS, {"days": []})
    by_date = {d["date"]: d for d in payouts["days"]}
    for f in files:
        match = next((p for p in PARSERS if p[0].search(f["name"])), None)
        if not match:
            print(f"  unknown report type, left alone: {f['name']}"); continue
        with tempfile.TemporaryDirectory() as td:
            local = Path(td) / f["name"]
            download(svc, f["id"], local)
            try:
                rows = match[2](local, f["name"])
            except NotImplementedError as e:
                print("  ", e); continue
            except Exception as e:
                print(f"  parse failed for {f['name']}: {e}"); continue
        for r in rows:
            by_date[r["date"]] = r
        state["seen"].append(f["id"])
        print(f"  {f['name']}: {len(rows)} day(s)")
    days = sorted(by_date.values(), key=lambda d: d["date"], reverse=True)[:400]
    save_json(PAYOUTS, {"updated": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"), "days": days})
    state["seen"] = state["seen"][-2000:]
    save_json(ROOT / "data" / "reports_state.json", state)

if __name__ == "__main__":
    main()
