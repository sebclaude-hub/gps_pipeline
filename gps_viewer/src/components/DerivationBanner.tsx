/**
 * DerivationBanner -- Warnhinweis-Streifen, der einen Track als
 * bearbeitete Version eines anderen markiert.
 *
 * Wird ueber dem 3D-Viewer angezeigt, wenn ``track.meta.derivation``
 * vorhanden ist. Sicherheitsfunktion: der Nutzer soll auf keinen Fall
 * versehentlich davon ausgehen, dass die Ansicht 1:1 die Original-
 * Messungen zeigt.
 *
 * Schliessbar ist der Banner bewusst NICHT -- er ist Teil der
 * "Wahrheit ueber die Daten" und soll auch sichtbar bleiben, wenn der
 * Track per Link geteilt wird.
 */

import type { TrackDerivation } from "../types";

interface Props {
  derivation: TrackDerivation;
}

export function DerivationBanner({ derivation }: Props) {
  // Pro Bearbeitungs-Typ ein eigener Text + Farbschema.
  const { background, border, title, body } = describe(derivation);

  return (
    <div style={{
      position: "absolute",
      top: 0,
      left: 0,
      right: 0,
      background,
      borderBottom: `1px solid ${border}`,
      color: "#fff",
      padding: "6px 16px",
      fontSize: 12,
      fontFamily: "system-ui, sans-serif",
      zIndex: 5,
      display: "flex",
      alignItems: "center",
      gap: 10,
      lineHeight: 1.4,
      pointerEvents: "none",   // soll Maus-Interaktion mit dem Viewer nicht blockieren
    }}>
      <span style={{ fontSize: 16 }}>⚠</span>
      <span style={{ fontWeight: 700 }}>{title}</span>
      <span style={{ opacity: 0.9 }}>{body}</span>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Hilfs-Logik
// ---------------------------------------------------------------------------

interface Description {
  background: string;
  border: string;
  title: string;
  body: string;
}

function describe(d: TrackDerivation): Description {
  if (d.type === "trimmed") {
    const cuts = (d.n_cuts ?? "?") as number | string;
    const removed = (d.n_points_removed ?? "?") as number | string;
    const before = (d.n_points_before ?? "?") as number | string;
    const after = (d.n_points_after ?? "?") as number | string;
    return {
      background: "rgba(180, 110, 30, 0.85)",     // gedaempftes Bernstein
      border: "rgba(255, 160, 60, 0.9)",
      title: "Getrimmter Track",
      body: `Original "${d.source_name}" — ${cuts} Cut(s) angewendet, `
          + `${removed} Punkte entfernt (${before} → ${after}). `
          + `Satellitendaten dieser Ansicht sind nicht vorhanden, da `
          + `Schema A beim Trimmen nicht uebernommen wird.`,
    };
  }
  if (d.type === "synthetic") {
    const warn = (d.warning ?? "Zeitstempel wurden modifiziert.") as string;
    return {
      background: "rgba(170, 40, 50, 0.88)",      // ernsteres Rot
      border: "rgba(255, 90, 110, 0.95)",
      title: "Synthetischer Track",
      body: `Original "${d.source_name}" — ${warn} `
          + `Satellitendaten sind nicht gueltig, weil die Zeitachse `
          + `gestaucht wurde. Distanzen sind echt, Geschwindigkeiten neu `
          + `berechnet.`,
    };
  }
  // Fallback fuer kuenftige Typen, die der Viewer noch nicht kennt.
  return {
    background: "rgba(100, 100, 110, 0.85)",
    border: "rgba(180, 180, 200, 0.9)",
    title: `Bearbeiteter Track (${d.type})`,
    body: `Original "${d.source_name}". Details: ${JSON.stringify(d)}`,
  };
}
