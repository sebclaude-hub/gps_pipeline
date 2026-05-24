/**
 * useRangeSelection -- State-Management fuer Cut-Ranges (auszuschneidende
 * Index-Bereiche).
 *
 * Modell
 * ------
 * Standardmaessig wird der ganze Track behalten. Cut-Ranges sind
 * Index-Intervalle ``[start, end]`` (inklusive), die beim Export
 * ausgeschnitten werden.
 *
 * Beispiele:
 *   - Reines Trimming (Anfang/Ende abschneiden):
 *       cuts = [{start: 0, end: 49}, {start: 580, end: 599}]
 *   - Eine Zwischenlandung entfernen:
 *       cuts = [{start: 200, end: 350}]
 *   - Anfang/Ende UND eine Pause:
 *       cuts = [{start: 0, end: 49}, {start: 200, end: 350}, {start: 580, end: 599}]
 *
 * Cut-Ranges duerfen sich ueberlappen -- beim Export werden sie zur
 * Vereinigungsmenge zusammengefasst. Ueberlapp ist ein UI-Detail und wird
 * im Backend toleriert.
 */

import { useCallback, useState } from "react";

export interface CutRange {
  /** Stabiler Schluessel fuer React-Listen. */
  id: string;
  /** Erster zu entfernender Index (inklusive). */
  start: number;
  /** Letzter zu entfernender Index (inklusive). */
  end: number;
}

let _idCounter = 0;
function nextId(): string {
  _idCounter += 1;
  return `cut-${_idCounter}`;
}

export interface RangeSelectionApi {
  ranges: CutRange[];
  /** Neuen Cut-Range einfuegen. Bei fehlenden Werten wird ein zentraler
   *  Range um die uebergebene Position herum erzeugt (10% Trackbreite). */
  addRange: (centerIdx: number, totalPoints: number) => void;
  /** Range mit gegebener ID loeschen. */
  removeRange: (id: string) => void;
  /** Start oder End eines Range anpassen. Clampt automatisch auf [0, n-1]
   *  und stellt sicher, dass ``start <= end`` bleibt. */
  updateRange: (id: string, patch: Partial<Pick<CutRange, "start" | "end">>, totalPoints: number) => void;
  /** Alle Ranges zuruecksetzen. */
  clearAll: () => void;
}

export function useRangeSelection(): RangeSelectionApi {
  const [ranges, setRanges] = useState<CutRange[]>([]);

  const addRange = useCallback((centerIdx: number, totalPoints: number) => {
    // Default-Breite: 10% des Tracks (oder mind. 5 Punkte).
    const halfWidth = Math.max(2, Math.floor(totalPoints * 0.05));
    const start = Math.max(0, centerIdx - halfWidth);
    const end = Math.min(totalPoints - 1, centerIdx + halfWidth);
    setRanges((prev) => [...prev, { id: nextId(), start, end }]);
  }, []);

  const removeRange = useCallback((id: string) => {
    setRanges((prev) => prev.filter((r) => r.id !== id));
  }, []);

  const updateRange = useCallback((id: string, patch: Partial<Pick<CutRange, "start" | "end">>, totalPoints: number) => {
    setRanges((prev) =>
      prev.map((r) => {
        if (r.id !== id) return r;
        let start = patch.start !== undefined ? patch.start : r.start;
        let end = patch.end !== undefined ? patch.end : r.end;
        // Clamp + sortieren
        start = Math.max(0, Math.min(totalPoints - 1, start));
        end = Math.max(0, Math.min(totalPoints - 1, end));
        if (start > end) [start, end] = [end, start];
        return { ...r, start, end };
      })
    );
  }, []);

  const clearAll = useCallback(() => setRanges([]), []);

  return { ranges, addRange, removeRange, updateRange, clearAll };
}
