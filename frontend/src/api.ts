import { API_ROOT } from "./config";
import type { Session } from "./types";

export class ApiError extends Error {
  status: number;
  validationErrors?: Array<{ loc: Array<string | number>; msg: string }>;

  constructor(message: string, status: number, validationErrors?: ApiError["validationErrors"]) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.validationErrors = validationErrors;
  }
}

export async function apiRequest<T>(path: string, session: Session, options: RequestInit = {}): Promise<T> {
  const response = await fetch(`${API_ROOT}${path}`, {
    ...options,
    headers: { Authorization: `Bearer ${session.access_token}`, ...(options.headers || {}) },
  });
  const body = response.status === 204 ? "" : await response.text();
  let data: any = null;
  if (body) {
    try {
      data = JSON.parse(body);
    } catch {
      data = { detail: `Máy chủ không thể hoàn tất yêu cầu (HTTP ${response.status}). Vui lòng thử lại.` };
    }
  }
  if (!response.ok) {
    const message = typeof data?.detail === "string"
      ? data.detail
      : "Dữ liệu chưa hợp lệ. Kiểm tra lại các trường đã nhập.";
    throw new ApiError(message, response.status, Array.isArray(data?.detail) ? data.detail : undefined);
  }
  return data as T;
}

export async function apiBlob(path: string, session: Session): Promise<{ blob: Blob; response: Response }> {
  const response = await fetch(`${API_ROOT}${path}`, {
    headers: { Authorization: `Bearer ${session.access_token}` },
  });
  if (!response.ok) {
    const payload = await response.json().catch(() => ({}));
    throw new ApiError(payload.detail || "Không tải được dữ liệu.", response.status);
  }
  return { blob: await response.blob(), response };
}
