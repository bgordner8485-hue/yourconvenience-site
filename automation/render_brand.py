"""Render the brand SVGs to PNG at the sizes browsers, phones and Google need.

Run after changing public/brand/*.svg:  python automation/render_brand.py
Chromium (via Playwright) is the renderer, so what you see in a browser is what you get.
"""
import pathlib
from playwright.sync_api import sync_playwright

BRAND = pathlib.Path(__file__).resolve().parent.parent / "public" / "brand"

JOBS = [
    ("mark.svg", 1024, "logo-1024.png"),     # Google Business Profile / Facebook upload
    ("mark.svg", 512, "logo-512.png"),       # social + schema.org logo
    ("favicon.svg", 180, "apple-touch-icon.png"),
    ("favicon.svg", 32, "favicon-32.png"),
    ("favicon.svg", 16, "favicon-16.png"),
]


def main():
    holder = BRAND / "_render.html"
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        for src, size, out in JOBS:
            holder.write_text(
                f'<!doctype html><body style="margin:0">'
                f'<img src="{src}" width="{size}" height="{size}">',
                encoding="utf-8")
            page = browser.new_page(viewport={"width": size, "height": size})
            page.goto(holder.as_uri())
            page.wait_for_function(
                "() => { const i = document.querySelector('img');"
                " return i.complete && i.naturalWidth > 0; }")
            page.screenshot(path=str(BRAND / out), omit_background=True)
            page.close()
            print(f"  {out}  ({size}x{size})")
        browser.close()
    holder.unlink(missing_ok=True)
    print("brand PNGs rendered")


if __name__ == "__main__":
    main()
