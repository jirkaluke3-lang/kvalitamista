#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Sestaví statický web KvalitaMísta do složky site/ z:
  data/*.csv          – obsah z Google tabulky (stáhne fetch.py)
  obrazky/            – fotografie z Google Disku (stáhne fetch.py)
  generator/static/   – styl a písmo

Jazyky: čeština (/), angličtina (/en/), němčina (/de/).
Prázdné buňky EN/DE se přeloží automaticky (translate.py), jinak se použije čeština.
"""

import csv, html, json, os, re, shutil, sys, unicodedata, urllib.parse
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import translate  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
IMG = ROOT / "obrazky"
STATIC = Path(__file__).resolve().parent / "static"
# verze stylu podle obsahu souboru – prohlížeč po každé změně načte nový styl
CSS_VER = __import__("hashlib").md5((STATIC / "styl.css").read_bytes()).hexdigest()[:8]
OUT = ROOT / "site"
SITE_URL = os.environ.get("SITE_URL", "https://kvalitamista.cz").rstrip("/")
LANGS = ["cs", "en", "de"]
COL = {"cs": "cz", "en": "en", "de": "de"}
LANG_LABEL = {"cs": "CZ", "en": "EN", "de": "DE"}
PHOTO_EXT = (".jpg", ".jpeg", ".png", ".webp", ".avif", ".gif")

# Texty, které v tabulce nemusí být (výchozí česká podoba; přeloží se automaticky)
DEFAULTS = {
    "menu_clanky": "Články",
    "menu_label": "Menu",
    "skip": "Přeskočit na obsah",
    "projekt_problem": "Výchozí situace",
    "projekt_reseni": "Řešení",
    "projekt_prinos": "Přínos",
    "projekt_zpet": "Zpět na ukázky z praxe",
    "clanky_stitek": "Články",
    "clanky_nadpis": "Články a inspirace",
    "clanky_zpet": "Všechny články",
    "clanky_autor": "Autor",
    "autor_text": "Jiří Lukeš je architekt a urbanista, autorizovaný architekt ČKA. Pomáhá obcím s analýzou místa, přípravou zadání a výběrem projektanta. Pokud ve své obci řešíte podobnou otázku, rád ji s vámi proberu.",
    "spoluprace_nadpis": "Formy spolupráce",
    "menu_nabidka": "Spolupráce",
    "nabidka_stitek": "Nabídka spolupráce",
    "nabidka_nadpis": "S čím obcím pomáháme",
    "nabidka_uvod": "Spolupráci domlouváme podle konkrétního úkolu. Začít lze kterýmkoli krokem, rozsah a cenu domluvíme předem.",
    "nabidka_vystup": "Výstup",
    "nabidka_zacit_nadpis": "Jak začít",
    "nabidka_zacit_text": "Zavolejte nebo napište, co ve vaší obci řešíte. Obvykle začínáme úvodní konzultací na místě.",
    "nabidka_odkaz": "Nabídka spolupráce",
    "spoluprace_1_nadpis": "Jednotlivý úkol",
    "spoluprace_1_text": "Analýza místa, zadání, doporučení způsobu výběru projektanta nebo posouzení záměru. Rozsah a cenu domluvíme předem.",
    "spoluprace_2_nadpis": "Dlouhodobá podpora",
    "spoluprace_2_text": "Obcím bez městského architekta pomáháme podle potřeby. Městským architektům posílíme kapacitu u větších úloh.",
    "spoluprace_3_nadpis": "Jasná role",
    "spoluprace_3_text": "Na začátku určíme, zda působíme jako nezávislý poradce, nebo jako projektant. V téže věci obě role nespojujeme.",
    "foto_autor": "Foto",
    "jazyk": "Jazyk",
    "hlavni_menu": "Hlavní menu",
    "odkazy": "Odkazy",
    "uvod_logo": "KvalitaMísta – úvod",
    "nenalezeno": "Stránka nenalezena.",
    "nenalezeno_odkaz": "Zpět na úvod",
    "form_jmeno": "Jméno",
    "form_zprava": "Zpráva",
    "form_email": "E-mail",
    "form_telefon": "Telefon",
    "form_obec": "Obec / organizace",
    "form_zprava_napoveda": "Co ve vaší obci řešíte? Stačí pár vět.",
    "vice_k_tematu": "Více k tématu",
    "situace_clanek": "verejny-prostor-zacina-zadanim",
    "bydleni_clanek": "dobre-bydleni-zacina-u-mista",
    "budovy_clanek": "",
    "uvod_odkaz": "Spolupráce",
    "form_povinne": "povinné",
    "form_odeslat": "Odeslat zprávu —",
    "form_souhlas": "Údaje z formuláře použijeme jen k odpovědi na vaši zprávu.",
    "form_dekujeme": "Děkujeme, zprávu jsme přijali. Ozveme se vám co nejdříve.",
    "form_chyba": "Zprávu se nepodařilo odeslat. Zavolejte nám prosím nebo napište e-mail.",
    "foto_predchozi": "Předchozí fotografie",
    "foto_dalsi": "Další fotografie",
    "form_predmet": "Zpráva z webu KvalitaMísta",
}


# ---------------------------------------------------------------- data
def read_csv(name):
    p = DATA / f"{name}.csv"
    if not p.exists():
        return []
    with p.open(encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
    clean = []
    for r in rows:
        r = {(k or "").strip().lower(): (v or "").strip() for k, v in r.items()}
        if any(r.values()):
            clean.append(r)
    return clean


def yes(v):
    return (v or "").strip().upper() in ("ANO", "A", "YES", "Y", "TRUE", "1", "X")


def num(v, default=999):
    try:
        return float(str(v).replace(",", "."))
    except ValueError:
        return default


CFG = {r.get("klic", ""): r.get("hodnota", "") for r in read_csv("nastaveni") if r.get("klic")}
TEXTS = {r.get("klic", ""): r for r in read_csv("texty") if r.get("klic")}
LISTS = [r for r in read_csv("seznamy") if yes(r.get("publikovat", "ANO"))]
OFFER = sorted([r for r in read_csv("nabidka") if yes(r.get("publikovat", "ANO")) and r.get("nazev_cz")],
               key=lambda r: num(r.get("poradi")))
STEPS = sorted([r for r in read_csv("kroky") if yes(r.get("publikovat", "ANO"))], key=lambda r: num(r.get("poradi")))
PROJECTS = sorted([r for r in read_csv("projekty") if yes(r.get("publikovat")) and r.get("slug")], key=lambda r: num(r.get("poradi")))
ARTICLES = sorted([r for r in read_csv("clanky") if yes(r.get("publikovat")) and r.get("slug")],
                  key=lambda r: r.get("datum", ""), reverse=True)


IMG_NAME = re.compile(r"^[\w.\- ]+\.(jpe?g|png|webp|avif|gif)$", re.I)


def doc_to_text(md):
    """Google dokument (export do Markdownu) -> značky článku.
    Tabulka o 1–3 sloupcích a 2 řádcích: 1. řádek názvy fotek (01.jpg), 2. řádek popis a autor
    pod každou fotkou. Více sloupců = obrázky vedle sebe.
    Odkaz na obrázek ve 2. řádku (např. Wikimedia Commons) se použije, když fotka ve složce chybí."""
    def unesc(t):
        t = re.sub(r"\\+&", "&", t)
        return re.sub(r"\\([\\`*_{}\[\]()#+\-.!|>~])", r"\1", t)
    lines = [re.sub(r"^(>\s?)+", "", x).rstrip() for x in md.replace("\r", "").split("\n")]
    out, i, prev = [], 0, None
    def emit(text, kind):
        nonlocal prev
        if out and (kind != prev or kind in ("p", "h", "fig_new")):
            out.append("")
        out.append(text)
        prev = "fig" if kind == "fig_new" else kind
    while i < len(lines):
        x = lines[i].strip()
        if not x:
            if prev not in ("fig",):
                prev = None
            i += 1; continue
        if x.startswith("|"):
            rows = []
            while i < len(lines) and lines[i].strip().startswith("|"):
                r = lines[i].strip()
                if not re.match(r"^\|[\s:\-|]+\|$", r):
                    rows.append([c.strip() for c in re.split(r"(?<!\\)\|", r.strip().strip("|"))])
                i += 1
            names = [unesc(re.sub(r"\*+", "", c)).strip() for c in (rows[0] if rows else [])]
            cols = [j for j, n in enumerate(names) if IMG_NAME.match(n)]
            if cols:
                # tabulka s 1–3 sloupci: 1. řádek názvy fotek, 2. řádek popisek a autor
                # → obrázky vedle sebe; samostatné tabulky hned za sebou také vedle sebe
                for k, j in enumerate(cols):
                    cap = rows[1][j] if len(rows) > 1 and j < len(rows[1]) else ""
                    fb = ""
                    def strip_img_link(m):
                        nonlocal fb
                        if re.search(r"\.(jpe?g|png|webp|gif)(\?.*)?$", m.group(2), re.I) or "upload.wikimedia.org" in m.group(2):
                            fb = fb or m.group(2)
                            return m.group(1)
                        return m.group(0)
                    cap = re.sub(r"\[([^\]]*)\]\((https?://(?:[^()\s]|\([^()\s]*\))+)\)", strip_img_link, cap)
                    cap = unesc(cap).replace("|", "/").strip()
                    m = re.search(r"\s*(?:·\s*)?(Foto\s*:.*)$", cap)
                    credit = m.group(1).strip() if m else ""
                    cap = cap[:m.start()].strip(" ·") if m else cap
                    src = names[j] + (f"::{fb}" if fb else "")
                    kind = "fig" if (k > 0 or prev == "fig") else "fig_new"
                    emit(f"![{cap} | {credit}]({src.replace(' ', '%20')})", kind)
            else:
                for r in rows:
                    emit(unesc(" ".join(c for c in r if c)), "p")
            continue
        if re.match(r"^!\[[^\]]*\]\(", x):   # vložený obrázek v dokumentu – ignorovat
            i += 1; continue
        m = re.match(r"^#{1,6}\s+(.*)$", x)
        if m:
            emit("## " + unesc(m.group(1)).replace("**", "").strip(), "h")
        elif re.match(r"^[*\-+]\s+", x):
            emit("- " + unesc(re.sub(r"^[*\-+]\s+", "", x)), "ul")
        elif re.match(r"^\d+[.)]\s+", x):
            emit(unesc(x), "ol")
        else:
            if prev == "p" and lines[i - 1].endswith("  "):
                out.append(unesc(x))
            else:
                emit(unesc(x), "p")
        i += 1
    return "\n".join(out).strip()


for _a in ARTICLES:
    _doc = IMG / "clanky" / _a["slug"] / "_text.md"
    if _doc.exists():
        _a["text_cz"] = doc_to_text(_doc.read_text(encoding="utf-8"))
        for _k in ("text_en", "text_de"):
            if _a.get(_k, "").startswith("Text článku je v Google dokumentu"):
                _a[_k] = ""


# ---------------------------------------------------------------- jazyky
def tr(cz, manual, lang):
    """Ruční překlad > automatický překlad > čeština."""
    if lang == "cs" or not cz:
        return cz
    if manual:
        return manual
    got = translate.translate_many([cz], lang)[0]
    return got or cz


def T(key, lang):
    r = TEXTS.get(key)
    if r is None:
        cz = DEFAULTS.get(key, "")
        return tr(cz, "", lang)
    return tr(r.get("cz", ""), r.get(COL[lang], ""), lang)


def F(row, field, lang):
    """Pole záznamu s jazykovou koncovkou (nazev_cz / nazev_en / nazev_de)."""
    cz = row.get(f"{field}_cz", "")
    return tr(cz, row.get(f"{field}_{COL[lang]}", ""), lang) if lang != "cs" else cz


def prefetch(lang):
    """Pošle do DeepL všechny chybějící překlady jedním dávkovým voláním."""
    texts = []
    for k, r in TEXTS.items():
        if r.get("cz") and not r.get(COL[lang]):
            texts.append(r["cz"])
    texts += [v for k, v in DEFAULTS.items() if k not in TEXTS]
    for r in LISTS:
        if r.get("cz") and not r.get(COL[lang]):
            texts.append(r["cz"])
    for rows in (STEPS, PROJECTS, ARTICLES):
        for r in rows:
            for k, v in r.items():
                if k.endswith("_cz") and v and not r.get(k[:-3] + "_" + COL[lang]):
                    texts.append(v)
    texts = list(dict.fromkeys(t for t in texts if t))
    translate.translate_many(texts, lang)
    translate.used.clear()


# ---------------------------------------------------------------- pomocné
# Česká typografie: jednopísmenné předložky a spojky (v, s, z, k, u, o, a, i)
# nesmí zůstat na konci řádku – za ně se vkládá nezlomitelná mezera.
NBSP_RE = re.compile(r'(?<![^\s„“"(\[–—])([vszkuoaiVSZKUOAI]) (?=\S)')


def nb(s):
    return NBSP_RE.sub("\\1\u00a0", s or "")


def e(s):
    return html.escape(nb(s), quote=True)


def br(s):
    """Text s ručním zalomením řádků (nový řádek v buňce = <br>)."""
    return "<br>".join(e(x) for x in (s or "").splitlines())


def paras(s, cls=""):
    out = []
    for block in re.split(r"\n\s*\n", (s or "").strip()):
        if block.strip():
            attr = f' class="{cls}"' if cls else ""
            out.append(f"<p{attr}>{br(block.strip())}</p>")
    return "\n".join(out)


def inline(s):
    """Escapovaný text s **tučným**, *kurzívou* a [odkazy](https://…)."""
    out = e(s)
    out = re.sub(r"\[([^\]]+)\]\((https?://[^)\s]+)\)",
                 lambda m: f'<a href="{m.group(2)}" rel="noopener">{m.group(1)}</a>', out)
    out = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", out)
    out = re.sub(r"(?<![\w*])\*(?!\s)(.+?)(?<!\s)\*(?![\w*])", r"<em>\1</em>", out)
    return out


IMG_LINE = re.compile(r"^!\[(.*)\]\((\S+)\)$")
WEB_CACHE = DATA / "cache" / "web"
LICENSES = {"CC BY-SA 4.0": "https://creativecommons.org/licenses/by-sa/4.0/",
            "CC BY-SA 3.0": "https://creativecommons.org/licenses/by-sa/3.0/",
            "CC BY 4.0": "https://creativecommons.org/licenses/by/4.0/",
            "CC BY 3.0": "https://creativecommons.org/licenses/by/3.0/",
            "CC BY-SA 2.0": "https://creativecommons.org/licenses/by-sa/2.0/",
            "CC BY 2.0": "https://creativecommons.org/licenses/by/2.0/",
            "CC0": "https://creativecommons.org/publicdomain/zero/1.0/"}
REMOTE = []   # (zdroj, cíl) – vzdálené obrázky ke zkopírování do webu
ART_PH = {}   # fotky z Disku pro právě sestavovaný článek


def is_img_block(block):
    lines = [x.strip() for x in block.strip().splitlines() if x.strip()]
    return bool(lines) and all(IMG_LINE.match(x) for x in lines)


def remote_image(src):
    """Stáhne obrázek z webu (např. Wikimedia Commons) do mezipaměti; vrátí cestu nebo None."""
    import hashlib, urllib.request
    name = urllib.parse.unquote(src.split("?")[0].rsplit("/", 1)[-1])
    stem = re.sub(r"[^A-Za-z0-9._-]+", "-", unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode())
    local = WEB_CACHE / f"{hashlib.sha1(src.encode()).hexdigest()[:8]}-{stem}"
    if not local.exists():
        try:
            WEB_CACHE.mkdir(parents=True, exist_ok=True)
            url = urllib.parse.quote(src, safe=":/?=&%#~+,;@!$'*")
            req = urllib.request.Request(url, headers={"User-Agent": "kvalitamista.cz-build/1.0 (jirka.luke3@gmail.com)"})
            with urllib.request.urlopen(req, timeout=120) as r:
                local.write_bytes(r.read())
            print(f"· staženo z webu: {name}")
        except Exception as ex:
            print(f"! obrázek {src} se nepodařilo stáhnout ({ex}) — v článku vynechán")
            return None
    REMOTE.append((local, OUT / "obrazky" / "web" / local.name))
    return local


def img_size(p):
    try:
        from PIL import Image, ImageOps
        return ImageOps.exif_transpose(Image.open(p)).size
    except Exception:
        return (3, 2)


def credit_html(credit, src):
    """„Foto: autor, CC BY-SA 4.0“ – licence a zdroj jako odkazy."""
    out = e(credit)
    for lic, href in LICENSES.items():
        if lic in credit:
            out = out.replace(e(lic), f'<a href="{href}" rel="noopener license">{e(lic)}</a>', 1)
            break
    return out


def figure_block(lines):
    """Jeden nebo více obrázků vedle sebe se společným popiskem.
    Řádek: ![Popisek | Foto: autor, licence](https://… nebo 02)"""
    items, cap, credit, first_src = [], "", "", ""
    for x in lines:
        m = IMG_LINE.match(x)
        text, src = m.group(1), m.group(2)
        parts = [t.strip() for t in text.split("|")]
        cap = cap or parts[0]
        credit = credit or (parts[1] if len(parts) > 1 else "")
        first_src = first_src or src
        if src.startswith("http"):
            local = remote_image(src)
            if not local:
                continue
            href = "/obrazky/web/" + urllib.parse.quote(local.name)
        else:
            src = urllib.parse.unquote(src)
            name, _, fallback = src.partition("::")
            stem = Path(name).stem.lower()
            f = next((p for p in ART_PH.get("list", [])
                      if p.name.lower() == name.lower() or p.stem.split("_")[0].lower() == stem), None)
            if f:
                ART_PH.setdefault("used", set()).add(f)
                local, href = f, img_url(f)
            elif fallback:
                local = remote_image(fallback)
                if not local:
                    continue
                href = "/obrazky/web/" + urllib.parse.quote(local.name)
            else:
                print(f"· obrázek „{name}“ zatím není ve složce článku na Disku — místo zůstane prázdné")
                continue
        w, h = img_size(local)
        items.append((href, w / h, parts[0], parts[1] if len(parts) > 1 else "", src))
    if not items:
        return ""
    own = [(c, cr) for _, _, c, cr, _ in items]
    separate = len(items) > 1 and len({x for x in own if any(x)}) > 1

    def cap_html(c, cr, s):
        if not (c or cr):
            return ""
        return (f"<figcaption>{inline(c)}"
                f'{f"<span class=fig-cr>{credit_html(cr, s)}</span>" if cr else ""}</figcaption>')
    if separate:
        imgs = "".join(f'<figure class="fig-i" style="flex:{r:.3f} 1 0"><img src="{href}" alt="{e(alt)}" loading="lazy">'
                       f'{cap_html(alt, cr, s)}</figure>' for href, r, alt, cr, s in items)
        return f'<div class="fig fig-row fig-sep"><div class="fig-imgs">{imgs}</div></div>'
    imgs = "".join(f'<div class="fig-i" style="flex:{r:.3f} 1 0"><img src="{href}" alt="{e(alt)}" loading="lazy"></div>'
                   for href, r, alt, _, _ in items)
    cls = "fig fig-row" if len(items) > 1 else "fig"
    capt = ""
    if cap or credit:
        capt = (f"<figcaption>{inline(cap)}"
                f'{f"<span class=fig-cr>{credit_html(credit, first_src)}</span>" if credit else ""}</figcaption>')
    return f'<figure class="{cls}"><div class="fig-imgs">{imgs}</div>{capt}</figure>'


def rich(s):
    """Delší text článku: bloky oddělené prázdným řádkem.
    „## Nadpis“ = mezititulek, řádky „- “ = odrážky, „1. “ = číslovaný seznam,
    „![Popisek | Foto: autor, licence](https://… nebo 02)“ = velký obrázek
    (více takových řádků pod sebou = obrázky vedle sebe), jinak odstavec. V textu lze použít **tučně**, *kurzívu* a [odkaz](https://…)."""
    out = []
    for block in re.split(r"\n\s*\n", (s or "").strip()):
        lines = [x.strip() for x in block.strip().splitlines() if x.strip()]
        if not lines:
            continue
        if all(IMG_LINE.match(x) for x in lines):
            out.append(figure_block(lines))
        elif lines[0].startswith("## ") and len(lines) == 1:
            out.append(f"<h2>{inline(lines[0][3:])}</h2>")
        elif all(x.startswith(("- ", "• ")) for x in lines):
            out.append("<ul>" + "".join(f"<li>{inline(x[2:])}</li>" for x in lines) + "</ul>")
        elif all(re.match(r"\d+\.\s", x) for x in lines):
            items = [inline(re.sub(r"^\d+\.\s+", "", x)) for x in lines]
            out.append("<ol>" + "".join(f"<li>{i}</li>" for i in items) + "</ol>")
        else:
            out.append("<p>" + "<br>".join(inline(x) for x in lines) + "</p>")
    return "\n".join(out)


def prefix(lang):
    return "" if lang == "cs" else f"{lang}/"


def url(lang, path=""):
    """Absolutní cesta v rámci webu, např. /en/projekty/vodna/."""
    return "/" + prefix(lang) + path


def photos(section, slug):
    d = IMG / section / slug
    if not d.is_dir():
        return []
    return sorted([p for p in d.iterdir() if p.suffix.lower() in PHOTO_EXT], key=lambda p: p.name.lower())


def captions(section, slug):
    """Volitelný soubor popisky.txt: řádek [01] a pod ním popisek."""
    p = IMG / section / slug / "popisky.txt"
    caps, cur = {}, None
    if p.exists():
        for line in p.read_text(encoding="utf-8").splitlines():
            m = re.match(r"\s*\[(\w+)\]\s*$", line)
            if m:
                cur = m.group(1)
                caps[cur] = ""
            elif cur and line.strip() and not caps[cur]:
                caps[cur] = line.strip()
    return caps


def img_url(p):
    return "/obrazky/" + urllib.parse.quote(p.relative_to(IMG).as_posix())


def name_caption(p):
    """Popisek z názvu souboru: vše za prvním podtržítkem (nebo pomlčkou).
    hlavni_Foto Petra Kunarova_Bern.jpg -> „Foto Petra Kunarova · Bern“"""
    stem = unicodedata.normalize("NFC", p.stem)
    for sep in ("_", "-"):
        if sep in stem:
            rest = stem.split(sep, 1)[1].strip()
            return re.sub(r"\s*_\s*", " · ", rest).strip(" ·")
    return ""


def plain(s):
    """Bez diakritiky a malými písmeny: „Hlavní_Bern“ -> „hlavni_bern“."""
    return unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode().lower()


def hero_photos():
    """Všechny fotky ve složce nastaveni, jejichž název začíná „Hlavní_“ (nebo je „hlavni“)."""
    d = IMG / "nastaveni"
    if not d.is_dir():
        return []
    out = []
    for f in sorted(d.iterdir(), key=lambda f: plain(f.name)):
        n = plain(f.stem)
        if f.suffix.lower() in PHOTO_EXT and (n == "hlavni" or n.startswith(("hlavni_", "hlavni-"))):
            out.append(f)
    return out


def hero_caption(p):
    cap = name_caption(p) if plain(p.stem) != "hlavni" else ""
    return "" if re.fullmatch(r"[\d\s·.]*", cap) else cap


FOTO_WORD = {"cs": "Foto", "en": "Photo", "de": "Foto"}


def tr_caption(cap, lang):
    """Popisek fotky: „Foto Jméno Příjmení“ se nepřekládá (jen slovo Foto),
    ostatní části za „ · “ přeloží DeepL."""
    if not cap or lang == "cs":
        return cap
    out = []
    for part in cap.split(" · "):
        m = re.match(r"(?i)foto(?:grafie)?:?\s+(.+)", part)
        if m:
            out.append(f"{FOTO_WORD[lang]}: {m.group(1)}")
        else:
            out.append(tr(part, "", lang))
    return " · ".join(out)


def cfg_photo(key):
    rel = CFG.get(key, "")
    if not rel:
        return None
    p = IMG / rel
    if p.exists():
        return p
    stem = (IMG / rel).with_suffix("")
    for ext in PHOTO_EXT:
        if stem.with_suffix(ext).exists():
            return stem.with_suffix(ext)
    # soubor s popiskem v názvu: hlavni_Foto … .jpg
    d, base = stem.parent, stem.name.lower()
    if d.is_dir():
        for f in sorted(d.iterdir()):
            n = f.stem.lower()
            if f.suffix.lower() in PHOTO_EXT and (n == base or n.startswith(base + "_") or n.startswith(base + "-")):
                return f
    return None


# Základní logo (logo 3 s pomlčkou) podle grafického manuálu, písmo převedené na křivky.
# Barva = currentColor (černé v hlavičce, bílé v patičce).
LOGO = ('<svg class="logo-svg" aria-hidden="true" focusable="false" viewBox="73 0 3010 1699" '
        'xmlns="http://www.w3.org/2000/svg"><path fill="currentColor" d="M198 0H73V657H198V502L278 377L404 657H544L366 273L538 0H399L198 314Z M928.9 0 812.9 473 695.9 0H563.9L742.9 657H875.9L1054.9 0Z M1131.9 657 1163.9 539H1372.9L1405.9 657H1533.9L1337.9 0H1205.9L1009.9 657ZM1267.9 154 1344.9 433H1191.9Z M1702.9 0H1577.9V657H1959.9V545H1702.9Z M2126.9 0H2001.9V657H2126.9Z M2172.9 112H2330.9V657H2454.9V112H2611.9V0H2172.9Z M2680.9 657 2712.9 539H2921.9L2954.9 657H3082.9L2886.9 0H2754.9L2558.9 657ZM2816.9 154 2893.9 433H2740.9Z M1113.0 1474H1185.0L1292.0 1280V1689H1413.0V1032H1306.0L1151.0 1318L994.0 1032H887.0V1689H1003.0V1277Z M1638.9 1032H1513.9V1689H1638.9Z M2145.9 1230V1216C2145.9 1096 2058.9 1022 1928.9 1022C1797.9 1022 1718.9 1106 1718.9 1207C1718.9 1300 1773.9 1354 1865.9 1388L1965.9 1426C2013.9 1443 2037.9 1471 2037.9 1512C2037.9 1560 2000.9 1595 1931.9 1595C1866.9 1595 1827.9 1563 1827.9 1510V1483H1704.9V1505C1704.9 1625 1799.9 1699 1934.9 1699C2070.9 1699 2159.9 1617 2159.9 1498C2159.9 1377 2076.9 1336 1994.9 1306L1901.9 1272C1853.9 1255 1839.9 1224 1839.9 1198C1839.9 1156 1871.9 1125 1928.9 1125C1986.9 1125 2023.9 1160 2023.9 1211V1230Z M2172.9 1144H2330.9V1689H2454.9V1144H2611.9V1032H2172.9Z M2680.9 1689 2712.9 1571H2921.9L2954.9 1689H3082.9L2886.9 1032H2754.9L2558.9 1689ZM2816.9 1186 2893.9 1465H2740.9ZM73.0 1298.0h689.0v125.0h-689.0ZM1514.0 782.0h689.0v125.0h-689.0Z"/></svg>')


# ---------------------------------------------------------------- kostra stránky
# Jména, tituly a značky, které nesmí měnit překladač v prohlížeči (Chrome/Safari
# jinak udělá z „arch.“ třeba „oblouk“).
NO_TRANSLATE = re.compile(
    r"(?:(?:Ing|Mgr|Bc|MgA|Dr|doc|prof|PhDr|RNDr)\.(?:\s+et)?\s+)+(?:arch\.\s+)?"
    r"[A-ZÁČĎÉĚÍŇÓŘŠŤÚŮÝŽ][\wÀ-ž]+\s+[A-ZÁČĎÉĚÍŇÓŘŠŤÚŮÝŽ][\wÀ-ž]+"
    r"|IN—FORM—ARCHITEKTI(?:,\s*s\.r\.o\.)?|Kvalita\s?M[íi]sta|ČKA")


def protect(body):
    def text(m):
        return ">" + NO_TRANSLATE.sub(lambda n: f'<span translate="no" class="notranslate">{n.group(0)}</span>', m.group(1)) + "<"
    parts = re.split(r"(<script\b.*?</script>|<title>.*?</title>)", body, flags=re.S)
    return "".join(p if i % 2 else re.sub(r">([^<>]+)<", text, p) for i, p in enumerate(parts))


HEAD_JS = """<script>
(function(){
  var h=document.querySelector('.site-head'), r=document.documentElement;
  function upd(){
    var y=window.scrollY;   /* hystereze proti cukání na hranici */
    if(y>80) h.classList.add('scrolled'); else if(y<8) h.classList.remove('scrolled');
    r.style.setProperty('--hh', h.offsetHeight+'px');
  }
  upd(); window.addEventListener('scroll', upd, {passive:true}); window.addEventListener('resize', upd);
})();
</script>"""


def browser_translation_allowed():
    """NASTAVENI prekladac_prohlizece = ANO povolí automatický překlad v prohlížeči."""
    return yes(CFG.get("prekladac_prohlizece", "NE"))


def notr_attr():
    return "" if browser_translation_allowed() else ' translate="no" class="notranslate"'


def notr_meta():
    return "" if browser_translation_allowed() else '\n<meta name="google" content="notranslate">'


def page(lang, path, title, desc, body, alternates=True, noindex=None):
    body = protect(body)
    if noindex is None:
        noindex = not yes(CFG.get("indexovat", "NE"))
    canonical = SITE_URL + url(lang, path)
    alt = ""
    if alternates:
        alt = "".join(f'<link rel="alternate" hreflang="{l}" href="{SITE_URL + url(l, path)}">\n' for l in LANGS)
        alt += f'<link rel="alternate" hreflang="x-default" href="{SITE_URL + url("cs", path)}">\n'
    cur = ' aria-current="true"'
    langnav = "".join(
        f'<a href="{url(l, path)}" lang="{l}"{cur if l == lang else ""}>{LANG_LABEL[l]}</a>'
        for l in LANGS)
    items = [("menu_postup", url(lang) + "#postup"), ("menu_praxe", url(lang) + "#praxe")]
    if ARTICLES:
        items.append(("menu_clanky", url(lang, "clanky/")))
    items.append(("menu_onas", url(lang) + "#o-nas"))
    if OFFER:
        items.append(("menu_nabidka", url(lang, "nabidka/")))
    items.append(("menu_kontakt", url(lang) + "#kontakt"))
    menu = "".join(f'<li><a href="{h}">{e(T(k, lang))}</a></li>' for k, h in items)
    accent = CFG.get("barva_akcentu", "") or "#ECE48A"
    links = ""
    for i in (1, 2, 3, 4):
        t, u = CFG.get(f"odkaz_{i}_text", ""), CFG.get(f"odkaz_{i}_url", "")
        if t and u:
            links += f'<a href="{e(u)}">{e(t)}</a>\n'
    return f"""<!doctype html>
