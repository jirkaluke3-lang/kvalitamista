# KvalitaMísta — web

Statický web **kvalitamista.cz** generovaný z Google tabulky a složky na Google Disku.
Běží zdarma na GitHub Pages.

## Jak upravit obsah
- **Texty, kroky, projekty, články:** Google tabulka *KvalitaMista-obsah-webu*
  (složka `web-kvalitamista` na Disku). Návod je v listu **NAVOD**.
- **Fotografie:** `web-kvalitamista/projekty/<slug>/`, `clanky/<slug>/`,
  `nastaveni/` (hlavni.jpg, portret.jpg). Soubory pojmenuj 01, 02, 03…
- **Kdy se změna projeví:** web se sám obnovuje každou hodinu. Hned to jde
  přes záložku **Actions → Sestavení a nasazení webu → Run workflow**.

## Jazyky
CZ / EN / DE. Prázdné buňky EN a DE se přeloží automaticky přes DeepL,
ruční text má vždy přednost. Přehled strojových překladů: `/preklady/`.
Odborné pojmy drží `generator/glosar.csv`.

## Vyhledávače
Dokud v listu NASTAVENI není řádek `indexovat` = `ANO`, má web nastaveno
`noindex` (vyhledávače ho nezařadí).

## Nastavení (Settings → Secrets and variables → Actions)
- `GDRIVE_API_KEY` – klíč Google Cloud omezený na Drive API
- `DEEPL_API_KEY` – klíč DeepL API
ID tabulky a složky jsou ve `.github/workflows/deploy.yml`.

## Lokální náhled
```
python3 generator/build.py      # použije data/*.csv
python3 -m http.server -d site  # otevři http://localhost:8000
```

## Fonty
Ciutadella (Emtype Foundry), webová licence k dispozici.

## Kontaktní formulář
Zprávy z formuláře se ukládají do soukromé Google tabulky a chodí e-mailem.
Skript a postup nasazení: `formular/apps-script.gs`. Adresu nasazené webové
aplikace vlož do listu NASTAVENI jako `formular_url`. Dokud adresa chybí,
formulář po odeslání otevře e-mailového klienta s předvyplněnou zprávou.

## Popisky fotografií
Text za prvním podtržítkem v názvu souboru se zobrazí jako popisek:
`hlavni_Foto Petra Kunarova_Bern.jpg` → „Foto Petra Kunarova · Bern“.
Funguje pro hlavní fotku i galerie projektů (`01_Pohled z návsi.jpg`).
