"""DEM (Digital Elevation Model) laden, auf Track-Bounds zuschneiden, downsamplen.

Eingabe: GeoTIFF-Datei (typisch Copernicus GLO-30, EU-DEM, oder SRTM).
Ausgabe: einfaches Dict mit ``lats``, ``lons``, ``elevations`` — direkt geeignet
für ``plotly.graph_objects.Surface``.

Konventionen
------------
* DEM wird im geographischen Koordinatensystem (EPSG:4326, WGS84 Lat/Lon)
  erwartet. Andere Projektionen werden NICHT automatisch reprojiziert —
  stattdessen wird eine klare Fehlermeldung ausgegeben.
* Die Höhenwerte sind in Metern über dem Geoid (genauer: das, was der
  jeweilige DEM-Hersteller liefert; bei Copernicus DEM ist es EGM2008).
* NoData-Werte werden zu NaN.

Bezugsquellen für freie DEMs
----------------------------
* OpenTopography (https://portal.opentopography.org/): Rechteck zeichnen,
  Copernicus GLO-30 oder SRTM herunterladen — beides hinreichend.
* AWS Public Dataset: ``s3://copernicus-dem-30m/`` — flächendeckend in
  30-m-Auflösung, Tiles à 1°×1°.

Wo Dateien hingehören
---------------------
Per Default in einen ``data/``-Ordner relativ zum Aufrufer. Der konkrete
Pfad wird beim ``load_dem``-Aufruf übergeben.
"""

from pathlib import Path
from typing import Dict, Optional, Tuple

import numpy as np
import rasterio
import rasterio.windows


def _compute_downsample_steps(
    nrows: int,
    ncols: int,
    transform,
    target_pixel_size_m: Optional[float],
    max_pixels_per_axis: Optional[int],
    ref_lat: Optional[float] = None,
) -> Tuple[int, int]:
    """Berechnet Downsampling-Schritte aus den Auflösungs-Parametern.

    Zwei Beschränkungen, die kombiniert werden:
      1. ``target_pixel_size_m`` — wie viele Meter pro Pixel mindestens.
      2. ``max_pixels_per_axis`` — harte Obergrenze pro Achse.

    Der gewählte Step ist das Maximum der beiden Anforderungen
    (= das grobere Downsampling gewinnt). Bei kleinen DEMs (Pixel ohnehin
    größer als Ziel) bleibt der Step 1 — keine künstliche Verschlechterung.
    """
    pixel_size_lon_deg = abs(transform[0])
    pixel_size_lat_deg = abs(transform[4])

    step_from_meters_row = 1
    step_from_meters_col = 1
    if target_pixel_size_m and target_pixel_size_m > 0:
        if ref_lat is None:
            ref_lat = 50.0
        m_per_deg_lat = 111_320.0
        m_per_deg_lon = 111_320.0 * np.cos(np.deg2rad(ref_lat))
        pixel_size_lat_m = pixel_size_lat_deg * m_per_deg_lat
        pixel_size_lon_m = pixel_size_lon_deg * m_per_deg_lon
        step_from_meters_row = max(1, int(target_pixel_size_m / pixel_size_lat_m))
        step_from_meters_col = max(1, int(target_pixel_size_m / pixel_size_lon_m))

    step_from_max_row = 1
    step_from_max_col = 1
    if max_pixels_per_axis:
        step_from_max_row = max(1, int(np.ceil(nrows / max_pixels_per_axis)))
        step_from_max_col = max(1, int(np.ceil(ncols / max_pixels_per_axis)))

    return (max(step_from_meters_row, step_from_max_row),
            max(step_from_meters_col, step_from_max_col))


