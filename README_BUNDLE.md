# Bundle-Übersicht — Track + Satellitenkonstellation, synchronisiert

Stand 19. Mai 2026. Dieses Bundle erweitert die GPS-Pipeline um eine
synchronisierte Track-Satelliten-Visualisierung: 3D-Track links,
Polar-Skyplot rechts, Slider unten, Klick auf einen Track-Punkt verschiebt
den Slider. Die HTML-Datei skaliert nicht mit der Tracklänge sondern mit
der Anzahl GSV-Bursts (Faktor 10–20 kleiner als eine naive Frame-Variante).

## Ordnerdiagramm

```
gps_pipeline_bundle/
├── README_BUNDLE.md             ← diese Datei
├── CHANGES.md                   ← Stand-Dokument (unverändert)
├── gps_pipeline/                ← lauffähiges Paket (python -m gps_pipeline)
│   ├── __init__.py
│   ├── __main__.py
│   ├── api.py                   ← GEÄNDERT: ruft jetzt
│   │                              render_track_with_satellites auf
│   ├── config.py
│   ├── README.md
│   ├── parsing/
│   │   ├── __init__.py
│   │   ├── nmea.py
│   │   ├── nmea_to_dataframe.py
│   │   ├── gpx.py
│   │   └── kml.py
│   ├── processing/
│   │   ├── __init__.py
│   │   ├── filter.py
│   │   ├── consolidate.py
│   │   ├── enrich.py
│   │   ├── enrich_terrain.py
│   │   ├── gsv_aggregate.py
│   │   └── gsv_align.py         ← NEU
│   ├── visualization/
│   │   ├── __init__.py
│   │   ├── three_d.py
│   │   ├── satellite_view.py    ← bleibt drin, wird aber von api.py nicht
│   │   │                          mehr aufgerufen (kann später entfernt
│   │   │                          oder als Bibliotheksfunktion verwendet
│   │   │                          werden)
│   │   ├── multi_track.py
│   │   └── track_with_satellites.py   ← NEU
│   ├── terrain/
│   │   ├── __init__.py
│   │   └── dem.py
│   ├── utils/
│   │   ├── __init__.py
│   │   └── safe_convert.py
│   └── dataframe_io/
│       ├── __init__.py
│       └── feather.py
└── history/                     ← Doku aus der Vorbereitungsphase
    ├── projekt_inventar.md
    ├── lernkarten.md
    └── refactor_plan.md
```

Hinweis: Das ursprüngliche Bundle enthielt nur eine `__init__.py` mit Inhalt
(im Top-Level `gps_pipeline/`). Hier sind aus Sauberkeit auch leere
`__init__.py`-Dateien in den Subpackages mit dabei — das ist semantisch
äquivalent zu impliziten Namespace-Paketen und für `python -m gps_pipeline`
nicht zwingend nötig, aber expliziter.

## Was ist neu

### `processing/gsv_align.py`

Daten-Funktion: für jeden Schema-C-Track-Punkt **pro Talker-ID** die zuletzt
gültige GSV-Multi-Sentence-Group anheften (`merge_asof`, `direction='backward'`).
Long-format Output mit den Spalten

    track_idx, track_timestamp, talker_id, gsv_timestamp, satellites, age_seconds

Multi-Constellation-tauglich: bei Empfängern mit mehreren Talkern (GP/GL/GA/GB)
entstehen mehrere Zeilen pro Track-Punkt, eine pro Konstellation. Track-Punkte
vor dem ersten GSV-Burst eines Talkers tauchen für diesen Talker *nicht* im
Output auf (dann erscheint im Visualisierer "Kein GSV-Burst bisher").

Außer von `track_with_satellites` direkt nutzbar — z.B. für Auswertungen wie
"wie viele Satelliten sah ich im Schnitt entlang des Tracks pro Konstellation?".

### `visualization/track_with_satellites.py`

Erzeugt **eine** HTML-Datei mit drei UI-Bausteinen:

1. **Plotly-Subplot** 3D-Track (links) + Polar-Skyplot (rechts).
2. **HTML-Range-Slider** unten, der durch alle Track-Punkte läuft.
3. **Status-Annotation** rechts neben dem Slider mit Timestamp, sichtbaren
   Satelliten und Alter des verwendeten GSV-Bursts pro Konstellation.

Skalierungs-Architektur:

