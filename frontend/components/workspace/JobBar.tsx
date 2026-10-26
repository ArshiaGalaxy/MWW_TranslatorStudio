"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { Terminal, X } from "lucide-react";
import { api } from "@/lib/api";
import { useI18n } from "@/lib/i18n";
import { Job } from "@/lib/types";
import { ProgressBar } from "@/components/ui";

const POLL_MS = 1500;

/**
 * Tracks the project's latest job.
 *
 * - Polls ONLY while a job is pending/running (idle = zero requests).
 * - `job` is the latest job and is KEPT after it finishes so the UI can
 *   observe the running → success/failed transition and show results.
 */
export function useActiveJob(projectId: string | undefined) {
  const [job, setJob] = useState<Job | null>(null);
  const [running, setRunning] = useState(false);
  const timer = useRef<ReturnType<typeof setInterval> | null>(null);
  const busyRef = useRef(false);
  const jobRef = useRef<Job | null>(null);

  const stopPolling = useCallback(() => {
    if (timer.current) {
      clearInterval(timer.current);
      timer.current = null;
    }
  }, []);

  const tick = useCallback(async () => {
    if (!projectId || busyRef.current) return;
    busyRef.current = true;
    try {
      if (jobRef.current) {
        // Lightweight path: the job endpoint returns just this job.
        const j = await api.get<Job>(`/api/jobs/${jobRef.current.id}/`);
        jobRef.current = j; // keep the ref fresh — `running` is computed from it
        setJob(j);
      } else {
        // Resume path: no job id yet (page reloaded mid-job) — find it on the
        // project detail, then subsequent polls hit the light endpoint.
        const detail = await api.get<{ active_job: Job | null }>(
          `/api/projects/${projectId}/`,
        );
        const aj = detail.active_job;
        jobRef.current = aj ?? null;
        setJob(aj);
      }
      setRunning((prev) => {
        const j = jobRef.current;
        const next = !!j && (j.status === "pending" || j.status === "running");
        return next === prev ? prev : next;
      });
    } catch {
      /* transient network error — keep previous state */
    } finally {
      busyRef.current = false;
    }
  }, [projectId]);

  // Initial single check — resumes polling if a job is already running
  useEffect(() => {
    void tick();
  }, [tick]);

  useEffect(() => {
    if (running && !timer.current) {
      timer.current = setInterval(() => void tick(), POLL_MS);
    }
    if (!running) stopPolling();
    return stopPolling;
  }, [running, tick, stopPolling]);

  /** Register a job right after triggering it (starts fast polling). */
  const beginJob = useCallback((j: Job) => {
    jobRef.current = j;
    setJob(j);
    setRunning(true);
  }, []);

  /** Ask the backend to cancel the active job (cooperative). */
  const cancelJob = useCallback(async () => {
    const j = jobRef.current;
    if (!j) return;
    try {
      const updated = await api.post<Job>(`/api/jobs/${j.id}/cancel/`, {});
      jobRef.current = updated;
      setJob(updated);
    } catch {
      /* transient error — the next poll re-syncs state */
    }
  }, []);

  return { job, running, beginJob, cancelJob };
}

export function JobBar({
  job,
  running,
  showLogs,
  setShowLogs,
  onCancel,
}: {
  job: Job | null;
  running: boolean;
  showLogs: boolean;
  setShowLogs: (v: boolean) => void;
  onCancel?: () => void | Promise<void>;
}) {
  const { t } = useI18n();
  const logRef = useRef<HTMLDivElement>(null);
  const [cancelling, setCancelling] = useState(false);

  useEffect(() => {
    if (showLogs && logRef.current) {
      logRef.current.scrollTop = logRef.current.scrollHeight;
    }
  }, [showLogs, job?.logs.length]);

  if (!running || !job || (job.status !== "running" && job.status !== "pending")) {
    return null;
  }

  const handleCancel = async () => {
    if (!onCancel || cancelling) return;
    setCancelling(true);
    try {
      await onCancel();
    } finally {
      setCancelling(false);
    }
  };

  return (
    <div className="card anim-pop mb-4 p-3">
      <div className="flex items-center gap-3">
        <span className="rounded-lg bg-primary/12 px-2 py-1 text-[10px] font-extrabold uppercase tracking-widest text-primary-strong">
          {job.kind}
        </span>
        <div className="flex-1">
          <ProgressBar value={job.progress} />
        </div>
        <span className="w-52 truncate text-xs text-muted">{job.stage}</span>
        <button
          onClick={() => setShowLogs(!showLogs)}
          className="flex items-center gap-1 text-xs text-muted transition-colors hover:text-ink"
        >
          <Terminal size={13} />
          {showLogs ? t("ws.hideLog") : t("ws.log")}
        </button>
        {onCancel && (
          <button
            onClick={() => void handleCancel()}
            disabled={cancelling}
            className="flex items-center gap-1 text-xs text-muted transition-colors hover:text-red-500 disabled:opacity-50"
          >
            <X size={13} />
            {cancelling ? t("ws.cancelling") : t("ws.cancel")}
          </button>
        )}
      </div>

      {showLogs && (
        <div
          ref={logRef}
          dir="ltr"
          className="mt-2 max-h-44 overflow-y-auto rounded-xl bg-base p-3 font-mono text-[11px] leading-relaxed text-muted"
        >
          {(job.logs ?? []).map((line, i) => (
            <div key={i}>{line}</div>
          ))}
        </div>
      )}
    </div>
  );
}
