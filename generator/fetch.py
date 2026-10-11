#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Stáhne obsah z Googlu PŘED sestavením webu:
  • listy Google tabulky  -> data/*.csv
  • fotografie z Google Disku -> obrazky/…

Proměnné prostředí (na GitHubu v nastavení repozitáře):
  GSHEET_ID       – ID Google tabulky (z její adresy)
  GDRIVE_ROOT_ID  – ID složky web-kvalitamista na Disku
  GDRIVE_API_KEY  – API klíč z Google Cloud (Drive API) – TAJNÝ (secret)

Když proměnné chybí, skript nic nedělá a build použije data/*.csv
a obrazky/… z repozitáře (režim náhledu). Jen standardní knihovna.
"""

import os, sys, json, shutil, urllib.parse, urllib.request, urllib.error, builtins
from datetime import datetime, timezone
from pathlib import Path

LOG = []


def print(*a, **k):  # noqa: A001 – zapisuje i do data/stav.txt (stránka /stav.txt)
    LOG.append(" ".join(str(x) for x in a))
    builtins.print(*a, **k)

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
IMG = ROOT / "obrazky"

GSHEET_ID = os.environ.get("GSHEET_ID", "").strip()
ROOT_ID = os.environ.get("GDRIVE_ROOT_ID", "").strip()
API_KEY = os.environ.get("GDRIVE_API_KEY", "").strip()

# list v tabulce -> soubor CSV
SHEETS = {"NASTAVENI": "nastaveni", "TEXTY": "texty", "SEZNAMY": "seznamy",
          "KROKY": "kroky", "PROJEKTY": "projekty", "CLANKY": "clanky"}
SECTION_WITH_SLUGS = ["projekty", "clanky"]   # podsložky podle slugu
SECTION_FLAT = ["nastaveni"]                   # obrázky přímo ve složce

IMG_EXT = (".jpg", ".jpeg", ".png", ".webp", ".avif", ".gif", ".txt")
MIME_EXT = {"image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp",
            "image/avif": ".avif", "image/gif": ".gif"}


def fetch(url, binary=False):
    req = urllib.request.Request(url, headers={"User-Agent": "kvalitamista-build/1.0"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return r.read() if binary else r.read().decode("utf-8")


def pull_sheet():
    if not GSHEET_ID:
        print("· GSHEET_ID není nastaven — použijí se data/*.csv z repozitáře.")
        return
    DATA.mkdir(exist_ok=True)
    for sheet, fname in SHEETS.items():
        url = (f"https://docs.google.com/spreadsheets/d/{GSHEET_ID}"
               f"/gviz/tq?tqx=out:csv&headers=1&sheet={urllib.parse.quote(sheet)}")
        try:
            text = fetch(url)
            if text.lstrip().startswith("<"):
                raise RuntimeError("tabulka nevrátila CSV (je nasdílená 'Kdokoli s odkazem'?)")
            (DATA / f"{fname}.csv").write_text(text, encoding="utf-8")
            print(f"· tabulka {sheet} -> data/{fname}.csv")
            if sheet == "NASTAVENI":
                import csv, io
                keys = [r[0].strip() for r in csv.reader(io.StringIO(text))][1:]
                print(f"  klíče NASTAVENI: {', '.join(k for k in keys if k)}")
        except Exception as ex:
            print(f"! list {sheet} se nepodařilo stáhnout: {describe(ex)}")


def drive_list(folder_id):
    q = urllib.parse.quote(f"'{folder_id}' in parents and trashed=false")
    url = (f"https://www.googleapis.com/drive/v3/files?q={q}&key={API_KEY}"
           f"&fields=files(id,name,mimeType)&pageSize=1000&orderBy=name"
           f"&supportsAllDrives=true&includeItemsFromAllDrives=true")
    return json.loads(fetch(url)).get("files", [])


def drive_download(file_id, dest):
    url = (f"https://www.googleapis.com/drive/v3/files/{file_id}"
           f"?alt=media&key={API_KEY}&supportsAllDrives=true")
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(fetch(url, binary=True))


def is_folder(f):
    return f["mimeType"] == "application/vnd.google-apps.folder"


def wanted_name(fl):
    """Název, pod kterým se soubor uloží; chybí-li přípona, doplní se podle typu."""
    name = fl["name"]
    if name.lower().endswith(IMG_EXT):
        return name
    ext = MIME_EXT.get(fl.get("mimeType", ""))
    return name + ext if ext else None


def pull_folder(folder_id, dest_dir, label):
    got, skipped, dup = 0, [], []
    for fl in drive_list(folder_id):
        if is_folder(fl):
            continue
        name = wanted_name(fl)
        if name is None:
            skipped.append(fl["name"]); continue
        dest = dest_dir / name
        if dest.exists():
            dup.append(fl["name"]); continue
        drive_download(fl["id"], dest)
        got += 1
    msg = f"· Disk {label}: staženo {got} souborů"
    if skipped:
        msg += f" | PŘESKOČENO (nepodporovaný formát, převeďte na JPG): {', '.join(skipped)}"
    if dup:
        msg += f" | DUPLICITNÍ NÁZEV (přejmenujte na Disku): {', '.join(dup)}"
    print(msg)


def pull_drive():
    if not (ROOT_ID and API_KEY):
        print("· GDRIVE_ROOT_ID / GDRIVE_API_KEY není nastaven — použijí se obrazky/ z repozitáře.")
        return
    sections = {f["name"].lower(): f["id"] for f in drive_list(ROOT_ID) if is_folder(f)}
    for sec in SECTION_WITH_SLUGS + SECTION_FLAT:
        d = IMG / sec
        if d.exists():
            shutil.rmtree(d)
    for sec in SECTION_WITH_SLUGS:
        if sec not in sections:
            print(f"· na Disku chybí složka '{sec}' — přeskakuji.")
            continue
        for sub in drive_list(sections[sec]):
            if is_folder(sub):
                slug = sub["name"].strip()
                pull_folder(sub["id"], IMG / sec / slug, f"{sec}/{slug}")
    for sec in SECTION_FLAT:
        if sec in sections:
            pull_folder(sections[sec], IMG / sec, f"{sec}/")


def describe(ex):
    if isinstance(ex, urllib.error.HTTPError):
        try:
            body = ex.read().decode("utf-8", "replace")[:400]
        except Exception:
            body = ""
        return f"HTTP {ex.code}: {body}"
    return str(ex)


if __name__ == "__main__":
    print("Načítám obsah z Googlu… " + datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"))
    print(f"· klíč Google Drive: {'nastaven' if API_KEY else 'CHYBÍ (secret GDRIVE_API_KEY)'}")
    print(f"· klíč DeepL: {'nastaven' if os.environ.get('DEEPL_API_KEY') else 'chybí (secret DEEPL_API_KEY)'}")
    try:
        pull_sheet()
    except Exception as ex:
        print(f"! chyba při načítání tabulky: {describe(ex)}")
    try:
        pull_drive()
    except Exception as ex:
        print(f"! chyba při načítání Disku: {describe(ex)}")
    print("Hotovo.")
    DATA.mkdir(exist_ok=True)
    (DATA / "stav.txt").write_text("\n".join(LOG) + "\n", encoding="utf-8")
