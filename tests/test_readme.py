"""Judge block checks: both READMEs must carry the proof links that config/site.json holds."""
import json
import os
import re
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
READMES = {"README.md": "## For judges", "README.ms.md": "## Untuk juri"}
MAX_ROWS = 9


def read(rel):
    with open(os.path.join(ROOT, rel), encoding="utf-8") as f:
        return f.read()


def site():
    return json.loads(read("config/site.json"))


def judge_block(text, heading):
    """Text from the judge heading to the next level two heading, or None."""
    start = text.find(heading + "\n")
    if start < 0:
        return None
    rest = text[start + len(heading) + 1:]
    nxt = re.search(r"^## ", rest, re.M)
    return rest[:nxt.start()] if nxt else rest


def table_rows(block):
    """Body rows of the first Markdown table in a block."""
    rows = [ln for ln in block.splitlines() if ln.startswith("|")]
    return rows[2:]


def problems(text, heading, cfg, exists=os.path.exists):
    """Every missing proof in one README; empty list = the README is complete."""
    out = []
    block = judge_block(text, heading)
    if block is None:
        return [f"no {heading!r} section"]
    rows = table_rows(block)
    if not rows or len(rows) > MAX_ROWS:
        out.append(f"judge table has {len(rows)} rows, want 1..{MAX_ROWS}")
    sha = cfg["banner"]["first_commit"]["sha"]
    wanted = {
        "youtube_url": cfg["youtube_url"],
        "links.fee_tx": cfg["links"]["fee_tx"],
        "prize_address": cfg["prize_address"],
        "first commit link": f"{cfg['repo_url']}/commit/{sha}",
        "first commit short sha": sha[:7],
    }
    for name, value in wanted.items():
        if not value:
            out.append(f"{name} is empty in config/site.json")
        elif value not in block:
            out.append(f"judge block lacks {name}: {value}")
    if cfg["youtube_url"] and text.count(cfg["youtube_url"]) < 2:
        out.append("no Watch section with the YouTube link outside the judge block")
    for target in re.findall(r"\]\(([^)#:]+\.pdf)\)", block):
        if not exists(os.path.join(ROOT, target)):
            out.append(f"linked deck missing: {target}")
    for lang, path in cfg["banner"].get("deck", {}).items():
        if path and path not in block:
            out.append(f"judge block lacks the {lang} deck: {path}")
    return out


class ReadmeJudgeBlockTest(unittest.TestCase):
    def test_both_readmes_carry_every_proof(self):
        cfg = site()
        for rel, heading in READMES.items():
            with self.subTest(readme=rel):
                self.assertEqual(problems(read(rel), heading, cfg), [])

    def test_judge_block_comes_before_the_first_section(self):
        for rel, heading in READMES.items():
            text = read(rel)
            first = re.search(r"^## ", text, re.M)
            with self.subTest(readme=rel):
                self.assertEqual(text[first.start():].split("\n", 1)[0], heading)

    def test_detects_a_missing_txid_and_a_changed_config(self):
        cfg = site()
        text = read("README.ms.md")
        broken = text.replace(cfg["links"]["fee_tx"], "https://example.invalid/tx")
        self.assertTrue(any("fee_tx" in p for p in problems(broken, READMES["README.ms.md"], cfg)))
        moved = json.loads(json.dumps(cfg))
        moved["youtube_url"] = "https://youtu.be/changed"
        self.assertTrue(any("youtube_url" in p for p in problems(text, READMES["README.ms.md"], moved)))

    def test_detects_a_missing_deck_file_and_a_long_table(self):
        cfg = site()
        text = read("README.md")
        self.assertTrue(any("deck missing" in p
                            for p in problems(text, READMES["README.md"], cfg, exists=lambda p: False)))
        extra = "| Extra | row |\n" * MAX_ROWS
        long_text = text.replace("| Tests |", extra + "| Tests |", 1)
        self.assertTrue(any("rows" in p for p in problems(long_text, READMES["README.md"], cfg)))

    def test_missing_heading_is_reported(self):
        self.assertEqual(problems("# Title\n", "## For judges", site()), ["no '## For judges' section"])


if __name__ == "__main__":
    unittest.main()