<html lang="{lang}"{notr_attr()}>
<head>
<meta charset="utf-8">{notr_meta()}
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{e(title)}</title>
<meta name="description" content="{e(desc)}">
{'<meta name="robots" content="noindex">' if noindex else ''}
<link rel="canonical" href="{canonical}">
{alt}<meta property="og:title" content="{e(title)}">
<meta property="og:description" content="{e(desc)}">
<meta property="og:type" content="website">
<meta property="og:url" content="{canonical}">
<link rel="icon" href="/favicon.svg" type="image/svg+xml">
<link rel="stylesheet" href="/styl.css?v={CSS_VER}">
<style>:root{{--accent:{e(accent)}}}</style>
</head>
<body>
<a class="skip" href="#obsah">{e(T("skip", lang))}</a>
<header class="site-head">
<div class="strip"></div>
<div class="wrap head">
<nav class="lang notranslate" translate="no" aria-label="{e(T('jazyk', lang))}">{langnav}</nav>
<div class="row">
<a class="logo notranslate" translate="no" href="{url(lang)}" aria-label="KvalitaMísta">{LOGO}</a>
<details class="menu">
<summary aria-label="{e(T('menu_label', lang))}"><span></span><span></span><span></span></summary>
<nav aria-label="{e(T('hlavni_menu', lang))}" onclick="if(event.target.closest('a'))this.closest('details').open=false"><ul>{menu}</ul></nav>
</details>
</div>
</div>
</header>
{HEAD_JS}
<main id="obsah">
{body}
</main>
<footer>
<div class="foot"><div class="wrap">
<p class="foot-logo notranslate" translate="no"><span class="sr">KvalitaMísta</span>{LOGO}</p>
<p class="foot-claim M">{e(T("paticka_heslo", lang))}</p>
</div></div>
<nav class="wrap foot-links" aria-label="{e(T('odkazy', lang))}">
{links}</nav>
</footer>
</body>
</html>
"""


# ---------------------------------------------------------------- kontaktní formulář
FORM_JS = """<script>
(function(){
  var d=document.getElementById('formular'); if(!d) return;
  function openForm(){ d.open=true; }
  document.querySelectorAll('[data-open-form]').forEach(function(a){ a.addEventListener('click', openForm); });
  if(location.hash==='#formular') openForm();
  var f=d.querySelector('form'), msg=d.querySelector('.form-msg');
  f.addEventListener('submit', function(ev){
    ev.preventDefault();
    if(!f.reportValidity()) return;
    var url=f.getAttribute('data-endpoint');
    var data=new FormData(f);
    if(!url){
      var body=(data.get('zprava')||'')+'\\n\\n'+(data.get('jmeno')||'')+'\\n'+(data.get('obec')||'')+'\\n'+(data.get('email')||'')+'\\n'+(data.get('telefon')||'');
      location.href='mailto:'+f.getAttribute('data-mail')+'?subject='+encodeURIComponent(f.getAttribute('data-subject'))+'&body='+encodeURIComponent(body);
      return;
    }
    var btn=f.querySelector('button'); btn.disabled=true;
    fetch(url,{method:'POST',mode:'no-cors',body:new URLSearchParams(data)})
      .then(function(){ f.hidden=true; msg.textContent=msg.getAttribute('data-ok'); msg.hidden=false; })
      .catch(function(){ btn.disabled=false; msg.textContent=msg.getAttribute('data-err'); msg.hidden=false; });
  });
})();
</script>"""


# ---------------------------------------------------------------- titulní fotografie (střídání)
SLIDES_JS = """<script>
(function(){
  var fig=document.currentScript.previousElementSibling;
  var imgs=fig.querySelectorAll('img[data-src]'), n=imgs.length, cap=fig.querySelector('figcaption'),
      cnt=fig.querySelector('.sl-count'), cur=-1, last=-1;
  if(!n) return;
  try{ last=parseInt(localStorage.getItem('km-hero'),10); }catch(e){}
  var start=Math.floor(Math.random()*n);
  if(n>1 && start===last) start=(start+1)%n;
  function load(i){ var im=imgs[(i+n)%n]; if(!im.getAttribute('src')) im.src=im.getAttribute('data-src'); }
  function show(i){
    i=(i+n)%n; if(i===cur) return;
    load(i);
    if(cur>=0) imgs[cur].classList.remove('on');
    imgs[i].classList.add('on'); cur=i;
    cap.textContent=imgs[i].getAttribute('data-cap')||'';
    if(cnt) cnt.textContent=(i+1)+' / '+n;
    try{ localStorage.setItem('km-hero', i); }catch(e){}
    if(n>1){ setTimeout(function(){ load(i+1); load(i-1); }, 800); }
  }
  show(start);
  if(n<2) return;
  fig.querySelector('.sl-prev').addEventListener('click', function(){ show(cur-1); });
  fig.querySelector('.sl-next').addEventListener('click', function(){ show(cur+1); });
  var x0=null, y0=0;
  fig.addEventListener('touchstart', function(ev){ x0=ev.touches[0].clientX; y0=ev.touches[0].clientY; }, {passive:true});
  fig.addEventListener('touchend', function(ev){
    if(x0===null) return;
    var dx=ev.changedTouches[0].clientX-x0, dy=ev.changedTouches[0].clientY-y0; x0=null;
    if(Math.abs(dx)>40 && Math.abs(dx)>Math.abs(dy)) show(cur+(dx<0?1:-1));
  }, {passive:true});
})();
</script>"""


def contact_form(lang, mail):
    endpoint = CFG.get("formular_url", "")
    req = f' <span class="muted">({e(T("form_povinne", lang))})</span>'
    return f"""
