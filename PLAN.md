# Plan: Review, CalSync-Vergleich und Deployment auf Hostinger

Stand: 19.11.2026 · **Update 20.11.2026:** Phase 1 ist umgesetzt (Paket `planner/`, Google Tasks und Calendar über Composio, ICS, Upload über die reMarkable Cloud mit `rmapi`, Docker, Tests). Anleitung für Phase 2–5: [`deploy/HOSTINGER.md`](deploy/HOSTINGER.md).

## 1. Kurzfazit

Das Repo erzeugt brauchbare Monats-PDFs (Jahres-, Monats-, Wochen-, Tagesseiten mit Links) aus Google Calendar und Todoist. Es ist aber in der jetzigen Form **nicht auf einem Hostinger-Server lauffähig**:

1. **Der Sync lädt nie etwas hoch.** Der Generator schreibt nach `planner_2026/`, der Upload sucht in `2026_Planner/` (`generate_and_sync.py:20` vs. `cal_generator.py:84`).
2. **Der Server erreicht das Tablet nicht.** Der Upload läuft per SSH ins lokale Netz (`10.11.99.1` bzw. LAN-IP). Ein VPS im Rechenzentrum kommt dort nicht hin.
3. **Google-Login braucht einen Browser.** `run_local_server` (`api_client.py:84`) funktioniert headless nicht.

Mit den Korrekturen aus Abschnitt 4 und einem Wechsel auf reMarkable-Cloud-Upload ist ein täglicher Lauf auf dem vorhandenen VPS realistisch.

## 2. Code-Review

### Blocker

| # | Befund | Stelle |
|---|---|---|
| B1 | Upload-Verzeichnis falsch (`{year}_Planner` statt `planner_{year}`), Sync meldet nur «skipped» | `generate_and_sync.py:20` |
| B2 | SSH-Sync setzt gleiches Netz wie das Tablet voraus, dazu Developer Mode auf Paper Pro / Move | `sync_to_remarkable.py` |
| B3 | OAuth-Flow öffnet lokalen Browser, kein Headless-Weg | `api_client.py:84` |
| B4 | Google und Todoist sind laut README optional, werden aber immer initialisiert. Ohne Token bricht der Lauf ab | `data_processor.py:9-10` |
| B5 | Todoist REST v2 ist abgekündigt (Nachfolger: `/api/v1`, Filter über `/tasks/filter?query=`). Beim ersten Lauf prüfen, ob der Endpunkt noch antwortet | `api_client.py:21` |

### Fehler mit falschem Ergebnis

| # | Befund | Stelle |
|---|---|---|
| F1 | Tagesgrenzen werden in UTC abgefragt, nicht in Europe/Zurich. Termine zwischen 00:00 und 01:00/02:00 landen am falschen Tag, Container hat keine `TZ` | `api_client.py:99-100` |
| F2 | Keine Pagination. Die Jahresabfrage endet nach 250 Terminen, spätere `@headline`-Einträge fehlen | `api_client.py:103` |
| F3 | Nur Kalender `primary`, Feiertage fest auf USA | `data_processor.py:113` |
| F4 | Jeder Lauf erzeugt alle 12 Monate neu. Todoist liefert nur offene Aufgaben, erledigte verschwinden also rückwirkend aus vergangenen Tagen | `cal_generator.py:87-91` |
| F5 | Jahr ist fest `2026` (Default und Compose). Ab 1.1.2027 läuft der Job ins Leere | `docker-compose.yml:18` |
| F6 | Zugriffstoken, das im Container erneuert wird, geht verloren (kein Volume). Steht die Google-App auf «Testing», läuft das Refresh-Token nach 7 Tagen ab | `dockerfile:9-10`, `config.py` |

### Betrieb und Sicherheit

