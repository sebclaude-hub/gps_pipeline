/**
 * Chart-Loader: laedt charts.json (Manifest aller Overlays) und die einzelnen
 * PNGs ueber ein <img>-Element.
 *
 * Die PNGs werden vom view.py-Server unter ``/data/charts/...`` ausgeliefert,
 * dasselbe Mount-Point-Schema wie alle anderen Daten.
 */

import type { ChartOverlay } from "../utils/chartMesh";

interface ChartsManifest {
  charts: ChartOverlay[];
}

/** Holt das Manifest. Gibt leere Liste zurueck, wenn die Datei fehlt
 *  (404 ist kein Fehler, sondern "keine Overlays definiert"). */
export async function loadChartsManifest(): Promise<ChartOverlay[]> {
  const res = await fetch("/data/charts.json");
  if (res.status === 404) return [];
  if (!res.ok) throw new Error(`charts.json Fehler (${res.status})`);
  const json: ChartsManifest = await res.json();
  return json.charts ?? [];
}

/** Laedt ein PNG ueber <img>. Wir verwenden ImageBitmap nicht direkt, weil
 *  HTMLImageElement von SimpleMeshLayer/luma.gl zuverlaessig als Textur
 *  akzeptiert wird (ImageBitmap funktioniert auch, aber HTMLImageElement
 *  hat das gleiche Verhalten in Cache und Memory-Lifetime). */
export function loadChartImage(url: string): Promise<HTMLImageElement> {
  return new Promise((resolve, reject) => {
    const img = new Image();
    // Aus dem gleichen Origin (view.py-Server), aber wir setzen crossOrigin
    // sicherheitshalber -- WebGL-Texturen verlangen CORS-Kompatibilitaet,
    // sobald die App spaeter mal von einem anderen Host laedt.
    img.crossOrigin = "anonymous";
    img.onload = () => resolve(img);
    img.onerror = () => reject(new Error(`Chart-Image fehlgeschlagen: ${url}`));
    img.src = `/data/${url}`;
  });
}
