import type { SVGProps } from "react";

const paths: Record<string, React.ReactNode> = {
  brand: <><path d="M6 7.5 12 12l6-4.5M6 16.5 12 12l6 4.5" /><circle cx="6" cy="7.5" r="2" fill="currentColor" stroke="none" /><circle cx="18" cy="7.5" r="2" fill="currentColor" stroke="none" /><circle cx="6" cy="16.5" r="2" fill="currentColor" stroke="none" /><circle cx="18" cy="16.5" r="2" fill="currentColor" stroke="none" /><circle cx="12" cy="12" r="2.25" fill="currentColor" stroke="none" /></>,
  workspace: <><rect x="4" y="4" width="6" height="6" rx="1" /><rect x="14" y="4" width="6" height="6" rx="1" /><rect x="4" y="14" width="6" height="6" rx="1" /><rect x="14" y="14" width="6" height="6" rx="1" /></>,
  request: <><path d="M7 3.75h7l3.25 3.25v13.25H7z" /><path d="M14 3.75V7h3.25M9.75 12h5.5m-2.75-2.75v5.5" /></>,
  approvals: <><path d="M12 3.5 19 6v5.25c0 4.35-2.92 7.6-7 9.25-4.08-1.65-7-4.9-7-9.25V6z" /><path d="m8.7 12.1 2.05 2.05 4.7-4.7" /></>,
  history: <><path d="M4.25 12a7.75 7.75 0 1 0 2.1-5.3" /><path d="M4.25 5.75v4h4M12 7.5V12l3.1 1.9" /></>,
  bell: <><path d="M18 9a6 6 0 0 0-12 0c0 7-3 7-3 9h18c0-2-3-2-3-9" /><path d="M10 21h4" /></>,
  logout: <><path d="M10 17l5-5-5-5" /><path d="M15 12H3M21 3v18" /></>,
  "panel-left-close": <><rect x="3" y="4" width="18" height="16" rx="2" /><path d="M9 4v16M15 9l-3 3 3 3" /></>,
  "panel-left-open": <><rect x="3" y="4" width="18" height="16" rx="2" /><path d="M9 4v16M12 9l3 3-3 3" /></>,
  plus: <path d="M12 5v14M5 12h14" />,
  check: <path d="m5 12 4.25 4.25L19 6.5" />,
  "chevron-left": <path d="m15 18-6-6 6-6" />,
  "chevron-right": <path d="m9 18 6-6-6-6" />,
  "arrow-right": <path d="M5 12h14M13 6l6 6-6 6" />,
  "arrow-left": <path d="M19 12H5m6-6-6 6 6 6" />,
  "arrow-down": <path d="M12 5v14m6-6-6 6-6-6" />,
  search: <><circle cx="11" cy="11" r="6.5" /><path d="m16 16 4 4" /></>,
  edit: <path d="M13.5 5.5 18.5 10.5M4.5 19.5l3.9-.9L19 8a2.12 2.12 0 0 0-3-3L5.4 15.6z" />,
  close: <path d="m6 6 12 12M18 6 6 18" />,
  upload: <path d="M12 16V4m0 0L7.5 8.5M12 4l4.5 4.5M5 14v5h14v-5" />,
  "file-text": <path d="M7 3.5h7l3 3v14H7zM14 3.5v3h3M9.5 11h5m-5 3h5m-5 3h3" />,
  "alert-triangle": <><path d="M10.25 4.25 3.2 17.1A2 2 0 0 0 4.95 20h14.1a2 2 0 0 0 1.75-2.9L13.75 4.25a2 2 0 0 0-3.5 0Z" /><path d="M12 9v4m0 3h.01" /></>,
  lock: <><rect x="5" y="10" width="14" height="10" rx="2" /><path d="M8 10V7a4 4 0 0 1 8 0v3M12 14v2" /></>,
  clock: <><circle cx="12" cy="12" r="8.5" /><path d="M12 7.5V12l3 2" /></>,
  "trending-up": <><path d="m4 16 6-6 4 4 6-7" /><path d="M15 7h5v5" /></>,
  loader: <path d="M19 12a7 7 0 1 1-2.05-4.95" />,
  settings: <><circle cx="12" cy="12" r="3" /><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1 0 2.83 2 2 0 0 1-2.83 0l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-2 2 2 2 0 0 1-2-2v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83 0 2 2 0 0 1 0-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1-2-2 2 2 0 0 1 2-2h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 0-2.83 2 2 0 0 1 2.83 0l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 2-2 2 2 0 0 1 2 2v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 0 2 2 0 0 1 0 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 2 2 2 2 0 0 1-2 2h-.09a1.65 1.65 0 0 0-1.51 1z" /></>,
  sliders: <><line x1="4" y1="21" x2="4" y2="14" /><line x1="4" y1="10" x2="4" y2="3" /><line x1="12" y1="21" x2="12" y2="12" /><line x1="12" y1="8" x2="12" y2="3" /><line x1="20" y1="21" x2="20" y2="16" /><line x1="20" y1="12" x2="20" y2="3" /><line x1="1" y1="14" x2="7" y2="14" /><line x1="9" y1="8" x2="15" y2="8" /><line x1="17" y1="16" x2="23" y2="16" /></>,
  shield: <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" />,
  cpu: <><rect x="4" y="4" width="16" height="16" rx="2" /><rect x="9" y="9" width="6" height="6" /><line x1="9" y1="1" x2="9" y2="4" /><line x1="15" y1="1" x2="15" y2="4" /><line x1="9" y1="20" x2="9" y2="23" /><line x1="15" y1="20" x2="15" y2="23" /><line x1="20" y1="9" x2="23" y2="9" /><line x1="20" y1="14" x2="23" y2="14" /><line x1="1" y1="9" x2="4" y2="9" /><line x1="1" y1="14" x2="4" y2="14" /></>,
};

export function Icon({ name, className = "", ...props }: { name: string } & SVGProps<SVGSVGElement>) {
  if (!paths[name]) return null;
  return <svg className={`app-icon ${className}`} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" focusable="false" {...props}>{paths[name]}</svg>;
}
