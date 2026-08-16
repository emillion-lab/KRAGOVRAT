#!/usr/bin/env python3
"""
Сваля аудиото и го транскрибира с диаризация.
Иска GPU. На Colab (T4): ~5 мин за час аудио.

  pip install -U yt-dlp whisperx
  python transcribe.py --hf-token hf_xxx

Изход: work/raw/{vid}.json  — whisperX сегменти със speaker етикети.
Идемпотентно: вече обработени видеа се прескачат.
"""
import argparse, json, os, subprocess, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
WORK = ROOT.parent / "work"
AUDIO, RAW = WORK / "audio", WORK / "raw"

# Whisper халюцинира по време на музика, джингъли и тишина — измисля цели
# изречения на чист български. VAD-ът е единствената реална защита.
ASR_OPTS = {
    "language": "bg",
    "vad_onset": 0.500,
    "vad_offset": 0.363,
}


def fetch_audio(src):
    out = AUDIO / f"{src['vid']}.m4a"
    if out.exists():
        return out
    subprocess.run([
        "yt-dlp", "-x", "--audio-format", "m4a", "--audio-quality", "0",
        "-o", str(out), src["url"],
    ], check=True)
    return out


def transcribe(audio, model, align_cache, diarizer, device):
    import whisperx

    result = model.transcribe(str(audio), language=ASR_OPTS["language"], batch_size=8)

    lang = result.get("language", "bg")
    if lang not in align_cache:
        align_cache[lang] = whisperx.load_align_model(language_code=lang, device=device)
    align_model, meta = align_cache[lang]
    result = whisperx.align(
        result["segments"], align_model, meta, str(audio), device,
        return_char_alignments=False,
    )

    if diarizer is not None:
        result = whisperx.assign_word_speakers(diarizer(str(audio)), result)

    return result


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sources", default=str(ROOT / "sources.json"))
    ap.add_argument("--model", default="large-v3")
    ap.add_argument("--hf-token", default=os.environ.get("HF_TOKEN"),
                    help="за диаризацията (pyannote). Без него интервютата са неизползваеми.")
    ap.add_argument("--device", default="cuda")
    ap.add_argument("--only", help="само този vid")
    args = ap.parse_args()

    import whisperx

    sources = json.loads(Path(args.sources).read_text(encoding="utf-8"))
    sources = [s for s in sources if not s["vid"].startswith("ЗАМЕНИ")]
    if args.only:
        sources = [s for s in sources if s["vid"] == args.only]
    if not sources:
        sys.exit("Няма източници. Попълни ingest/sources.json.")

    AUDIO.mkdir(parents=True, exist_ok=True)
    RAW.mkdir(parents=True, exist_ok=True)

    compute = "float16" if args.device == "cuda" else "int8"
    model = whisperx.load_model(args.model, args.device, compute_type=compute, language="bg")

    diarizer = None
    if args.hf_token:
        diarizer = whisperx.DiarizationPipeline(use_auth_token=args.hf_token, device=args.device)
    else:
        print("! Без --hf-token: няма диаризация. За интервюта това значи, "
              "че думите на водещия ще се смесят с неговите.", file=sys.stderr)

    align_cache = {}
    for src in sources:
        out = RAW / f"{src['vid']}.json"
        if out.exists():
            print(f"= {src['vid']} вече е готово")
            continue
        print(f"→ {src['vid']}  {src.get('title', '')}")
        try:
            audio = fetch_audio(src)
            result = transcribe(audio, model, align_cache, diarizer, args.device)
        except Exception as e:
            print(f"! {src['vid']} падна: {e}", file=sys.stderr)
            continue
        out.write_text(json.dumps(
            {"source": src, "asr_model": args.model, "segments": result["segments"]},
            ensure_ascii=False, indent=1,
        ), encoding="utf-8")
        print(f"✓ {out.name}  ({len(result['segments'])} сегмента)")


if __name__ == "__main__":
    main()
