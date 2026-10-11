from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, Field

from src.models.purchase_request import PurchaseRequest as NewPurchaseRequest


class ChatRequest(BaseModel):
    """Yêu cầu Hội thoại / Chat với Trợ lý Mua sắm (Chat Request Schema).

    Chức năng:
    - Tiếp nhận nội dung tin nhắn hỏi đáp tự do từ phía người dùng gửi tới trợ lý.

    Thuộc tính:
    - `message`: Nội dung tin nhắn của người dùng (từ 1 đến 5000 ký tự).
    """

    message: str = Field(..., min_length=1, max_length=5000, description="Tin nhắn từ user")


class ChatResponse(BaseModel):
    """Phản hồi Hội thoại từ Trợ lý Mua sắm (Chat Response Schema).

    Chức năng:
    - Đóng gói nội dung câu trả lời của trợ lý.

    Thuộc tính:
    - `response`: Câu trả lời hoàn chỉnh hiển thị cho người dùng.
    """

    response: str = Field(..., description="Phản hồi từ agent")
    analysis: str = Field(default="", description="Phân tích nội bộ")


class LoginRequest(BaseModel):
    email: str = Field(..., min_length=3, max_length=254)
    password: str = Field(..., min_length=1, max_length=128)


class UserProfile(BaseModel):
    id: str
    name: str
    email: str
    role: Literal["procurement", "manager"]


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_at: datetime
    user: UserProfile


class PRStatus(StrEnum):
    DRAFT = "draft"
    AWAITING_QUOTATION = "awaiting_quotation"
    COMPARING = "comparing"
    PENDING_APPROVAL = "pending_approval"
    APPROVED = "approved"
    REJECTED = "rejected"


class PurchaseRequestCreate(BaseModel):
    code: str = Field(..., min_length=3, max_length=50, pattern=r"^[A-Za-z0-9_-]+$")
    category: str = Field(..., min_length=3, max_length=500)
    quantity: int = Field(..., gt=0, le=1_000_000)
    estimated_budget: Decimal = Field(..., gt=0, max_digits=14, decimal_places=2)
    delivery_due_date: date

    # ==============================================================================
    # RÀNG BUỘC HẠN GIAO:
    # - Đã bỏ ràng buộc bắt buộc ngày giao phải ở tương lai để hỗ trợ dữ liệu test/lịch sử
    # ==============================================================================
    # @field_validator("delivery_due_date")
    # @classmethod
    # def delivery_due_date_must_be_future(cls, value: date) -> date:
    #     if value <= date.today():
    #         raise ValueError("Hạn giao phải là một ngày trong tương lai.")
    #     return value


class PurchaseRequestUpdate(BaseModel):
    """Các thông tin PR được phép sửa trước khi tải báo giá đầu tiên."""

    category: str = Field(..., min_length=3, max_length=500)
    estimated_budget: Decimal = Field(..., gt=0, max_digits=14, decimal_places=2)


class PurchaseRequest(BaseModel):
    id: str
    code: str
    creator_id: str
    creator_name: str
    category: str
    quantity: int
    estimated_budget: Decimal
    delivery_due_date: date
    status: PRStatus
    quotation_count: int = 0
    rejection_reason: str | None = None
    po_id: str | None = None
    created_at: datetime = Field(default_factory=datetime.now)


class QuotationStatus(StrEnum):
    UNCONFIRMED = "unconfirmed"
    CONFIRMED = "confirmed"


class QuotationItem(BaseModel):
    product_name: str = Field(..., min_length=1, max_length=500)
    product_code: str = Field(default="", max_length=100)
    unit: str = Field(default="", max_length=100)
    quantity: int = Field(..., gt=0, le=1_000_000)
    unit_price: Decimal = Field(..., gt=0, max_digits=14, decimal_places=2)
    line_total: Decimal = Field(..., gt=0, max_digits=14, decimal_places=2)


class Quotation(BaseModel):
    supplier_id: str | None = None
    id: str
    pr_id: str
    supplier_name: str
    source_filename: str
    source_hash: str
    source_path: str = Field(exclude=True)
    source_content_type: str
    extraction_version: int = 1
    delivery_time: str = ""
    payment_terms: str = ""
    warranty: str = ""
    currency: str = ""
    items: list[QuotationItem] = Field(default_factory=list)
    status: QuotationStatus = QuotationStatus.UNCONFIRMED
    extraction_warnings: list[str] = Field(default_factory=list)
    cache_hit: bool = False
    created_at: datetime = Field(default_factory=datetime.now)
    confirmed_at: datetime | None = None
    vat_rate: Decimal | None = Field(default=None, ge=0, le=1)
    vat_included: bool | None = None
    shipping_fee: Decimal | None = Field(default=None, ge=0)
    lead_time_days: int | None = Field(default=None, ge=0)
    warranty_months: int | None = Field(default=None, ge=0)
    goods_total_including_tax: Decimal | None = Field(default=None, ge=0)
    shipping_total_including_tax: Decimal | None = Field(default=None, ge=0)
    confirmation_audit: dict | None = Field(default=None, exclude=True)
    extraction_mode: str = "parser"
    agent_extractions: list[dict] = Field(default_factory=list)
    source_ocr_text: str | None = Field(default=None, exclude=True)


