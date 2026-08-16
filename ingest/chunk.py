#!/usr/bin/env python3
"""
work/raw/*.json  →  data/segments/{vid}.json

Реже по говорител и по изречение, никога по средата на дума.
Маркира ниска увереност за ръчен преглед.

  python chunk.py
  python chunk.py --report        # само статистика, без запис
"""
import argparse, json, re, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
RAW = ROOT.parent / "work" / "raw"
OUT = ROOT.parent / "data" / "segments"
SPEAKERS = ROOT / "speakers.json"

MIN_CHARS, MAX_CHARS = 400, 700
LOW_CONF = 0.75
SENT_END = re.compile(r"(?<=[.!?…])\s+")


def load_speaker_map():
    """{vid: {"SPEAKER_00": "sirakov", ...}} — ръчно, след като чуеш проба."""
    if SPEAKERS.exists():
        return json.loads(SPEAKERS.read_text(encoding="utf-8"))
    return {}


def guess_main_speaker(segments):
    """Резервен вариант: най-многото говорене е негово. Вярно за лекции,
    рисковано за интервюта — затова се записва speaker_guessed: true."""
    talk = {}
    for s in segments:
        spk = s.get("speaker", "unknown")
        talk[spk] = talk.get(spk, 0) + (s.get("end", 0) - s.get("start", 0))
    return max(talk, key=talk.get) if talk else None


def seg_conf(s):
    words = s.get("words") or []
    scores = [w["score"] for w in words if isinstance(w.get("score"), (int, float))]
    return round(sum(scores) / len(scores), 3) if scores else None


def flush(buf, src, asr_model, guessed):
    text = " ".join(b["text"].strip() for b in buf).strip()
    text = re.sub(r"\s+", " ", text)
    if len(text) < 120:
        return None
    start = buf[0]["start"]
    confs = [c for c in (b["conf"] for b in buf) if c is not None]
    conf = round(sum(confs) / len(confs), 3) if confs else None
    vid = src["vid"]
    return {
        "id": f"yt:{vid}@{int(start)}",
        "source": {
            "type": src.get("type", "lecture"),
            "title": src.get("title", ""),
            "url": f"https://youtu.be/{vid}?t={int(start)}",
            "date": src.get("date"),
            "publisher": src.get("publisher"),
        },
        "t_start": round(start, 1),
        "t_end": round(buf[-1]["end"], 1),
        "page": None,
        "speaker": buf[0]["role"],
        "speaker_guessed": guessed,
        "text": text,
        "terms": [],
        "claim_type": None,
        "asr": {
            "model": asr_model,
            "conf": conf,
            "low_conf": conf is not None and conf < LOW_CONF,
            "human_checked": False,
        },
        "has_diagram": False,
        "frame": None,
        "dup_of": None,
    }


def process(path, smap):
    raw = json.loads(path.read_text(encoding="utf-8"))
    src, asr_model = raw["source"], raw.get("asr_model", "?")
    vid = src["vid"]

    mapping = smap.get(vid, {})
    guessed = False
    if not mapping:
        main = guess_main_speaker(raw["segments"])
        if main:
            mapping = {main: "sirakov"}
            guessed = True

    out, buf, size = [], [], 0
    for s in raw["segments"]:
        text = (s.get("text") or "").strip()
        if not text:
            continue
        role = mapping.get(s.get("speaker"), "unknown" if mapping else "sirakov")
        item = {"text": text, "start": s.get("start", 0), "end": s.get("end", 0),
                "conf": seg_conf(s), "role": role}

        # смяна на говорителя реже безусловно — иначе чужди думи влизат в негов сегмент
        if buf and buf[0]["role"] != role:
            rec = flush(buf, src, asr_model, guessed)
            if rec:
                out.append(rec)
            buf, size = [], 0

        buf.append(item)
        size += len(text)

        if size >= MAX_CHARS or (size >= MIN_CHARS and SENT_END.search(text[-2:] + " ")):
            rec = flush(buf, src, asr_model, guessed)
            if rec:
                out.append(rec)
            buf, size = [], 0

    if buf:
        rec = flush(buf, src, asr_model, guessed)
        if rec:
            out.append(rec)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--report", action="store_true")
    args = ap.parse_args()

    if not RAW.exists():
        sys.exit("Няма work/raw/. Пусни transcribe.py първо.")
    smap = load_speaker_map()
    OUT.mkdir(parents=True, exist_ok=True)

    total = low = guessed_files = 0
    for path in sorted(RAW.glob("*.json")):
        segs = process(path, smap)
        his = [s for s in segs if s["speaker"] == "sirakov"]
        n_low = sum(1 for s in his if s["asr"]["low_conf"])
        if his and his[0]["speaker_guessed"]:
            guessed_files += 1
        total += len(his)
        low += n_low
        print(f"{path.stem}: {len(his)} негови / {len(segs)} общо, {n_low} за преглед"
              + ("  [говорителят е ПОГАДАН]" if his and his[0]["speaker_guessed"] else ""))
        if not args.report:
            (OUT / path.name).write_text(
                json.dumps(segs, ensure_ascii=False, indent=1), encoding="utf-8")

    print(f"\nОбщо {total} негови сегмента, {low} с ниска увереност "
          f"({low / total * 100:.0f}%)" if total else "\nНищо.")
    if guessed_files:
        print(f"! {guessed_files} файла без speakers.json. Чуй по 30 сек от всеки "
              f"и запиши мапинга, преди да индексираш.")


if __name__ == "__main__":
    main()
