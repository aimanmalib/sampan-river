"""Read-only browser check of the film page (decision 0009).

python3 deploy/check_page.py BASE_URL [--out DIR]

Opens every language page in WebKit (iPhone 13) and Chromium (desktop and 320 px wide) and fails when: the page
scrolls sideways, the prize address is not on the first screen of an iPhone, the first video on a phone (iPhone 13 and
320 px) is not the 9:16 film with at least `check.min_visible` (config/site.json) of its height on the first screen, the 16:9 film is not on the
first desktop screen, a video does not load its metadata (players set to preload="none" are asked to load after the
first-screen check), the copy button does not report back, the Share button is hidden or shares another address than
the page's canonical one (checked with a stand-in navigator.share, then without one: the panel opens and Copy link
reports back), the Watch on YouTube link (decision 0017) is not the only YouTube link, points elsewhere than youtube_url,
is under 44 px, has text contrast under 4.5:1 or is below the first iPhone screen, the repository link is hidden while
banner.repo_check is "on", the fee figure does not link to its transaction, the banner note is missing, or the console shows an
error. Screenshots go to --out.
"""
import argparse
import json
import os
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from tools.bands import contrast  # noqa: E402  (WCAG ratio, shared with the film's caption check)

PROBE = """() => {
  const doc = document.documentElement;
  const box = el => { const r = el.getBoundingClientRect(); return {top: r.top, bottom: r.bottom, h: r.height}; };
  const addr = document.getElementById('addr');
  const film = document.querySelector('.film video');
  const vertical = document.querySelector('.vertical video');
  const shown = [...document.querySelectorAll('video')].filter(v => v.getClientRects().length)
    .sort((a, b) => a.getBoundingClientRect().top - b.getBoundingClientRect().top);
  return {
    firstVideo: shown.length ? (shown[0] === vertical ? 'vertical' : shown[0] === film ? 'film' : 'other') : '',
    verticalBox: vertical ? box(vertical) : null,
    overflow: doc.scrollWidth - doc.clientWidth,
    viewport: window.innerHeight,
    addr: addr ? addr.textContent.trim() : '',
    addrBox: addr ? box(addr) : null,
    filmBox: film ? box(film) : null,
    videos: [...document.querySelectorAll('video')].map(v => ({ready: v.readyState, w: v.videoWidth, src: v.currentSrc})),
    lang: doc.lang,
    shareBtn: (() => { const b = document.querySelector('[data-share] .share-btn');
      return b && b.getClientRects().length ? Object.assign(box(b), {w: b.getBoundingClientRect().width}) : null; })(),
    shareUrl: (document.querySelector('[data-share]') || {getAttribute: () => ''}).getAttribute('data-url') || '',
    links: [...document.querySelectorAll('a[href]')].map(a => a.href),
    shownLinks: [...document.querySelectorAll('a[href]')].filter(a => a.getClientRects().length).map(a => a.href),
    youtubeLinks: [...document.querySelectorAll('a[href]')].filter(a => a.hostname === 'youtu.be' || a.hostname === 'youtube.com' || a.hostname.endsWith('.youtube.com')).length,
    watch: (() => { const a = document.querySelector('a[data-watch]');
      if (!a || !a.getClientRects().length) return null;
      const s = getComputedStyle(a);
      return Object.assign(box(a), {w: a.getBoundingClientRect().width, href: a.getAttribute('href'),
                                    color: s.color, bg: s.backgroundColor}); })(),
    bannerNote: (() => { const n = document.querySelector('.banner-note');
      return n && n.getClientRects().length ? n.textContent.trim() : ''; })(),
  };
}"""

# Share with a stand-in navigator.share that records what the page asked to share.
SHARE_WITH_SHEET = """() => {
  window.__shared = null;
  Object.defineProperty(navigator, 'share', {configurable: true, writable: true,
    value: d => { window.__shared = d; return Promise.resolve(); }});
}"""
# No share sheet: the button must open the panel instead.
SHARE_WITHOUT_SHEET = """() => {
  Object.defineProperty(navigator, 'share', {configurable: true, writable: true, value: undefined});
}"""


