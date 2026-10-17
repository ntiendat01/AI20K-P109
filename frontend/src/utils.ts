export function formatBudget(value: unknown): string {
  return `${Number(value).toLocaleString("vi-VN", { maximumFractionDigits: 2 })} VND`;
}

export function formatDate(value: string): string {
  return new Intl.DateTimeFormat("vi-VN", { day: "2-digit", month: "2-digit", year: "numeric" })
    .format(new Date(`${value.slice(0, 10)}T00:00:00`));
}

export const PURCHASE_ITEMS_CSV_TEMPLATE_URL = "/demo/danh_sach_vat_lieu_xay_dung.csv";

export function formatComparisonMoney(value: unknown): string {
  const amount = Number(value);
  return Number.isFinite(amount) ? amount.toLocaleString("vi-VN", { maximumFractionDigits: 2 }) : "—";
}

export function parseReviewMoney(value: unknown): number {
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

export function formatReviewMoney(value: unknown): string {
  const amount = parseReviewMoney(value);
  return Number.isFinite(amount) ? amount.toLocaleString("vi-VN", { maximumFractionDigits: 2 }) : "";
}
