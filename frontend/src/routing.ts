export function legacyHashToPath(hash: string): string | null {
  if (!hash.startsWith("#/")) return null;
  const legacy = hash.slice(2);
  if (legacy === "workspace") return "/dashboard";
  if (legacy === "new-pr") return "/purchase-requests/new";
  if (legacy.startsWith("pr/")) return `/purchase-requests/${legacy.slice(3)}`;
  if (legacy.startsWith("quotations/")) return `/purchase-requests/${legacy.slice(11)}/quotations`;
  if (legacy.startsWith("comparison/")) return `/purchase-requests/${legacy.slice(11)}/comparison`;
  if (legacy.startsWith("po/")) return `/purchase-orders/${legacy.slice(3)}`;
  return `/${legacy}`;
}