<details class="form" id="formular">
<summary class="btn">{e(T("tlacitko", lang))}</summary>
<form data-endpoint="{e(endpoint)}" data-mail="{e(mail)}" data-subject="{e(T('form_predmet', lang))}" novalidate>
<label>{e(T("form_jmeno", lang))}<input name="jmeno" autocomplete="name"></label>
<label>{e(T("form_obec", lang))}<input name="obec" autocomplete="organization"></label>
<label><span>{e(T("form_zprava", lang))}{req}</span><textarea name="zprava" rows="5" placeholder="{e(T("form_zprava_napoveda", lang))}" required></textarea></label>
<label><span>{e(T("form_email", lang))}{req}</span><input name="email" type="email" autocomplete="email" required></label>
<label>{e(T("form_telefon", lang))}<input name="telefon" type="tel" autocomplete="tel"></label>
<label class="hp" aria-hidden="true">Web<input name="web" tabindex="-1" autocomplete="off"></label>
<input type="hidden" name="jazyk" value="{lang}">
<p class="muted measure" style="margin:4px 0 0">{e(T("form_souhlas", lang))}</p>
<p style="margin:8px 0 0"><button class="btn" type="submit">{e(T("form_odeslat", lang))}</button></p>
</form>
<p class="form-msg M" role="status" hidden data-ok="{e(T('form_dekujeme', lang))}" data-err="{e(T('form_chyba', lang))}"></p>
</details>
{FORM_JS}"""


# ---------------------------------------------------------------- úvodní stránka
def topic_link(section, lang):
    """Tichý odkaz „Více k tématu“ na článek podle slugu v textu <sekce>_clanek."""
    slug = T(f"{section}_clanek", "cs")
    a = next((x for x in ARTICLES if x.get("slug") == slug), None) if slug else None
    if not a:
        return ""
    return (f'<p style="margin:24px 0 0"><span class="muted">{e(T("vice_k_tematu", lang))}:</span> '
            f'<a class="link" href="{url(lang, "clanky/" + slug + "/")}">{e(F(a, "nazev", lang))}</a></p>')


def dash_list(name, lang):
    rows = sorted([r for r in LISTS if r.get("seznam") == name], key=lambda r: num(r.get("poradi")))
    if not rows:
        return ""
    lis = "".join(f'<li><span aria-hidden="true">—</span><span>{e(tr(r.get("cz", ""), r.get(COL[lang], ""), lang))}</span></li>' for r in rows)
    return f'<ul class="dash M">{lis}</ul>'


def project_meta(p, lang):
    parts = [p.get("lokalita", ""), p.get("rok", ""), F(p, "typ", lang)]
    return " · ".join(x for x in parts if x)


def cooperation(p, lang):
    name = p.get("spoluprace", "")
    if not name:
        return ""
    link = p.get("spoluprace_odkaz", "")
    who = f'<a href="{e(link)}">{e(name)}</a>' if link else e(name)
    return f'<p class="muted" style="margin:10px 0 0">{e(T("praxe_spoluprace", lang))} {who}</p>'


def home(lang):
    phone = CFG.get("telefon", "")
    mail = CFG.get("email", "")
    tel = re.sub(r"[^\d+]", "", phone)
    hphotos = hero_photos()
    if not hphotos and cfg_photo("hlavni_foto"):
        hphotos = [cfg_photo("hlavni_foto")]
    hero_html = ""
    if hphotos:
        pos = e(CFG.get("hlavni_foto_pozice", "") or "50% 22%")
        alt = e(T("foto_popis", lang))
        imgs = "".join(
            f'<img data-src="{img_url(p)}" data-cap="{e(tr_caption(hero_caption(p), lang))}" alt="{alt}" style="object-position:{pos}">'
            for p in hphotos)
        cap0 = tr_caption(hero_caption(hphotos[0]), lang)
        nav = ""
        if len(hphotos) > 1:
            nav = (f'<button class="sl-prev" type="button" aria-label="{e(T("foto_predchozi", lang))}"></button>'
                   f'<button class="sl-next" type="button" aria-label="{e(T("foto_dalsi", lang))}"></button>'
                   f'<span class="sl-count" aria-hidden="true"></span>')
        hero_html = (f'<figure class="photo slides">{imgs}'
                     f'<noscript><img src="{img_url(hphotos[0])}" alt="{alt}" style="object-position:{pos}"></noscript>'
                     f'{nav}<figcaption>{e(cap0)}</figcaption></figure>{SLIDES_JS}')
    portrait = cfg_photo("portret")

    steps = "".join(
        f'<li><span class="num">{i:02d}</span>'
        f'<h3>{e(F(s, "nazev", lang))}</h3><p>{e(F(s, "popis", lang))}</p></li>'
        for i, s in enumerate(STEPS, 1))

    cards = ""
    for p in PROJECTS:
        ph = photos("projekty", p["slug"])
        img = (f'<div class="img"><img src="{img_url(ph[0])}" alt="{e(F(p, "nazev", lang))}" loading="lazy"></div>'
               if ph else "")
        cards += f"""<article class="card">
{img}
<p class="b" style="margin:20px 0 0">{e(project_meta(p, lang))}</p>
<h3>{e(F(p, "nazev", lang))}</h3>
<p class="measure" style="margin:12px 0 0">{br(F(p, "anotace", lang))}</p>
{cooperation(p, lang)}
<p style="margin:14px 0 0"><a class="link" href="{url(lang, 'projekty/' + p['slug'] + '/')}">{e(T("praxe_odkaz", lang))}</a></p>
</article>
"""

    spec = T("postup_specialiste", lang)
    offer_link = (f'<p style="margin:24px 0 0"><a class="link" href="{url(lang, 'nabidka/')}">{e(T("nabidka_odkaz", lang))} →</a></p>'
                  if OFFER else "")

    # Sekce „Místo a bydlení“ – zobrazí se jen tehdy, když má v tabulce vyplněný nadpis
    housing_html = ""
    if T("bydleni_nadpis", lang):
        h_intro = T("bydleni_uvod_seznamu", lang)
        h_text2 = T("bydleni_text_2", lang)
        h_end = T("bydleni_zaver", lang)
        housing_html = f"""<section id="bydleni" class="wrap sec cont">