def load_dem(
    dem_path: str,
    bounds: Optional[Tuple[float, float, float, float]] = None,
    *,
    target_pixel_size_m: Optional[float] = 50.0,
    max_pixels_per_axis: Optional[int] = 2000,
    padding_deg: float = 0.005,
    bounds_padding_pct: float = 0.15,
    dem_smooth: float = 1.0,
    target_resolution: Optional[int] = None,
) -> Optional[Dict[str, np.ndarray]]:
    """Lädt ein GeoTIFF-DEM und liefert ein für Plotly geeignetes Dict.

    Parameters
    ----------
    dem_path : str
        Pfad zur GeoTIFF-Datei.
    bounds : tuple, optional
        Zuschneide-Bereich (lon_min, lat_min, lon_max, lat_max).
    target_pixel_size_m : float, optional
        Ziel-Pixelgröße in Metern (Default 50). Bei feineren DEMs wird
        downsampled, bei gröberen bleibt die Auflösung. None deaktiviert.
    max_pixels_per_axis : int, optional
        Harte Obergrenze pro Achse (Default 2000). Schützt vor Browser-
        Crashes.
    padding_deg : float
        Fester Puffer in Grad.
    bounds_padding_pct : float
        Prozentualer Puffer (symmetrisch in alle vier Richtungen).
    dem_smooth : float
        Sigma für Gaussian-Smoothing.
    target_resolution : int, optional
        Veraltet — überschreibt max_pixels_per_axis, wenn gesetzt.

    Returns
    -------
    dict or None
    """
    # Rückwärtskompatibilität
    if target_resolution is not None:
        max_pixels_per_axis = target_resolution

    path = Path(dem_path)
    if not path.is_file():
        print(f"DEM-Datei nicht gefunden: {dem_path}")
        return None

    try:
        with rasterio.open(path) as src:
            # CRS-Check: wir erwarten geographische Koordinaten
            if src.crs is None:
                print(f"Warnung: DEM hat kein CRS-Tag. Nehme Lat/Lon (EPSG:4326) an.")
            elif src.crs.to_epsg() != 4326:
                print(f"DEM ist in {src.crs} (EPSG:{src.crs.to_epsg()}), erwartet wird "
                      f"EPSG:4326 (Lat/Lon). Aktuelle Implementierung reprojiziert nicht.")
                return None

            # Optional: auf bounds zuschneiden (mit Padding)
            if bounds is not None:
                lon_min, lat_min, lon_max, lat_max = bounds
                # Prozentualer Puffer symmetrisch in alle vier Richtungen
                # (kleinerer der beiden Werte, damit die Box ausgewogen ist).
                lon_span = lon_max - lon_min
                lat_span = lat_max - lat_min
                sym_pad_deg = min(bounds_padding_pct * lon_span,
                                  bounds_padding_pct * lat_span)
                lon_pad = padding_deg + sym_pad_deg
                lat_pad = padding_deg + sym_pad_deg
                lon_min -= lon_pad
                lat_min -= lat_pad
                lon_max += lon_pad
                lat_max += lat_pad

                # Sicherheits-Clamp gegen das DEM-eigene Extent
                dem_bounds = src.bounds
                original_request = (lon_min, lat_min, lon_max, lat_max)
                lon_min = max(lon_min, dem_bounds.left)
                lat_min = max(lat_min, dem_bounds.bottom)
                lon_max = min(lon_max, dem_bounds.right)
                lat_max = min(lat_max, dem_bounds.top)

                # Warnen, wenn der gewünschte Bereich teilweise außerhalb war
                clamped = (lon_min, lat_min, lon_max, lat_max)
                if clamped != original_request:
                    print(f"Hinweis: gewünschter Bereich {original_request} ragt über das "
                          f"DEM-Extent {tuple(dem_bounds)} hinaus. Lade nur den Schnitt: "
                          f"{clamped}. Für vollständige Abdeckung weitere DEM-Tiles ergänzen.")

                if lon_min >= lon_max or lat_min >= lat_max:
                    print(f"Bounds {bounds} liegen außerhalb des DEM-Extents {dem_bounds}.")
                    return None

                window = rasterio.windows.from_bounds(
                    lon_min, lat_min, lon_max, lat_max, transform=src.transform
                )
                elevation = src.read(1, window=window)
                transform = src.window_transform(window)
            else:
                elevation = src.read(1)
                transform = src.transform

            # NoData zu NaN
            if src.nodata is not None:
                elevation = np.where(elevation == src.nodata, np.nan, elevation).astype(np.float32)
            else:
                elevation = elevation.astype(np.float32)

            nrows, ncols = elevation.shape
            if nrows == 0 or ncols == 0:
                print("DEM-Fenster ist leer.")
                return None

            # Pixel-Koordinaten zu Lat/Lon (Pixelzentren)
            # affine transform: x = a*col + b*row + c, y = d*col + e*row + f
            # Bei norden-orientierten DEMs ist e negativ (y nimmt nach unten ab).
            cols = np.arange(ncols)
            rows = np.arange(nrows)
            lons = transform[2] + (cols + 0.5) * transform[0]
            lats = transform[5] + (rows + 0.5) * transform[4]

            # Downsampling über kombinierte Helferfunktion
            ref_lat_dem = float((lats.min() + lats.max()) / 2) if len(lats) > 0 else 50.0
            step_row, step_col = _compute_downsample_steps(
                nrows, ncols, transform,
                target_pixel_size_m, max_pixels_per_axis,
                ref_lat=ref_lat_dem,
            )
            if step_row > 1 or step_col > 1:
                elevation = elevation[::step_row, ::step_col]
                lats = lats[::step_row]
                lons = lons[::step_col]

            # Lat-Reihenfolge normalisieren: bei Standard-DEMs läuft die erste
            # Zeile von Nord nach Süd (lats absteigend), wir wollen aufsteigend.
            if len(lats) > 1 and lats[0] > lats[-1]:
                lats = lats[::-1]
                elevation = elevation[::-1, :]

            # Optionales Gaussian-Smoothing — reduziert Zackigkeit durch
            # Gebäudekanten in DSMs. NaN-Werte werden vor dem Smoothing
            # interpoliert, danach wieder gesetzt.
            if dem_smooth and dem_smooth > 0:
                from scipy.ndimage import gaussian_filter
                nan_mask = np.isnan(elevation)
                if nan_mask.any():
                    # Schlichte Strategie: NaN durch Mittelwert ersetzen für
                    # die Filterung, hinterher NaN-Maske wieder anwenden.
                    filled = np.where(nan_mask, np.nanmean(elevation), elevation)
                    smoothed = gaussian_filter(filled, sigma=dem_smooth)
                    elevation = np.where(nan_mask, np.nan, smoothed)
                else:
                    elevation = gaussian_filter(elevation, sigma=dem_smooth)

            print(f"DEM geladen: {elevation.shape[0]}×{elevation.shape[1]} Punkte, "
                  f"Höhe {np.nanmin(elevation):.0f}–{np.nanmax(elevation):.0f} m, "
                  f"Bereich Lat {lats.min():.4f}°–{lats.max():.4f}° / "
                  f"Lon {lons.min():.4f}°–{lons.max():.4f}°")

            return {"lats": lats, "lons": lons, "elevations": elevation}

    except Exception as e:
        print(f"Fehler beim Laden des DEM: {e}")
        return None


