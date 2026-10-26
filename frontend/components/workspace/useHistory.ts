"use client";

import { useCallback, useRef, useState } from "react";

export interface HistoryEntry {
  /** Short label for tooltips (e.g. "edit", "add", "delete"). */
  label: string;
  /** Epoch ms when the entry was last extended — used for coalescing. */
  at: number;
  /** Coalescing bucket: rapid pushes with the same key merge into one step
      (one undo for a whole drag, slider sweep, or typing burst). */
  mergeKey?: string;
  undo: () => void;
  redo: () => void;
}

/**
 * Linear undo/redo stack for workspace edits (block patches, add/delete,
 * brush marks, bulk translation imports).
 *
 * Server jobs: only jobs that MINT new block ids (extract, re-OCR) or
 * restructure pages (crop, append, delete-page) clear the stack. Jobs that
 * merely produce images (clean/render/apply) or rewrite existing
 * translations (translate) leave entries valid — history entries patch by
 * block id, which survives those.
 */
export function useHistory(limit = 120) {
  const stackRef = useRef<HistoryEntry[]>([]);
  const posRef = useRef(-1); // index of the last applied entry
  const [pos, setPos] = useState(-1);
  const [len, setLen] = useState(0);

  const sync = useCallback(() => {
    setPos(posRef.current);
    setLen(stackRef.current.length);
  }, []);

  /** Record an already-applied change. */
  const push = useCallback((entry: HistoryEntry, mergeWindowMs = 0) => {
    const stack = stackRef.current.slice(0, posRef.current + 1);
    const top = stack[stack.length - 1];
    if (
      mergeWindowMs > 0 &&
      entry.mergeKey &&
      top?.mergeKey === entry.mergeKey &&
      entry.at - top.at < mergeWindowMs
    ) {
      // Coalesce: keep the ORIGINAL undo, adopt the newest redo.
      top.redo = entry.redo;
      top.at = entry.at;
      stackRef.current = stack;
      sync();
      return;
    }
    stack.push(entry);
    stackRef.current = stack.slice(-limit);
    posRef.current = stackRef.current.length - 1;
    sync();
  }, [limit, sync]);

  const undo = useCallback(() => {
    const entry = stackRef.current[posRef.current];
    if (!entry) return false;
    posRef.current -= 1;
    entry.undo();
    sync();
    return true;
  }, [sync]);

  const redo = useCallback(() => {
    const entry = stackRef.current[posRef.current + 1];
    if (!entry) return false;
    posRef.current += 1;
    entry.redo();
    sync();
    return true;
  }, [sync]);

  const clear = useCallback(() => {
    stackRef.current = [];
    posRef.current = -1;
    sync();
  }, [sync]);

  return {
    push,
    undo,
    redo,
    clear,
    canUndo: pos >= 0,
    canRedo: pos < len - 1,
  };
}

export type History = ReturnType<typeof useHistory>;
