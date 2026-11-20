"""The film page build (decision 0009): measured videos only, both languages, sourced copy, deploy files (offline).

Videos and posters are small fixture files with their own sha256, never the real media.
"""
import hashlib
import json
import os
import re
import shutil
import subprocess
import tempfile
import unittest

from tools import site

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ADDRESS = "bitcoincash:zplrydnf2z4pj4z9rv7uhmwsuxyrm8hj7uken87e7q"
# Smallest JPEG shape the size reader accepts: SOI, then a SOF0 segment for 64 x 36.
FAKE_JPEG = b"\xff\xd8\xff\xc0\x00\x11\x08\x00\x24\x00\x40\x03" + b"\x00" * 9 + b"\xff\xd9"
# The same shape for 36 x 64: the share image must be portrait (decision 0014).
FAKE_PORTRAIT_JPEG = b"\xff\xd8\xff\xc0\x00\x11\x08\x00\x40\x00\x24\x03" + b"\x00" * 9 + b"\xff\xd9"
VIDEOS = {"9x16": b"fixture vertical bytes", "16x9": b"fixture film bytes", "short-9x16": b"fixture short bytes"}


def sha(data):
    return hashlib.sha256(data).hexdigest()


def measured(shas):
    rows = "\n".join(f"| {v} | 1 | 1 | 1.0 | yes | -14 | -1.5 | 0 | 1/1 | {s} |" for v, s in shas.items())
    return ("# Measured\n\n| version | width | height | duration_s | audio | lufs_i | true_peak_db | whisper_words | "
            "caption_cues | sha256 |\n|---|---|---|---|---|---|---|---|---|---|\n" + rows + "\n")


class SiteBuildTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="site-test-")
        self.root = os.path.join(self.tmp, "repo")
        shutil.copytree(os.path.join(ROOT, "site"), os.path.join(self.root, "site"))
        os.makedirs(os.path.join(self.root, "config"))
        os.makedirs(os.path.join(self.root, "docs", "frames"))
        shutil.copy(os.path.join(ROOT, "docs", "FACTS.md"), os.path.join(self.root, "docs", "FACTS.md"))
        with open(os.path.join(ROOT, "config", "site.json"), encoding="utf-8") as f:
            self.cfg = json.load(f)
        for rel in {v["poster"] for v in self.cfg["videos"].values() if v.get("poster")} | {self.cfg["twitter_image"]}:
            with open(os.path.join(self.root, rel), "wb") as f:
                f.write(FAKE_JPEG)
        with open(os.path.join(self.root, self.cfg["og_image"]), "wb") as f:
            f.write(FAKE_PORTRAIT_JPEG)
        self.media = os.path.join(self.tmp, "media")
        os.makedirs(self.media)
        for v in self.cfg["videos"].values():
            with open(os.path.join(self.media, v["file"]), "wb") as f:
                f.write(VIDEOS[v["version"]])
        self.write_measured({v: sha(b) for v, b in VIDEOS.items()})
        self.out = os.path.join(self.tmp, "public")

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def write_measured(self, shas):
        with open(os.path.join(self.root, self.cfg["measured"]), "w", encoding="utf-8") as f:
            f.write(measured(shas))

    def write_cfg(self, **changes):
        self.cfg.update(changes)
        with open(os.path.join(self.root, "config", "site.json"), "w", encoding="utf-8") as f:
            json.dump(self.cfg, f)

    def page(self, rel):
        with open(os.path.join(self.out, rel), encoding="utf-8") as f:
            return f.read()

    def test_builds_both_languages_with_address_and_measured_videos(self):
        self.write_cfg()
        result = site.build(self.root, self.media, self.out)
        self.assertEqual(result["pages"], ["/", "/ms/"])
        en, ms = self.page("index.html"), self.page("ms/index.html")
        for html, lang in ((en, "en"), (ms, "ms")):
            self.assertIn(f'<html lang="{lang}">', html)
            self.assertIn(ADDRESS, html)
            self.assertNotIn("{{", html)
            for version, data in VIDEOS.items():
                path = self.video_path(version)
                self.assertIn(path, html)
                with open(self.out + path, "rb") as f:
                    self.assertEqual(f.read(), data)
        self.assertIn('href="/ms/"', en)
        self.assertIn('href="/"', ms)
        self.assertIn(f'content="https://{self.cfg["domain"]}/img/og.', en)
        self.assertIn('content="64"', en)
        for name in ("robots.txt", "healthz", "style.css", "copy.js"):
            self.assertTrue(os.path.isfile(os.path.join(self.out, name)), name)

    def video_path(self, version):
        file = next(v["file"] for v in self.cfg["videos"].values() if v["version"] == version)
        return f"/media/{sha(VIDEOS[version])[:8]}/{file}"

    def test_video_sources_keep_the_delivered_file_names(self):
        self.write_cfg()
        site.build(self.root, self.media, self.out)
        for rel in ("index.html", "ms/index.html"):
            html = self.page(rel)
            for v in self.cfg["videos"].values():
                self.assertRegex(html, r'(src|href)="/media/[0-9a-f]{8}/' + re.escape(v["file"]) + '"', rel)

    def test_video_with_a_different_sha_stops_the_build(self):
        self.write_cfg()
        self.write_measured(dict({v: sha(b) for v, b in VIDEOS.items()}, **{"16x9": sha(b"another file")}))
        with self.assertRaisesRegex(site.BuildError, "not the measured"):
            site.build(self.root, self.media, self.out)

    def test_vertical_video_with_a_different_sha_stops_the_build(self):
        self.write_cfg()
        self.write_measured(dict({v: sha(b) for v, b in VIDEOS.items()}, **{"9x16": sha(b"an older render")}))
        with self.assertRaisesRegex(site.BuildError, "sampan-river-9x16.mp4 sha256 .* not the measured"):
            site.build(self.root, self.media, self.out)

    def test_silent_copy_is_refused(self):
        self.cfg["videos"]["vertical"] = dict(self.cfg["videos"]["vertical"], version="9x16-tanpa-suara",
                                              file="sampan-river-9x16-tanpa-suara.mp4")
        self.write_cfg()
        with self.assertRaisesRegex(site.BuildError, "silent copy"):
            site.build(self.root, self.media, self.out)

    def test_vertical_player_comes_first_and_alone_preloads(self):
        self.write_cfg()
        site.build(self.root, self.media, self.out)
        vertical = self.video_path("9x16")
        short = self.video_path("short-9x16")
        for rel in ("index.html", "ms/index.html"):
            html = self.page(rel)
            main = html.split("<main>", 1)[1]
            videos = re.findall(r"<video\b[^>]*>\s*<source src=\"([^\"]+)\"", main)
            self.assertEqual(videos[0], vertical, rel)
            self.assertEqual(len(videos), 2, rel)
            self.assertNotIn(short, videos)
            self.assertIn(f'href="{short}" download', main)
            preloads = re.findall(r'<video\b[^>]*preload="(\w+)"', main)
            self.assertEqual(preloads, ["metadata", "none"], rel)

    def test_wallet_links_and_narration_label_in_both_languages(self):
        self.write_cfg()
        site.build(self.root, self.media, self.out)
        links = self.cfg["links"]
        for rel in ("index.html", "ms/index.html"):
            html = self.page(rel)
            for key in ("paytaca", "selene", "wallets"):
                self.assertIn(f'href="{links[key]}"', html, f"{rel} {key}")
            self.assertRegex(html, r">Paytaca</a>.*>Selene</a>")
            self.assertIn("ElevenLabs", html, rel)

    def test_version_missing_from_measured_stops_the_build(self):
        self.write_cfg()
        self.write_measured({v: sha(b) for v, b in VIDEOS.items() if v != "short-9x16"})
        with self.assertRaisesRegex(site.BuildError, "short-9x16 has no sha256"):
            site.build(self.root, self.media, self.out)

    def test_no_youtube_or_repo_link_until_set(self):
        self.write_cfg(youtube_url="", banner=dict(self.cfg["banner"], repo_check="off"))
        site.build(self.root, self.media, self.out)
        for rel in ("index.html", "ms/index.html"):
            html = self.page(rel).lower()
            self.assertNotIn("youtube.com", html)
            self.assertNotIn("youtu.be", html)
            self.assertNotIn("github.com", html)

    def test_links_appear_when_set(self):
        self.write_cfg(youtube_url="https://youtu.be/fixture", banner=dict(self.cfg["banner"], repo_check="on"))
        site.build(self.root, self.media, self.out)
        html = self.page("index.html")
        self.assertIn('href="https://youtu.be/fixture"', html)
        self.assertIn(f'href="{self.cfg["repo_url"]}"', html)

    def test_output_folder_must_be_empty(self):
        self.write_cfg()
        os.makedirs(self.out)
        open(os.path.join(self.out, "old"), "w").close()
        with self.assertRaisesRegex(site.BuildError, "not empty"):
            site.build(self.root, self.media, self.out)

    def test_large_og_image_stops_the_build(self):
        self.write_cfg(og_image_max_bytes=10)
        with self.assertRaisesRegex(site.BuildError, "larger than"):
            site.build(self.root, self.media, self.out)


