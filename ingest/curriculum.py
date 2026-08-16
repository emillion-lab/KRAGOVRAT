#!/usr/bin/env python3
"""
Възстановява реалната структура на канала от заглавията.

Каналът е азбучно подреден — Библиотекари IX стои преди V, а лекция от
2022 се смесва с 2024. Тук се вади датата, града, модула, номера на частта
и се групира в курсове, подредени както са били преподавани.

  python curriculum.py            # -> ingest/curriculum.json + отчет
"""
import json, re
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SRC = ROOT / "sources.json"
OUT = ROOT / "curriculum.json"

ROMAN = {"I": 1, "II": 2, "III": 3, "IV": 4, "V": 5, "VI": 6, "VII": 7, "VIII": 8,
         "IX": 9, "X": 10, "XI": 11, "XII": 12, "XIII": 13, "XIV": 14, "XV": 15}
WORDS = {"ПЪРВА": 1, "ВТОРА": 2, "ТРЕТА": 3, "ЧЕТВЪРТА": 4, "ПЕТА": 5,
         "ШЕСТА": 6, "СЕДМА": 7, "ОСМА": 8}
MODULE_WORDS = {"ПЪРВИ": 1, "ВТОРИ": 2, "ТРЕТИ": 3}

CITIES = ["Варна", "Пловдив", "София", "Бургас", "Хасково", "Разград", "Ямбол",
          "Шумен", "Търново", "Стара Загора", "Сливен", "Карандила", "Лондон",
          "Ботевград", "Етрополе"]

RE_DATE = re.compile(r"(\d{1,2})[.\-/](\d{1,2})[.\-/](\d{2,4})")
RE_ROMAN = re.compile(r"(?:Част|ЧАСТ|Part)\s+([IVX]+)\b")
RE_ROMAN_BARE = re.compile(r"\s([IVX]+)\s+-\s")           # "Библиотекари IX - ОБУЧЕНИЕ"
RE_NUM = re.compile(r"(?:Част|ЧАСТ|Part)\s*(\d+)\b|\b(\d+)\s*(?:ЧАСТ|Част)\b")
RE_WORD = re.compile(r"\b(" + "|".join(WORDS) + r")\s+ЧАСТ\b", re.IGNORECASE)
RE_MODULE_W = re.compile(r"\b(" + "|".join(MODULE_WORDS) + r")\s+МОДУЛ\b", re.IGNORECASE)
RE_MODULE_N = re.compile(r"\bМодул\s*(\d+)\b", re.IGNORECASE)
RE_EPISODE = re.compile(r"\bЕпизод\s*(\d+)\b|\bE(\d{2})\b|\bЕ(\d{2})\b", re.IGNORECASE)
RE_TRACK = re.compile(r"^(Библиотекари|Пазители(?:\s+на\s+Словото)?|Повелители)\b", re.IGNORECASE)


def norm_date(t):
    m = RE_DATE.search(t)
    if not m:
        return None
    d, mo, y = m.groups()
    y = int(y)
    if y < 100:
        y += 2000
    if not (2015 <= y <= 2027 and 1 <= int(mo) <= 12 and 1 <= int(d) <= 31):
        return None
    return f"{y}-{int(mo):02d}-{int(d):02d}"


def part_of(t):
    m = RE_WORD.search(t)
    if m:
        return WORDS[m.group(1).upper()]
    m = RE_ROMAN.search(t)
    if m and m.group(1) in ROMAN:
        return ROMAN[m.group(1)]
    m = RE_ROMAN_BARE.search(t)
    if m and m.group(1) in ROMAN:
        return ROMAN[m.group(1)]
    m = RE_NUM.search(t)
    if m:
        return int(m.group(1) or m.group(2))
    m = RE_EPISODE.search(t)
    if m:
        return int(next(g for g in m.groups() if g))
    return None


def module_of(t):
    m = RE_MODULE_W.search(t)
    if m:
        return MODULE_WORDS[m.group(1).upper()]
    m = RE_MODULE_N.search(t)
    if m:
        return int(m.group(1))
    return None


def city_of(t):
    low = t.lower()
    for c in CITIES:
        if c.lower() in low:
            return c
    return None


def series_key(t):
    """Маха всичко променливо -> остава името на курса."""
    s = t
    s = RE_DATE.sub(" ", s)
    s = re.sub(r"\(?ПЪЛЕН ЗАПИС\)?|ЗАПИС|#\w+", " ", s)
    s = RE_WORD.sub(" ", s)
    s = RE_ROMAN.sub(" ", s)
    s = RE_NUM.sub(" ", s)
    s = RE_EPISODE.sub(" ", s)
    s = RE_MODULE_W.sub(" ", s)
    s = RE_MODULE_N.sub(" ", s)
    s = RE_TRACK.sub(" ", s)
    # голите римски числа ("Библиотекари IX - ОБУЧЕНИЕ") иначе правят 14 курса от един
    s = " ".join("" if w.strip("-–—") in ROMAN else w for w in s.split())
    for c in CITIES:
        s = re.sub(c, " ", s, flags=re.IGNORECASE)
    s = re.sub(r"[-–—|,.]+", " ", s)
    s = re.sub(r"\b(г|ЛЕКЦИЯ|Лекция|ОБУЧЕНИЕ|Обучение|ЦЯЛА|Част|ЧАСТ)\b", " ", s)
    s = re.sub(r"\s+", " ", s).strip().lower()
    return s or "разни"


def main():
    rows = json.loads(SRC.read_text(encoding="utf-8"))
    rows = [r for r in rows if not r["vid"].startswith("ЗАМЕНИ")]

    for r in rows:
        t = r["title"]
        r["date"] = r.get("date") or norm_date(t)
        r["module"] = module_of(t)
        r["city"] = city_of(t)
        r["part"] = part_of(t)
        m = RE_TRACK.match(t)
        r["track"] = m.group(1).split()[0].capitalize() if m else None
        r["series"] = series_key(t)

    groups = {}
    for r in rows:
        key = (r["series"], r["module"], r["city"], r["track"], r["date"])
        groups.setdefault(key, []).append(r)

    courses = []
    for (series, module, city, track, date), items in groups.items():
        items.sort(key=lambda x: (x["part"] is None, x["part"] or 0, x["title"]))
        courses.append({
            "series": series, "module": module, "city": city,
            "track": track, "date": date,
            "parts": len(items),
            "hours": round(sum(i["duration"] or 0 for i in items) / 3600, 2),
            "videos": [{"vid": i["vid"], "part": i["part"], "title": i["title"],
                        "duration": i["duration"]} for i in items],
        })

    courses.sort(key=lambda c: (c["date"] or "9999", -c["hours"]))
    OUT.write_text(json.dumps(courses, ensure_ascii=False, indent=1), encoding="utf-8")

    dated = sum(1 for r in rows if r["date"])
    multi = [c for c in courses if c["parts"] > 1]
    print(f"{len(rows)} видеа, {sum(r['duration'] or 0 for r in rows)/3600:.1f} часа")
    print(f"дати извлечени: {dated}/{len(rows)}")
    print(f"курсове: {len(courses)}, от които многочастни: {len(multi)}\n")
    for c in sorted(multi, key=lambda x: -x["hours"])[:15]:
        tag = " ".join(x for x in [c["track"], c["city"],
                                   f"М{c['module']}" if c["module"] else None,
                                   c["date"]] if x)
        print(f"{c['hours']:6.1f}ч  {c['parts']:2}ч.  {c['series'][:44]:44} {tag}")


if __name__ == "__main__":
    main()
