"""The slide deck (decision 0016): five 16:9 slides per language, printed to PDF with Chromium.

`config/site.json` `deck` names the template, the output pattern, the stamp file, the frames and the limits. The text is
the language file (`deck.*`, plus the page's own `hero.title`, `ai.*` and `banner.*` sentences) filled into
site/deck/deck.html with the same renderer as the page, so the deck says what the page says. Pictures are committed film
frames, embedded as data URIs; nothing is generated.

    python3 tools/deck.py --shots <folder>   print both PDFs, one PNG per slide into <folder>, write the stamp
    python3 tools/deck.py --check            offline: what is wrong with the committed PDFs (exit 1 when anything)

The stamp holds, per language, the sha256 of the HTML that was printed and of the PDF that came out. The check renders
the HTML again from the current inputs: a PDF printed from older text, or a PDF swapped by hand, no longer matches.
"""
import argparse
import base64
import hashlib
import html
import os
import re
import sys

try:
    from tools import banner, site
except ImportError:  # run as a script
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from tools import banner, site

ROOT = site.ROOT


def load(root):
    cfg = site.load_json(os.path.join(root, "config", "site.json"))
    langs = {l["code"]: site.load_json(os.path.join(root, "site", "lang", f"{l['code']}.json")) for l in cfg["languages"]}
    return cfg, langs


def tokens(root):
    """The page's :root custom properties, so the slides use the same palette and type."""
    with open(os.path.join(root, "site", "style.css"), encoding="utf-8") as f:
        m = re.search(r":root\s*\{.*?\}", f.read(), re.S)
    if not m:
        raise site.BuildError("site/style.css has no :root block")
    return m.group(0)


def data_uri(path):
    with open(path, "rb") as f:
        return "data:image/jpeg;base64," + base64.b64encode(f.read()).decode("ascii")


def render(root, cfg, langs, code):
    """The deck HTML for one language."""
    d = cfg["deck"]
    lang = next(l for l in cfg["languages"] if l["code"] == code)
    strings = site.flatten(langs[code])
    fee_url = cfg["links"]["fee_tx"]
    values = {
        "html_lang": lang["html_lang"],
        "tokens": tokens(root),
        "domain": cfg["domain"] + (lang["path"] if lang["path"] != "/" else ""),
        "site_url": f"https://{cfg['domain']}{lang['path']}",
        "address": cfg["prize_address"],
        "fee_url": fee_url,
        "txid": fee_url.rstrip("/").rsplit("/", 1)[-1],
    }
    try:
        values["banner_note"] = banner.note(cfg, strings)
    except banner.BannerError as e:
        raise site.BuildError(str(e))
    for name, rel in d["frames"].items():
        values["img_" + name] = data_uri(os.path.join(root, rel))
    with open(os.path.join(root, d["template"]), encoding="utf-8") as f:
        template = f.read()
    return site.render(template, strings, values, {})


