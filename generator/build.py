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

import csv, html, json, os, re, shutil, sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import translate  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
IMG = ROOT / "obrazky"
STATIC = Path(__file__).resolve().parent / "static"
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
    "foto_autor": "Foto",
    "jazyk": "Jazyk",
    "hlavni_menu": "Hlavní menu",
    "odkazy": "Odkazy",
    "uvod_logo": "KvalitaMísta – úvod",
    "nenalezeno": "Stránka nenalezena.",
    "nenalezeno_odkaz": "Zpět na úvod",
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
STEPS = sorted([r for r in read_csv("kroky") if yes(r.get("publikovat", "ANO"))], key=lambda r: num(r.get("poradi")))
PROJECTS = sorted([r for r in read_csv("projekty") if yes(r.get("publikovat")) and r.get("slug")], key=lambda r: num(r.get("poradi")))
ARTICLES = sorted([r for r in read_csv("clanky") if yes(r.get("publikovat")) and r.get("slug")],
                  key=lambda r: r.get("datum", ""), reverse=True)


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
def e(s):
    return html.escape(s or "", quote=True)


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
    return "/obrazky/" + p.relative_to(IMG).as_posix()


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
    return None


LOGO = ('<span aria-hidden="true">KVALITA<span class="logo-dash"></span><br>'
        'M<span class="logo-i">I</span>STA</span>')


# ---------------------------------------------------------------- kostra stránky
def page(lang, path, title, desc, body, alternates=True, noindex=None):
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
    items += [("menu_onas", url(lang) + "#o-nas"), ("menu_kontakt", url(lang) + "#kontakt")]
    menu = "".join(f'<li><a href="{h}">{e(T(k, lang))}</a></li>' for k, h in items)
    accent = CFG.get("barva_akcentu", "") or "#ECE48A"
    links = ""
    for i in (1, 2, 3, 4):
        t, u = CFG.get(f"odkaz_{i}_text", ""), CFG.get(f"odkaz_{i}_url", "")
        if t and u:
            links += f'<a href="{e(u)}">{e(t)}</a>\n'
    return f"""<!doctype html>
<html lang="{lang}">
<head>
<meta charset="utf-8">
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
<link rel="stylesheet" href="/styl.css">
<style>:root{{--accent:{e(accent)}}}</style>
</head>
<body>
<a class="skip" href="#obsah">{e(T("skip", lang))}</a>
<div class="strip"></div>
<header>
<div class="wrap head">
<nav class="lang" aria-label="{e(T('jazyk', lang))}">{langnav}</nav>
<div class="row">
<a class="logo" href="{url(lang)}" aria-label="{e(T('uvod_logo', lang))}">{LOGO}</a>
<details class="menu">
<summary aria-label="{e(T('menu_label', lang))}"><span></span><span></span><span></span></summary>
<nav aria-label="{e(T('hlavni_menu', lang))}" onclick="if(event.target.closest('a'))this.closest('details').open=false"><ul>{menu}</ul></nav>
</details>
</div>
</div>
</header>
<main id="obsah">
{body}
</main>
<footer>
<div class="foot"><div class="wrap">
<p class="foot-logo"><span class="sr">KvalitaMísta</span>{LOGO}</p>
<p class="foot-claim M">{e(T("paticka_heslo", lang))}</p>
</div></div>
<nav class="wrap foot-links" aria-label="{e(T('odkazy', lang))}">
{links}</nav>
</footer>
</body>
</html>
"""


