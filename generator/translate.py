# -*- coding: utf-8 -*-
"""
Automatický překlad prázdných buněk EN / DE přes DeepL.

• Ruční text v tabulce má vždy přednost – sem se dostanou jen prázdné buňky.
• Překlady se ukládají do data/cache/preklady.json (mezi běhy je drží
  GitHub Actions cache), takže se každý text překládá jen jednou.
• Odborné pojmy drží slovníček generator/glosar.csv (cs;en;de).
• Bez proměnné DEEPL_API_KEY se nic nepřekládá a použije se čeština.
"""

import os, json, csv, hashlib, urllib.request, urllib.parse
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CACHE = ROOT / "data" / "cache" / "preklady.json"
GLOSAR = Path(__file__).resolve().parent / "glosar.csv"
KEY = os.environ.get("DEEPL_API_KEY", "").strip()
HOST = "https://api-free.deepl.com" if KEY.endswith(":fx") else "https://api.deepl.com"
TARGET = {"en": "EN-GB", "de": "DE"}

_cache = None
_glossary = {}
_disabled = False
used = []   # [(lang, cz, preklad)] – pro kontrolní stránku


def _load():
    global _cache
    if _cache is None:
        try:
            _cache = json.loads(CACHE.read_text(encoding="utf-8"))
        except Exception:
            _cache = {}
    return _cache


def save():
    if _cache is not None:
        CACHE.parent.mkdir(parents=True, exist_ok=True)
        CACHE.write_text(json.dumps(_cache, ensure_ascii=False, indent=1, sort_keys=True), encoding="utf-8")


def _key(text, lang):
    return lang + ":" + hashlib.sha1(text.encode("utf-8")).hexdigest()


def _request(path, data, method="POST"):
    body = json.dumps(data).encode("utf-8") if data is not None else None
    req = urllib.request.Request(HOST + path, data=body, method=method, headers={
        "Authorization": f"DeepL-Auth-Key {KEY}", "Content-Type": "application/json",
        "User-Agent": "kvalitamista-build/1.0"})
    with urllib.request.urlopen(req, timeout=60) as r:
        raw = r.read().decode("utf-8")
        return json.loads(raw) if raw else {}


def _glossary_id(lang):
    """Vytvoří (jednou za běh) slovníček pro daný jazyk. Selže-li, překládá se bez něj."""
    if lang in _glossary:
        return _glossary[lang]
    _glossary[lang] = None
    if not GLOSAR.exists():
        return None
    col = {"en": 1, "de": 2}[lang]
    rows = []
    with GLOSAR.open(encoding="utf-8") as f:
        for r in csv.reader(f, delimiter=";"):
            if len(r) > col and r[0].strip() and not r[0].startswith("#") and r[col].strip():
                rows.append(f"{r[0].strip()}\t{r[col].strip()}")
    if not rows:
        return None
    try:
        res = _request("/v2/glossaries", {"name": f"kvalitamista-{lang}", "source_lang": "cs",
                                           "target_lang": lang, "entries": "\n".join(rows),
                                           "entries_format": "tsv"})
        _glossary[lang] = res.get("glossary_id")
    except Exception as ex:
        print(f"· slovníček DeepL ({lang}) se nepodařilo vytvořit, překládám bez něj: {ex}")
    return _glossary[lang]


def cleanup():
    for lang, gid in _glossary.items():
        if gid:
            try:
                _request(f"/v2/glossaries/{gid}", None, method="DELETE")
            except Exception:
                pass


def translate_many(texts, lang):
    """Přeloží seznam českých textů; vrátí seznam (None tam, kde překlad není)."""
    global _disabled
    cache = _load()
    out = [cache.get(_key(t, lang)) if t else "" for t in texts]
    missing = [i for i, t in enumerate(texts) if t and out[i] is None]
    if missing and KEY and not _disabled:
        for start in range(0, len(missing), 40):
            chunk = missing[start:start + 40]
            payload = {"text": [texts[i] for i in chunk], "source_lang": "CS",
                       "target_lang": TARGET[lang], "preserve_formatting": True}
            gid = _glossary_id(lang)
            if gid:
                payload["glossary_id"] = gid
            try:
                res = _request("/v2/translate", payload)
            except Exception as ex:
                print(f"! DeepL: překlad do {lang} selhal ({ex}) — použije se čeština.")
                _disabled = True
                break
            for i, tr in zip(chunk, res.get("translations", [])):
                out[i] = tr.get("text", "")
                cache[_key(texts[i], lang)] = out[i]
    for i, t in enumerate(texts):
        if t and out[i]:
            used.append((lang, t, out[i]))
    return out
