"""Build the full generation prompt for a shot from config/shots.json: shot action + shared style + shared exclusions."""
import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SHOTS = os.path.join(ROOT, "config", "shots.json")


def load_shots(path=SHOTS):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def shot(data, shot_id):
    for s in data["shots"]:
        if s["id"] == shot_id:
            return s
    raise KeyError(f"shot {shot_id!r} is not in config/shots.json")


def build(data, shot_id):
    s = shot(data, shot_id)
    return "\n".join([s["prompt"].strip(), "[Style] " + data["style"].strip(), "[Exclude] " + data["exclude"].strip()])
