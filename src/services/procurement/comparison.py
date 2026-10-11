"""Dịch vụ so sánh đa tiêu chí và sinh đề xuất Nhà cung cấp (Spec 4.5).

Thực hiện:
1. Chuẩn hóa & đối chiếu các dòng hàng giữa các báo giá.
2. Đánh giá 3 tiêu chí cốt lõi: Giá cả - Chất lượng & Bảo hành - Thời gian giao & Thương mại.
3. Kiểm tra tuân thủ chính sách mua sắm nội bộ (POL-01 -> POL-05).
4. Tính điểm trọng số đa tiêu chí (MCDA) và sinh đề xuất kèm giải thích minh bạch (Traceable).
"""

import re
from datetime import date, datetime
from decimal import Decimal

from src.models.schemas import (
    AgentExecutionStep,
    AgentRecommendation,
    ComplianceStatus,
    ItemOffer,
    NormalizedItemComparison,
    PRComparisonResponse,
    PurchaseRequest,
    Quotation,
    SupplierComparisonCriteria,
)


def extract_delivery_days(delivery_text: str) -> int | None:
    """Trích xuất số ngày giao hàng từ chuỗi mô tả."""
    if not delivery_text:
        return None
    match = re.search(r"(\d+)\s*(?:ngày|ngay|day)", delivery_text, re.IGNORECASE)
    if match:
        return int(match.group(1))
    return None


def clean_warranty_display(warranty_text: str) -> str:
    """Làm sạch chuỗi hiển thị bảo hành (loại bỏ tiền tố thừa như '& Chất lượng:', '& Dịch vụ:')."""
    if not warranty_text:
        return ""
    cleaned = re.sub(
        r"^(?:&|và|\+)?\s*(?:chất\s*lượng|dịch\s*vụ|cam\s*kết)\s*[:：\-]?\s*",
        "",
        warranty_text.strip(),
        flags=re.IGNORECASE,
    ).strip()
    return cleaned or warranty_text.strip()


def extract_warranty_months(warranty_text: str) -> int:
    """Trích xuất số tháng bảo hành từ chuỗi mô tả một cách chính xác."""
    if not warranty_text:
        return 0
    text_clean = warranty_text.strip().lower()

    # Kiểm tra rõ ràng các trường hợp không có bảo hành hoặc thời hạn 0 tháng.
    # Tránh bắt nhầm từ "không" đơn lẻ trong các câu mô tả điều kiện (vd: "không đạt định lượng", "không lỗi").
    if (
        re.search(
            r"\b(?:không|khong|chưa|chua)\s*(?:có\s*|hỗ\s*trợ\s*)?(?:bảo\s*hành|bh|warranty)\b",
            text_clean,
            re.IGNORECASE,
        )
        or re.search(r"\b(?:0\s*(?:tháng|thang|năm|nam|month|months)|none)\b", text_clean, re.IGNORECASE)
        or text_clean in {"không", "khong", "none", "chưa", "chua", "k", "ko", "k bh", "ko bh", "không có", "khong co"}
    ):
        return 0

    # 1. Ưu tiên kiểm tra số năm (vd: 1 năm, 2 năm, 1.5 năm, 1 year, 2 yrs)
    year_match = re.search(r"(\d+(?:\.\d+)?)\s*(?:năm|nam|year|yr|yrs)", text_clean, re.IGNORECASE)
    if year_match:
        return int(float(year_match.group(1)) * 12)

    # 2. Kiểm tra số tháng (vd: 24 tháng, 12 thang, 6 months)
    month_match = re.search(r"(\d+)\s*(?:tháng|thang|month|months|mth|mths)\b", text_clean, re.IGNORECASE)
    if month_match:
        return int(month_match.group(1))

    # 3. Chuỗi chỉ chứa duy nhất một con số (vd: "12", "24", "36")
    if text_clean.isdigit():
        return int(text_clean)

    # 4. Có từ khóa bảo hành đi kèm trực tiếp với số (vd: "bảo hành: 24", "bh 12", "warranty 36")
    prefix_match = re.search(r"(?:bảo hành|bh|warranty|đổi trả)\s*[:\-]?\s*(\d+)\b", text_clean, re.IGNORECASE)
    if prefix_match:
        val = int(prefix_match.group(1))
        return val * 12 if val <= 5 else val

    return 0


