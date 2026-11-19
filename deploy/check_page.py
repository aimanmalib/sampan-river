"""Read-only browser check of the film page (decision 0009).

python3 deploy/check_page.py BASE_URL [--out DIR]

Opens every language page in WebKit (iPhone 13) and Chromium (desktop and 320 px wide) and fails when: the page
scrolls sideways, the prize address or the film is not on the first screen of a phone, a video does not load its
metadata, the copy button does not report back, or the console shows an error. Screenshots go to --out.
"""
import argparse
import json
import os
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

PROBE = """() => {
  const doc = document.documentElement;
  const box = el => { const r = el.getBoundingClientRect(); return {top: r.top, bottom: r.bottom, h: r.height}; };
  const addr = document.getElementById('addr');
  const film = document.querySelector('.film video');
  return {
    overflow: doc.scrollWidth - doc.clientWidth,
    viewport: window.innerHeight,
    addr: addr ? addr.textContent.trim() : '',
    addrBox: addr ? box(addr) : null,
    filmBox: film ? box(film) : null,
    videos: [...document.querySelectorAll('video')].map(v => ({ready: v.readyState, w: v.videoWidth, src: v.currentSrc})),
    lang: doc.lang,
  };
}"""


def load_config():
    with open(os.path.join(ROOT, "config", "site.json"), encoding="utf-8") as f:
        return json.load(f)


def wait_videos(page, timeout_ms):
    page.wait_for_function("() => [...document.querySelectorAll('video')].every(v => v.readyState >= 1)",
                           timeout=timeout_ms)


def check_page(page, url, name, cfg, out, first_screen):
    errors = []
    page.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.goto(url, wait_until="load")
    problems = []
    try:
        wait_videos(page, 20000)
    except Exception:  # reported below from the probe
        pass
    p = page.evaluate(PROBE)
    page.screenshot(path=os.path.join(out, f"{name}.png"))
    page.screenshot(path=os.path.join(out, f"{name}-full.png"), full_page=True)
    if p["overflow"] > 0:
        problems.append(f"page scrolls sideways by {p['overflow']} px")
    if p["addr"] != cfg["prize_address"]:
        problems.append("prize address missing or different")
    for v in p["videos"]:
        if v["ready"] < 1 or not v["w"]:
            problems.append(f"video did not load: {v['src']}")
    if first_screen:
        if not p["addrBox"] or p["addrBox"]["bottom"] > p["viewport"]:
            problems.append("prize address is below the first screen")
        if not p["filmBox"] or p["filmBox"]["top"] + p["filmBox"]["h"] / 2 > p["viewport"]:
            problems.append("film is not on the first screen")
    # Scrolled: nothing may spill sideways further down either.
    page.evaluate("() => window.scrollTo(0, document.documentElement.scrollHeight)")
    page.wait_for_timeout(300)
    if page.evaluate("() => document.documentElement.scrollWidth - document.documentElement.clientWidth") > 0:
        problems.append("page scrolls sideways after scrolling down")
    page.evaluate("() => window.scrollTo(0, 0)")
    try:
        page.click("button.copy", timeout=5000)
        page.wait_for_function("() => document.querySelector('.copy-status').textContent.trim() !== ''", timeout=5000)
    except Exception:
        problems.append("copy button gave no feedback")
    problems += [f"console: {e}" for e in errors]
    return problems


def main(argv=None):
    from playwright.sync_api import sync_playwright
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("base")
    ap.add_argument("--out", default="")
    args = ap.parse_args(argv)
    cfg = load_config()
    out = args.out or tempfile.mkdtemp(prefix="river-check-")
    os.makedirs(out, exist_ok=True)
    base = args.base.rstrip("/")
    failures = {}
    with sync_playwright() as pw:
        webkit, chromium = pw.webkit.launch(), pw.chromium.launch()
        runs = [
            ("webkit-iphone13", webkit, dict(pw.devices["iPhone 13"]), True),
            ("chromium-desktop", chromium, {"viewport": {"width": 1366, "height": 900}}, False),
            ("chromium-320", chromium, {"viewport": {"width": 320, "height": 640}, "is_mobile": True,
                                        "has_touch": True, "device_scale_factor": 2}, False),
        ]
        for label, browser, opts, first in runs:
            ctx = browser.new_context(**opts)
            for lang in cfg["languages"]:
                name = f"{label}-{lang['code']}"
                page = ctx.new_page()
                problems = check_page(page, base + lang["path"], name, cfg, out, first)
                page.close()
                print(f"{name}: {'ok' if not problems else '; '.join(problems)}")
                if problems:
                    failures[name] = problems
            ctx.close()
        webkit.close()
        chromium.close()
    print(f"screenshots: {out}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
