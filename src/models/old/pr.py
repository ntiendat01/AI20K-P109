from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import AliasChoices, Field, field_validator

from src.models.procurement import ContractModel, Quantity


class PRCreateRequest(ContractModel):
    """Yêu cầu Khởi tạo Ca Mua sắm (Create Procurement Case Request).

    Chức năng:
    - Tiếp nhận thông tin bài toán mua sắm do Buyer nhập từ Frontend gửi lên API POST `/api/pr`.
    - Kiểm tra hợp lệ các trường nghiệp vụ (deadline không được ở quá khứ, số lượng > 0, ngân sách >= 0).

    Thuộc tính:
    - `pr_number`: Mã số PR (vd: 'PR-2026-001').
    - `quantity`: Số lượng hàng hóa/dịch vụ cần mua.
    - `deadline`: Ngày hạn chót yêu cầu giao hàng.
    - `budget`: Ngân sách tối đa dự kiến.
    """

    pr_number: str = Field(min_length=1, validation_alias=AliasChoices("pr_number", "pr_code"))
    quantity: Quantity
    deadline: date
    budget: float | None = Field(default=None, ge=0)

    @field_validator("deadline")
    @classmethod
    def deadline_must_not_be_in_the_past(cls, value: date) -> date:
        """Kiểm tra hạn chót giao hàng không được nằm trong quá khứ."""
        if value < date.today():
            raise ValueError("deadline must be today or a future date")
        return value


class PRResponse(ContractModel):
    """Phản hồi sau khi Khởi tạo Ca Mua sắm Thành công (Create PR Response).

    Chức năng:
    - Trả về mã định danh `case_id` và thông tin khởi tạo của ca mua sắm để Buyer tiếp tục tải tệp PDF lên.

    Thuộc tính:
    - `case_id`: UUID duy nhất định danh phiên làm việc của ca mua sắm.
    - `pr_number`: Mã số PR tương ứng.
    - `quantity`: Số lượng yêu cầu.
    - `deadline`: Hạn chót giao hàng.
    - `budget`: Ngân sách dự kiến.
    - `status`: Trạng thái ca mua sắm (mặc định: 'awaiting_documents' - chờ tải tài liệu).
    - `same_day_deadline`: Cờ đánh dấu nếu hạn chót là ngay trong ngày hiện tại.
    - `document_count`: Số lượng tài liệu đã tải lên hiện tại (khởi tạo: 0).
    """

    case_id: str
    pr_number: str
    quantity: Quantity
    deadline: date
    budget: float | None = Field(ge=0)
    status: Literal["awaiting_documents"]
    same_day_deadline: bool
    document_count: int = Field(ge=0)


class DocumentUploadResponse(ContractModel):
    """Phản hồi khi Tải lên Thành công một Tệp Báo giá PDF (Document Upload Response).

    Chức năng:
    - Trả về thông tin tệp PDF vừa được lưu trữ kèm tổng số lượng tài liệu hiện có trong ca mua sắm.

    Thuộc tính:
    - `case_id`: Mã định danh ca mua sắm.
    - `status`: Trạng thái ('uploaded').
    - `filename`: Tên tệp PDF vừa tải lên.
    - `size_bytes`: Kích thước tệp (bytes).
    - `document_count`: Tổng số tệp tài liệu hiện có của ca mua sắm.
    """

    case_id: str
    status: Literal["uploaded"]
    filename: str = Field(min_length=1)
    size_bytes: int = Field(ge=0)
    document_count: int = Field(ge=1)