* Die Sat-Daten werden **einmal** als JSON-Payload ins HTML eingebettet, mit
  deduplizierten Bursts pro Talker und einer `track_idx → burst_idx` Lookup-
  Liste. Bei einer Stunde Aufzeichnung mit GSV-Bursts alle 2,5 s sind das pro
  Konstellation ca. 1.500 Bursts statt 36.000 Frames.
* Ein eingebettetes JS-Snippet aktualisiert bei Slider-Change und Klick die
  zwei oder drei betroffenen Plotly-Traces per `Plotly.restyle` und das
  Annotation-`<div>` per `innerHTML`. Keine Plotly-`frames` mehr — diese hatten
  Trace-Daten dupliziert und waren das Hauptproblem bei langen Tracks.

Größenordnungen (im Test):

| Track-Punkte | Konstellationen | HTML-Größe |
|--------------|-----------------|------------|
| 30           | 2               | 22 KB      |
| 5.000        | 2               | 0,68 MB    |
| 60.000       | 4               | 7,93 MB    |

API:

```python
from gps_pipeline.visualization.track_with_satellites import (
    render_track_with_satellites,
)

render_track_with_satellites(
    df_c, df_raw, output_path,
    color_by="speed_kmh",        # optional
    dem_data=dem_data,           # optional, wenn vorher geladen
    track_z_offset=track_z_offset,
)
```

Schreibt die HTML-Datei direkt, gibt `bool` zurück (True = geschrieben,
False = Inputs leer).

## Was sich geändert hat

### `api.py`

Zwei Stellen:

1. **Import**: `visualize_satellites` → `render_track_with_satellites`.
2. **Aufruf in `render_visualizations`**: Statt einer separaten statischen
   `<prefix>_satellites.html` wird jetzt eine kombinierte
   `<prefix>_track_satellites.html` mit Slider + Klick-Synchronisation
   geschrieben.

**Output-Dateiname-Änderung**: Wenn andere Skripte oder Notebooks gezielt
`_satellites.html` aus dem alten Output erwarten, müssen die auf
`_track_satellites.html` umgestellt werden.

### `visualization/satellite_view.py`

Bleibt im Bundle erhalten und ist weiterhin importierbar als Bibliotheks-
funktion (`from gps_pipeline.visualization.satellite_view import visualize_satellites`).
Wird aber von `api.render_visualizations` nicht mehr aufgerufen. Wer das
Modul nicht braucht, kann es im eigenen Workspace nachträglich löschen —
mit Suche nach Verwendungen lässt sich das in einem Schritt verifizieren.

## Lauffähigkeit verifiziert

Importiert als komplettes Paket — getestet mit:

```bash
cd gps_pipeline_bundle
python -m py_compile gps_pipeline/api.py
python -m py_compile gps_pipeline/processing/gsv_align.py
python -m py_compile gps_pipeline/visualization/track_with_satellites.py
PYTHONPATH=. python -c "from gps_pipeline import process_nmea, render_visualizations"
```

End-to-End mit synthetischen Schema-A- und Schema-C-Daten (100 Track-Punkte,
1 Konstellation, 10 GSV-Bursts) erzeugt sauber die vier Standard-Outputs:

```
e2e.feather                 (12,7 KB)
e2e_3d.html                 (84,4 KB)
e2e_3d_altitude.html        (84,4 KB)
e2e_track_satellites.html   (83,5 KB)   ← neu, ersetzt e2e_satellites.html
```

## Bekannte offene Punkte

* **Render-Zeit ~8 s** bei 60k Track-Punkten. Bottleneck ist der
  `iterrows`-Loop in `_build_payload`. Vektorisierbar wenn nötig — wäre eine
  überschaubare Optimierung, aktuell nicht umgesetzt.
* **Hover-Text-Größe**: bei sehr langen Tracks macht der Track-Hover-Text
  einen merklichen Teil der HTML-Größe aus. Lässt sich in `_build_initial_figure`
  kürzen.
* **Plotly via CDN**: Beim Öffnen der HTML wird Plotly aus dem Netz geladen
  (~3 MB Ersparnis pro Datei). Wenn offline gearbeitet wird,
  `include_plotlyjs="cdn"` in `_build_html` auf `True` umstellen.
* **`CHANGES.md`**: nicht angepasst. Das TODO *"Satellite-View-Animation"*
  ist jetzt umgesetzt; der Eintrag dort kann manuell abgehakt werden.