<p class="label">{e(T("bydleni_stitek", lang))}</p>
<div class="split">
<h2 class="L">{e(T("bydleni_nadpis", lang))}</h2>
<div>
<p class="M p0" style="max-width:34ch">{e(T("bydleni_text", lang))}</p>
{f'<p class="b" style="margin:28px 0 0">{e(h_intro)}</p>' if h_intro else ''}
{dash_list("bydleni", lang)}
{f'<p class="b" style="margin:28px 0 0">{e(h_text2)}</p>' if h_text2 else ''}
{dash_list("bydleni_posoudime", lang)}
{f'<p class="measure" style="margin:24px 0 0">{e(h_end)}</p>' if h_end else ''}
{topic_link("bydleni", lang)}
</div>
</div>
</section>"""

    onas_url = CFG.get("onas_url", "")
    imprint_ids = " · ".join(x for x in (f"IČO {CFG.get('ico')}" if CFG.get("ico") else "",
                                         f"DIČ {CFG.get('dic')}" if CFG.get("dic") else "") if x)
    addr = "<br>".join(e(CFG.get(k)) for k in ("adresa_1", "adresa_2") if CFG.get(k))

    body = f"""
<section class="wrap hero">
<h1 class="L XL">{br(T("uvod_nadpis", lang))}</h1>
<div class="hero-sub">
<p class="b p0">{e(T("uvod_stitek", lang))}</p>
<p class="M" style="margin:12px 0 0;max-width:36ch">{e(T("uvod_text", lang))}</p>
<p class="hero-cta" style="margin:32px 0 0">{f'<a class="btn" href="{url(lang, "nabidka/")}">{e(T("uvod_odkaz", lang))} —</a>' if OFFER else f'<a class="btn" href="#formular" data-open-form>{e(T("tlacitko", lang))}</a>'}</p>
</div>
</section>

