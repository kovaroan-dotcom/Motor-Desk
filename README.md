# Motor Desk — Setup

Tři soubory, GitHub repozitář, 10 minut.

## Soubory

```
motor-desk/
├── generate.py                      ← Python skript (stahuje RSS, generuje HTML)
├── template.html                    ← design šablona
├── motor-desk.html                  ← výsledný web (generuje se automaticky)
└── .github/
    └── workflows/
        └── update.yml               ← GitHub Actions (spouští se 1. v měsíci)
```

## Instalace

### 1. Vytvoř GitHub repozitář

Na github.com → New repository → název např. `motor-desk` → **Public** (nutné pro GitHub Pages zdarma).

### 2. Nahraj soubory

```bash
git clone https://github.com/TVOJE_JMENO/motor-desk.git
cd motor-desk

# nakopíruj generate.py, template.html
# vytvoř složku .github/workflows/ a nakopíruj update.yml

git add .
git commit -m "Initial setup"
git push
```

### 3. Zapni GitHub Pages

Repozitář → **Settings** → **Pages** → Source: `Deploy from a branch` → Branch: `main` → Folder: `/ (root)` → **Save**

Za pár minut bude web live na:
`https://TVOJE_JMENO.github.io/motor-desk/motor-desk.html`

### 4. První spuštění (vygeneruje HTML hned)

Repozitář → záložka **Actions** → `Update Motor Desk` → **Run workflow** → **Run workflow**

Za ~2 minuty se v repozitáři objeví `motor-desk.html` a web je živý.

---

## Automatická aktualizace

GitHub Actions spustí `generate.py` automaticky **2× denně — v 5:00 a 13:00 UTC** (7:00 a 15:00 CET).
Skript stáhne RSS ze 43 zdrojů, vezme max. 5 článků za posledních 30 dní z každého zdroje a přegeneruje `motor-desk.html` i `archive.html`.

Spustit ručně kdykoliv: **Actions** → `Update Motor Desk` → **Run workflow**

---

## Přidání / odebrání zdrojů

Edituj seznam `SOURCES` v `generate.py`:

```python
{"name": "Nový zdroj", "url": "https://example.com/rss", "region": "world", "cat": "ev"},
```

- `region`: `"world"`, `"europe"`, `"china"`, `"cz"`, `"ctx-world"`, `"ctx-eu"` nebo `"ctx-cz"`
- `cat`: `"ev"`, `"auto"`, `"autonomy"`, `"policy"`, `"industry"`, `"tech"`, `"ai"`, `"politics"`, `"economy"`, `"culture"` (automaticky přepsáno podle klíčových slov v titulku/popisku)

## Změna počtu článků na zdroj

V `generate.py` nahoře:

```python
ARTICLES_PER_SOURCE = 5   ← změň na libovolné číslo
```