- Rund 1100 Google- und 365 Todoist-Aufrufe pro Lauf (3 bzw. 1 pro Tag, Jahresübersicht 12-mal). Eine Abfrage pro Jahr und Gruppierung im Speicher reicht.
- `credentials.json` und `token.json` werden ins Image kopiert (`dockerfile:9-10`).
- SSH ohne Host-Key-Prüfung (`AutoAddPolicy`, `sync_to_remarkable.py:34`), Root-Passwort in `.env`.
- Ein einzelner API-Fehler bricht den ganzen Lauf ab; mehrere `except:` ohne Typ verschlucken Fehler.
- Keine Tests (`test_api_data.py` ist ein manuelles Skript), Abhängigkeiten ohne Versionen.
- README beschreibt Volumes, die im Compose-File nicht existieren.
- Format US Letter, Sprache Englisch, Zeitraster fest 5–23 Uhr.

## 3. Vergleich mit CalSync (einkpads.com)

| CalSync-Funktion | Dieses Repo | Lücke |
|---|---|---|
| Google Calendar | ja, nur `primary` | mehrere Kalender |
| Apple iCloud, Outlook, CalDAV, ICS-Dateien | nein | ICS-Feed deckt alle drei ab |
| Mehrere Kalender kombinieren | nein | klein |
| Todoist | ja (alte API) | API v1 |
| Microsoft To Do, Google Tasks, CalDAV-Tasks | nein | je ein Client |
| Task Markup (Haken mit Stift schliesst Aufgabe in der App) | nein | gross: Strichdaten vom Tablet lesen und erkennen |
| Sync über reMarkable Cloud, ohne Developer Mode | nein, nur SSH | mittel (rmapi) |
| Handschrift bleibt beim Update | ja, PDF wird unter gleicher ID ersetzt | bei Cloud-Upload neu zu prüfen |
| Jahres-, Monats-, freie Zeiträume | nur 12 Monats-PDFs pro Jahr | klein |
| Cover mit Farbe, Sprung zu «heute» | nein | klein |
| Agenda auf dem Sleep-Screen | nein | mittel, geht nur per SSH |
| Mehrere Tablets / Profile | ein Gerät per `.env` | klein |
| Sprachen inkl. Deutsch, lokale Datumsformate | nur Englisch | klein |
| Alle reMarkable-Modelle, Universal Mode (reines PDF) | PDF ist universell, Layout aber Letter | Seitenformat pro Gerät |
| Desktop-App Mac/Windows/Linux, kein Setup | CLI und Docker | bewusst nicht Ziel |
| Sync bei ausgeschaltetem Computer (nur CalSync Pro) | ja, sobald es auf dem VPS läuft | **Vorteil dieses Ansatzes** |

Was das Repo zusätzlich hat: `@headline`-Einträge in der Jahresübersicht, Abgleich Todoist/Kalender gegen Duplikate, Wochen-Zeitbudget, 10 Notizseiten pro Monat.

Einordnung: CalSync kostet einmalig 47 USD. Der Eigenbau lohnt sich für das eigene Layout und den serverseitigen Lauf ohne laufenden Rechner, nicht um Task Markup nachzubauen.

## 4. Deployment-Plan Hostinger

### Ausgangslage

- Im Konto vorhanden: **ein VPS «KVM 2»** (2 vCPU, 8 GB RAM, 100 GB, Ubuntu 26.04, `srv2102762.hstgr.cloud`, läuft, keine Firewall-Gruppe zugewiesen).
- Kein Webhosting-Paket. Wäre auch ungeeignet: der Job ist ein geplanter Python/Docker-Lauf ohne Website.
- Ziel: Docker-Compose-Job auf dem VPS, täglich 04:30 Europe/Zurich, Upload über die reMarkable Cloud.

### Phase 1 – Code deploybar machen (ca. 1 Tag)