# ---------------------------------------------------------------- úvodní stránka
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
    hero_photo = cfg_photo("hlavni_foto")
    portrait = cfg_photo("portret")

    steps = "".join(
        f'<li><span class="L" style="display:block">{i:02d}</span>'
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
    onas_url = CFG.get("onas_url", "")
    imprint_ids = " · ".join(x for x in (f"IČO {CFG.get('ico')}" if CFG.get("ico") else "",
                                         f"DIČ {CFG.get('dic')}" if CFG.get("dic") else "") if x)
    addr = "<br>".join(e(CFG.get(k)) for k in ("adresa_1", "adresa_2") if CFG.get(k))

    body = f"""
<section class="wrap hero">
<h1 class="L">{br(T("uvod_nadpis", lang))}</h1>
<div class="hero-sub">
<p class="b p0">{e(T("uvod_stitek", lang))}</p>
<p class="M" style="margin:12px 0 0;max-width:36ch">{e(T("uvod_text", lang))}</p>
<p style="margin:32px 0 0"><a class="btn" href="#kontakt">{e(T("tlacitko", lang))}</a></p>
</div>
</section>

{f'<div class="photo"><img src="{img_url(hero_photo)}" alt="{e(T("foto_popis", lang))}"></div>' if hero_photo else ''}

<section class="wrap sec">
<p class="label">{e(T("situace_stitek", lang))}</p>
<div class="split">
<h2 class="L">{e(T("situace_nadpis", lang))}</h2>
<div>
<p class="M p0" style="max-width:34ch">{e(T("situace_text", lang))}</p>
<p class="b" style="margin:28px 0 0">{e(T("situace_uvod_seznamu", lang))}</p>
{dash_list("situace", lang)}
</div>
</div>
</section>

<section id="budovy" class="wrap sec cont">
<p class="label">{e(T("budovy_stitek", lang))}</p>
<div class="split">
<h2 class="L">{e(T("budovy_nadpis", lang))}</h2>
<div>
<p class="M p0" style="max-width:34ch">{e(T("budovy_text", lang))}</p>
<p class="measure" style="margin:28px 0 0">{e(T("budovy_text_2", lang))}</p>
{dash_list("budovy", lang)}
</div>
</div>
</section>

<section id="postup" class="accent">
<div class="wrap sec">
<p class="label">{e(T("postup_stitek", lang))}</p>
<h2 class="L" style="margin-top:40px">{br(T("postup_nadpis", lang))}</h2>
<ol class="steps">{steps}</ol>
<p class="M" style="margin:clamp(48px,6vw,72px) 0 0">{e(T("postup_zaver", lang))}</p>
{f'<p class="measure" style="margin:16px 0 0">{e(spec)}</p>' if spec else ''}
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
<p class="M" style="margin:24px 0 0">{e(T("kontakt_text", lang))}</p>
<div class="big-contact">
{f'<a href="tel:{tel}">{e(phone)}</a>' if phone else ''}
{f'<a href="mailto:{e(mail)}">{e(mail)}</a>' if mail else ''}
</div>
{f'<p style="margin:36px 0 0"><a class="btn" href="mailto:{e(mail)}">{e(T("tlacitko", lang))}</a></p>' if mail else ''}
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
        cap = caps.get(f.stem, "")
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


def article_page(a, lang):
    name = F(a, "nazev", lang)
    ph = photos("clanky", a["slug"])
    caps = captions("clanky", a["slug"])
    lead = (f'<figure style="margin:clamp(32px,4vw,56px) 0 0"><img src="{img_url(ph[0])}" alt="{e(caps.get(ph[0].stem, name))}"></figure>'
            if ph else "")
    rest = "".join(f'<figure style="margin:24px 0 0"><img src="{img_url(f)}" alt="{e(caps.get(f.stem, name))}" loading="lazy">'
                   f'{f"<figcaption class=muted>{e(caps.get(f.stem))}</figcaption>" if caps.get(f.stem) else ""}</figure>'
                   for f in ph[1:])
    desc = a.get("seo_popis_cz", "") if lang == "cs" else tr(a.get("seo_popis_cz", "") or a.get("perex_cz", ""), "", lang)
    body = f"""
<article class="wrap detail-head sec">
<p class="label">{e(article_meta(a, lang))}</p>
<h1 class="L" style="margin-top:40px;max-width:20ch">{e(name)}</h1>
<p class="M measure" style="margin:28px 0 0">{e(F(a, "perex", lang))}</p>
{lead}
<div class="prose" style="margin-top:clamp(32px,4vw,56px)">{paras(F(a, "text", lang))}</div>
{rest}
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


def copy_images():
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
    write("stav.txt", lines)
    translate.save()
    translate.cleanup()
    print(f"Hotovo: {len(pages)} stránek v site/ (indexování: {'ANO' if index else 'NE'}).")


if __name__ == "__main__":
    main()
