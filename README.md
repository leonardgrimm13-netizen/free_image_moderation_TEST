# Screen-1 Icon Watcher (Python)

Dieses Projekt überwacht **Screen 1** permanent auf ein Referenzbild (`target.png`).
Solange das Referenzbild erkannt wird, speichert das Script automatisch alle 3 Sekunden einen vollständigen Screenshot von Screen 1. Wenn das Bild nicht erkannt wird, werden **keine** Screenshots geschrieben.

## Python-Version

Empfohlen: **Python 3.10+** (getestet mit 3.11).

## Installation

```bash
python -m venv .venv
# Windows PowerShell:
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

## Start

```bash
python monitor_if_icon_visible.py
```

Self-Test (ohne echten Monitor-Check, validiert Pfad- und Speicherlogik):

```bash
python monitor_if_icon_visible.py --self-test
```

## Konfigurationswerte

Die wichtigsten Defaults stehen oben in `monitor_if_icon_visible.py`:

- `BASE_DIR`: Script-Ordner (absoluter Pfad)
- `TEMPLATE_PATH`: `<script_ordner>/target.png`
- `SAVE_DIR`: `<script_ordner>/screenshots`
- `MONITOR_INDEX = 1`
- `CHECK_EVERY` (Polling-Intervall)
- `SCREENSHOT_EVERY = 3.0`
- `MATCH_THRESHOLD = 0.74`
- `SCALES = (0.85, 0.92, 1.0, 1.08, 1.16)`
- `DEBUG` (optional)
- `IMMEDIATE_FIRST_SHOT = True`

Zusätzliche Laufzeitoptionen:

```bash
python monitor_if_icon_visible.py --threshold 0.72 --check-every 0.4 --screenshot-every 3.0 --scales 0.9,1.0,1.1 --monitor 1 --debug
```

Erster Screenshot beim Übergang auf „erkannt“ deaktivieren:

```bash
python monitor_if_icon_visible.py --no-immediate-first-shot
```

## Hinweise zu `target.png`

- Datei muss im **gleichen Ordner** wie das Script liegen.
- Transparenz (PNG Alpha) wird unterstützt (Maske beim Matching).
- Zu kleine Bilder (unter 2x2) werden abgelehnt.

## Verhalten / Zustandsautomat

- **erkannt** → Screenshots alle 3 Sekunden
- **nicht erkannt** → keine Screenshots
- Bei Zustandswechsel startet/stopppt der Screenshot-Zyklus automatisch.

## Robustheit, die bereits eingebaut ist

- Absolute Pfade über `Path(__file__).resolve()`
- Prüfung auf fehlendes `target.png`
- Prüfung auf ungültigen Monitorindex
- Fehlerbehandlung für OpenCV-/Capture-/Write-Fehler
- `cv2.imwrite`-Rückgabewert wird geprüft
- Danach wird geprüft, ob die Datei wirklich existiert und > 0 Byte ist
- Transparenzbild (PNG mit Alpha) wird ohne Absturz verarbeitet
- Mehrskalen-Template-Matching für „ähnlich genug“ statt pixelgenau
- Nicht-spammy Logging (Startinfos, Statuswechsel, Saves, Errors)
- Sauberes Beenden mit `Ctrl+C`

## Beispiel-Konsolenausgabe

```text
Starting monitor watcher...
Script path: C:\Projects\Aufnahme
Target path: C:\Projects\Aufnahme\target.png
Screenshot folder: C:\Projects\Aufnahme\screenshots
Monitor index: 1
Threshold: 0.740, scales: [0.85, 0.92, 1.0, 1.08, 1.16]
[STATE] erkannt (score=0.8123)
[SAVE] C:\Projects\Aufnahme\screenshots\screen1_2026-03-28_10-14-03.png
[SAVE] C:\Projects\Aufnahme\screenshots\screen1_2026-03-28_10-14-06.png
[STATE] nicht erkannt (score=0.4120)
Stopped by user (Ctrl+C).
```

## Troubleshooting

### 1) Nichts wird erkannt

- `target.png` prüfen (richtige Datei, guter Ausschnitt, nicht zu klein).
- Threshold lockern, z. B. `--threshold 0.70`.
- Skalen erweitern, z. B. `--scales 0.8,0.9,1.0,1.1,1.2`.
- Mit `--debug` Scores beobachten.

### 2) Zu viele Fehl-Erkennungen

- Threshold erhöhen, z. B. `--threshold 0.80`.
- Skalenbereich einschränken.
- Eindeutigeres `target.png` verwenden.

### 3) Screenshots werden nicht gespeichert

- Prüfen, ob Zustand überhaupt auf `[STATE] erkannt` wechselt.
- Schreibrechte im Projektordner prüfen.
- Error-Ausgaben beachten (`[ERROR] Save failed: ...`).

### 4) Falscher Monitor

- Standard ist `--monitor 1` (erster physischer Monitor in MSS).
- Bei mehreren Displays ggf. `--monitor 2`, `--monitor 3`, ... testen.
- Bei ungültigem Index meldet das Script den gültigen Bereich.

## Dateinamen

Screenshots werden als

`screen1_YYYY-MM-DD_HH-MM-SS.png`

im Ordner `screenshots` gespeichert.
