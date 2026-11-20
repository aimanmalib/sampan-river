"""Build the static film page (decision 0009).

python3 tools/site.py --media DIR --out DIR

Reads config/site.json, site/lang/*.json, site/index.html, site/*.css|js and docs/MEASURED.md. Writes one
HTML page per language, the videos, their posters, robots.txt and healthz into an empty output folder. A video
whose sha256 differs from its row in docs/MEASURED.md stops the build: the page only ever serves measured files.
"""
import argparse
import hashlib
import html
import json
import os
import re
import shutil
import sys
from urllib.parse import urlparse

try:
    from tools import banner, page_links
except ImportError:  # run as python3 tools/site.py
    import banner
    import page_links

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OG_LOCALES = {"en": "en_GB", "ms": "ms_MY"}


class BuildError(Exception):
    pass


def load_json(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def flatten(obj, prefix=""):
    """Nested copy file to {'a.b': text}."""
    out = {}
    for key, value in obj.items():
        name = prefix + key
        if isinstance(value, dict):
            out.update(flatten(value, name + "."))
        else:
            out[name] = value
    return out


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def measured_shas(text):
    """{version: sha256} from every markdown table in MEASURED.md that has `version` and `sha256` columns."""
    out, header = {}, None
    for line in text.splitlines():
        if not line.startswith("|"):
            header = None
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if header is None:
            header = cells
            continue
        if set(cells) <= {"---", ""} or "version" not in header or "sha256" not in header:
            continue
        row = dict(zip(header, cells))
        if re.fullmatch(r"[0-9a-f]{64}", row.get("sha256", "")):
            out[row["version"]] = row["sha256"]
    return out


def fact_ids(text):
    return set(re.findall(r"^\|\s*`([a-z0-9-]+)`\s*\|", text, re.M))


def check_copy(langs, cfg, facts_text):
    """Problems with the page copy: key parity, banned words, claims without a fact."""
    problems = []
    flat = {code: flatten(copy) for code, copy in langs.items()}
    keys = [set(f) for f in flat.values()]
    if any(k != keys[0] for k in keys):
        problems.append("language files do not have the same keys")
    known = fact_ids(facts_text)
    for key, ids in cfg.get("copy_facts", {}).items():
        for code, f in flat.items():
            if key not in f:
                problems.append(f"copy_facts key {key} missing in {code}")
        for fid in ids:
            if fid not in known:
                problems.append(f"fact {fid} for {key} is not in docs/FACTS.md")
    for code, f in flat.items():
        for key, text in f.items():
            low = text.lower()
            for word in cfg.get("banned_words", []):
                if word.lower() in low:
                    problems.append(f"{code} {key} uses '{word}'")
            if "\u2014" in text:
                problems.append(f"{code} {key} uses an em dash")
            claims = [w for w in cfg.get("claim_words", []) if w.lower() in low]
            if claims and key not in cfg.get("copy_facts", {}):
                problems.append(f"{code} {key} states a claim ({claims[0]}) with no fact in copy_facts")
    return problems + page_links.mark_problems(flat, cfg, facts_text)


def render(template, strings, values, flags, link=None):
    """`<!--if:x-->...<!--end:x-->` kept only when flags[x]; {{t:key}} copy and {{v:key}} values escaped, {{r:key}} raw.
    `link` turns the link marks in escaped copy into links (page_links.link_marked); without it they are dropped."""
    def block(m):
        name = m.group(1)
        if name not in flags:
            raise BuildError(f"unknown block {name}")
        return m.group(2) if flags[name] else ""
    out = re.sub(r"<!--if:(\w+)-->\n?(.*?)<!--end:\1-->\n?", block, template, flags=re.S)

    def field(m):
        kind, key = m.group(1), m.group(2)
        table = strings if kind == "t" else values
        if key not in table:
            raise BuildError(f"no value for {{{{{kind}:{key}}}}}")
        text = str(table[key])
        if kind == "r":
            return text
        if kind == "v":
            return html.escape(text, quote=True)
        escaped = html.escape(text, quote=True)
        return link(escaped) if link else page_links.plain(escaped)
    out = re.sub(r"\{\{([tvr]):([\w.]+)\}\}", field, out)
    if "{{" in out:
        raise BuildError("unfilled placeholder left in the page")
    return out


def short_hash(data):
    return hashlib.sha256(data).hexdigest()[:10]


def place(src, out_dir, sub, stem=None, expected=None):
    """Copy src to out_dir/sub/stem.<sha8><ext> (or out_dir/sub/<sha8>/<file name> when stem is None) and return its
    URL path; refuse when the sha256 is not `expected`. The hash in the path lets the files be cached as immutable."""
    if not os.path.isfile(src):
        raise BuildError(f"missing file {src}")
    digest = sha256_file(src)
    if expected is not None and digest != expected:
        raise BuildError(f"{os.path.basename(src)} sha256 {digest[:8]} is not the measured {expected[:8]}")
    if stem is None:
        name = f"{digest[:8]}/{os.path.basename(src)}"
    else:
        name = f"{stem}.{digest[:8]}{os.path.splitext(src)[1]}"
    os.makedirs(os.path.dirname(os.path.join(out_dir, sub, name)), exist_ok=True)
    dest = os.path.join(out_dir, sub, name)
    shutil.copyfile(src, dest)
    if expected is not None and sha256_file(dest) != expected:
        raise BuildError(f"copy of {name} changed on the way")
    return f"/{sub}/{name}"


def jpeg_size(path):
    """(width, height) of a baseline or progressive JPEG, read from its SOF marker."""
    with open(path, "rb") as f:
        data = f.read()
    i = 2
    while i < len(data) - 9:
        if data[i] != 0xFF:
            i += 1
            continue
        marker, length = data[i + 1], int.from_bytes(data[i + 2:i + 4], "big")
        if marker in (0xC0, 0xC1, 0xC2):
            return int.from_bytes(data[i + 7:i + 9], "big"), int.from_bytes(data[i + 5:i + 7], "big")
        i += 2 + length
    raise BuildError(f"no JPEG size in {path}")


def build(root, media_dir, out_dir):
    cfg = load_json(os.path.join(root, "config", "site.json"))
    langs = {l["code"]: load_json(os.path.join(root, "site", "lang", l["code"] + ".json")) for l in cfg["languages"]}
    with open(os.path.join(root, "docs", "FACTS.md"), encoding="utf-8") as f:
        problems = check_copy(langs, cfg, f.read())
    problems += banner.problems(cfg)
    if problems:
        raise BuildError("; ".join(problems))
    if os.path.exists(out_dir) and os.listdir(out_dir):
        raise BuildError(f"output folder {out_dir} is not empty")
    os.makedirs(out_dir, exist_ok=True)
    with open(os.path.join(root, cfg["measured"]), encoding="utf-8") as f:
        shas = measured_shas(f.read())

    values = {"address": cfg["prize_address"], "copy_reset_ms": cfg["copy_reset_ms"],
              "wallets_url": cfg["links"]["wallets"], "wallets_host": urlparse(cfg["links"]["wallets"]).netloc,
              "paytaca_url": cfg["links"]["paytaca"], "selene_url": cfg["links"]["selene"],
              "event_url": cfg["links"]["event"], "youtube_url": cfg["youtube_url"], "repo_url": cfg["repo_url"]}
    silent = cfg.get("silent_suffix", "")
    for name, v in cfg["videos"].items():
        if silent and (v["version"].endswith(silent) or silent in v["file"]):
            raise BuildError(f"video {name} is the silent copy {v['version']}; the page serves the narrated files")
        if v["version"] not in shas:
            raise BuildError(f"version {v['version']} has no sha256 in {cfg['measured']}")
        # Served under its own file name so the page and a saved download carry the name in the submission.
        values[name + "_src"] = place(os.path.join(media_dir, v["file"]), out_dir, "media", expected=shas[v["version"]])
        if v.get("poster"):
            values[name + "_poster"] = place(os.path.join(root, v["poster"]), out_dir, "img", f"poster-{name}")
        values[name + "_width"], values[name + "_height"] = v["width"], v["height"]
    og_src = os.path.join(root, cfg["og_image"])
    if os.path.getsize(og_src) > cfg["og_image_max_bytes"]:
        raise BuildError(f"{cfg['og_image']} is larger than {cfg['og_image_max_bytes']} bytes")
    base = f"https://{cfg['domain']}"
    values["og_image"] = base + place(og_src, out_dir, "img", "og")
    values["og_width"], values["og_height"] = jpeg_size(og_src)
    if cfg.get("og_image_portrait", True) and values["og_height"] <= values["og_width"]:
        raise BuildError(f"{cfg['og_image']} is not vertical; previews crop it from a portrait image (decision 0014)")
    values["twitter_image"] = base + place(os.path.join(root, cfg["twitter_image"]), out_dir, "img", "twitter")
    values["og_video"] = base + values["vertical_src"]

    for asset in ("style.css", "copy.js", "share.js", "repo.js"):
        with open(os.path.join(root, "site", asset), "rb") as f:
            data = f.read()
        with open(os.path.join(out_dir, asset), "wb") as f:
            f.write(data)
        values[asset.split(".")[0] + "_v"] = short_hash(data)

    with open(os.path.join(root, "site", "index.html"), encoding="utf-8") as f:
        template = f.read()
    flags = {"youtube": bool(cfg["youtube_url"]), "repo": banner.repo_shown(cfg),
             "repo_check": bool(banner.api_attr(cfg)), "share": bool(cfg.get("share", {}).get("enabled"))}
    values["repo_gate"], values["repo_api"] = banner.gate_attr(cfg), banner.api_attr(cfg)
    alternates = "\n".join(f'<link rel="alternate" hreflang="{l["html_lang"]}" href="{base}{l["path"]}">'
                           for l in cfg["languages"])
    default = next(l for l in cfg["languages"] if l["code"] == cfg["default_language"])
    alternates += f'\n<link rel="alternate" hreflang="x-default" href="{base}{default["path"]}">'
    pages = []
    for i, lang in enumerate(cfg["languages"]):
        other = cfg["languages"][(i + 1) % len(cfg["languages"])]
        page_values = dict(values, html_lang=lang["html_lang"], canonical=base + lang["path"], alternates=alternates,
                           other_path=other["path"], other_lang=other["html_lang"],
                           og_locale=OG_LOCALES.get(lang["code"], lang["code"]))
        strings = flatten(langs[lang["code"]])
        deck = cfg["banner"]["deck"].get(lang["code"], "")
        deck_url = place(os.path.join(root, deck), out_dir, "deck") if deck else ""
        try:
            page_values["banner_note"] = banner.note(cfg, strings)
        except banner.BannerError as e:
            raise BuildError(str(e))
        page_values["banner_links"] = banner.links(cfg, strings, deck_url)
        if flags["share"]:
            page_values["share_links"] = page_links.share_links(cfg, strings, page_values["canonical"])
            page_values["share_text"] = page_links.plain(strings["share.text"])
        page = render(template, strings, page_values, flags,
                      link=lambda text: page_links.link_marked(text, cfg, strings))
        folder = os.path.join(out_dir, lang["path"].strip("/"))
        os.makedirs(folder, exist_ok=True)
        with open(os.path.join(folder, "index.html"), "w", encoding="utf-8") as f:
            f.write(page)
        pages.append(lang["path"])
    with open(os.path.join(out_dir, "robots.txt"), "w") as f:
        f.write("User-agent: *\nAllow: /\n")
    with open(os.path.join(out_dir, "healthz"), "w") as f:
        f.write("ok\n")
    return {"pages": pages, "videos": {k: values[k + "_src"] for k in cfg["videos"]}}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--media", required=True, help="folder holding the measured video files")
    ap.add_argument("--out", required=True, help="empty output folder")
    ap.add_argument("--root", default=ROOT, help="project folder (default: this repository)")
    args = ap.parse_args(argv)
    try:
        result = build(args.root, args.media, args.out)
    except BuildError as e:
        print(f"site build stopped: {e}", file=sys.stderr)
        return 1
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
