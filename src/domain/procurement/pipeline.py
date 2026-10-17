"""Canonical procurement contracts shared by the API and LangGraph workflow."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import AliasChoices, BaseModel, ConfigDict, Field, PlainSerializer, field_validator, model_validator

ConfidenceScore = Annotated[float, Field(ge=0, le=1)]
Quantity = Annotated[
    Decimal,
    Field(gt=0),
    PlainSerializer(float, return_type=float, when_used="json"),
]


class ContractModel(BaseModel):
    """Lớp cơ sở (Base Model) cho tất cả các Schema Hợp đồng trong hệ sinh thái Procurement.

    Thiết lập cấu hình nghiêm ngặt:
    - `extra="forbid"`: Nghiêm cấm các trường nằm ngoài khai báo để tránh sai lệch dữ liệu.
    - `populate_by_name=True`: Cho phép khởi tạo bằng tên thuộc tính Python hoặc alias.
    """

    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class PRData(ContractModel):
    """Dữ liệu Yêu cầu Mua sắm (Purchase Request / PR Requirements).

    Chức năng:
    - Chứa các tiêu chí đầu bài và ràng buộc nghiệp vụ do Buyer thiết lập.
    - Dùng làm mốc quy chuẩn cho Node `normalize` (target_uom, target_currency),
      Node `decision_llm` / `analyze_risks` (đối chiếu deadline, ngân sách, top_n, ngưỡng chênh lệch).

    Thuộc tính:
    - `pr_number`: Mã số định danh của PR (vd: "PR-2026-001").
    - `quantity`: Số lượng hàng hóa/dịch vụ cần mua (> 0).
    - `deadline`: Hạn chót giao hàng yêu cầu.
    - `budget`: Ngân sách trần dự kiến (nếu có).
    - `target_uom`: Đơn vị tính chuẩn hóa mục tiêu (mặc định: "cái").
    - `target_currency`: Loại tiền tệ chuẩn hóa mục tiêu (mặc định: "VND").
    - `top_n`: Số lượng nhà cung cấp tối ưu cần đưa vào đề xuất cuối cùng (3 đến 5).
    - `deviation_threshold`: Ngưỡng sai lệch phần trăm (mặc định 0.15 = 15%) để gắn cờ cảnh báo chênh lệch trong ma trận so sánh.
    """

    pr_number: str = Field(min_length=1, validation_alias=AliasChoices("pr_number", "pr_code"))
    quantity: Quantity
    deadline: date
    budget: float | None = Field(default=None, ge=0)
    target_uom: str = Field(default="cái", min_length=1)
    target_currency: str = Field(default="VND", min_length=1)
    top_n: int = Field(default=3, ge=3, le=5)
    deviation_threshold: float = Field(default=0.15, ge=0, le=1)

    @field_validator("deadline")
    @classmethod
    def deadline_must_not_be_in_the_past(cls, value: date) -> date:
        if value < date.today():
            raise ValueError("deadline must be today or a future date")
        return value


class SourceReference(ContractModel):
    """Thông tin Truy vết Nguồn gốc Dữ liệu (Provenance & Citation Source).

    Chức năng:
    - Lưu vết tọa độ, số trang và đường dẫn tệp tài liệu PDF gốc nơi trích xuất ra giá trị.
    - Hỗ trợ tính năng Audit Trail và gán bằng chứng (Evidence Tracing) ở Node `generate_evidence`.

    Thuộc tính:
    - `document_id`: Định danh tài liệu.
    - `document_path`: Đường dẫn tệp tài liệu trên ổ đĩa.
    - `filename`: Tên tệp PDF báo giá.
    - `page_number`: Số trang PDF chứa thông tin (1-indexed).
    - `source_text`: Đoạn văn bản thô OCR trích xuất được.
    - `bbox`: Tọa độ hộp bao [x0, y0, x1, y1] của vùng chứa dữ liệu trên trang PDF.
    """

    document_id: str | None = None
    document_path: str | None = None
    filename: str | None = None
    page_number: int | None = Field(default=None, ge=1)
    source_text: str | None = None
    bbox: list[float] | None = Field(default=None, min_length=4, max_length=4)

    @model_validator(mode="after")
    def require_source_location(self) -> SourceReference:
        if not any(
            (
                self.document_id,
                self.document_path,
                self.filename,
                self.page_number,
                self.source_text,
                self.bbox,
            )
        ):
            raise ValueError("source reference must identify a document location")
        return self


class Surcharge(ContractModel):
    """Phụ phí phát sinh trong Báo giá của Nhà cung cấp.

    Chức năng:
    - Tách riêng các khoản chi phí ngoài đơn giá (phí vận chuyển, bảo hiểm, bốc xếp, chi phí ẩn...)
      để phục vụ tính toán Tổng chi phí sở hữu (TCO) và kiểm tra tính minh bạch của báo giá.

    Thuộc tính:
    - `kind`: Loại phụ phí ('shipping', 'handling', 'other', 'hidden').
    - `description`: Mô tả chi tiết khoản phí.
    - `amount`: Số tiền phụ phí theo đồng tiền gốc.
    - `currency`: Loại tiền tệ của phụ phí.
    - `included_in_tco`: Cờ xác định phụ phí có được cộng vào TCO hay không.
    - `source`: Nguồn gốc trích xuất phụ phí trong file PDF.
    - `normalized_amount`: Số tiền phụ phí sau khi đã quy đổi về loại tiền tệ của PR.
    - `normalized_currency`: Loại tiền tệ sau chuẩn hóa.
    - `requires_manual_conversion`: Đánh dấu nếu ngoại tệ lạ cần can thiệp quy đổi thủ công.
    """

    kind: Literal["shipping", "handling", "other", "hidden"] = "other"
    description: str | None = None
    amount: float = Field(ge=0)
    currency: str | None = None
    included_in_tco: bool = True
    source: SourceReference | None = None
    normalized_amount: float | None = Field(default=None, ge=0)
    normalized_currency: str | None = None
    requires_manual_conversion: bool = False


class RawExtraction(ContractModel):
    """Dòng Sản phẩm Báo giá Thô (Raw Quote Line / Raw Extraction).

    Chức năng:
    - Đại diện cho một dòng mặt hàng trích xuất từ tài liệu PDF báo giá của NCC trước khi chuẩn hóa.
    - Lưu trữ điểm tin cậy tổng thể (`confidence_score`) và điểm tin cậy từng trường (`field_confidence`).
    - Gắn cờ `needs_confirmation = True` nếu bất kỳ trường nào < 80%, làm cơ sở cho Node `validate_extraction`
      và `confidence_router` quyết định có bắt buộc đối soát HITL hay không.

    Thuộc tính:
    - `extraction_id`: Mã định danh duy nhất (UUID) của dòng trích xuất.
    - `source`: Nguồn gốc tài liệu PDF (file, trang).
    - `supplier_id`: Tên/mã nhà cung cấp.
    - `item_name`: Tên mặt hàng/dịch vụ báo giá.
    - `unit_price`: Đơn giá gốc.
    - `quantity`: Số lượng chào bán.
    - `unit`: Đơn vị tính gốc.
    - `currency`: Đồng tiền báo giá gốc.
    - `vat_rate`: Thuế suất VAT (0.0 đến 1.0).
    - `vat_included`: Đơn giá đã gồm VAT hay chưa.
    - `surcharges`: Danh sách phụ phí đi kèm.
    - `warranty_months`: Thời gian bảo hành (tháng).
    - `lead_time_days`: Thời gian giao hàng (ngày).
    - `confidence_score`: Điểm tin cậy trích xuất tổng thể (0.0 đến 1.0).
    - `field_confidence`: Bản đồ điểm tin cậy chi tiết cho từng trường.
    - `field_needs_confirmation`: Cờ đánh dấu các trường cụ thể cần Buyer xác thực (< 80%).
    - `needs_confirmation`: Cờ tổng thể báo hiệu dòng này cần Buyer xác nhận.
    - `confirmed_by_human`: Trạng thái đã được Buyer duyệt qua hay chưa.
    - `extraction_error`: Thông báo lỗi nếu trích xuất dòng này thất bại.
    """

    extraction_id: str = Field(min_length=1)
    source: SourceReference
    supplier_id: str | None = Field(
        default=None,
        validation_alias=AliasChoices("supplier_id", "supplier", "supplier_name"),
    )
    item_name: str | None = Field(
        default=None,
        validation_alias=AliasChoices("item_name", "product_name"),
    )
    unit_price: float | None = Field(default=None, ge=0)
    quantity: Quantity | None = None
    unit: str | None = Field(default=None, validation_alias=AliasChoices("unit", "uom"))
    currency: str | None = None
    vat_rate: float | None = Field(default=None, ge=0, le=1)
    vat_included: bool | None = Field(
        default=None,
        validation_alias=AliasChoices("vat_included", "is_vat_included"),
    )
    surcharges: list[Surcharge] = Field(default_factory=list)
    warranty_months: int | None = Field(default=None, ge=0)
    lead_time_days: int | None = Field(default=None, ge=0)
    lead_time_min: int | None = Field(default=None, ge=0)
    lead_time_max: int | None = Field(default=None, ge=0)
    lead_time_unit: str | None = None
    confidence_score: float = Field(default=0, ge=0, le=1)
    field_confidence: dict[str, ConfidenceScore] = Field(default_factory=dict)
    field_needs_confirmation: dict[str, bool] = Field(default_factory=dict)
    needs_confirmation: bool = False
    confirmed_by_human: bool = False
    extraction_error: str | None = None

    @model_validator(mode="after")
    def validate_lead_time_range(self) -> RawExtraction:
        if (
            self.lead_time_min is not None
            and self.lead_time_max is not None
            and self.lead_time_min > self.lead_time_max
        ):
            raise ValueError("lead_time_min must not exceed lead_time_max")
        return self

    @model_validator(mode="before")
    @classmethod
    def migrate_legacy_fields(cls, value: object) -> object:
        """Chuyển đổi các định dạng trích xuất phẳng cũ sang cấu trúc chuẩn mực."""
        if not isinstance(value, dict):
            return value

        data = dict(value)
        if "source" not in data:
            document_path = data.pop("document", None)
            page_number = data.pop("page_number", None)
            data["source"] = {
                "document_path": document_path,
                "page_number": page_number,
            }
        else:
            data.pop("document", None)
            data.pop("page_number", None)

        shipping_fee = data.pop("shipping_fee", None)
        if not data.get("surcharges") and shipping_fee is not None:
            data["surcharges"] = [
                {
                    "kind": "shipping",
                    "description": "Shipping fee",
                    "amount": shipping_fee,
                    "currency": data.get("currency"),
                }
            ]
        return data


class NormalizedLine(RawExtraction):
    """Dòng Báo giá Đã Chuẩn hóa (Normalized Quote Line).

    Chức năng:
    - Kế thừa từ `RawExtraction`, bổ sung các trường giá trị sau khi đã được quy đổi ĐVT (UOM) và Tiền tệ
      về hệ quy chuẩn của PR bởi Node `normalize`.
    - Giữ nguyên các trường dữ liệu gốc kế thừa từ `RawExtraction` để đối chiếu và lập bằng chứng.

    Thuộc tính bổ sung:
    - `normalized_quantity`: Số lượng đã quy đổi về ĐVT của PR.
    - `normalized_uom`: ĐVT chuẩn của PR.
    - `normalized_unit_price`: Đơn giá đã quy đổi về ĐVT và Tiền tệ của PR.
    - `normalized_currency`: Loại tiền tệ chuẩn của PR.
    - `requires_manual_conversion`: Cờ đánh dấu nếu không thể tự động quy đổi (cần Buyer can thiệp).
    - `conversion_note`: Ghi chú về tỷ giá hoặc hệ số quy đổi được áp dụng.
    """

    normalized_quantity: Quantity | None = None
    normalized_uom: str | None = None
    normalized_unit_price: float | None = Field(
        default=None,
        ge=0,
        validation_alias=AliasChoices("normalized_unit_price", "normalized_price"),
    )
    normalized_currency: str | None = None
    requires_manual_conversion: bool = Field(
        default=False,
        validation_alias=AliasChoices("requires_manual_conversion", "needs_manual_conversion"),
    )
    conversion_note: str | None = None


class DataNormalized(ContractModel):
    """Báo giá Đã Chuẩn hóa Cấp Nhà Cung Cấp (Supplier-level Normalized Quote / DataNormalized).

    Chức năng:
    - Tập hợp tất cả các dòng mặt hàng (`NormalizedLine`) thuộc về một Nhà cung cấp cụ thể.
    - Dùng làm đầu vào trực tiếp cho các công cụ tính toán TCO, lập ma trận so sánh và phân tích rủi ro.

    Thuộc tính:
    - `supplier_id`: Tên hoặc mã định danh của Nhà cung cấp.
    - `items`: Danh sách các mặt hàng đã được chuẩn hóa.
    - `has_manual_conversion`: Cờ báo hiệu có bất kỳ mặt hàng nào phải quy đổi thủ công hay không.
    - `needs_confirmation`: Báo giá có dòng nào cần Buyer xác nhận hay không.
    - `confirmed_by_human`: Trạng thái đã được người dùng xác nhận toàn bộ.
    """

    supplier_id: str = Field(min_length=1)
    items: list[NormalizedLine]
    has_manual_conversion: bool = False
    needs_confirmation: bool = False
    confirmed_by_human: bool = False


class TCOItem(ContractModel):
    """Kết quả Tính Tổng Chi Phí Sở Hữu Từng Mặt Hàng (Item-level TCO Calculation).

    Chức năng:
    - Chứa kết quả tính toán TCO chi tiết cho một mặt hàng theo công thức xác định (deterministic):
      TCO = (Đơn giá chuẩn hóa * Số lượng chuẩn hóa + Phụ phí) * (1 + Thuế suất VAT).

    Thuộc tính:
    - `item_name`: Tên mặt hàng.
    - `quantity`: Số lượng đã chuẩn hóa.
    - `unit_price`: Đơn giá đã chuẩn hóa.
    - `subtotal`: Thành tiền trước thuế và phụ phí (unit_price * quantity).
    - `surcharges`: Tổng phụ phí phân bổ cho mặt hàng.
    - `vat_rate`: Thuế suất VAT áp dụng.
    - `vat_included`: Đơn giá gốc đã bao gồm VAT hay chưa.
    - `item_tco`: Tổng chi phí sở hữu cuối cùng của mặt hàng.
    """

    item_name: str = Field(
        default="",
        validation_alias=AliasChoices("item_name", "product_name"),
    )
    quantity: Quantity | None = None
    unit_price: float | None = Field(default=None, ge=0)
    subtotal: float = Field(default=0, ge=0)
    surcharges: float = Field(default=0, ge=0)
    vat_rate: float = Field(default=0, ge=0, le=1)
    vat_included: bool = Field(
        default=False,
        validation_alias=AliasChoices("vat_included", "is_vat_included"),
    )
    item_tco: float | None = Field(default=None, ge=0)


class TCOResult(ContractModel):
    """Kết quả Tính Tổng Chi Phí Sở Hữu Cấp Nhà Cung Cấp (Supplier-level TCO Result).

    Chức năng:
    - Lưu trữ tổng chi phí sở hữu toàn diện của một Nhà cung cấp (tính bởi tool `calculate_tco`).
    - Dùng làm căn cứ số học chính xác nhất cho LLM xếp hạng và lập báo cáo tài chính.

    Thuộc tính:
    - `supplier_id`: Định danh Nhà cung cấp.
    - `items_tco`: Danh sách chi tiết TCO từng mặt hàng.
    - `subtotal`: Tổng thành tiền của tất cả mặt hàng.
    - `total_surcharges`: Tổng tất cả các loại phụ phí.
    - `total_vat`: Tổng tiền thuế VAT.
    - `total_tco`: Tổng chi phí sở hữu cuối cùng (Total TCO).
    - `status`: Trạng thái tính toán ('calculated' nếu đủ số liệu, 'missing_data' nếu thiếu dữ liệu).
    - `missing_fields`: Danh sách các trường bị thiếu khiến không thể tính được TCO.
    """

    supplier_id: str
    items_tco: list[TCOItem] = Field(default_factory=list)
    subtotal: float = Field(default=0, ge=0)
    total_surcharges: float = Field(default=0, ge=0)
    total_vat: float = Field(default=0, ge=0)
    total_tco: float | None = Field(default=None, ge=0)
    status: Literal["calculated", "missing_data"]
    missing_fields: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_calculation_status(self) -> TCOResult:
        if self.status == "calculated":
            if self.total_tco is None:
                raise ValueError("calculated TCO requires total_tco")
            if self.missing_fields:
                raise ValueError("calculated TCO cannot contain missing_fields")
        elif self.total_tco is not None:
            raise ValueError("missing-data TCO cannot contain total_tco")
        return self


class ComparisonCell(ContractModel):
    """Ô Dữ liệu trong Ma trận So sánh Đối đầu giữa các Nhà Cung Cấp (Comparison Matrix Cell).

    Chức năng:
    - Đại diện cho một giá trị giao điểm giữa Nhà cung cấp và Tiêu chí đánh giá.
    - Lưu trữ giá trị thực tế của NCC, phần trăm chênh lệch (`deviation_pct`) so với mức trung bình (mean)
      của TẤT CẢ các NCC cùng gửi báo giá trong ca mua sắm này (hoàn toàn KHÔNG dùng giá thị trường bên ngoài).
    - Đánh dấu nổi bật (`highlight = True`) nếu NCC này có tiêu chí chênh lệch vượt ngưỡng (mặc định > 15%)
      so với mặt bằng chung của các NCC khác, giúp Buyer nhận diện ngay NCC vượt trội hoặc bất thường.

    Thuộc tính:
    - `value`: Giá trị của tiêu chí (vd: đơn giá, TCO, lead time, bảo hành của NCC này).
    - `deviation_pct`: Tỷ lệ % chênh lệch so với giá trị trung bình giữa các NCC trong đợt thầu.
    - `highlight`: `True` nếu độ chênh lệch so với các NCC khác vượt ngưỡng cấu hình (deviation_threshold).
    - `note`: Ghi chú bổ sung (vd: "Thiếu dữ liệu", "Không đủ dữ liệu so sánh").
    """

    value: float | str
    deviation_pct: float | None = None
    highlight: bool = False
    note: str | None = None


class ComparisonMatrix(ContractModel):
    """Ma trận So sánh Tổng hợp Đối đầu các Nhà Cung Cấp (Supplier Comparison Matrix).

    Chức năng:
    - Chứa bảng so sánh toàn diện đa chiều giữa các NCC theo nhiều tiêu chí (TCO, đơn giá, thời gian giao hàng, bảo hành...).
    - Do tool `compare_suppliers` tính toán xác định.
    - Được trình bày cho Buyer ở Checkpoint HITL 2 và làm ngữ cảnh cho LLM ra quyết định.

    Thuộc tính:
    - `suppliers`: Danh sách tên các Nhà cung cấp được so sánh.
    - `criteria`: Danh sách các tiêu chí đánh giá (vd: 'tco', 'unit_price', 'lead_time_days', 'warranty_months').
    - `matrix`: Cấu trúc lồng ghép `matrix[supplier_id][criterion] = ComparisonCell`.
    - `means`: Giá trị trung bình của từng tiêu chí tính trên tất cả các NCC.
    - `deviation_threshold`: Ngưỡng sai lệch áp dụng (mặc định 15%).
    """

    suppliers: list[str] = Field(default_factory=list)
    criteria: list[str] = Field(default_factory=list)
    matrix: dict[str, dict[str, ComparisonCell]] = Field(default_factory=dict)
    means: dict[str, float | None] = Field(default_factory=dict)
    deviation_threshold: float = Field(default=0.15, ge=0, le=1)


class RiskFlag(ContractModel):
    """Cảnh báo Rủi ro Nhà Cung Cấp (Structured Risk Warning).

    Chức năng:
    - Lưu trữ các rủi ro phát hiện tự động bởi tool `analyze_risks` (giao hàng trễ sau deadline của PR,
      thiếu thời hạn bảo hành, chi phí ẩn, ngoại tệ không tự động quy đổi được...).

    Thuộc tính:
    - `supplier_id`: Nhà cung cấp liên quan đến rủi ro.
    - `risk_type`: Phân loại rủi ro (vd: 'delivery_delay', 'missing_warranty', 'hidden_surcharge').
    - `severity`: Mức độ nghiêm trọng ('info', 'warning', 'error').
    - `message`: Thông điệp cảnh báo rõ ràng cho Buyer.
    - `detail`: Dữ liệu chi tiết về rủi ro (vd: ngày giao dự kiến vs ngày deadline).
    - `source`: Vị trí tài liệu PDF gốc liên quan đến rủi ro.
    """

    supplier_id: str
    risk_type: str
    severity: Literal["info", "warning", "error"]
    message: str
    detail: dict[str, object] = Field(default_factory=dict)
    source: SourceReference | None = None


class EvidenceItem(ContractModel):
    """Bằng chứng Trích dẫn cho Luận điểm Đề xuất (Evidence Citation).

    Chức năng:
    - Kết nối từng số liệu hoặc luận điểm trong giải trình của LLM (`rationale`) về tài liệu PDF gốc
      (tên file, số trang, vị trí) do Node `generate_evidence` tạo ra.
    - Đảm bảo tính trung thực (factuality), chống ảo giác (hallucination) của AI và giúp Buyer dễ dàng kiểm chứng.

    Thuộc tính:
    - `field`: Trường thông tin được trích dẫn (vd: 'lead_time', 'warranty', 'unit_price', 'tco').
    - `supplier_id`: Nhà cung cấp được trích dẫn.
    - `source`: Tham chiếu đến trang và file PDF gốc chứa thông tin.
    - `edited_by_human`: Đánh dấu `True` nếu giá trị này từng được Buyer sửa thủ công.
    - `low_confidence`: Đánh dấu `True` nếu thông tin nguồn có độ tin cậy thấp hoặc thiếu số trang.
    - `original_value`: Giá trị gốc ban đầu trước khi bị người dùng chỉnh sửa.
    """

    field: str
    supplier_id: str = Field(validation_alias=AliasChoices("supplier_id", "supplier"))
    source: SourceReference | None = None
    edited_by_human: bool = False
    low_confidence: bool = False
    original_value: object = None

    @model_validator(mode="before")
    @classmethod
    def migrate_legacy_source(cls, value: object) -> object:
        """Hỗ trợ tương thích ngược với định dạng source phẳng cũ."""
        if not isinstance(value, dict):
            return value
        data = dict(value)
        source = data.get("source")
        page = data.pop("page", None)
        if isinstance(source, str):
            data["source"] = {"document_path": source, "page_number": page}
        return data


class RankedSupplier(ContractModel):
    """Nhà Cung Cấp Được Xếp Hạng trong Báo Cáo Đề Xuất (Ranked Supplier Output).

    Chức năng:
    - Đại diện cho một Nhà cung cấp được LLM lựa chọn và xếp hạng (Top 1, 2, 3...)
      kèm giải trình lý do (`rationale`) và danh sách bằng chứng đối soát (`evidence`).

    Thuộc tính:
    - `rank`: Thứ hạng (1, 2, 3...).
    - `supplier_id`: Định danh Nhà cung cấp.
    - `rationale`: Lập luận giải trình logic của AI vì sao chọn và xếp hạng NCC này (có số liệu TCO).
    - `evidence`: Danh sách các bằng chứng trích dẫn kèm số trang PDF tương ứng.
    """

    rank: int = Field(ge=1)
    supplier_id: str = Field(validation_alias=AliasChoices("supplier_id", "supplier"))
    rationale: str
    evidence: list[EvidenceItem] = Field(default_factory=list)


class Recommendation(ContractModel):
    """Báo Cáo Đề Xuất Cuối Cùng (Final Recommendation Package).

    Chức năng:
    - Đóng gói toàn bộ kết quả đề xuất gửi tới Buyer tại Checkpoint HITL 2 (`human_review_recommendation`).
    - Lưu lại lịch sử các vòng phản hồi (`feedback_history`) nếu Buyer yêu cầu chỉnh sửa (`revise`).

    Thuộc tính:
    - `ranked`: Danh sách các Nhà cung cấp đã được xếp hạng (Top N).
    - `top_n`: Số lượng NCC tối đa theo cấu hình.
    - `error`: Thông báo lỗi nếu quá trình đề xuất gặp sự cố.
    - `feedback_processed`: Đánh dấu `True` nếu đề xuất này đã tiếp thu phản hồi từ vòng trước.
    - `feedback_history`: Lịch sử các góp ý / chỉ đạo của Buyer qua các vòng lặp.
    """

    ranked: list[RankedSupplier] = Field(default_factory=list)
    top_n: int = Field(default=3, ge=3, le=5)
    error: str | None = None
    feedback_processed: bool = False
    feedback_history: list[str] = Field(default_factory=list)


class AnalysisResponse(ContractModel):
    """Kết quả hoàn tất của API phân tích mua sắm.

    Chức năng:
    - Trả dữ liệu trích xuất, ma trận so sánh và đề xuất sau khi workflow đồng bộ hoàn tất.

    Thuộc tính:
    - `case_id`: Mã định danh ca mua sắm.
    - `status`: Trạng thái hoàn tất.
    - `raw_extractions`: Dữ liệu trích xuất thô.
    - `comparison_matrix`: Ma trận so sánh NCC.
    - `recommendation`: Đề xuất Top N và giải trình.
    """

    case_id: str
    status: Literal["completed"] = "completed"
    raw_extractions: list[RawExtraction]
    comparison_matrix: ComparisonMatrix
    recommendation: Recommendation


class DecisionPipelineResponse(ContractModel):
    """Kết quả hoàn tất của API pipeline tới Decision LLM.

    Thuộc tính:
    - `case_id`: Mã định danh ca mua sắm.
    - `status`: Trạng thái hoàn tất.
    - `raw_extractions`: Dữ liệu trích xuất thô.
    - `normalized_quotes`: Dữ liệu báo giá đã chuẩn hóa.
    - `tco_results`: Kết quả tính toán TCO.
    - `comparison_matrix`: Ma trận so sánh NCC.
    - `risk_flags`: Cảnh báo rủi ro.
    - `decision_proposal`: JSON chưa được kiểm chứng từ Decision LLM; không dùng để phê duyệt.
    """

    case_id: str
    status: Literal["untrusted_proposal", "awaiting_confirmation"] = "untrusted_proposal"
    raw_extractions: list[RawExtraction] = Field(default_factory=list)
    normalized_quotes: list[DataNormalized] = Field(default_factory=list)
    tco_results: list[TCOResult] = Field(default_factory=list)
    comparison_matrix: ComparisonMatrix = Field(default_factory=dict)
    risk_flags: list[RiskFlag] = Field(default_factory=list)
    decision_proposal: dict = Field(default_factory=dict)