def load_config():
    with open(os.path.join(ROOT, "config", "site.json"), encoding="utf-8") as f:
        return json.load(f)


def wait_videos(page, timeout_ms):
    page.evaluate("() => document.querySelectorAll('video[preload=none]').forEach(v => { v.preload = 'metadata'; v.load(); })")
    page.wait_for_function("() => [...document.querySelectorAll('video')].every(v => v.readyState >= 1)",
                           timeout=timeout_ms)


def visible_share(box, viewport):
    """Share of a box's height inside the first screen (0 when it starts below it)."""
    if not box or box["h"] <= 0:
        return 0.0
    return max(0.0, min(box["bottom"], viewport) - max(box["top"], 0)) / box["h"]


def first_screen_problems(p, mode, min_visible):
    """Problems with what the first screen shows: mode 'iphone' and 'phone' want the 9:16 film first, 'desktop' the 16:9."""
    problems = []
    if mode == "iphone" and (not p["addrBox"] or p["addrBox"]["bottom"] > p["viewport"]):
        problems.append("prize address is below the first screen")
    if mode in ("iphone", "phone"):
        if p["firstVideo"] != "vertical":
            problems.append(f"first video on a phone is {p['firstVideo'] or 'missing'}, not the 9:16 film")
        share = visible_share(p["verticalBox"], p["viewport"])
        if share < min_visible:
            problems.append(f"only {share:.0%} of the 9:16 player is on the first screen")
    elif mode == "desktop":
        if not p["filmBox"] or p["filmBox"]["top"] + p["filmBox"]["h"] / 2 > p["viewport"]:
            problems.append("film is not on the first screen")
    return problems


def expected_links(cfg):
    """Links the page must carry: the fee transaction (decision 0013)."""
    links = cfg.get("links", {})
    return [links[m["href"]] for m in cfg.get("link_marks", {}).values() if isinstance(m, dict) and m.get("href") in links]


def page_problems(p, cfg, canonical, touch_px=44):
    """Problems with the Share button, linked figures and the banner note in a probe result."""
    problems = []
    share_on = cfg.get("share", {}).get("enabled")
    if share_on and not p.get("shareBtn"):
        problems.append("Share button is not shown")
    elif share_on:
        if min(p["shareBtn"]["h"], p["shareBtn"]["w"]) < touch_px:
            problems.append(f"Share button is smaller than {touch_px} px")
        if p.get("shareUrl") != canonical:
            problems.append(f"Share address is {p.get('shareUrl') or 'missing'}, not {canonical}")
    for href in expected_links(cfg):
        if href not in p.get("links", []):
            problems.append(f"no link to {href}")
    if not p.get("bannerNote"):
        problems.append("banner note is not shown")
    return problems


def rgb(css):
    """'rgb(1, 2, 3)' or 'rgba(1, 2, 3, a)' to ((r, g, b), alpha)."""
    parts = [float(x) for x in css[css.index("(") + 1:css.index(")")].replace("/", ",").replace(" ", ",").split(",") if x]
    return tuple(int(round(v)) for v in parts[:3]), (parts[3] if len(parts) > 3 else 1.0)


def watch_problems(p, cfg, mode, touch_px=44, contrast_min=4.5):
    """Problems with the Watch on YouTube link and the repository link (decision 0017)."""
    problems = []
    url = cfg.get("youtube_url", "")
    w = p.get("watch")
    if url and not w:
        problems.append("Watch on YouTube link is not shown")
    elif url:
        if p.get("youtubeLinks") != 1:
            problems.append(f"{p.get('youtubeLinks')} YouTube links, not one")
        if w["href"] != url:
            problems.append(f"Watch on YouTube points to {w['href']}, not {url}")
        if min(w["h"], w["w"]) < touch_px:
            problems.append(f"Watch on YouTube link is smaller than {touch_px} px")
        (fg, _), (bg, alpha) = rgb(w["color"]), rgb(w["bg"])
        ratio = contrast("#%02x%02x%02x" % fg, [bg]) if alpha == 1 else 0.0
        if ratio < contrast_min:
            problems.append(f"Watch on YouTube text contrast {ratio} is under {contrast_min}")
        if mode == "iphone" and w["bottom"] > p["viewport"]:
            problems.append("Watch on YouTube link is below the first screen")
    elif p.get("youtubeLinks"):
        problems.append("a YouTube link is shown while youtube_url is empty")
    repo = cfg.get("repo_url", "").rstrip("/")
    if repo and cfg.get("banner", {}).get("repo_check") == "on" and not any(
            h.rstrip("/") == repo for h in p.get("shownLinks", [])):
        problems.append("repository link is not shown although repo_check is on")
    return problems


