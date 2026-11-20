"""Banner values for the film page (decision 0015): the new project note, the deck link and the repository links.

`config/site.json` `banner` holds the event start, the first commit (sha and UTC date), the repository check and the
deck files per language. The note is `banner.note` from the language file with {first_commit} (day month year) and
{event_start} (day month) filled from config, month names from `banner.months`. Repository links (the repository and
its first commit) follow `repo_check`: "on" shows them, "off" leaves them out, "auto" writes them hidden and
site/repo.js shows them only when the public GitHub API lists the repository (a private repository is not listed).
"""
import html
from datetime import datetime

CHECKS = ("auto", "on", "off")


class BannerError(Exception):
    pass


def parse_utc(text):
    return datetime.fromisoformat(text.replace("Z", "+00:00"))


def problems(cfg):
    """What is wrong with config `banner`, as short sentences."""
    b = cfg.get("banner")
    if not isinstance(b, dict):
        return ["config has no banner"]
    out = []
    try:
        start, first = parse_utc(b["event_start_utc"]), parse_utc(b["first_commit"]["date_utc"])
        if first <= start:
            out.append(f"first commit {b['first_commit']['date_utc']} is not after the event start {b['event_start_utc']}")
    except (KeyError, TypeError, ValueError) as e:
        out.append(f"banner dates unreadable ({e})")
    sha = str(b.get("first_commit", {}).get("sha", ""))
    if len(sha) != 40 or any(c not in "0123456789abcdef" for c in sha):
        out.append("banner.first_commit.sha is not a full commit id")
    if b.get("repo_check") not in CHECKS:
        out.append(f"banner.repo_check must be one of {', '.join(CHECKS)}")
    if b.get("repo_check") == "auto" and not str(b.get("repo_api", "")).startswith("https://api.github.com/"):
        out.append("banner.repo_api must be a https://api.github.com/ URL when repo_check is auto")
    if not isinstance(b.get("deck"), dict):
        out.append("banner.deck must map each language to a PDF path or an empty string")
    return out


def date_text(text, months, with_year):
    d = parse_utc(text)
    names = months.split()
    if len(names) != 12:
        raise BannerError("banner.months must name twelve months")
    return f"{d.day} {names[d.month - 1]}" + (f" {d.year}" if with_year else "")


def note(cfg, strings):
    b = cfg["banner"]
    template = strings["banner.note"]
    for slot in ("{first_commit}", "{event_start}"):
        if slot not in template:
            raise BannerError(f"banner.note has no {slot}")
    return template.replace("{first_commit}", date_text(b["first_commit"]["date_utc"], strings["banner.months"], True)) \
                   .replace("{event_start}", date_text(b["event_start_utc"], strings["banner.months"], False))


def repo_shown(cfg):
    return bool(cfg.get("repo_url")) and cfg["banner"]["repo_check"] != "off"


def gate_attr(cfg):
    """Attributes on an element that only shows once the repository is public."""
    return " data-repo-link hidden" if cfg["banner"]["repo_check"] == "auto" else ""


def api_attr(cfg):
    if cfg["banner"]["repo_check"] != "auto" or not cfg.get("repo_url"):
        return ""
    name = "/".join(cfg["repo_url"].rstrip("/").split("/")[-2:])
    return (f' data-repo-api="{html.escape(cfg["banner"]["repo_api"], quote=True)}"'
            f' data-repo-name="{html.escape(name, quote=True)}"')


def links(cfg, strings, deck_url):
    """Raw HTML for the banner link row: the deck when there is one, then the repository and the first commit."""
    items = []
    if deck_url:
        items.append(f'<a href="{html.escape(deck_url, quote=True)}" type="application/pdf">'
                     f'{html.escape(strings["banner.deck"])}</a>')
    gated = []
    if repo_shown(cfg):
        repo = cfg["repo_url"].rstrip("/")
        sha = cfg["banner"]["first_commit"]["sha"]
        for href, label in ((repo, strings["banner.repo"]),
                            (f"{repo}/commit/{sha}", strings["banner.first_commit"].replace("{sha}", sha[:7]))):
            gated.append(f'<a href="{html.escape(href, quote=True)}" rel="noopener"{gate_attr(cfg)}>{html.escape(label)}</a>')
    if not items and not gated:
        return ""
    row_attr = gate_attr(cfg) if not items else ""
    return f'<p class="banner-links"{row_attr}>' + " ".join(items + gated) + "</p>"