class QuotationConfirmation(BaseModel):
    supplier_name: str = Field(..., min_length=2, max_length=200)
    delivery_time: str = Field(default="", max_length=500)
    payment_terms: str = Field(default="", max_length=1000)
    items: list[QuotationItem] = Field(..., min_length=1, max_length=100)
    currency: str | None = None
    vat_rate: Decimal = Field(..., ge=0, le=1)
    vat_included: bool
    shipping_fee: Decimal = Field(..., ge=0)
    lead_time_days: int = Field(..., ge=0)
    warranty_months: int = Field(..., ge=0)
    goods_total_including_tax: Decimal | None = Field(default=None, ge=0)
    shipping_total_including_tax: Decimal | None = Field(default=None, ge=0)


class ComplianceStatus(StrEnum):
    COMPLIANT = "compliant"
    WARNING = "warning"
    NON_COMPLIANT = "non_compliant"


class SupplierComparisonCriteria(BaseModel):
    supplier_name: str
    quotation_id: str
    total_amount: Decimal
    currency: str = "VNĐ"
    within_budget: bool
    budget_variance: Decimal
    budget_variance_percent: float
    delivery_time: str
    estimated_delivery_days: int | None = None
    meets_deadline: bool = True
    payment_terms: str
    payment_risk_level: Literal["low", "medium", "high"] = "low"
    warranty: str
    warranty_months: int = 12
    quality_score: float = Field(..., ge=0.0, le=100.0)
    overall_score: float = Field(..., ge=0.0, le=100.0)
    compliance_status: ComplianceStatus
    compliance_notes: list[str] = Field(default_factory=list)
    strengths: list[str] = Field(default_factory=list)
    drawbacks: list[str] = Field(default_factory=list)


class ItemOffer(BaseModel):
    unit_price: Decimal
    line_total: Decimal
    is_best_price: bool = False


class NormalizedItemComparison(BaseModel):
    product_name: str
    product_code: str = ""
    unit: str = ""
    quantity: int
    lowest_unit_price: Decimal
    offers: dict[str, ItemOffer] = Field(default_factory=dict)


class AgentExecutionStep(BaseModel):
    step: int
    title: str
    status: str = "completed"
    detail: str
    timestamp: datetime = Field(default_factory=datetime.now)


class AgentRecommendation(BaseModel):
    recommended_supplier: str
    recommended_quotation_id: str
    overall_score: float
    confidence_score: float = 0.95
    summary: str
    detailed_rationale: str
    tradeoff_analysis: str
    policy_summary: str
    execution_steps: list[AgentExecutionStep] = Field(default_factory=list)


class PRComparisonResponse(BaseModel):
    pr: NewPurchaseRequest
    suppliers: list[SupplierComparisonCriteria]
    items: list[NormalizedItemComparison]
    recommendation: AgentRecommendation
    generated_at: datetime = Field(default_factory=datetime.now)


class POStatus(StrEnum):
    DRAFT = "draft"
    CANCELLED = "cancelled"


class PurchaseOrderItem(BaseModel):
    product_name: str
    product_code: str = ""
    unit: str = ""
    quantity: int
    unit_price: Decimal
    line_total: Decimal


class PurchaseOrder(BaseModel):
    id: str
    code: str
    pr_id: str
    pr_code: str
    quotation_id: str
    supplier_name: str
    items: list[PurchaseOrderItem]
    total_amount: Decimal
    currency: str = "VNĐ"
    delivery_time: str = ""
    payment_terms: str = ""
    warranty: str = ""
    status: POStatus = POStatus.DRAFT
    approver_id: str
    approver_name: str
    approved_at: datetime = Field(default_factory=datetime.now)
    manager_note: str | None = None
    created_at: datetime = Field(default_factory=datetime.now)
    subtotal: Decimal | None = None
    shipping_amount: Decimal | None = None
    tax_amount: Decimal | None = None
    prices_include_tax: bool | None = None
    recommendation_id: str | None = None
    recommendation_version: int | None = None
    snapshot_revision: str | None = None


class ApprovePRRequest(BaseModel):
    selected_quotation_id: str | None = None
    manager_note: str | None = None


class RejectPRRequest(BaseModel):
    rejection_reason: str = Field(..., min_length=3, max_length=500)
