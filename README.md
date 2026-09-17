# @ Your Convenience — website + winner autoposter

## How it works
1. **Clerk posts a winner:** snap the ticket, save it to the Google Drive folder **11_Win_Gallery**,
   and name it with the dollar amount — e.g. `$500 winner`, `$1,000 Cash 5`, `$250 Linden`.
   (No `$` in the name = ignored. Put `Linden` in the name for the Linden store.)
2. **Every 20 minutes** (`.github/workflows/winners.yml`) the bot adds new photos to the website's
   winners wall and posts them to Facebook, Instagram and Google Business Profile.
3. **Every Sunday 7pm** (`montage.yml`) it builds a vertical video of the week's winners set to a
   Rust & Rail song (rotates through the list in `automation/config.json`) and posts it to Facebook,
   Instagram Reels, TikTok and YouTube Shorts. Skips the week if fewer than 2 winners.

## Ticket photo rule
Cover or crop the **barcode / validation number** before saving, or only save tickets that are already cashed.

## One-time setup
1. **GitHub:** create a repo, push this folder.
2. **Hosting:** GitHub Pages (Settings → Pages → Source: GitHub Actions). Domain www.atyourconveniencestores.com.
   GoDaddy DNS: A `@` → 185.199.108.153, .109.153, .110.153, .111.153 (delete the parking A records); CNAME `www` → bgordner8485-hue.github.io.
3. **Google Drive:** Google Cloud Console → create project → enable *Google Drive API* → create a
   *service account* → create a JSON key. Share the **11_Win_Gallery** folder and the Rust & Rail
   music folder with the service account's email (Viewer). Save the JSON as GitHub secret `GDRIVE_SERVICE_ACCOUNT_JSON`.
4. **Postiz:** connect the @YourConvenience Facebook page, Instagram, TikTok, YouTube and Google Business Profile.
   Settings → Public API → copy key → GitHub secret `POSTIZ_API_KEY`. Paste each channel's ID into `automation/config.json`.
5. Set `site_url` in `automation/config.json`, and hours + deals in `public/site.json`.
6. Optional: GitHub → Actions → *Sync winners* → Run workflow once. To load past winners onto the
   site without posting them, run `python automation/winners_sync.py --backfill` locally once.

## Lottery data on the site
- **Winning numbers** (`automation/lottery_data.py`): pulled hourly from the Lottery's own RSS feed
  (`palottery.pa.gov/feeds/Games.aspx`) into `public/numbers.json`, then rendered to `/numbers` and a page per game.
- **Scratch-off top prizes left**: parsed daily from `palottery.pa.gov/Scratch-Offs/Prizes-Remaining.aspx` into
  `public/prizes.json` → `/scratch-offs`.
- **Daily payouts and other retailer reports**: emailed reports are filed into a Drive folder by
  `automation/gmail_to_drive.gs` (Google Apps Script, installed in the mailbox that receives them), then
  `automation/reports_ingest.py` parses them into `public/payouts.json`. Parsers are matched on file name —
  add one per report type as real samples arrive.
- **ScratchinLottoTV**: set `youtube_url` or `youtube_channel_id` in `public/site.json`; `automation/youtube_feed.py`
  pulls the latest episodes into `public/videos.json` for `/scratchinlottotv` and the numbers page.
- **Blog**: write markdown in `content/posts/`; `automation/build_site.py` renders `/blog`, the sitemap and the RSS feed.

## Editing
- Deals and hours: `public/site.json` (edit on GitHub, site updates in ~2 min).
- Songs / chorus start time: `automation/config.json` → `montage.music`.
- Test a montage without posting: Actions → *Weekly winners montage* → run with `DRY_RUN`, or locally `python automation/weekly_montage.py --no-post`.
