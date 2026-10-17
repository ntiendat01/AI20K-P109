import { useSyncExternalStore } from "react";
import { apiRequest } from "./api";
import type { Session } from "./types";

export type QuotationExtractionJob = {
  id: string;
  prId: string;
  code: string;
  userId: string;
  status: "running" | "stopping" | "completed" | "failed" | "cancelled";
  total: number;
  completed: number;
  errors: string[];
  hidden?: boolean;
  finishedAt?: number;
};

export const JOB_AUTO_HIDE_MS = 60_000;
const storageKey = "dotcom-quotation-extraction-jobs";
const listeners = new Set<() => void>();
const controllers = new Map<string, AbortController>();

function restore(): QuotationExtractionJob[] {
  try {
    const saved = JSON.parse(sessionStorage.getItem(storageKey) || "[]") as QuotationExtractionJob[];
    if (!Array.isArray(saved)) return [];
    // File objects and browser requests do not survive a full reload.
    return saved.map((job) => ["running", "stopping"].includes(job.status) ? {
      ...job,
      id: job.id || crypto.randomUUID(),
      status: "failed" as const,
      finishedAt: Date.now(),
      errors: [...(job.errors || []), "Trang đã tải lại trong lúc trích xuất. Kiểm tra các báo giá đã lưu và tải lại file còn thiếu."],
    } : { ...job, id: job.id || crypto.randomUUID(), finishedAt: job.finishedAt || Date.now() });
  } catch { return []; }
}

let jobs = restore();
let generation = 0;
sessionStorage.setItem(storageKey, JSON.stringify(jobs));

function publish(next: QuotationExtractionJob[]) {
  jobs = next;
  sessionStorage.setItem(storageKey, JSON.stringify(jobs));
  listeners.forEach((listener) => listener());
}

function replace(job: QuotationExtractionJob) {
  publish(jobs.map((item) => item.id === job.id ? { ...job, hidden: item.hidden } : item));
}

export function subscribeQuotationJobs(listener: () => void) {
  listeners.add(listener);
  return () => { listeners.delete(listener); };
}

export function getQuotationJobs() { return jobs; }

export function useQuotationJobs() {
  return useSyncExternalStore(subscribeQuotationJobs, getQuotationJobs);
}

export function hideQuotationJob(id: string) {
  publish(jobs.map((job) => job.id === id ? { ...job, hidden: true } : job));
}

export function hideExpiredQuotationJobs(now = Date.now()) {
  if (!jobs.some((job) => !job.hidden && job.finishedAt && now - job.finishedAt >= JOB_AUTO_HIDE_MS)) return;
  publish(jobs.map((job) => !job.hidden && job.finishedAt && now - job.finishedAt >= JOB_AUTO_HIDE_MS ? { ...job, hidden: true } : job));
}

export function clearQuotationJobs() {
  generation += 1;
  controllers.forEach((controller) => controller.abort());
  controllers.clear();
  publish([]);
}

export function startQuotationExtraction(prId: string, code: string, files: File[], session: Session): boolean {
  if (!files.length || jobs.some((job) => job.prId === prId && job.userId === session.user.id && ["running", "stopping"].includes(job.status))) return false;
  const job: QuotationExtractionJob = { id: crypto.randomUUID(), prId, code, userId: session.user.id, status: "running", total: files.length, completed: 0, errors: [] };
  const controller = new AbortController();
  const currentGeneration = generation;
  const isRunning = () => jobs.some((item) => item.id === job.id && item.status === "running");
  controllers.set(job.id, controller);
  publish([...jobs.filter((item) => item.prId !== prId || item.userId !== session.user.id), job]);

  // The queue belongs to the module, so navigating away from Step 2 does not stop it.
  void (async () => {
    try {
      for (const file of files) {
        if (currentGeneration !== generation || !isRunning()) return;
        const body = new FormData();
        body.append("file", file);
        body.append("extraction_mode", "agent");
        body.append("extraction_job_id", job.id);
        try {
          await apiRequest(`/prs/${encodeURIComponent(prId)}/quotations`, session, { method: "POST", body, signal: controller.signal });
          if (!isRunning()) return;
          job.completed += 1;
        } catch (error) {
          if (!isRunning() || currentGeneration !== generation) return;
          job.errors.push(`${file.name}: ${error instanceof Error ? error.message : "Không thể trích xuất."}`);
        }
        replace(job);
      }
      if (currentGeneration !== generation || !isRunning()) return;
      job.status = job.errors.length ? "failed" : "completed";
      job.finishedAt = Date.now();
      replace(job);
    } finally {
      controllers.delete(job.id);
    }
  })();
  return true;
}

export async function cancelQuotationExtraction(id: string, session: Session): Promise<boolean> {
  const job = jobs.find((item) => item.id === id && item.userId === session.user.id);
  if (!job || job.status !== "running") return false;
  job.status = "stopping";
  replace(job);
  controllers.get(id)?.abort();
  try {
    await apiRequest(`/prs/${encodeURIComponent(job.prId)}/quotations/cancel`, session, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ job_id: id }),
    });
    job.status = "cancelled";
  } catch (error) {
    job.status = "failed";
    job.errors.push(`Không xác nhận được lệnh ngừng trên máy chủ: ${error instanceof Error ? error.message : "Vui lòng kiểm tra lại."}`);
  }
  job.finishedAt = Date.now();
  replace(job);
  return job.status === "cancelled";
}