{hero_html}

<section class="wrap sec">
<p class="label">{e(T("situace_stitek", lang))}</p>
<div class="split">
<h2 class="L">{e(T("situace_nadpis", lang))}</h2>
<div>
<p class="M p0" style="max-width:34ch">{e(T("situace_text", lang))}</p>
<p class="b" style="margin:28px 0 0">{e(T("situace_uvod_seznamu", lang))}</p>
{dash_list("situace", lang)}
{topic_link("situace", lang)}
</div>
</div>
</section>

<section id="budovy" class="wrap sec cont">
<p class="label">{e(T("budovy_stitek", lang))}</p>
<div class="split">
<h2 class="L">{e(T("budovy_nadpis", lang))}</h2>
<div>
<p class="M p0" style="max-width:34ch">{e(T("budovy_text", lang))}</p>
<p class="b" style="margin:28px 0 0">{e(T("budovy_text_2", lang))}</p>
{dash_list("budovy", lang)}
{f'<p class="measure" style="margin:24px 0 0">{e(T("budovy_zaver", lang))}</p>' if T("budovy_zaver", lang) else ''}
{topic_link("budovy", lang)}
</div>
</div>
</section>

{housing_html}

<section id="postup" class="accent">
<div class="wrap sec">
<p class="label">{e(T("postup_stitek", lang))}</p>
<h2 class="L" style="margin-top:40px">{br(T("postup_nadpis", lang))}</h2>
<ol class="steps">{steps}</ol>
<p class="M" style="margin:clamp(48px,6vw,72px) 0 0">{e(T("postup_zaver", lang))}</p>
{f'<p class="measure" style="margin:16px 0 0">{e(spec)}</p>' if spec else ''}
{offer_link}
</div>
</section>

