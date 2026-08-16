#!/usr/bin/env python3
"""
YouTube авто-субтитри (.bg.vtt)  ->  сегменти по схемата.

Без GPU, без whisper. По-ниско качество: няма пунктуация, няма говорители,
термините често се чуват грешно. Но дава търсим текст и точен таймкод още днес.
Whisper минава после, само по важните лекции.

  python from_captions.py            # work/subs/*.vtt -> data/segments/
"""
import json, re, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SUBS = ROOT.parent / "work" / "subs"
OUT = ROOT.parent / "data" / "segments"
SOURCES = ROOT / "sources.json"

MIN_CHARS, MAX_CHARS = 400, 700
TS = re.compile(r"(\d+):(\d\d):(\d\d)\.(\d+)\s*-->\s*(\d+):(\d\d):(\d\d)\.")
TAG = re.compile(r"<[^>]+>")


def secs(h, m, s, ms="0"):
    return int(h) * 3600 + int(m) * 60 + int(s) + int(ms[:3] or 0) / 1000


def parse_vtt(path):
    """Авто-субтитрите се презаписват — всеки блок повтаря предишния ред.
    Дедупликацията е задължителна, иначе текстът се утроява."""
    cues, seen, start = [], set(), None
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        m = TS.match(line)
        if m:
            start = secs(*m.groups()[:4])
            continue
        if start is None or not line.strip() or line.startswith(("WEBVTT", "Kind:", "Language:")):
            continue
        text = TAG.sub("", line).strip()
        if not text or text in seen:
            continue
        seen.add(text)
        if len(seen) > 400:
            seen = set(list(seen)[-200:])
        cues.append((start, text))
    return cues


def build(vid, cues, src):
    out, buf, size = [], [], 0
    for start, text in cues:
        if not buf:
            buf_start = start
        buf.append(text)
        size += len(text)
        if size >= MAX_CHARS:
            out.append(make(vid, buf_start, start, " ".join(buf), src))
            buf, size = [], 0
    if size >= MIN_CHARS:
        out.append(make(vid, buf_start, cues[-1][0], " ".join(buf), src))
    return out


def make(vid, t0, t1, text, src):
    return {
        "id": f"yt:{vid}@{int(t0)}",
        "source": {
            "type": src.get("type", "lecture"),
            "title": src.get("title", ""),
            "url": f"https://youtu.be/{vid}?t={int(t0)}",
            "date": src.get("date"),
            "publisher": src.get("publisher", "Истинска Земя"),
        },
        "t_start": round(t0, 1), "t_end": round(t1, 1), "page": None,
        "speaker": "unknown",           # авто-субтитрите не различават говорители
        "speaker_guessed": True,
        "text": re.sub(r"\s+", " ", text).strip(),
        "terms": [], "claim_type": None,
        "asr": {"model": "youtube-auto", "conf": None,
                "low_conf": True,        # целият слой е за проверка по дефиниция
                "human_checked": False},
        "has_diagram": False, "frame": None, "dup_of": None,
    }


def main():
    if not SUBS.exists():
        sys.exit("Няма work/subs/. Пусни ingest workflow-а с mode=captions.")
    meta = {s["vid"]: s for s in json.loads(SOURCES.read_text(encoding="utf-8"))
            if not s["vid"].startswith("ЗАМЕНИ")}
    OUT.mkdir(parents=True, exist_ok=True)
    total = 0
    for vtt in sorted(SUBS.glob("*.vtt")):
        vid = vtt.name.split(".")[0]
        cues = parse_vtt(vtt)
        if not cues:
            print(f"! {vid}: празни субтитри")
            continue
        segs = build(vid, cues, meta.get(vid, {}))
        (OUT / f"{vid}.json").write_text(
            json.dumps(segs, ensure_ascii=False, indent=1), encoding="utf-8")
        total += len(segs)
        print(f"{vid}: {len(segs)} сегмента, {int(cues[-1][0] / 60)} мин")
    print(f"\nОбщо {total} сегмента. Всички са low_conf — това е черновият слой.")


if __name__ == "__main__":
    main()
