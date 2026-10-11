# -*- coding: utf-8 -*-
"""
Automatický překlad prázdných buněk EN / DE přes DeepL.

• Ruční text v tabulce má vždy přednost – sem se dostanou jen prázdné buňky.
• Překlady se ukládají do data/cache/preklady.json (mezi běhy je drží
  GitHub Actions cache), takže se každý text překládá jen jednou.
• Odborné pojmy drží slovníček generator/glosar.csv (cs;en;de).
• Bez proměnné DEEPL_API_KEY se nic nepřekládá a použije se čeština.
"""

import os, re, json, csv, hashlib, urllib.request, urllib.parse
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
failed = []  # texty, které se nepodařilo přeložit
last_error = ""


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
    # slovníček je součástí klíče: po jeho změně se texty přeloží znovu
    return lang + ":v5:" + _glossary_hash() + ":" + hashlib.sha1(text.encode("utf-8")).hexdigest()


# Výrazy, které DeepL nesmí měnit (značka, firma, tituly se jmény).
KEEP = re.compile(r"Kvalita\s?M[íi]sta|IN—FORM—ARCHITEKTI(?:,\s*s\.r\.o\.)?|ČKA"
                  r"|(?:(?:Ing|Mgr|Bc|MgA|Dr|doc|prof)\.(?:\s+et)?\s+)+(?:arch\.\s+)?"
                  r"[A-ZÁČĎÉĚÍŇÓŘŠŤÚŮÝŽ][\wÀ-ž]+\s+[A-ZÁČĎÉĚÍŇÓŘŠŤÚŮÝŽ][\wÀ-ž]+")


_terms = None


def _glossary_terms():
    """Slovníček jako {jazyk: [(cz, překlad), …]} – delší výrazy první."""
    global _terms
    if _terms is None:
        _terms = {"en": [], "de": []}
        if GLOSAR.exists():
            with GLOSAR.open(encoding="utf-8") as f:
                for r in csv.reader(f, delimiter=";"):
                    if len(r) >= 3 and r[0].strip() and not r[0].startswith("#"):
                        for lang, col in (("en", 1), ("de", 2)):
                            if r[col].strip():
                                _terms[lang].append((r[0].strip(), r[col].strip()))
        for v in _terms.values():
            v.sort(key=lambda x: -len(x[0]))
    return _terms


def _glossary_hash():
    return hashlib.sha1(GLOSAR.read_bytes()).hexdigest()[:8] if GLOSAR.exists() else "0"


def _wrap(text, lang):
    """Chráněné výrazy a pojmy ze slovníčku se do DeepL pošlou už hotové v <k>…</k>."""
    t = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    t = KEEP.sub(lambda m: "<k>" + m.group(0) + "</k>", t)
    for cz, target in _glossary_terms()[lang]:
        if cz == target:
            continue
        parts = re.split(r"(<k>.*?</k>)", t)
        t = "".join(p if p.startswith("<k>") else
                    re.sub(r"(?<!\w)" + re.escape(cz) + r"(?!\w)", "<k>" + target + "</k>", p)
                    for p in parts)
    return t


def _fix_spaces(out, src, lang):
    """Chráněný výraz nebo pojem ze slovníčku nesmí být slepený s okolním slovem."""
    terms = {m.group(0) for m in KEEP.finditer(src)}
    terms |= {t for cz, t in _glossary_terms()[lang] if cz in src}
    for t in sorted(terms, key=len, reverse=True):
        out = re.sub(r"(?<=[^\W\d_])" + re.escape(t), " " + t, out)
        out = re.sub(re.escape(t) + r"(?=[^\W\d_])", t + " ", out)
    return out


def _unwrap(text):
    # chráněný výraz je vždy samostatné slovo – DeepL občas „sní“ mezeru u značky
    text = re.sub(r"(\w)<k>", r"\1 <k>", text)
    text = re.sub(r"</k>(\w)", r"</k> \1", text)
    t = re.sub(r"[„“\"‚‘']?<k>(.*?)</k>[“”\"‘’']?", r"\1", text, flags=re.S)
    return t.replace("&lt;", "<").replace("&gt;", ">").replace("&amp;", "&")


def _request(path, data, method="POST"):
    """Volání DeepL s opakováním při přetížení (429) a chybách serveru."""
    import time, urllib.error
    for attempt in range(5):
        try:
            return _request_once(path, data, method)
        except urllib.error.HTTPError as ex:
            if ex.code in (429, 500, 502, 503, 504, 529) and attempt < 4:
                time.sleep(2 ** attempt * 2)
                continue
            raise
        except (urllib.error.URLError, TimeoutError):
            if attempt < 4:
                time.sleep(2 ** attempt * 2)
                continue
            raise


def _request_once(path, data, method="POST"):
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
            payload = {"text": [_wrap(texts[i], lang) for i in chunk], "source_lang": "CS",
                       "target_lang": TARGET[lang], "preserve_formatting": True,
                       "tag_handling": "xml", "ignore_tags": ["k"],
                       "outline_detection": False}
            gid = _glossary_id(lang)
            if gid:
                payload["glossary_id"] = gid
            try:
                res = _request("/v2/translate", payload)
            except Exception as ex:
                global last_error
                last_error = str(ex)
                print(f"! DeepL: překlad do {lang} selhal ({ex}) — použije se čeština.")
                failed.extend(texts[i] for i in chunk)
                if getattr(ex, "code", 0) in (403, 456):   # špatný klíč / vyčerpaná kvóta
                    _disabled = True
                    break
                continue
            for i, tr in zip(chunk, res.get("translations", [])):
                out[i] = _fix_spaces(_unwrap(tr.get("text", "")), texts[i], lang)
                cache[_key(texts[i], lang)] = out[i]
    for i, t in enumerate(texts):
        if t and out[i]:
            used.append((lang, t, out[i]))
    return out