1. B1 beheben, Jahr aus dem aktuellen Datum ableiten, im Dezember zusätzlich das Folgejahr erzeugen (F5).
2. Google und Todoist wirklich optional machen (B4), Todoist auf API v1 (B5).
3. Daten einmal pro Jahr laden, mit Pagination, in Europe/Zurich gruppieren (F1, F2, API-Last).
4. Nur aktuellen und künftige Monate neu erzeugen (F4).
5. Kalenderquellen konfigurierbar: Liste von Google-Kalender-IDs **und** ICS-URLs. ICS braucht kein OAuth und ist der einfachste Weg für den Server.
6. Sync-Backend wählbar: `cloud` (rmapi, Fork `ddvk/rmapi`) oder `ssh` (bestehend). Für Cloud: Upload mit Ersetzen des PDF-Inhalts unter Beibehaltung der Annotationen (`put --content-only`), im Test verifizieren.
7. Docker: keine Secrets im Image, ein Volume `/config` (Google-Token, rmapi-Konfiguration), ein Volume `/out`, `TZ=Europe/Zurich`, `network_mode: host` entfernen, Versionen in `requirements.txt` fixieren.
8. Exit-Code ≠ 0 bei Fehlern, damit die Überwachung greift.

### Phase 2 – VPS vorbereiten

1. Prüfen, was auf dem VPS bereits läuft (Docker, andere Stacks), damit nichts kollidiert.
2. Firewall-Gruppe in hPanel zuweisen: eingehend nur SSH. Der Job braucht keine offenen Ports.
3. Docker Engine und Compose-Plugin installieren, falls nicht vorhanden.
4. Verzeichnis `/opt/remarkable-calendar`, Repo klonen, `.env` mit `chmod 600` (Todoist-Token, Kalender-IDs/ICS-URLs).

### Phase 3 – Einmalige Anmeldungen

1. **reMarkable Cloud:** Einmalcode unter my.remarkable.com (Gerät verbinden) erzeugen, `rmapi` einmal interaktiv im Container starten, Token landet in `/config`.
2. **Google (falls nicht ICS):** OAuth einmal lokal am Laptop durchlaufen, `token.json` nach `/config` kopieren. OAuth-Zustimmungsbildschirm auf «In production» stellen, sonst läuft das Token nach 7 Tagen ab.

### Phase 4 – Zeitplan und Überwachung

1. systemd-Timer `remarkable-sync.timer`, täglich 04:30 mit `Persistent=true`; Service führt `docker compose run --rm calendar` aus.
2. Logs über `journalctl -u remarkable-sync`.
3. Benachrichtigung bei Fehlschlag (`OnFailure=` mit Mail oder Healthcheck-Ping), sonst fällt ein abgelaufenes Token erst am Tablet auf.

### Phase 5 – Abnahme

1. Manueller Lauf, PDFs in `/out` prüfen (Zeitzone, Umlaute, Termine am richtigen Tag).
2. Auf dem Tablet: Ordner und 12 Dokumente vorhanden.
3. Handschrift-Test: Notiz auf einer Tagesseite, zweiter Lauf, Notiz muss bleiben.
4. Timer drei Tage beobachten, dann README aktualisieren.

### Phase 6 – optional, Richtung CalSync

Priorität nach Nutzen/Aufwand: A4- bzw. Geräteformat und deutsche Datumsformate, Schweizer Feiertage, Cover mit «Heute»-Link, weitere Task-Quellen. Task Markup und Sleep-Screen bewusst zurückgestellt.

## 5. Offene Entscheidungen

1. **Welches Tablet?** (rM2 / Paper Pro / Move) – bestimmt Seitenformat und ob SSH überhaupt in Frage kommt.
2. **Cloud-Sync per rmapi in Ordnung?** rmapi ist ein inoffizielles Community-Tool gegen die reMarkable-Cloud. Alternative: Job zuhause laufen lassen (Raspberry Pi/NAS) statt auf Hostinger.
3. **Kalenderquelle:** Google-OAuth oder private ICS-URL?
4. **Wird Todoist genutzt**, oder eine andere Aufgaben-App?