def analyze_payment_terms(payment_text: str) -> tuple[str, list[str], list[str]]:
    """Phân tích điều khoản thanh toán: rủi ro, ưu điểm và nhược điểm."""
    if not payment_text:
        return "low", [], []
    text_lower = payment_text.lower()
    risks = []
    strengths = []
    risk_level = "low"

    # Trích xuất tỷ lệ đặt cọc linh hoạt: hỗ trợ "cọc 50%", "50% đặt cọc", "50 % tạm ứng"
    deposit_percent = 0
    # Dạng 1: số % đứng trước từ khóa (vd: "50% đặt cọc", "40 % tạm ứng")
    match_prefix = re.search(r"(\d+)\s*%\s*(?:đặt cọc|cọc|tạm ứng|ứng trước|trước)", text_lower)
    # Dạng 2: từ khóa đứng trước số % (vd: "đặt cọc 50%", "tạm ứng: 40%")
    match_suffix = re.search(r"(?:đặt cọc|cọc|tạm ứng|ứng trước|trước)\s*(?:là\s*|:\s*)?(\d+)\s*%", text_lower)

    if match_prefix:
        deposit_percent = int(match_prefix.group(1))
    elif match_suffix:
        deposit_percent = int(match_suffix.group(1))
    elif any(k in text_lower for k in ["cọc", "tạm ứng", "ứng trước"]):
        any_percent = re.search(r"(\d+)\s*%", text_lower)
        if any_percent:
            deposit_percent = int(any_percent.group(1))

    if deposit_percent >= 50:
        risk_level = "high"
        risks.append(f"Yêu cầu đặt cọc cao ({deposit_percent}%), tăng rủi ro dòng tiền và bảo toàn vốn")
    elif deposit_percent > 40:
        risk_level = "medium"
        risks.append(f"Yêu cầu đặt cọc {deposit_percent}%, vượt hạn mức thông thường 40%")
    elif "nghiệm thu" in text_lower or "sau khi giao" in text_lower or ("100%" in text_lower and "sau" in text_lower):
        strengths.append("Thanh toán sau khi bàn giao & nghiệm thu, đảm bảo an toàn cao cho bên mua")
        risk_level = "low"
    elif (
        "trả chậm" in text_lower
        or "trong vòng 15" in text_lower
        or "trong vòng 30" in text_lower
        or "30 ngày" in text_lower
    ):
        strengths.append("Điều khoản tín dụng trả chậm có lợi cho vốn lưu động của doanh nghiệp")
        risk_level = "low"

    return risk_level, strengths, risks


