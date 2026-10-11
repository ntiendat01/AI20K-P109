const icons = {
  brand: `<path d="M6 7.5 12 12l6-4.5M6 16.5 12 12l6 4.5" /><circle cx="6" cy="7.5" r="2" fill="currentColor" stroke="none" /><circle cx="18" cy="7.5" r="2" fill="currentColor" stroke="none" /><circle cx="6" cy="16.5" r="2" fill="currentColor" stroke="none" /><circle cx="18" cy="16.5" r="2" fill="currentColor" stroke="none" /><circle cx="12" cy="12" r="2.25" fill="currentColor" stroke="none" />`,
  workspace: `<rect x="4" y="4" width="6" height="6" rx="1" /><rect x="14" y="4" width="6" height="6" rx="1" /><rect x="4" y="14" width="6" height="6" rx="1" /><rect x="14" y="14" width="6" height="6" rx="1" />`,
  request: `<path d="M7 3.75h7l3.25 3.25v13.25H7z" /><path d="M14 3.75V7h3.25M9.75 12h5.5m-2.75-2.75v5.5" />`,
  quotations: `<path d="M5 5.25h10.25L19 9v9.75H5z" /><path d="M15.25 5.25V9H19M8 12.25h8m-8 3.25h5" /><path d="M3.5 8.5v11.75H15" />`,
  approvals: `<path d="M12 3.5 19 6v5.25c0 4.35-2.92 7.6-7 9.25-4.08-1.65-7-4.9-7-9.25V6z" /><path d="m8.7 12.1 2.05 2.05 4.7-4.7" />`,
  history: `<path d="M4.25 12a7.75 7.75 0 1 0 2.1-5.3" /><path d="M4.25 5.75v4h4M12 7.5V12l3.1 1.9" />`,
};

export function icon(name, className = "") {
  const paths = icons[name];
  if (!paths) return "";
  return `<svg class="app-icon ${className}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" focusable="false">${paths}</svg>`;
}