def get_track_bounds(df, padding_deg: float = 0.0) -> Tuple[float, float, float, float]:
    """Bounding-Box eines Schema-B/C-DataFrames als (lon_min, lat_min, lon_max, lat_max).

    Padding wird auf alle Seiten draufgelegt (in Grad).
    """
    lon_min = float(df["directional_longitude"].min()) - padding_deg
    lat_min = float(df["directional_latitude"].min()) - padding_deg
    lon_max = float(df["directional_longitude"].max()) + padding_deg
    lat_max = float(df["directional_latitude"].max()) + padding_deg
    return (lon_min, lat_min, lon_max, lat_max)


def load_dems(
    dem_paths,
    bounds: Optional[Tuple[float, float, float, float]] = None,
    *,
    target_pixel_size_m: Optional[float] = 50.0,
    max_pixels_per_axis: Optional[int] = 2000,
    padding_deg: float = 0.005,
    bounds_padding_pct: float = 0.15,
    dem_smooth: float = 1.0,
    target_resolution: Optional[int] = None,
) -> Optional[Dict[str, np.ndarray]]:
    """Lädt mehrere DEM-Tiles, merged sie und schneidet auf bounds zu.

    Siehe ``load_dem`` für die Parameter.
    """
    # Rückwärtskompatibilität
    if target_resolution is not None:
        max_pixels_per_axis = target_resolution

    from rasterio.merge import merge as rio_merge

    paths = [Path(p) for p in dem_paths]
    paths = [p for p in paths if p.is_file()]
    if not paths:
        print("Keine gültigen DEM-Dateien in dem_paths gefunden.")
        return None

    if len(paths) == 1:
        return load_dem(str(paths[0]), bounds=bounds,
                        target_pixel_size_m=target_pixel_size_m,
                        max_pixels_per_axis=max_pixels_per_axis,
                        padding_deg=padding_deg,
                        bounds_padding_pct=bounds_padding_pct,
                        dem_smooth=dem_smooth)

    # Vorfilter und Padding-Berechnung
    if bounds is not None:
        lon_min, lat_min, lon_max, lat_max = bounds
        lon_span = lon_max - lon_min
        lat_span = lat_max - lat_min
        sym_pad_deg = min(bounds_padding_pct * lon_span,
                          bounds_padding_pct * lat_span)
        lon_pad = padding_deg + sym_pad_deg
        lat_pad = padding_deg + sym_pad_deg
        lon_min -= lon_pad
        lat_min -= lat_pad
        lon_max += lon_pad
        lat_max += lat_pad

        relevant = []
        for p in paths:
            with rasterio.open(p) as src:
                b = src.bounds
                if (b.left < lon_max and b.right > lon_min
                    and b.bottom < lat_max and b.top > lat_min):
                    relevant.append(p)
        if not relevant:
            print(f"Keiner der DEM-Tiles deckt {bounds} ab.")
            return None
        paths = relevant

    # Sources öffnen und mergen
    srcs = [rasterio.open(p) for p in paths]
    try:
        # Optional auf den gewünschten Bereich beschränken — sonst wird
        # die Vereinigung aller Tiles geladen.
        merge_bounds = None
        if bounds is not None:
            merge_bounds = (lon_min, lat_min, lon_max, lat_max)
        merged_array, merged_transform = rio_merge(srcs, bounds=merge_bounds)

        # rio_merge gibt ein 3D-Array zurück (Bands, H, W). Wir wollen Band 1.
        elevation = merged_array[0].astype(np.float32)

        # NoData behandeln (nimm den aus dem ersten src; bei verschieden
        # gesetzten NoData-Werten müsste man feiner unterscheiden)
        nodata = srcs[0].nodata
        if nodata is not None:
            elevation = np.where(elevation == nodata, np.nan, elevation)
    finally:
        for s in srcs:
            s.close()

    nrows, ncols = elevation.shape
    if nrows == 0 or ncols == 0:
        print("Merged DEM ist leer.")
        return None

    # Pixel-Zentren in Lat/Lon
    cols = np.arange(ncols)
    rows = np.arange(nrows)
    lons = merged_transform[2] + (cols + 0.5) * merged_transform[0]
    lats = merged_transform[5] + (rows + 0.5) * merged_transform[4]

    # Downsampling über kombinierte Helferfunktion
    ref_lat_dem = float((lats.min() + lats.max()) / 2) if len(lats) > 0 else 50.0
    step_row, step_col = _compute_downsample_steps(
        nrows, ncols, merged_transform,
        target_pixel_size_m, max_pixels_per_axis,
        ref_lat=ref_lat_dem,
    )
    if step_row > 1 or step_col > 1:
        elevation = elevation[::step_row, ::step_col]
        lats = lats[::step_row]
        lons = lons[::step_col]

    # Lat-Reihenfolge normalisieren (aufsteigend)
    if len(lats) > 1 and lats[0] > lats[-1]:
        lats = lats[::-1]
        elevation = elevation[::-1, :]

    # Optionales Gaussian-Smoothing
    if dem_smooth and dem_smooth > 0:
        from scipy.ndimage import gaussian_filter
        nan_mask = np.isnan(elevation)
        if nan_mask.any():
            filled = np.where(nan_mask, np.nanmean(elevation), elevation)
            smoothed = gaussian_filter(filled, sigma=dem_smooth)
            elevation = np.where(nan_mask, np.nan, smoothed)
        else:
            elevation = gaussian_filter(elevation, sigma=dem_smooth)

    print(f"DEM aus {len(paths)} Tiles gemerged: {elevation.shape[0]}×{elevation.shape[1]} Punkte, "
          f"Höhe {np.nanmin(elevation):.0f}–{np.nanmax(elevation):.0f} m, "
          f"Bereich Lat {lats.min():.4f}°–{lats.max():.4f}° / "
          f"Lon {lons.min():.4f}°–{lons.max():.4f}°")

    return {"lats": lats, "lons": lons, "elevations": elevation}