<section id="praxe" class="wrap sec">
<p class="label">{e(T("praxe_stitek", lang))}</p>
<h2 class="L" style="margin-top:40px;max-width:16ch">{e(T("praxe_nadpis", lang))}</h2>
<div class="cards">{cards}</div>
</section>

<section id="o-nas" class="sand">
<div class="wrap sec">
<p class="label">{e(T("onas_stitek", lang))}</p>
<blockquote class="L" style="margin:40px 0 0;max-width:18ch">{e(T("onas_citat", lang))}</blockquote>
<div class="about">
{f'<div class="portrait"><img src="{img_url(portrait)}" alt="{e(T("onas_jmeno", lang))}" loading="lazy"></div>' if portrait else ''}
<div style="flex:1 1 380px;min-width:0;align-self:flex-end">
<h3 class="M b p0" style="line-height:1.2">{e(T("onas_jmeno", lang))}</h3>
<p class="measure" style="margin:14px 0 0">{e(T("onas_text", lang))}</p>
<p class="measure" style="margin:12px 0 0">{e(T("onas_text_2", lang))}</p>
{f'<p style="margin:18px 0 0"><a class="link" href="{e(onas_url)}">{e(T("onas_odkaz", lang))}</a></p>' if onas_url else ''}
</div>
</div>
</div>
</section>