def share_problems(page, cfg, canonical):
    """Click Share with and without a share sheet; returns problems."""
    if not cfg.get("share", {}).get("enabled"):
        return []
    problems = []
    try:
        page.evaluate(SHARE_WITH_SHEET)
        page.click("[data-share] .share-btn", timeout=5000)
        page.wait_for_function("() => window.__shared !== null", timeout=5000)
        shared = page.evaluate("() => window.__shared")
        if shared.get("url") != canonical:
            problems.append(f"share sheet got {shared.get('url')}, not {canonical}")
    except Exception:
        problems.append("Share button did not open the share sheet")
    try:
        page.evaluate(SHARE_WITHOUT_SHEET)
        page.click("[data-share] .share-btn", timeout=5000)
        page.wait_for_selector("[data-share] .share-panel:not([hidden])", timeout=5000)
        page.click("[data-share] .share-copy", timeout=5000)
        page.wait_for_function("() => document.querySelector('[data-share] .share-status').textContent.trim() !== ''",
                               timeout=5000)
    except Exception:
        problems.append("without a share sheet the panel or Copy link gave no feedback")
    if page.evaluate("() => document.documentElement.scrollWidth - document.documentElement.clientWidth") > 0:
        problems.append("page scrolls sideways with the Share panel open")
    return problems


def check_page(page, url, name, cfg, out, mode, canonical):
    errors = []
    page.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.goto(url, wait_until="load")
    page.wait_for_timeout(300)
    p = page.evaluate(PROBE)
    page.screenshot(path=os.path.join(out, f"{name}.png"))
    problems = first_screen_problems(p, mode, cfg["check"]["min_visible"])
    print(f"{name}: first video {p['firstVideo']}, 9:16 top {p['verticalBox']['top']:.0f} height "
          f"{p['verticalBox']['h']:.0f} of viewport {p['viewport']}" if p["verticalBox"] else f"{name}: no 9:16 player")
    try:
        wait_videos(page, 20000)
    except Exception:  # reported below from the probe
        pass
    p = dict(p, videos=page.evaluate(PROBE)["videos"])
    page.screenshot(path=os.path.join(out, f"{name}-full.png"), full_page=True)
    if p["overflow"] > 0:
        problems.append(f"page scrolls sideways by {p['overflow']} px")
    if p["addr"] != cfg["prize_address"]:
        problems.append("prize address missing or different")
    for v in p["videos"]:
        if v["ready"] < 1 or not v["w"]:
            problems.append(f"video did not load: {v['src']}")
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
    problems += page_problems(p, cfg, canonical)
    problems += watch_problems(p, cfg, mode)
    problems += share_problems(page, cfg, canonical)
    page.screenshot(path=os.path.join(out, f"{name}-share.png"))
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
            ("webkit-iphone13", webkit, dict(pw.devices["iPhone 13"]), "iphone"),
            ("chromium-desktop", chromium, {"viewport": {"width": 1366, "height": 900}}, "desktop"),
            ("chromium-320", chromium, {"viewport": {"width": 320, "height": 640}, "is_mobile": True,
                                        "has_touch": True, "device_scale_factor": 2}, "phone"),
        ]
        for label, browser, opts, mode in runs:
            ctx = browser.new_context(**opts)
            for lang in cfg["languages"]:
                name = f"{label}-{lang['code']}"
                page = ctx.new_page()
                problems = check_page(page, base + lang["path"], name, cfg, out, mode,
                                      "https://" + cfg["domain"] + lang["path"])
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