def compare_track_dem(df, dem_paths) -> Optional[Dict[str, float]]:
    """Vergleicht Track-Höhen mit DEM-Höhen punktweise, gibt Statistik aus.

    Nützlich, um den vertikalen Bezug von Track und DEM zu prüfen — der
    Median der Differenz ist ein guter Kandidat für ``track_z_offset``
    in der Visualisierung. Hoher Mittelwert mit kleiner Standardabweichung
    deutet auf systematischen Bezugs-Offset (Geoid vs. Ellipsoid o.ä.) hin.

    Bei mehreren DEM-Tiles werden alle berücksichtigt — pro Track-Punkt wird
    automatisch das passende Tile gewählt (siehe ``sample_dem_at_points``).

    Parameters
    ----------
    df : pd.DataFrame
        Schema-B/C-DataFrame mit ``directional_latitude``, ``directional_longitude``,
        ``altitude_corrected``.
    dem_paths : str, Path, or iterable
        Ein Pfad oder eine Liste von DEM-Dateien.

    Returns
    -------
    dict or None
        Statistik: ``n_compared``, ``mean_diff``, ``median_diff``,
        ``std_diff``, ``min_diff``, ``max_diff``, ``suggested_offset``.
    """
    if df.empty or "altitude_corrected" not in df.columns:
        return None

    valid_track = df["altitude_corrected"].notna()
    if not valid_track.any():
        return None

    dem_values = sample_dem_at_points(
        df.loc[valid_track, "directional_latitude"].to_numpy(),
        df.loc[valid_track, "directional_longitude"].to_numpy(),
        dem_paths,
    )
    if dem_values is None:
        return None

    track_alt = df.loc[valid_track, "altitude_corrected"].to_numpy(dtype=np.float32)
    diffs = track_alt - dem_values
    valid = diffs[~np.isnan(diffs)]
    if len(valid) == 0:
        print("Track liegt komplett außerhalb der DEM-Bereiche oder keine Treffer.")
        return None

    stats = {
        "n_compared": int(len(valid)),
        "mean_diff": float(np.mean(valid)),
        "median_diff": float(np.median(valid)),
        "std_diff": float(np.std(valid)),
        "min_diff": float(np.min(valid)),
        "max_diff": float(np.max(valid)),
        "suggested_offset": float(-np.median(valid)),
    }

    print(f"Track-vs-DEM-Vergleich ({stats['n_compared']} Punkte):")
    print(f"  Höhendifferenz (Track − DEM):")
    print(f"    Mittelwert: {stats['mean_diff']:+.1f} m")
    print(f"    Median:     {stats['median_diff']:+.1f} m")
    print(f"    Std-Abw.:   {stats['std_diff']:.1f} m")
    print(f"    Bereich:    {stats['min_diff']:+.1f} bis {stats['max_diff']:+.1f} m")
    print(f"  Vorgeschlagener track_z_offset: {stats['suggested_offset']:+.1f} m")
    # Heuristik für Warnungen:
    #  * Großer Unterschied Mittelwert ↔ Median: Track ist offensichtlich
    #    teilweise hoch oben (Flug, Drohne) — kein Bug, nur Info.
    #  * Kleiner Median + hohe Std-Abw.: GPS-Höhe-Rauschen oder DEM-Probleme.
    mean_median_gap = abs(stats["mean_diff"] - stats["median_diff"])
    if mean_median_gap > 50:
        print(f"  ℹ Mittelwert ({stats['mean_diff']:+.1f} m) weicht stark vom "
              f"Median ab — Track ist offenbar teilweise weit über dem Gelände "
              f"(Flug/Drohne?). Ggf. track_z_offset='none' setzen.")
    elif stats["std_diff"] > 20 and abs(stats["median_diff"]) < 50:
        print(f"  ⚠ Hohe Standardabweichung bei kleinem Median — Track passt "
              f"schlecht auf DEM. Mögliche Ursachen: GPS-Höhe stark verrauscht, "
              f"Track auf Brücken/Tunnel, DEM zu grob oder veraltet.")

    return stats