def fingerprint(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def out_path(cfg, code):
    return cfg["deck"]["out"].replace("{lang}", code)


def read_stamp(path):
    """{name: sha256} from lines `<sha256>  <name>`."""
    out = {}
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            for line in f:
                parts = line.split()
                if len(parts) == 2:
                    out[parts[1]] = parts[0]
    return out


def slides(page_html):
    """Each <section class="slide"> in order, as its inner HTML."""
    return re.findall(r'<section class="slide"[^>]*>(.*?)</section>', page_html, re.S)


def visible_text(fragment):
    return html.unescape(re.sub(r"<[^>]+>", " ", re.sub(r"<style.*?</style>", " ", fragment, flags=re.S)))


def problems(root=ROOT):
    """What is wrong with the committed deck, without a browser."""
    cfg, langs = load(root)
    d = cfg["deck"]
    stamp = read_stamp(os.path.join(root, d["stamp"]))
    out = []
    for lang in cfg["languages"]:
        code, pdf = lang["code"], out_path(cfg, lang["code"])
        try:
            page = render(root, cfg, langs, code)
        except (site.BuildError, OSError, KeyError) as e:
            out.append(f"{code}: deck does not render ({e})")
            continue
        parts = slides(page)
        if len(parts) != d["slides"]:
            out.append(f"{code}: {len(parts)} slides, config says {d['slides']}")
        elif cfg["prize_address"] not in visible_text(parts[d["address_slide"] - 1]):
            out.append(f"{code}: slide {d['address_slide']} does not show the prize address")
        low = visible_text(page).lower()
        out += [f"{code}: deck uses '{w}'" for w in cfg.get("banned_words", []) if w.lower() in low]
        if stamp.get(f"text-{code}") != fingerprint(page):
            out.append(f"{code}: {pdf} was printed from other text; run tools/deck.py again")
        path = os.path.join(root, pdf)
        if not os.path.exists(path):
            out.append(f"{code}: {pdf} is missing")
            continue
        with open(path, "rb") as f:
            data = f.read()
        if not data.startswith(b"%PDF"):
            out.append(f"{code}: {pdf} is not a PDF")
        if len(data) > d["max_bytes"]:
            out.append(f"{code}: {pdf} is {len(data)} bytes, over {d['max_bytes']}")
        if stamp.get(pdf) != hashlib.sha256(data).hexdigest():
            out.append(f"{code}: {pdf} is not the file the stamp records")
    return out


LAYOUT_JS = """() => [...document.querySelectorAll('.slide')].flatMap((s, i) => {
  const box = s.getBoundingClientRect(), foot = s.querySelector('footer').getBoundingClientRect().top;
  const bad = [];
  if (s.scrollWidth > s.clientWidth || s.scrollHeight > s.clientHeight) bad.push(`slide ${i + 1} overflows`);
  for (const el of s.querySelectorAll('h1, h2, p, li, img, figcaption')) {
    if (el.closest('footer')) continue;
    const r = el.getBoundingClientRect();
    if (r.bottom > foot || r.right > box.right) bad.push(`slide ${i + 1}: ${el.tagName} runs into the footer or edge`);
  }
  return bad;
})"""


def print_all(root, shots):
    """Print every language, screenshot each slide, then write the stamp. Stops before writing on a crowded slide."""
    from playwright.sync_api import sync_playwright
    cfg, langs = load(root)
    d = cfg["deck"]
    os.makedirs(shots, exist_ok=True)
    pages, stamp = {}, []
    with sync_playwright() as p:
        browser = p.chromium.launch()
        try:
            tab = browser.new_page(viewport={"width": d["width"], "height": d["height"]})
            for lang in cfg["languages"]:
                code = lang["code"]
                page = render(root, cfg, langs, code)
                tab.set_content(page, wait_until="load")
                bad = tab.evaluate(LAYOUT_JS)
                count = tab.locator(".slide").count()
                if bad or count != d["slides"]:
                    raise site.BuildError(f"{code}: {count} slides; " + "; ".join(bad))
                for i in range(count):
                    tab.locator(".slide").nth(i).screenshot(path=os.path.join(shots, f"deck-{code}-{i + 1}.png"))
                pages[code] = tab.pdf(width=f"{d['width']}px", height=f"{d['height']}px", print_background=True,
                                      prefer_css_page_size=True)
                stamp.append(f"{fingerprint(page)}  text-{code}")
        finally:
            browser.close()
    for code, data in pages.items():
        if len(data) > d["max_bytes"]:
            raise site.BuildError(f"{code}: PDF is {len(data)} bytes, over {d['max_bytes']}")
        with open(os.path.join(root, out_path(cfg, code)), "wb") as f:
            f.write(data)
        stamp.append(f"{hashlib.sha256(data).hexdigest()}  {out_path(cfg, code)}")
        print(f"{out_path(cfg, code)}: {len(data)} bytes")
    with open(os.path.join(root, d["stamp"]), "w", encoding="utf-8") as f:
        f.write("\n".join(stamp) + "\n")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--shots", help="folder for one PNG per slide (printing needs it)")
    ap.add_argument("--check", action="store_true", help="only check the committed PDFs")
    ap.add_argument("--root", default=ROOT)
    args = ap.parse_args(argv)
    if not args.check:
        if not args.shots:
            ap.error("--shots is required to print")
        try:
            print_all(args.root, args.shots)
        except site.BuildError as e:
            print(f"deck stopped: {e}", file=sys.stderr)
            return 1
    found = problems(args.root)
    for line in found:
        print(line, file=sys.stderr)
    return 1 if found else 0


if __name__ == "__main__":
    sys.exit(main())
