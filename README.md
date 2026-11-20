# reMarkable Kalender

Erzeugt jede Nacht einen verlinkten PDF-Planer aus **Google Tasks** (über [Composio](https://composio.dev)), **Google Calendar** und beliebigen **ICS-Kalendern** und lädt ihn über die **reMarkable Cloud** aufs Tablet. Läuft als Docker-Container auf einem Server (z.B. Hostinger VPS); dein Computer muss dafür nicht eingeschaltet sein. Handschriftliche Notizen bleiben bei jeder Aktualisierung erhalten.

Ursprünglich ein Fork von [usuallycwdillon/remarkable-calendar](https://github.com/usuallycwdillon/remarkable-calendar), inzwischen komplett umgebaut.

## Was im Planer steht

Ein PDF pro Monat, Name z.B. `2026-11 November`, im Ordner `Kalender` auf dem Tablet:

| Seiten | Inhalt |
|---|---|
| 4 × Jahresübersicht | 3 Monate pro Seite, Highlights (`@headline`, Feiertage), Kalenderwochen |
| 1 × Monat | Monatsraster mit Terminen, Links zu Tagen und Wochen |
| 4–6 × Woche | Stundenraster Mo–So mit Terminen |
| 2 × pro Tag | Tagesplan (Termine, Ganztägiges) und Aufgabenseite (Top 3, Aufgaben mit Kästchen, Tagesrückblick) |
| 10 × Notizen | Punktraster |

- **Aufgaben aus Google Tasks** erscheinen am Fälligkeitstag. Offene Aufgaben aus der Vergangenheit wandern auf heute (mit «überfällig»), erledigte bleiben angekreuzt an ihrem Tag.
- Aufgaben, die gleich heissen wie ein Termin am selben Tag, werden nicht doppelt gezeigt.
- `@headline` im Titel oder in den Notizen einer Aufgabe bzw. in der Beschreibung eines Termins setzt den Eintrag zusätzlich in die Jahresübersicht.
- Die Seitenzahl eines Monats ist fix. Deshalb bleibt deine Handschrift beim Aktualisieren auf der richtigen Seite.
- Erzeugt werden jede Nacht der aktuelle Monat und die nächsten Monate (`MONTHS_AHEAD`, Standard 3). Vergangene Monate werden nicht mehr verändert.

## Einrichtung

### 1. Composio und Google Tasks

1. Bei [dashboard.composio.dev](https://dashboard.composio.dev) unter *Settings → API Keys* einen API-Key erzeugen → `COMPOSIO_API_KEY`.
2. Unter *Connected Accounts* das Toolkit **Google Tasks** verbinden (optional auch **Google Calendar**).
3. Die **User-ID**, unter der die Verbindung hängt, als `COMPOSIO_USER_ID` übernehmen.
4. Optional `GOOGLE_TASKS_LISTS` auf bestimmte Listen beschränken, z.B. `DO,INBOX` (Namen oder IDs).

### 2. Kalender

Eine oder beide Varianten:

- **Google Calendar über Composio:** `GOOGLE_CALENDAR_IDS=primary` (weitere Kalender-IDs kommagetrennt). Feiertage z.B. mit `HOLIDAY_CALENDAR_IDS=de.ch#holiday@group.v.calendar.google.com`.
- **ICS-Links:** `ICS_URLS=https://…` für iCloud, Outlook oder die geheime iCal-Adresse von Google. Feiertagsfeeds unter `HOLIDAY_ICS_URLS`.

### 3. reMarkable Cloud

1. Auf [my.remarkable.com/device/desktop/connect](https://my.remarkable.com/device/desktop/connect) einen Einmalcode erzeugen.
2. Einmal anmelden:
   ```bash
   docker compose run --rm planner auth ABCD1234
   ```
   Alternativ `RMAPI_ONE_TIME_CODE=ABCD1234` setzen: der Container meldet sich beim nächsten Start an, falls noch kein Token gespeichert ist.
3. Das Token liegt danach im Volume (`/data/rmapi.conf`) und bleibt bei Updates erhalten.

Der Upload nutzt [rmapi](https://github.com/ddvk/rmapi), ein Community-Tool für die inoffizielle Cloud-Schnittstelle von reMarkable. Developer Mode ist nicht nötig. Ändert reMarkable die Schnittstelle, kann der Upload bis zu einem rmapi-Update ausfallen; die PDFs liegen dann trotzdem unter `/data/output`.

Wer den Planer zuhause im selben Netz wie das Tablet laufen lässt, kann stattdessen `SYNC_MODE=ssh` mit `REMARKABLE_HOST` und `REMARKABLE_PASSWORD` nutzen (beim Paper Pro mit Developer Mode).

### 4. Starten

```bash
cp .env.example .env    # Werte eintragen
docker compose up -d --build
docker compose run --rm planner check   # testet Quellen und Login
docker compose logs -f
```

Der Container läuft dauerhaft und erzeugt den Planer täglich zu den Zeiten in `SYNC_TIMES` (Standard 04:30, Zeitzone `TZ`), mit `RUN_ON_START=true` zusätzlich direkt nach dem Start.

**Deployment auf Hostinger:** siehe [deploy/HOSTINGER.md](deploy/HOSTINGER.md).

## Befehle

| Befehl | Zweck |
|---|---|
| `serve` | Standard im Container: läuft dauerhaft, täglich zu `SYNC_TIMES` |
| `run` | einmal erzeugen und hochladen |
| `generate` | nur PDFs erzeugen (`/data/output`) |
| `check` | Quellen und reMarkable-Login testen |
| `auth [CODE]` | einmalige Anmeldung bei der reMarkable Cloud |
| `healthcheck` | Exit 1, wenn der letzte Lauf fehlschlug oder älter als 26 h ist (Docker-Healthcheck) |

Aufruf im Container: `docker compose run --rm planner <befehl>`, lokal: `python -m planner <befehl>`.

## Konfiguration

Alle Einstellungen sind in [`.env.example`](.env.example) beschrieben. Die wichtigsten:

| Variable | Standard | Bedeutung |
|---|---|---|
| `PAGE_FORMAT` | `remarkable` | `remarkable` (rM1/rM2), `paperpro`, `move`, `a4`, `a5`, `letter` |
| `PLANNER_LANGUAGE` | `de` | `de` oder `en` |
| `MONTHS_AHEAD` | `3` | Anzahl Monate ab heute, die jede Nacht neu erzeugt werden |
| `DAY_START_HOUR` / `DAY_END_HOUR` | `6` / `22` | Zeitraster der Tages- und Wochenseiten |
| `SYNC_TIMES` | `04:30` | Uhrzeiten, kommagetrennt |
| `HEALTHCHECK_URL` | – | z.B. healthchecks.io; bei Fehlern wird `…/fail` aufgerufen |

Fällt eine Quelle aus (z.B. Composio nicht erreichbar), wird der Planer trotzdem mit den übrigen Daten erzeugt. Der Lauf zählt dann als fehlerhaft, damit die Überwachung anschlägt.

## Entwicklung

```bash
pip install -r requirements.txt -r requirements-dev.txt
python -m pytest
DATA_DIR=./data SYNC_MODE=none python -m planner generate
```

Struktur:

```
planner/
  __main__.py        Befehle und Zeitplan
  config.py          Einstellungen aus der Umgebung
  collect.py         Daten laden, nach Tag gruppieren, Duplikate und Überfälliges
  generator.py       ein PDF pro Monat
  pages.py           Seitenlayouts
  i18n.py            Deutsch / Englisch
  sources/           composio.py, google_tasks.py, google_calendar.py, ics.py
  sync/              rmcloud.py (rmapi), ssh.py
tests/
deploy/              Hostinger-Compose-Datei und Anleitung
```

## Lizenz

MIT, siehe [license.txt](license.txt). Das Docker-Image enthält zusätzlich `rmapi` (AGPL-3.0) als eigenständiges Programm.