def sample_dem_at_points(
    lats: np.ndarray,
    lons: np.ndarray,
    dem_paths,
) -> Optional[np.ndarray]:
    """Liefert die DEM-Höhe an jeder gegebenen (lat, lon)-Stelle.

    Wenn mehrere DEM-Tiles übergeben werden, sucht die Funktion pro Track-Punkt
    automatisch das passende Tile. Punkte in Überlappungszonen nehmen das
    erste passende. Punkte außerhalb aller Tiles bekommen NaN.

    Die Werte werden direkt aus dem GeoTIFF gesampelt — also **roh, ungeglättet**.
    Das ist Absicht: Diese Funktion ist für Diagnose und Daten-Anreicherung
    gedacht, nicht für Visualisierung; ehrliche Daten sind hier wichtiger als
    visuelle Glätte.

    Parameters
    ----------
    lats, lons : ndarray
        Gleichlange 1D-Arrays mit Lat- und Lon-Koordinaten.
    dem_paths : str, Path, or iterable of these
        Ein Pfad oder eine Liste von Pfaden zu GeoTIFF-Dateien.

    Returns
    -------
    ndarray or None
        Array gleicher Länge mit Höhen in Metern. NaN für Punkte, die
        außerhalb aller DEM-Bereiche liegen oder NoData treffen.
        None, wenn keine der Dateien geöffnet werden konnte.
    """
    # Normalisieren: einzelner Pfad → Liste mit einem Element
    if isinstance(dem_paths, (str, Path)):
        paths = [Path(dem_paths)]
    else:
        paths = [Path(p) for p in dem_paths]

    paths = [p for p in paths if p.is_file()]
    if not paths:
        print("Keine gültigen DEM-Dateien für Sampling verfügbar.")
        return None

    lons_arr = np.asarray(lons, dtype=np.float64)
    lats_arr = np.asarray(lats, dtype=np.float64)
    n = len(lats_arr)
    result = np.full(n, np.nan, dtype=np.float32)

    # Welche Punkte sind noch nicht gesampelt? Wir füllen tilewise auf.
    pending = np.ones(n, dtype=bool)

    for path in paths:
        if not pending.any():
            break
        try:
            with rasterio.open(path) as src:
                b = src.bounds
                # Welche der pending-Punkte liegen in diesem Tile?
                in_tile = (
                    pending
                    & (lons_arr >= b.left) & (lons_arr <= b.right)
                    & (lats_arr >= b.bottom) & (lats_arr <= b.top)
                )
                if not in_tile.any():
                    continue

                coords = list(zip(lons_arr[in_tile], lats_arr[in_tile]))
                values = np.array([v[0] for v in src.sample(coords)],
                                  dtype=np.float32)
                if src.nodata is not None:
                    values = np.where(values == src.nodata, np.nan, values)
                result[in_tile] = values
                pending[in_tile] = False
        except Exception as e:
            print(f"Fehler beim Sampling aus {path.name}: {e}")
            continue

    return result


