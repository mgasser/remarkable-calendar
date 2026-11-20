# Deployment auf dem Hostinger VPS

Der Planer ist ein einzelner Container ohne offene Ports. Er passt neben bestehende Projekte im Docker Manager und braucht wenig Ressourcen (ein Lauf dauert je nach Datenmenge unter einer Minute).

Voraussetzungen: VPS mit Docker (Hostinger-Vorlage «Docker» oder Docker Manager in hPanel), die Werte aus [`.env.example`](../.env.example) und ein frischer reMarkable-Einmalcode.

## Variante A: Docker Manager in hPanel (ohne SSH)

Der Docker Manager baut keine Images. [`hostinger-compose.yml`](hostinger-compose.yml) startet deshalb das offizielle Image `python:3.12-slim` und lädt bei jedem Start [`bootstrap.sh`](bootstrap.sh), den Code des Branches `GIT_REF` und `rmapi` (mit Prüfsumme) von GitHub.

1. hPanel → **VPS** → **Docker Manager** → Projekt `remarkable-calendar` (oder neu anlegen und den Inhalt von `hostinger-compose.yml` einfügen).
2. Unter **Environment** ergänzen:
   ```
   COMPOSIO_API_KEY=...
   COMPOSIO_USER_ID=...
   GOOGLE_TASKS_LISTS=DO,INBOX
   GOOGLE_CALENDAR_IDS=primary
   RMAPI_ONE_TIME_CODE=abcd1234
   ```
   Solange die Änderungen nicht in `main` gemergt sind, muss `GIT_REF=claude/epic-cerf-y6sgqr` gesetzt bleiben.
3. Speichern und neu deployen. Den Einmalcode erst direkt davor erzeugen.
4. In den Logs prüfen: `reMarkable Cloud: logged in` und `Uploaded … to /Kalender`.
5. `RMAPI_ONE_TIME_CODE` wieder leeren. Das Token liegt im Volume und bleibt bei Neustarts erhalten.

**Update:** Container neu starten. Er lädt dabei den aktuellen Stand von `GIT_REF`.

## Variante B: per SSH

```bash
ssh root@srv2102762.hstgr.cloud
git clone https://github.com/mgasser/remarkable-calendar.git /opt/remarkable-calendar
cd /opt/remarkable-calendar
cp .env.example .env && chmod 600 .env && nano .env
docker compose up -d --build
docker compose run --rm planner auth ABCD1234
docker compose run --rm planner check
docker compose run --rm planner run
```

**Update:**

```bash
cd /opt/remarkable-calendar && git pull && docker compose up -d --build
```

## Betrieb

| Aufgabe | Befehl / Ort |
|---|---|
| Logs | Docker Manager → Projekt → Logs, oder `docker compose logs -f` |
| Sofort neu erzeugen | `docker compose run --rm planner run` |
| Status des letzten Laufs | `docker compose exec planner cat /data/status.json` |
| Gesundheitszustand | Container wird «unhealthy», wenn der letzte Lauf fehlschlug oder älter als 26 h ist |
| Benachrichtigung | `HEALTHCHECK_URL` auf z.B. einen healthchecks.io-Check setzen |
| Neuer reMarkable-Login | Einmalcode erzeugen, `docker compose run --rm planner auth CODE` |

## Fehlersuche

| Meldung | Ursache und Lösung |
|---|---|
| `Not logged in to reMarkable Cloud` | Noch kein Token. Einmalcode erzeugen und `auth` ausführen bzw. `RMAPI_ONE_TIME_CODE` setzen. |
| `failed to create a new device token` | Code falsch oder abgelaufen. Neuen Code erzeugen. |
| `GOOGLETASKS_…: HTTP 401/403` | `COMPOSIO_API_KEY` falsch. |
| `GOOGLETASKS_…: … no connection` o.ä. | Unter dieser `COMPOSIO_USER_ID` ist Google Tasks nicht verbunden, oder die Verbindung ist abgelaufen. Im Composio-Dashboard neu verbinden. |
| Termine fehlen | `GOOGLE_CALENDAR_IDS` leer oder Google Calendar in Composio nicht verbunden. `check` zeigt jede Quelle einzeln. |
| Handschrift auf falscher Seite | Nur nach Änderung von `PAGE_FORMAT`, `NOTES_PAGES` oder des Codes. Bei solchen Änderungen den Ordner auf dem Tablet vorher umbenennen. |