class CopyTest(unittest.TestCase):
    def setUp(self):
        with open(os.path.join(ROOT, "config", "site.json"), encoding="utf-8") as f:
            self.cfg = json.load(f)
        self.langs = {}
        for code in ("en", "ms"):
            with open(os.path.join(ROOT, "site", "lang", code + ".json"), encoding="utf-8") as f:
                self.langs[code] = json.load(f)
        with open(os.path.join(ROOT, "docs", "FACTS.md"), encoding="utf-8") as f:
            self.facts = f.read()

    def test_repository_copy_passes(self):
        self.assertEqual(site.check_copy(self.langs, self.cfg, self.facts), [])

    def test_language_files_have_the_same_keys(self):
        self.assertEqual(set(site.flatten(self.langs["en"])), set(site.flatten(self.langs["ms"])))
        del self.langs["ms"]["hero"]["lede"]
        self.assertTrue(any("same keys" in p for p in site.check_copy(self.langs, self.cfg, self.facts)))

    def test_banned_word_is_reported(self):
        self.langs["en"]["facts"]["note"] = "A guaranteed fare."
        self.assertTrue(any("guaranteed" in p for p in site.check_copy(self.langs, self.cfg, self.facts)))

    def test_claim_without_fact_is_reported(self):
        self.langs["en"]["short"]["text"] = "Fees are 219 satoshis."
        self.assertTrue(any("short.text" in p for p in site.check_copy(self.langs, self.cfg, self.facts)))

    def test_unknown_fact_id_is_reported(self):
        self.cfg["copy_facts"]["facts.fee"] = ["no-such-fact"]
        self.assertTrue(any("no-such-fact" in p for p in site.check_copy(self.langs, self.cfg, self.facts)))

    def test_narration_is_declared_in_both_languages(self):
        for code, copy in self.langs.items():
            line = site.flatten(copy)["ai.voice"]
            self.assertIn("ElevenLabs", line, code)
            self.assertIn("AI", line, code)
            self.assertNotIn("no voice", site.flatten(copy)["ai.music"].lower(), code)
            self.assertNotIn("tiada suara", site.flatten(copy)["ai.music"].lower(), code)

    def test_wallet_line_has_its_facts(self):
        self.assertEqual(self.cfg["copy_facts"]["wallet.label"], ["wallet-paytaca", "wallet-selene"])
        for fid in ("wallet-paytaca", "wallet-selene", "wallet-link"):
            self.assertIn(f"| `{fid}` |", self.facts)

    def test_address_in_config_is_the_prize_address(self):
        self.assertEqual(self.cfg["prize_address"], ADDRESS)


class RenderTest(unittest.TestCase):
    def test_escapes_copy_and_drops_off_blocks(self):
        out = site.render("<p>{{t:a}}</p>\n<!--if:x-->\n<i>{{v:b}}</i>\n<!--end:x-->\n{{r:c}}",
                          {"a": "<b>&"}, {"b": "1", "c": "<link>"}, {"x": False})
        self.assertEqual(out, "<p>&lt;b&gt;&amp;</p>\n<link>")

    def test_missing_value_raises(self):
        with self.assertRaises(site.BuildError):
            site.render("{{t:nope}}", {}, {}, {})

    def test_measured_reader_takes_only_full_sha_rows(self):
        text = measured({"16x9": "a" * 64}) + "\n| file | sha256 |\n|---|---|\n| x.wav | " + "b" * 64 + " |\n"
        self.assertEqual(site.measured_shas(text), {"16x9": "a" * 64})


class FirstScreenTest(unittest.TestCase):
    """deploy/check_page.py decisions on a probe result, without a browser."""

    def probe(self, first="vertical", top=200.0, h=480.0, viewport=664):
        return {"firstVideo": first, "viewport": viewport, "addrBox": {"top": 60, "bottom": 140, "h": 80},
                "verticalBox": {"top": top, "bottom": top + h, "h": h},
                "filmBox": {"top": top + h + 40, "bottom": top + h + 260, "h": 220}}

    def setUp(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location("check_page", os.path.join(ROOT, "deploy", "check_page.py"))
        self.cp = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.cp)

    def test_phone_with_vertical_first_and_on_screen_passes(self):
        self.assertEqual(self.cp.first_screen_problems(self.probe(), "iphone", 0.6), [])

    def test_phone_with_film_first_fails(self):
        problems = self.cp.first_screen_problems(self.probe(first="film"), "phone", 0.6)
        self.assertTrue(any("not the 9:16 film" in p for p in problems))

    def test_phone_with_vertical_mostly_below_the_fold_fails(self):
        problems = self.cp.first_screen_problems(self.probe(top=500), "phone", 0.6)
        self.assertTrue(any("of the 9:16 player" in p for p in problems))

    def test_desktop_wants_the_film_on_screen(self):
        self.assertEqual(self.cp.first_screen_problems(self.probe(first="film", top=100, h=300), "desktop", 0.6), [])
        problems = self.cp.first_screen_problems(self.probe(first="film", top=900), "desktop", 0.6)
        self.assertTrue(any("film is not on the first screen" in p for p in problems))

    def test_threshold_comes_from_config(self):
        with open(os.path.join(ROOT, "config", "site.json"), encoding="utf-8") as f:
            self.assertGreater(json.load(f)["check"]["min_visible"], 0)


