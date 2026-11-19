"""Links the page build adds to its copy (decision 0013): marked words that link to a source, and the share targets.

A copy text may wrap words in [[name]]...[[/name]]; config/site.json link_marks.<name> names the link (links.<href>),
the screen reader label (a lang key) and the copy keys allowed to carry the mark. The copy is HTML escaped before the
marks are swapped for the link, so a `<` in a language file never becomes markup.
"""
import html
import re
from urllib.parse import quote

MARK = re.compile(r"\[\[(/?)([a-z_]+)\]\]")


def marks(cfg):
    return {k: v for k, v in cfg.get("link_marks", {}).items() if not k.startswith("_")}


def fact_hashes(facts_text, fact_id):
    """64 hex ids (transaction ids) written in the docs/FACTS.md row of fact_id."""
    for line in facts_text.splitlines():
        if line.startswith(f"| `{fact_id}` |"):
            return set(re.findall(r"\b[0-9a-f]{64}\b", line))
    return set()


def mark_problems(flat_by_lang, cfg, facts_text=""):
    """Marks in keys that may not carry them, unknown or unbalanced marks, links or labels that are missing, and a
    link whose `fact` row names a transaction id the link does not carry."""
    problems, known = [], marks(cfg)
    for name, m in known.items():
        href = cfg.get("links", {}).get(m["href"], "")
        if not href:
            problems.append(f"link mark {name} has no links.{m['href']}")
        if m.get("fact"):
            ids = fact_hashes(facts_text, m["fact"])
            if not ids or not any(i in href for i in ids):
                problems.append(f"link mark {name} does not point at the transaction in fact {m['fact']}")
    for code, flat in flat_by_lang.items():
        for name, m in known.items():
            if not flat.get(m["label"], "").strip():
                problems.append(f"link mark {name} label {m['label']} missing in {code}")
        for key, text in flat.items():
            found = MARK.findall(str(text))
            if not found:
                continue
            names = {n for _, n in found}
            for n in names - set(known):
                problems.append(f"{code} {key} uses unknown link mark {n}")
            for n in names & set(known):
                if key not in known[n]["keys"]:
                    problems.append(f"{code} {key} may not carry link mark {n}")
                if [s for s, x in found if x == n] != ["", "/"]:
                    problems.append(f"{code} {key} link mark {n} is not one open and one close")
    return problems


def link_marked(escaped, cfg, strings):
    """Swap the marks in already escaped copy for <a> elements."""
    known = marks(cfg)

    def swap(m):
        closing, name = m.group(1), m.group(2)
        if closing:
            return f'<span class="sr"> {html.escape(strings[known[name]["label"]])}</span></a>'
        href = html.escape(cfg["links"][known[name]["href"]], quote=True)
        return f'<a class="src" href="{href}" rel="noopener">'
    return MARK.sub(lambda m: swap(m) if m.group(2) in known else m.group(0), escaped)


def plain(text):
    """Copy text with the marks removed (for attributes and meta tags)."""
    return MARK.sub("", text)


def share_links(cfg, strings, url):
    """HTML list items for the share panel: one link per config target, {url} and {text} URL encoded."""
    text = plain(strings["share.text"])
    items = []
    for t in cfg["share"]["targets"]:
        href = t["url"].replace("{url}", quote(url, safe="")).replace("{text}", quote(text, safe=""))
        label = strings[f"share.targets.{t['id']}"]
        items.append(f'<li><a class="share-to" href="{html.escape(href, quote=True)}" rel="noopener" target="_blank" '
                     f'data-target="{html.escape(t["id"], quote=True)}">{html.escape(label)}</a></li>')
    return "\n".join(items)