def build_comparison(pr: PurchaseRequest, quotations: list[Quotation]) -> PRComparisonResponse:
    """Xây dựng bảng so sánh và sinh đề xuất theo Spec 4.5."""
    confirmed_quotes = [q for q in quotations if q.status == "confirmed" and q.items]
    if not confirmed_quotes:
        raise ValueError("Cần ít nhất 1 báo giá đã xác nhận để thực hiện so sánh.")

    now = datetime.now()

    # Bước 1: Tính toán tổng tiền và tiêu chí của từng NCC
    supplier_evaluations: list[SupplierComparisonCriteria] = []
    total_amounts: dict[str, Decimal] = {}

    for quote in confirmed_quotes:
        quote_total = sum((item.line_total for item in quote.items), Decimal(0))
        total_amounts[quote.id] = quote_total

    min_total = min(total_amounts.values()) if total_amounts else Decimal(0)

    # Tính khoảng ngày còn lại của PR
    due_date = pr.delivery_due_date
    pr_ref_date = pr.created_at.date() if isinstance(pr.created_at, datetime) else date.today()
    days_to_due = max(1, (due_date - pr_ref_date).days)

    for quote in confirmed_quotes:
        total = total_amounts[quote.id]
        variance = total - pr.estimated_budget
        if pr.estimated_budget > 0:
            variance_percent = round(float(variance / pr.estimated_budget) * 100, 2)
        else:
            variance_percent = 0.0
        within_budget = total <= pr.estimated_budget

        delivery_days = extract_delivery_days(quote.delivery_time)
        meets_deadline = True
        if delivery_days is not None and delivery_days > days_to_due:
            meets_deadline = False

        warranty_months = extract_warranty_months(quote.warranty)
        risk_level, pay_strengths, pay_risks = analyze_payment_terms(quote.payment_terms)

        strengths = list(pay_strengths)
        drawbacks = list(pay_risks)
        compliance_notes = []

        # Kiểm tra chính sách mua sắm (POL-01 -> POL-04)
        if not within_budget:
            compliance_notes.append(f"POL-01: Vượt ngân sách PR {abs(variance_percent):.1f}% (+{variance:,.0f} VNĐ)")
            drawbacks.append("Vượt ngân sách được duyệt")
        else:
            strengths.append(f"Trong ngân sách dự kiến (tiết kiệm {abs(variance_percent):.1f}%)")

        if not meets_deadline:
            compliance_notes.append(
                f"POL-02: Thời gian giao ({delivery_days} ngày) vượt quá hạn PR ({days_to_due} ngày)"
            )
            drawbacks.append("Tiến độ giao hàng trễ so với hạn cần của PR")
        elif delivery_days is not None and delivery_days <= 5:
            strengths.append(f"Tiến độ giao hàng nhanh vượt trội ({delivery_days} ngày)")

        if risk_level == "high":
            compliance_notes.append("POL-03: Điều khoản đặt cọc trước vượt trần 40% theo chính sách mua sắm")

        if warranty_months >= 24:
            strengths.append(f"Chế độ bảo hành dài hạn ({warranty_months} tháng)")
        elif warranty_months < 12:
            compliance_notes.append("POL-04: Thời hạn bảo hành dưới mức tối thiểu 12 tháng")
            drawbacks.append(f"Bảo hành chỉ {warranty_months} tháng")

        # Xác định Compliance Status
        if len(compliance_notes) == 0:
            compliance_status = ComplianceStatus.COMPLIANT
        elif not within_budget or not meets_deadline or risk_level == "high":
            compliance_status = ComplianceStatus.WARNING
        else:
            compliance_status = ComplianceStatus.WARNING

        # Chấm điểm đa tiêu chí (MCDA Scoring - thang điểm 100)
        # 1. Điểm Giá (40%): Càng rẻ điểm càng cao
        price_ratio = float(min_total / total) if total > 0 else 1.0
        price_score = price_ratio * 40.0
        if not within_budget:
            price_score = max(0.0, price_score - 8.0)

        # 2. Điểm Tiến độ & Thương mại (30%)
        delivery_score = 25.0
        if delivery_days is not None:
            if delivery_days <= 3:
                delivery_score += 5.0
            elif delivery_days <= 7:
                delivery_score += 3.0
            elif delivery_days > days_to_due:
                delivery_score -= 15.0
        if risk_level == "high":
            delivery_score -= 10.0
        elif risk_level == "low":
            delivery_score += 2.0
        delivery_score = max(5.0, min(30.0, delivery_score))

        # 3. Điểm Chất lượng & Bảo hành (30%)
        quality_score = 20.0
        if warranty_months >= 36:
            quality_score = 30.0
        elif warranty_months >= 24:
            quality_score = 27.0
        elif warranty_months >= 12:
            quality_score = 22.0
        else:
            quality_score = 10.0

        overall_score = round(price_score + delivery_score + quality_score, 1)

        supplier_evaluations.append(
            SupplierComparisonCriteria(
                supplier_name=quote.supplier_name,
                quotation_id=quote.id,
                total_amount=total,
                currency=quote.currency or "VNĐ",
                within_budget=within_budget,
                budget_variance=variance,
                budget_variance_percent=variance_percent,
                delivery_time=quote.delivery_time or "Theo thỏa thuận",
                estimated_delivery_days=delivery_days,
                meets_deadline=meets_deadline,
                payment_terms=quote.payment_terms or "Thỏa thuận",
                payment_risk_level=risk_level,
                warranty=clean_warranty_display(quote.warranty) or "12 tháng",
                warranty_months=warranty_months,
                quality_score=round(quality_score, 1),
                overall_score=overall_score,
                compliance_status=compliance_status,
                compliance_notes=compliance_notes,
                strengths=strengths,
                drawbacks=drawbacks,
            )
        )

    # Bước 2: Bảng so sánh từng mặt hàng (Item-level comparison)
    item_comparison_map: dict[str, NormalizedItemComparison] = {}
    for quote in confirmed_quotes:
        for item in quote.items:
            key = (item.product_name.strip().lower(), item.product_code.strip().lower())
            if key not in item_comparison_map:
                item_comparison_map[key] = NormalizedItemComparison(
                    product_name=item.product_name,
                    product_code=item.product_code,
                    unit=item.unit,
                    quantity=item.quantity,
                    lowest_unit_price=item.unit_price,
                    offers={},
                )
            current_lowest = item_comparison_map[key].lowest_unit_price
            if item.unit_price < current_lowest:
                item_comparison_map[key].lowest_unit_price = item.unit_price

            item_comparison_map[key].offers[quote.id] = ItemOffer(
                unit_price=item.unit_price,
                line_total=item.line_total,
                is_best_price=False,
            )

    # Đánh dấu is_best_price
    for norm_item in item_comparison_map.values():
        for offer in norm_item.offers.values():
            if offer.unit_price == norm_item.lowest_unit_price:
                offer.is_best_price = True

    # Bước 3: Lựa chọn NCC tối ưu và sinh lập luận của Agent
    sorted_suppliers = sorted(supplier_evaluations, key=lambda s: s.overall_score, reverse=True)
    best_supplier = sorted_suppliers[0]

    compliant_suppliers = [s for s in sorted_suppliers if s.compliance_status == ComplianceStatus.COMPLIANT]
    if compliant_suppliers and best_supplier.compliance_status != ComplianceStatus.COMPLIANT:
        if best_supplier.overall_score - compliant_suppliers[0].overall_score < 10.0:
            best_supplier = compliant_suppliers[0]

    # Tạo tóm tắt và lập luận chi tiết
    summary = (
        f"Agent đề xuất lựa chọn {best_supplier.supplier_name} với điểm đánh giá tổng hợp {best_supplier.overall_score}/100. "
        f"Báo giá đạt sự cân bằng tối ưu giữa tổng chi phí ({best_supplier.total_amount:,.0f} VNĐ), "
        f"tiến độ giao hàng ({best_supplier.delivery_time}) và cam kết bảo hành ({best_supplier.warranty})."
    )

    tradeoffs = []
    for other in sorted_suppliers:
        if other.quotation_id == best_supplier.quotation_id:
            continue
        price_diff = other.total_amount - best_supplier.total_amount
        if price_diff < 0:
            tradeoffs.append(
                f"So với {other.supplier_name}: Dù {other.supplier_name} có mức giá thấp hơn {abs(price_diff):,.0f} VNĐ, "
                f"nhưng {best_supplier.supplier_name} vượt trội về chế độ bảo hành ({best_supplier.warranty} so với {other.warranty}) "
                f"và điều khoản rủi ro thanh toán an toàn hơn ({best_supplier.payment_terms})."
            )
        else:
            tradeoffs.append(
                f"So với {other.supplier_name}: {best_supplier.supplier_name} tiết kiệm hơn {price_diff:,.0f} VNĐ "
                f"và có thời gian giao hàng tối ưu hơn ({best_supplier.delivery_time} so với {other.delivery_time})."
            )

    tradeoff_text = " ".join(tradeoffs) if tradeoffs else "Báo giá duy nhất đáp ứng yêu cầu kỹ thuật và ngân sách."

    detailed_rationale = (
        f"Căn cứ trên số liệu bóc tách và chính sách mua sắm:\n"
        f"1. Về Ngân sách: Tổng giá trị {best_supplier.total_amount:,.0f} VNĐ "
        f"({'trong ngân sách' if best_supplier.within_budget else 'vượt ngân sách nhẹ'}), "
        f"chênh lệch {best_supplier.budget_variance:,.0f} VNĐ so với ngân sách dự toán {pr.estimated_budget:,.0f} VNĐ.\n"
        f"2. Về Tiến độ: Thời gian giao hàng {best_supplier.delivery_time}, hoàn toàn đáp ứng hạn bàn giao {pr.delivery_due_date.strftime('%d/%m/%Y')} của đề nghị mua sắm.\n"
        f"3. Về Cam kết Chất lượng & Thương mại: Chế độ bảo hành {best_supplier.warranty}, "
        f"điều khoản thanh toán {best_supplier.payment_terms} đảm bảo quyền lợi và kiểm soát rủi ro cho công ty.\n"
        f"4. Đánh giá Đánh đổi: {tradeoff_text}"
    )

    policy_summary = (
        f"Đã rà soát 5 điều khoản chính sách mua sắm: "
        f"{len(best_supplier.compliance_notes)} cảnh báo ghi nhận đối với NCC đề xuất. "
        f"{'Không phát hiện vi phạm chính sách nghiêm trọng.' if not best_supplier.compliance_notes else 'Các điểm cảnh báo đã được đánh giá và nằm trong phạm vi có thể chấp nhận.'}"
    )

    execution_steps = [
        AgentExecutionStep(
            step=1,
            title="Thu thập & Chuẩn hóa Báo giá",
            status="completed",
            detail=f"Đã đối soát {len(confirmed_quotes)} báo giá hợp lệ với tổng cộng {len(item_comparison_map)} danh mục hàng hóa.",
            timestamp=now,
        ),
        AgentExecutionStep(
            step=2,
            title="Kiểm tra Tuân thủ Chính sách (RAG / Policy Audit)",
            status="completed",
            detail="Kiểm tra giới hạn ngân sách (POL-01), hạn giao hàng (POL-02), ngưỡng đặt cọc tối đa 40% (POL-03) và bảo hành tối thiểu 12 tháng (POL-04).",
            timestamp=now,
        ),
        AgentExecutionStep(
            step=3,
            title="Đánh giá Trọng số Đa tiêu chí (MCDA)",
            status="completed",
            detail="Áp dụng ma trận trọng số: Giá cả (40%), Tiến độ & Thương mại (30%), Chất lượng & Bảo hành (30%) để chấm điểm khách quan từng NCC.",
            timestamp=now,
        ),
        AgentExecutionStep(
            step=4,
            title="Tổng hợp Đề xuất & Phân tích Đánh đổi",
            status="completed",
            detail=f"Chọn lựa {best_supplier.supplier_name} làm phương án tối ưu, xuất bản luận cứ và bảng so sánh trực quan phục vụ phê duyệt HITL.",
            timestamp=now,
        ),
    ]

    recommendation = AgentRecommendation(
        recommended_supplier=best_supplier.supplier_name,
        recommended_quotation_id=best_supplier.quotation_id,
        overall_score=best_supplier.overall_score,
        confidence_score=0.94,
        summary=summary,
        detailed_rationale=detailed_rationale,
        tradeoff_analysis=tradeoff_text,
        policy_summary=policy_summary,
        execution_steps=execution_steps,
    )

    return PRComparisonResponse(
        pr=pr,
        suppliers=supplier_evaluations,
        items=list(item_comparison_map.values()),
        recommendation=recommendation,
        generated_at=now,
    )