<section id="kontakt" class="wrap sec">
<p class="label">{e(T("kontakt_stitek", lang))}</p>
<h2 class="L" style="margin-top:40px;max-width:18ch">{e(T("kontakt_nadpis", lang))}</h2>
<p class="M" style="margin:24px 0 0;max-width:44ch">{e(T("kontakt_text", lang))}</p>
<div class="big-contact">
{f'<a href="tel:{tel}">{e(phone)}</a>' if phone else ''}
{f'<a href="mailto:{e(mail)}">{e(mail)}</a>' if mail else ''}
</div>
{contact_form(lang, mail)}
<div class="imprint">
<div style="flex:1 1 320px">
<p class="b" style="margin:0 0 6px;color:var(--fg)">{e(T("znacka_nadpis", lang))}</p>
<p class="p0 measure">{e(T("znacka_text", lang))}</p>
</div>
<div style="flex:1 1 240px">
<p class="p0">{e(imprint_ids)}{'<br>' if imprint_ids and addr else ''}{addr}</p>
</div>
</div>
</section>
"""
    jsonld = {"@context": "https://schema.org", "@type": "ProfessionalService", "name": "KvalitaMísta",
              "url": SITE_URL + url(lang), "description": T("seo_popis", lang), "areaServed": "CZ"}
    if phone:
        jsonld["telephone"] = phone
    if mail:
        jsonld["email"] = mail
    body += f'<script type="application/ld+json">{json.dumps(jsonld, ensure_ascii=False)}</script>\n'
    return page(lang, "", T("seo_titulek", lang), T("seo_popis", lang), body)


# ---------------------------------------------------------------- detail projektu
def project_page(p, lang):
    name = F(p, "nazev", lang)
    ph = photos("projekty", p["slug"])
    caps = captions("projekty", p["slug"])
    facts = ""
    for field, key in (("problem", "projekt_problem"), ("reseni", "projekt_reseni"), ("prinos", "projekt_prinos")):
        txt = F(p, field, lang)
        if txt:
            facts += f'<div><h2>{e(T(key, lang))}</h2>{paras(txt)}</div>'
    gallery = ""
    for f in ph:
        cap = tr_caption(caps.get(f.stem, "") or caps.get(f.stem.split("_")[0], "") or name_caption(f), lang)
        gallery += (f'<figure><img src="{img_url(f)}" alt="{e(cap or name)}" loading="lazy">'
                    f'{f"<figcaption>{e(cap)}</figcaption>" if cap else ""}</figure>')
    author = p.get("autor_fotografii", "")
    desc = p.get("seo_popis_cz", "") if lang == "cs" else tr(p.get("seo_popis_cz", ""), "", lang)
    body = f"""
<article class="wrap detail-head sec">
<p class="label">{e(project_meta(p, lang))}</p>
<h1 class="L" style="margin-top:40px;max-width:18ch">{e(name)}</h1>
<div class="M measure" style="margin-top:28px">{paras(F(p, "anotace", lang))}</div>
{cooperation(p, lang)}
{f'<div class="facts">{facts}</div>' if facts else ''}
{f'<div class="gallery">{gallery}</div>' if gallery else ''}
{f'<p class="muted" style="margin:16px 0 0">{e(T("foto_autor", lang))}: {e(author)}</p>' if author and author not in ("—", "-") else ''}
<p style="margin:clamp(40px,5vw,64px) 0 0"><a class="link" href="{url(lang)}#praxe">← {e(T("projekt_zpet", lang))}</a></p>
</article>
"""
    return page(lang, f"projekty/{p['slug']}/", f"{name} — KvalitaMísta", desc or name, body)


# ---------------------------------------------------------------- články
def article_meta(a, lang):
    d = a.get("datum", "")
    try:
        y, m, dd = [int(x) for x in d[:10].split("-")]
        d = f"{dd}. {m}. {y}" if lang in ("cs", "de") else date(y, m, dd).strftime("%-d %B %Y")
    except Exception:
        pass
    return " · ".join(x for x in (d, a.get("autor", "")) if x)


def articles_index(lang):
    lis = "".join(
        f'<li><a href="{url(lang, "clanky/" + a["slug"] + "/")}"><p class="muted p0">{e(article_meta(a, lang))}</p>'
        f'<h2>{e(F(a, "nazev", lang))}</h2><p class="measure" style="margin:8px 0 0">{e(F(a, "perex", lang))}</p></a></li>'
        for a in ARTICLES)
    body = f"""
<section class="wrap detail-head sec">
<p class="label">{e(T("clanky_stitek", lang))}</p>
<h1 class="L" style="margin-top:40px">{e(T("clanky_nadpis", lang))}</h1>
<ul class="list-articles">{lis}</ul>
</section>
"""
    return page(lang, "clanky/", f'{T("clanky_nadpis", lang)} — KvalitaMísta', T("clanky_nadpis", lang), body)


def article_text(a, lang):
    """Text článku; obrázkové bloky se do DeepL neposílají, překládá se jen jejich popisek."""
    cz = a.get("text_cz", "")
    manual = a.get(f"text_{COL[lang]}", "") if lang != "cs" else ""
    if lang == "cs" or manual or not cz:
        return F(a, "text", lang)
    out, prose = [], []
    def flush():
        if prose:
            out.append(tr("\n\n".join(prose), "", lang))
            prose.clear()
    for block in re.split(r"\n\s*\n", cz.strip()):
        if is_img_block(block):
            flush()
            lines = []
            for x in block.strip().splitlines():
                m = IMG_LINE.match(x.strip())
                if not m:
                    continue
                parts = [t.strip() for t in m.group(1).split("|")]
                parts[0] = tr(parts[0], "", lang)
                lines.append(f"![{' | '.join(parts)}]({m.group(2)})")
            out.append("\n".join(lines))
        else:
            prose.append(block)
    flush()
    return "\n\n".join(out)


def coop_block(lang):
    items = "".join(
        f'<li><h3>{e(T(f"spoluprace_{i}_nadpis", lang))}</h3><p>{e(T(f"spoluprace_{i}_text", lang))}</p></li>'
        for i in (1, 2, 3, 4) if T(f"spoluprace_{i}_nadpis", lang))
    if not items or not T("spoluprace_nadpis", lang):
        return ""
    return f'<h2 class="coop-h">{e(T("spoluprace_nadpis", lang))}</h2><ul class="coop">{items}</ul>'


def offer_page(lang):
    phone = CFG.get("telefon", "")
    mail = CFG.get("email", "")
    tel = re.sub(r"[^\d+]", "", phone)
    acc = ""
    for r in OFFER:
        out = F(r, "vystup", lang)
        acc += (f'<details class="offer"><summary>{e(F(r, "nazev", lang))}</summary>'
                f'<div><p class="measure p0">{e(F(r, "popis", lang))}</p>'
                + (f'<p class="measure" style="margin:12px 0 0"><span class="b">{e(T("nabidka_vystup", lang))}:</span> {e(out)}</p>' if out else "")
                + '</div></details>')
    contact = " · ".join(x for x in (
        f'<a href="tel:{tel}">{e(phone)}</a>' if phone else "",
        f'<a href="mailto:{e(mail)}">{e(mail)}</a>' if mail else "") if x)
    body = f"""