class PageProblemsTest(unittest.TestCase):
    """deploy/check_page.py Share, linked figure and banner note decisions, without a browser."""

    CFG = {"share": {"enabled": True}, "links": {"fee_tx": "https://explorer.example/tx/abc"},
           "link_marks": {"_note": "x", "fee": {"href": "fee_tx"}}}
    CANON = "https://page.example/ms/"

    def setUp(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location("check_page", os.path.join(ROOT, "deploy", "check_page.py"))
        self.cp = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.cp)

    def probe(self, **kw):
        p = {"shareBtn": {"top": 700, "bottom": 748, "h": 48, "w": 120}, "shareUrl": self.CANON,
             "links": ["https://explorer.example/tx/abc"], "bannerNote": "New project."}
        p.update(kw)
        return p

    def test_complete_page_passes(self):
        self.assertEqual(self.cp.page_problems(self.probe(), self.CFG, self.CANON), [])

    def test_each_missing_part_is_named(self):
        cases = {"Share button is not shown": {"shareBtn": None},
                 "not " + self.CANON: {"shareUrl": "https://page.example/"},
                 "smaller than 44": {"shareBtn": {"top": 0, "bottom": 30, "h": 30, "w": 120}},
                 "no link to https://explorer.example/tx/abc": {"links": []},
                 "banner note": {"bannerNote": ""}}
        for words, change in cases.items():
            problems = self.cp.page_problems(self.probe(**change), self.CFG, self.CANON)
            self.assertTrue(any(words in p for p in problems), (words, problems))

    def test_share_off_in_config_needs_no_button(self):
        cfg = dict(self.CFG, share={"enabled": False})
        self.assertEqual(self.cp.page_problems(self.probe(shareBtn=None), cfg, self.CANON), [])

    def test_the_live_config_names_the_fee_transaction(self):
        with open(os.path.join(ROOT, "config", "site.json"), encoding="utf-8") as f:
            cfg = json.load(f)
        self.assertEqual(self.cp.expected_links(cfg), [cfg["links"]["fee_tx"]])


class DeployFilesTest(unittest.TestCase):
    def read(self, rel):
        with open(os.path.join(ROOT, rel), encoding="utf-8") as f:
            return f.read()

    def test_deploy_script_parses(self):
        subprocess.run(["bash", "-n", os.path.join(ROOT, "deploy", "deploy.sh")], check=True)

    def test_rollback_holder_follows_the_container_name(self):
        # The host keeps the previous image in a stopped container named "<live container>-undur"; a second name
        # would leave two holders and a rollback reading the wrong one.
        script = self.read("deploy/deploy.sh")
        service = re.search(r"^SERVICE=(\S+)$", script, re.M).group(1)
        holder = re.search(r"^HOLDER=(\S+)$", script, re.M).group(1).strip("\"")
        self.assertIn(holder, (service + "-undur", "$SERVICE-undur", "${SERVICE}-undur"))
        self.assertIn("container_name: " + service, self.read("deploy/compose.yaml"))

    def test_headers_live_in_one_block(self):
        conf = self.read("deploy/nginx.conf")
        locations = re.findall(r"^  location [^{]*\{(.*?)\n  \}", conf, re.S | re.M)
        self.assertTrue(locations)
        for body in locations:
            self.assertNotIn("add_header", body)
        for header in ("Content-Security-Policy", "X-Content-Type-Options", "Referrer-Policy"):
            self.assertIn(header, conf)
        self.assertIn("default-src 'self'", conf)

    def test_container_is_limited_and_named_for_the_project(self):
        compose = self.read("deploy/compose.yaml")
        self.assertIn("cpus: 0.5", compose)
        self.assertIn("read_only: true", compose)
        services = compose.split("\nservices:\n", 1)[1].split("\nnetworks:\n", 1)[0]
        names = re.findall(r"^  ([a-z0-9-]+):\n", services, re.M)
        self.assertTrue(names)
        for name in names:
            self.assertTrue(name.startswith("sampan-river"), name)

    def test_image_context_takes_only_the_built_page(self):
        lines = self.read(".dockerignore").split()
        self.assertEqual(lines[lines.index("*"):], ["*", "!public/", "!deploy/nginx.conf"])


if __name__ == "__main__":
    unittest.main()
