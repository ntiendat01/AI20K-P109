export const API_ROOT = "/api/v1";
export const STORAGE_KEY = "procura_demo_session";
export const FLASH_KEY = "procura_ui_flash";
export const ANALYSIS_POLL_INTERVAL_MS = 2_000;
export const ANALYSIS_POLL_MAX_WAIT_MS = 6 * 60 * 1_000;

export type NavItem = readonly [string, string, string];

export interface NavGroup {
  readonly title: string;
  readonly items: readonly NavItem[];
}

export const roleConfig = {
  procurement: {
    label: "Nhân viên mua sắm",
    home: "/dashboard",
    nav: [
      ["/dashboard", "workspace", "Dashboard"],
      ["/requests", "request", "Danh sách đề nghị"],
      ["/settings", "settings", "Cấu hình hệ thống"],
    ] as const,
    navGroups: [
      {
        title: "TỔNG QUAN",
        items: [
          ["/dashboard", "workspace", "Dashboard"],
        ],
      },
      {
        title: "NGHIỆP VỤ MUA SẮM",
        items: [
          ["/requests", "request", "Danh sách đề nghị"],
          ["/purchase-orders", "file-text", "Đơn mua hàng (PO)"],
        ],
      },
      {
        title: "HỆ THỐNG",
        items: [
          ["/settings", "settings", "Cấu hình hệ thống"],
        ],
      },
    ] as const,
  },
  manager: {
    label: "Quản lý phê duyệt",
    home: "/dashboard",
    nav: [
      ["/dashboard", "workspace", "Dashboard"],
      ["/requests", "approvals", "Danh sách chờ duyệt"],
      ["/purchase-orders", "file-text", "Đơn mua hàng (PO)"],
      ["/settings", "settings", "Cấu hình hệ thống"],
    ] as const,
    navGroups: [
      {
        title: "TỔNG QUAN",
        items: [
          ["/dashboard", "workspace", "Dashboard"],
        ],
      },
      {
        title: "QUẢN LÝ PHÊ DUYỆT",
        items: [
          ["/requests", "approvals", "Danh sách chờ duyệt"],
          ["/purchase-orders", "file-text", "Đơn mua hàng (PO)"],
        ],
      },
      {
        title: "HỆ THỐNG",
        items: [
          ["/settings", "settings", "Cấu hình hệ thống"],
        ],
      },
    ] as const,
  },
} as const;

export const statusLabels: Record<string, string> = {
  draft: "Nháp",
  awaiting_quotation: "Chờ báo giá",
  comparing: "Đang so sánh",
  pending_approval: "Chờ duyệt",
  approved: "Đã duyệt",
  rejected: "Từ chối",
};
