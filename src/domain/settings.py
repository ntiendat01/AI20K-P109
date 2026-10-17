"""Domain contracts and models for dynamic system configuration."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class SynonymPair(BaseModel):
    """Pair of source text and canonical target text for fuzzy product matching."""

    id: str = Field(min_length=1)
    source: str = Field(min_length=1)
    target: str = Field(min_length=1)

    model_config = ConfigDict(extra="ignore")


class SystemSettings(BaseModel):
    """Dynamic configuration values adjustable by Buyer and Manager roles."""

    # 1. Extraction & OCR
    confidence_threshold: float = Field(default=0.80, ge=0.50, le=0.99, description="Ngưỡng tin cậy cảnh báo OCR")
    high_confidence_threshold: float = Field(default=0.95, ge=0.80, le=1.0, description="Ngưỡng tin cậy cao OCR")
    default_currency: str = Field(default="VND", description="Đơn vị tiền tệ ngầm định")
    default_vat_rate: float = Field(default=0.10, ge=0.0, le=1.0, description="Thuế suất VAT ngầm định")
    auto_highlight_bbox: bool = Field(default=True, description="Tự động highlight Bounding Box khi hover")
    auto_scroll_pdf: bool = Field(default=True, description="Tự động cuộn trang tài liệu gốc đến trường đang chọn")

    # 2. Product Matching (Fuzzy matching)
    auto_match_threshold: float = Field(default=0.90, ge=0.50, le=1.0, description="Ngưỡng tự động ghép đôi hàng hóa")
    suggest_threshold: float = Field(default=0.70, ge=0.40, le=1.0, description="Ngưỡng hiển thị gợi ý ứng viên")
    min_name_score: float = Field(default=0.55, ge=0.30, le=1.0, description="Điểm tương đồng tên tối thiểu")
    synonyms: list[SynonymPair] = Field(default_factory=list, description="Từ điển từ đồng nghĩa & viết tắt ngành hàng")

    # 3. Supplier Comparison & Evaluation (Manager role)
    deviation_threshold: float = Field(default=0.15, ge=0.01, le=0.50, description="Ngưỡng cảnh báo lệch giá thị trường")
    min_quotations_required: int = Field(default=2, ge=1, le=10, description="Số lượng báo giá tối thiểu bắt buộc")
    weight_tco: int = Field(default=50, ge=0, le=100, description="Trọng số tổng chi phí TCO")
    weight_lead_time: int = Field(default=25, ge=0, le=100, description="Trọng số tiến độ giao hàng")
    weight_warranty: int = Field(default=15, ge=0, le=100, description="Trọng số thời gian bảo hành")
    weight_payment: int = Field(default=10, ge=0, le=100, description="Trọng số điều khoản công nợ")

    # 4. Approval & Budget Policies (Manager role)
    budget_overrun_alert_pct: float = Field(default=10.0, ge=0.0, le=100.0, description="Ngưỡng vượt dự toán bắt buộc giải trình")
    po_code_prefix: str = Field(default="PO-{YYYYMMDD}-{SEQ}", description="Tiền tố định dạng mã PO tự động")
    approval_sla_hours: int = Field(default=24, ge=1, le=168, description="SLA thời gian cam kết phê duyệt")
    require_rejection_reason: bool = Field(default=True, description="Bắt buộc nhập lý do khi từ chối đề nghị")
    min_rejection_chars: int = Field(default=20, ge=0, le=500, description="Số ký tự tối thiểu khi từ chối")

    # 5. AI Engine & Prompt Directives (Manager role)
    llm_model: str = Field(default="gpt-6-luna", description="Mô hình AI chủ đạo")
    reasoning_effort: str = Field(default="none", description="Mức độ suy luận của LLM")
    decision_prompt_directive: str = Field(default="", description="Chỉ đạo ưu tiên đặc thù cho AI khi lập đề xuất")

    model_config = ConfigDict(extra="ignore")
