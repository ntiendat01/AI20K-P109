export function escapeHtml(value) {
  return String(value).replace(/[&<>"]/g, (character) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" })[character]);
}

export function formatBudget(value) {
  return `${Number(value).toLocaleString("vi-VN", { maximumFractionDigits: 2 })} VND`;
}

export function formatDate(value) {
  return new Intl.DateTimeFormat("vi-VN", { day: "2-digit", month: "2-digit", year: "numeric" }).format(new Date(`${value}T00:00:00`));
}

export function formatComparisonMoney(value) {
  const amount = Number(value);
  return Number.isFinite(amount) ? amount.toLocaleString("vi-VN", { maximumFractionDigits: 2 }) : "—";
}

export function parseReviewMoney(value) {
  let formatted = String(value ?? "").replace(/[^\d,.-]/g, "");
  if (!formatted) return Number.NaN;
  if (/^\d{1,3}(?:\.\d{3})+$/.test(formatted)) formatted = formatted.replace(/\./g, "");
  else if (/^\d{1,3}(?:,\d{3})+$/.test(formatted)) formatted = formatted.replace(/,/g, "");
  else if (formatted.includes(",") && formatted.includes(".")) {
    const decimalSeparator = formatted.lastIndexOf(",") > formatted.lastIndexOf(".") ? "," : ".";
    const groupSeparator = decimalSeparator === "," ? "." : ",";
    formatted = formatted.replaceAll(groupSeparator, "").replace(decimalSeparator, ".");
  } else if (formatted.includes(",")) formatted = formatted.replace(",", ".");
  return Number(formatted);
}

export function formatReviewMoney(value) {
  const amount = parseReviewMoney(value);
  return Number.isFinite(amount) ? amount.toLocaleString("vi-VN", { maximumFractionDigits: 2 }) : "";
}
