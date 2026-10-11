import { API_ROOT } from "../config/constants.js";

export async function requestApi(path, session, options = {}) {
  const response = await fetch(`${API_ROOT}${path}`, {
    ...options,
    headers: { Authorization: `Bearer ${session.access_token}`, ...(options.headers || {}) },
  });
  const body = response.status === 204 ? "" : await response.text();
  let data = null;
  if (body) {
    try { data = JSON.parse(body); }
    catch { data = { detail: `Máy chủ không thể hoàn tất yêu cầu (HTTP ${response.status}). Vui lòng thử lại.` }; }
  }
  if (!response.ok) {
    const error = new Error(typeof data?.detail === "string" ? data.detail : "Dữ liệu chưa hợp lệ. Kiểm tra lại các trường đã nhập.");
    error.status = response.status;
    if (Array.isArray(data?.detail)) error.validationErrors = data.detail;
    throw error;
  }
  return data;
}
