export type Role = "procurement" | "manager";

export interface User {
  id: string;
  name: string;
  email: string;
  role: Role;
}

export interface Session {
  access_token: string;
  user: User;
}

export interface FlashMessage {
  message: string;
  tone: "success" | "error" | "info";
}

export interface PurchaseItem {
  item_id?: string;
  id?: string;
  order_index?: number;
  product_name: string;
  product_code?: string;
  quantity: number;
  unit: string;
  notes?: string;
}

export interface PurchaseRequest {
  id: string;
  code: string;
  category: string;
  status: string;
  creator_name?: string;
  estimated_budget: number;
  delivery_due_date: string;
  created_at: string;
  requested_quantity?: number;
  quantity?: number;
  requested_uom?: string;
  target_currency?: string;
  metadata?: {
    budget?: number | null;
    delivery_time?: string | null;
    department?: string | null;
    requested_by?: string | null;
    purpose?: string | null;
  } | null;
  items?: PurchaseItem[];
  quotation_count?: number;
  rejection_reason?: string;
  po_id?: string;
  version?: number;
}

export interface QuotationItem {
  matched_pr_item_id?: string | null;
  match_status?: string | null;
  product_code?: string;
  product_name: string;
  unit?: string;
  quantity: number;
  unit_price: number;
  line_total: number;
}

export interface Quotation {
  id: string;
  pr_id: string;
  supplier_id?: string | null;
  supplier_name: string;
  source_filename: string;
  status: "confirmed" | "unconfirmed" | string;
  items: QuotationItem[];
  cache_hit?: boolean;
  extraction_warnings?: string[];
  delivery_time?: string;
  payment_terms?: string;
  warranty?: string;
  currency?: string;
  vat_rate?: number | null;
  vat_included?: boolean | null;
  shipping_fee?: number | null;
  lead_time_days?: number | null;
  warranty_months?: number | null;
}

export type JsonObject = Record<string, any>;