def estimate_html_size_mb(dem_data: Dict[str, np.ndarray]) -> float:
    """Schätzt die Plotly-HTML-Größe für eine go.Surface mit diesem DEM.

    Empirisch ermittelt: Plotly serialisiert eine Surface kompakter, als man
    zuerst denken würde (~1.5 Byte/Vertex bei ``include_plotlyjs='cdn'``,
    weil das Plotly-Skript nicht eingebettet ist und Float32-Werte effizient
    in JSON gepackt werden). Wir rechnen mit 3 Byte als konservativem
    Mittelwert plus 200 KB Hüll-JSON.
    """
    if dem_data is None:
        return 0.0
    elev = dem_data.get("elevations")
    if elev is None:
        return 0.0
    n_vertices = elev.size
    bytes_estimated = 3 * n_vertices + 200_000
    return bytes_estimated / (1024 ** 2)


def reduce_dem_to_fit(
    dem_data: Dict[str, np.ndarray],
    max_html_mb: float,
) -> Dict[str, np.ndarray]:
    """Reduziert ein geladenes DEM, falls die geschätzte HTML-Größe das Limit überschreitet.

    Halbiert die Auflösung iterativ (Step 2, 3, 4, ...), bis die Schätzung passt.
    Gibt das Original zurück, wenn schon klein genug.
    """
    if dem_data is None:
        return dem_data

    estimated = estimate_html_size_mb(dem_data)
    if estimated <= max_html_mb:
        return dem_data

    elev = dem_data["elevations"]
    lats = dem_data["lats"]
    lons = dem_data["lons"]
    nrows, ncols = elev.shape

    for step in range(2, 11):
        reduced_n = (nrows // step) * (ncols // step)
        reduced_size_mb = (3 * reduced_n + 200_000) / (1024 ** 2)
        if reduced_size_mb <= max_html_mb:
            print(f"DEM-Auflösung wird automatisch reduziert: "
                  f"{nrows}x{ncols} -> {nrows // step}x{ncols // step} "
                  f"(geschätzte HTML-Größe {estimated:.0f} MB -> {reduced_size_mb:.0f} MB, "
                  f"Limit {max_html_mb:.0f} MB). "
                  f"Auf leistungsstarken Systemen kann config.DEM_MAX_HTML_MB "
                  f"hochgesetzt werden.")
            return {
                "lats": lats[::step],
                "lons": lons[::step],
                "elevations": elev[::step, ::step],
            }

    print(f"⚠ DEM konnte nicht unter {max_html_mb} MB reduziert werden; "
          f"HTML wird groß ({estimated:.0f} MB). Bitte config-Werte prüfen.")
    return dem_data