<section class="wrap detail-head sec">
<p class="label">{e(T("nabidka_stitek", lang))}</p>
<h1 class="L" style="margin-top:40px;max-width:20ch">{e(T("nabidka_nadpis", lang))}</h1>
<p class="M measure" style="margin:28px 0 0">{e(T("nabidka_uvod", lang))}</p>
<div class="offers">{acc}</div>
{coop_block(lang)}
<h2 class="coop-h">{e(T("nabidka_zacit_nadpis", lang))}</h2>
<p class="measure" style="margin:12px 0 0">{e(T("nabidka_zacit_text", lang))}</p>
{f'<p style="margin:12px 0 0">{contact}</p>' if contact else ''}
<p style="margin:28px 0 0"><a class="btn" href="{url(lang)}#formular">{e(T("tlacitko", lang))}</a></p>
</section>
"""
    return page(lang, "nabidka/", f"{T('nabidka_stitek', lang)} — KvalitaMísta", T("nabidka_uvod", lang), body)


def author_box(lang):
    """Krátký podpis autora pod článkem s odkazem na nabídku – bez tlačítka a banneru."""
    text = T("autor_text", lang)
    if not text:
        return ""
    link = (f' · <a href="{url(lang, "nabidka/")}">{e(T("nabidka_odkaz", lang))}</a>' if OFFER else "")
    return (f'<aside class="author-box"><p class="b p0">{e(T("clanky_autor", lang))}</p>'
            f'<p class="measure" style="margin:8px 0 0">{e(text)}{link}</p></aside>')


def article_page(a, lang):
    name = F(a, "nazev", lang)
    ph = photos("clanky", a["slug"])
    caps = captions("clanky", a["slug"])
    ART_PH.clear()
    ART_PH["list"] = ph
    text_html = rich(article_text(a, lang))
    used = ART_PH.get("used", set())
    lead = (f'<figure style="margin:clamp(32px,4vw,56px) 0 0"><img src="{img_url(ph[0])}" alt="{e(caps.get(ph[0].stem, name))}"></figure>'
            if ph and ph[0] not in used else "")
    rest = "".join(f'<figure style="margin:24px 0 0"><img src="{img_url(f)}" alt="{e(caps.get(f.stem, name))}" loading="lazy">'
                   f'{f"<figcaption class=muted>{e(caps.get(f.stem))}</figcaption>" if caps.get(f.stem) else ""}</figure>'
                   for f in ph[1:] if f not in used)
    desc = a.get("seo_popis_cz", "") if lang == "cs" else tr(a.get("seo_popis_cz", "") or a.get("perex_cz", ""), "", lang)
    body = f"""
<article class="wrap detail-head sec">
<p class="label">{e(article_meta(a, lang))}</p>
<h1 class="L" style="margin-top:40px;max-width:20ch">{e(name)}</h1>
<p class="M measure" style="margin:28px 0 0">{e(F(a, "perex", lang))}</p>
{lead}
<div class="prose" style="margin-top:clamp(32px,4vw,56px)">{text_html}</div>
{rest}
{author_box(lang)}
<p style="margin:clamp(40px,5vw,64px) 0 0"><a class="link" href="{url(lang, 'clanky/')}">← {e(T("clanky_zpet", lang))}</a></p>
</article>
"""
    return page(lang, f"clanky/{a['slug']}/", f"{name} — KvalitaMísta", desc or name, body)


# ---------------------------------------------------------------- ostatní
def write(rel, content):
    p = OUT / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")


def control_page():
    rows = "".join(f"<tr><td>{l.upper()}</td><td>{e(cz)}</td><td>{e(t)}</td></tr>"
                   for l, cz, t in sorted(set(translate.used)))
    body = f"""
<section class="wrap detail-head sec">
<p class="label">Kontrola strojových překladů</p>
<h1 class="L" style="margin-top:40px">Přeloženo automaticky</h1>
<p class="measure" style="margin:24px 0 0">Tyto texty v tabulce nemají ruční překlad a web je přeložil přes DeepL.
Pokud chceš překlad opravit, zkopíruj ho do příslušného sloupce EN nebo DE v tabulce a uprav. Ruční text má pak přednost.</p>
<table class="tr"><thead><tr><th>Jazyk</th><th>Česky</th><th>Překlad</th></tr></thead><tbody>{rows}</tbody></table>
</section>
"""
    return page("cs", "preklady/", "Kontrola překladů — KvalitaMísta", "Kontrola překladů", body,
                alternates=False, noindex=True)


def not_found():
    body = f"""
<section class="wrap hero">
<h1 class="L">404</h1>
<div class="hero-sub"><p class="M p0">{e(T("nenalezeno", "cs"))}</p>
<p style="margin:24px 0 0"><a class="link" href="/">{e(T("nenalezeno_odkaz", "cs"))}</a></p></div>
</section>
"""
    return page("cs", "404.html", "404 — KvalitaMísta", "Stránka nenalezena", body, alternates=False, noindex=True)


def copy_remote():
    try:
        from PIL import Image, ImageOps
    except ImportError:
        Image = None
    for src, dest in set(REMOTE):
        if dest.exists():
            continue
        dest.parent.mkdir(parents=True, exist_ok=True)
        try:
            im = ImageOps.exif_transpose(Image.open(src))
            im.thumbnail((2400, 2400))
            im.convert("RGB").save(dest, "JPEG", quality=82, optimize=True, progressive=True)
        except Exception:
            shutil.copy2(src, dest)


def copy_images():
    copy_remote()
    if not IMG.exists():
        return
    try:
        from PIL import Image, ImageOps
    except ImportError:
        Image = None
    for src in IMG.rglob("*"):
        if not src.is_file() or src.suffix.lower() not in PHOTO_EXT:
            continue
        dest = OUT / "obrazky" / src.relative_to(IMG)
        dest.parent.mkdir(parents=True, exist_ok=True)
        if Image and src.suffix.lower() in (".jpg", ".jpeg", ".png", ".webp"):
            try:
                im = ImageOps.exif_transpose(Image.open(src))
                if max(im.size) > 2400:
                    im.thumbnail((2400, 2400))
                if src.suffix.lower() in (".jpg", ".jpeg"):
                    im.convert("RGB").save(dest, quality=82, optimize=True, progressive=True)
                else:
                    im.save(dest, optimize=True)
                continue
            except Exception as ex:
                print(f"! obrázek {src.name} nešlo zmenšit ({ex}) — kopíruji originál")
        shutil.copy2(src, dest)


def main():
    if OUT.exists():
        shutil.rmtree(OUT)
    OUT.mkdir()
    for lang in ("en", "de"):
        prefetch(lang)
    pages = []
    for lang in LANGS:
        write(prefix(lang) + "index.html", home(lang)); pages.append(url(lang))
        for p in PROJECTS:
            write(prefix(lang) + f"projekty/{p['slug']}/index.html", project_page(p, lang))
            pages.append(url(lang, f"projekty/{p['slug']}/"))
        if OFFER:
            write(prefix(lang) + "nabidka/index.html", offer_page(lang)); pages.append(url(lang, "nabidka/"))
        if ARTICLES:
            write(prefix(lang) + "clanky/index.html", articles_index(lang)); pages.append(url(lang, "clanky/"))
            for a in ARTICLES:
                write(prefix(lang) + f"clanky/{a['slug']}/index.html", article_page(a, lang))
                pages.append(url(lang, f"clanky/{a['slug']}/"))
    write("preklady/index.html", control_page())
    write("404.html", not_found())
    shutil.copytree(STATIC, OUT, dirs_exist_ok=True)
    copy_images()
    index = yes(CFG.get("indexovat", "NE"))
    write("robots.txt", "User-agent: *\nAllow: /\nDisallow: /preklady/\n" + f"Sitemap: {SITE_URL}/sitemap.xml\n")
    write("sitemap.xml", '<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
          + "".join(f"<url><loc>{SITE_URL}{u}</loc></url>\n" for u in pages) + "</urlset>\n")
    stav = DATA / "stav.txt"
    lines = stav.read_text(encoding="utf-8") if stav.exists() else "fetch.py neběžel (lokální sestavení)\n"
    lines += f"· sestaveno stránek: {len(pages)}; fotografií: {len(list((OUT / 'obrazky').rglob('*.*'))) if (OUT / 'obrazky').exists() else 0}\n"
    lines += f"· strojových překladů: {len(set(translate.used))}\n"
    if translate.failed:
        lines += f"! DeepL selhal u {len(translate.failed)} textů (zobrazí se česky do příštího sestavení): {translate.last_error}\n"
    write("stav.txt", lines)
    translate.save()
    translate.cleanup()
    print(f"Hotovo: {len(pages)} stránek v site/ (indexování: {'ANO' if index else 'NE'}).")


if __name__ == "__main__":
    main()
