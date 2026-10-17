#!/usr/bin/env python3
"""Generate sample CSVs and matching supplier quotation PDFs for manual demo.

Creates realistic, matching data:
1. CSV template: danh_sach_vat_lieu_xay_dung.csv (3 items)
2. PDF quotation 1: bao_gia_vlxd_mien_nam.pdf (NCC Miền Nam)
3. PDF quotation 2: bao_gia_vlxd_sai_gon.pdf (NCC Sài Gòn)
4. CSV template 2: danh_sach_bao_bi_dong_goi.csv (2 items)
5. PDF quotation 3: bao_gia_bao_bi_minh_khang.pdf
6. PDF quotation 4: bao_gia_nhua_hoang_gia.pdf

Output directory: ./samples/
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import HRFlowable, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

ROOT_DIR = Path(__file__).resolve().parents[1]
OUTPUT_DIR = ROOT_DIR / "samples"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# Register Arial Unicode fonts from Windows
pdfmetrics.registerFont(TTFont("Arial", "C:/Windows/Fonts/arial.ttf"))
pdfmetrics.registerFont(TTFont("Arial-Bold", "C:/Windows/Fonts/arialbd.ttf"))
pdfmetrics.registerFont(TTFont("Arial-Italic", "C:/Windows/Fonts/ariali.ttf"))


def build_pdf_quotation(
    target_path: Path,
    supplier_name: str,
    quote_code: str,
    date_str: str,
    delivery_time: str,
    payment_terms: str,
    warranty: str,
    items: list[dict],
    vat_rate: float = 0.08,
    shipping_note: str = "Miễn phí vận chuyển đến địa chỉ bên mua chỉ định",
):
    doc = SimpleDocTemplate(
        str(target_path),
        pagesize=A4,
        leftMargin=36,
        rightMargin=36,
        topMargin=36,
        bottomMargin=36,
    )

    styles = getSampleStyleSheet()

    title_style = ParagraphStyle(
        "TitleStyle",
        fontName="Arial-Bold",
        fontSize=15,
        leading=18,
        alignment=1,
        textColor=colors.HexColor("#0f2942"),
    )
    company_style = ParagraphStyle(
        "CompanyStyle",
        fontName="Arial-Bold",
        fontSize=11,
        leading=15,
        textColor=colors.HexColor("#1e3a8a"),
    )
    meta_label_style = ParagraphStyle(
        "MetaLabel",
        fontName="Arial-Bold",
        fontSize=9,
        leading=13,
        textColor=colors.HexColor("#334155"),
    )
    meta_val_style = ParagraphStyle(
        "MetaVal",
        fontName="Arial",
        fontSize=9,
        leading=13,
        textColor=colors.HexColor("#1e293b"),
    )
    table_head_style = ParagraphStyle(
        "TableHead",
        fontName="Arial-Bold",
        fontSize=9,
        leading=12,
        alignment=1,
        textColor=colors.HexColor("#0f172a"),
    )
    table_cell_style = ParagraphStyle(
        "TableCell",
        fontName="Arial",
        fontSize=8.5,
        leading=12,
        textColor=colors.HexColor("#1e293b"),
    )
    table_cell_bold = ParagraphStyle(
        "TableCellBold",
        fontName="Arial-Bold",
        fontSize=8.5,
        leading=12,
        textColor=colors.HexColor("#1e293b"),
    )

    elements = []

    # Header section
    elements.append(Paragraph(supplier_name.upper(), company_style))
    elements.append(Paragraph("Địa chỉ: KCN Tân Bình, P. Tây Thạnh, Q. Tân Phú, TP. Hồ Chí Minh", meta_val_style))
    elements.append(Paragraph("Hotline: (028) 3812 6868 | Email: kinhdoanh@vlxd.vn", meta_val_style))
    elements.append(Spacer(1, 8))
    elements.append(HRFlowable(width="100%", thickness=1.5, color=colors.HexColor("#1e3a8a"), spaceAfter=12))

    elements.append(Paragraph("BẢNG BÁO GIÁ VÀ ĐIỀU KIỆN THƯƠNG MẠI", title_style))
    elements.append(Spacer(1, 4))
    elements.append(Paragraph(f"Số: {quote_code} | Ngày lập: {date_str}", ParagraphStyle("Sub", fontName="Arial-Italic", fontSize=9, alignment=1, textColor=colors.HexColor("#64748b"))))
    elements.append(Spacer(1, 12))

    # Commercial terms summary (single item per line to ensure clean OCR/text extraction)
    meta_terms = [
        ("Nhà cung cấp", supplier_name),
        ("Thời gian giao hàng", delivery_time),
        ("Điều khoản thanh toán", payment_terms),
        ("Bảo hành", warranty),
        ("Đơn vị tiền tệ", "VNĐ"),
    ]
    meta_data = [
        [
            Paragraph(f"<b>{k}:</b>", meta_label_style),
            Paragraph(v, meta_val_style),
        ]
        for k, v in meta_terms
    ]
    meta_table = Table(meta_data, colWidths=[140, 385])
    meta_table.setStyle(
        TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("TOPPADDING", (0, 0), (-1, -1), 2),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
            ("LEFTPADDING", (0, 0), (-1, -1), 0),
            ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ])
    )
    elements.append(meta_table)
    elements.append(Spacer(1, 12))

    # Items table
    table_data = [
        [
            Paragraph("STT", table_head_style),
            Paragraph("Tên hàng hóa / Quy cách", table_head_style),
            Paragraph("ĐVT", table_head_style),
            Paragraph("Số lượng", table_head_style),
            Paragraph("Đơn giá (VNĐ)", table_head_style),
            Paragraph("Thành tiền (VNĐ)", table_head_style),
        ]
    ]

    subtotal = 0
    for idx, item in enumerate(items, start=1):
        qty = item["quantity"]
        price = item["unit_price"]
        line_total = qty * price
        subtotal += line_total

        table_data.append([
            Paragraph(str(idx), table_cell_style),
            Paragraph(item["product_name"], table_cell_bold),
            Paragraph(item["unit"], table_cell_style),
            Paragraph(f"{qty:,}", table_cell_style),
            Paragraph(f"{price:,}", table_cell_style),
            Paragraph(f"{line_total:,}", table_cell_bold),
        ])

    tax_amount = int(subtotal * vat_rate)
    grand_total = subtotal + tax_amount

    # Summary rows
    table_data.append([
        "", "", "", "",
        Paragraph("Cộng tiền hàng:", meta_label_style),
        Paragraph(f"{subtotal:,}", table_cell_bold),
    ])
    table_data.append([
        "", "", "", "",
        Paragraph(f"Thuế VAT ({int(vat_rate * 100)}%):", meta_label_style),
        Paragraph(f"{tax_amount:,}", table_cell_style),
    ])
    table_data.append([
        "", "", "", "",
        Paragraph("Tổng cộng thanh toán:", meta_label_style),
        Paragraph(f"{grand_total:,}", table_cell_bold),
    ])

    col_widths = [30, 230, 45, 55, 80, 85]
    items_table = Table(table_data, colWidths=col_widths, repeatRows=1)
    items_table.setStyle(
        TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#f1f5f9")),
            ("ALIGN", (0, 0), (0, -1), "CENTER"),
            ("ALIGN", (2, 0), (3, -1), "CENTER"),
            ("ALIGN", (4, 0), (-1, -1), "RIGHT"),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("GRID", (0, 0), (-1, len(items)), 0.5, colors.HexColor("#cbd5e1")),
            ("LINEBELOW", (0, len(items)), (-1, -1), 0.5, colors.HexColor("#94a3b8")),
            ("TOPPADDING", (0, 0), (-1, -1), 5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ])
    )
    elements.append(items_table)
    elements.append(Spacer(1, 14))

    # Notes & Signatures
    elements.append(Paragraph(f"Ghi chú vận chuyển: {shipping_note}.", meta_val_style))
    elements.append(Paragraph("Báo giá trên đã bao gồm toàn bộ chi phí bốc xếp và vận chuyển đến công trình.", meta_val_style))
    elements.append(Spacer(1, 18))

    sig_data = [
        [
            Paragraph("ĐẠI DIỆN BÊN MUA<br/><font size=8 color='#64748b'><i>(Ký và ghi rõ họ tên)</i></font>", ParagraphStyle("S1", fontName="Arial-Bold", fontSize=9, alignment=1)),
            Paragraph(f"ĐẠI DIỆN {supplier_name.upper()}<br/><font size=8 color='#64748b'><i>(Giám đốc kinh doanh ký duyệt)</i></font>", ParagraphStyle("S2", fontName="Arial-Bold", fontSize=9, alignment=1)),
        ]
    ]
    sig_table = Table(sig_data, colWidths=[260, 265])
    sig_table.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("ALIGN", (0, 0), (-1, -1), "CENTER")]))
    elements.append(sig_table)

    doc.build(elements)


def main():
    print(f"Generating demo CSV templates and matching quotation PDFs to: {OUTPUT_DIR}...")

    # =========================================================================
    # SET 1: VẬT LIỆU XÂY DỰNG (Khớp 100% với template CSV có sẵn trên frontend)
    # =========================================================================
    csv_vlxd = (
        "Tên sản phẩm,Số lượng,Đơn vị,Ghi chú\r\n"
        "Xi măng PCB40 Hà Tiên,50,Bao,Đóng bao 50 kg tiêu chuẩn\r\n"
        "Thép xây dựng CB400 D10,500,kg,Thép cuộn mác CB400 có chứng chỉ\r\n"
        "Cát xây tô,2,m3,Cát vàng sạch không lẫn tạp chất\r\n"
    )
    csv_vlxd_path = OUTPUT_DIR / "danh_sach_vat_lieu_xay_dung.csv"
    csv_vlxd_path.write_text("\ufeff" + csv_vlxd, encoding="utf-8")
    print(f"Created CSV: {csv_vlxd_path.name}")

    # PDF 1: NCC Miền Nam (Giá tốt hơn ở Thép & Giao nhanh 2 ngày)
    items_mn = [
        {"product_name": "Xi măng PCB40 Hà Tiên (bao 50kg)", "unit": "Bao", "quantity": 50, "unit_price": 88000},
        {"product_name": "Thép cuộn xây dựng CB400 phi 10", "unit": "kg", "quantity": 500, "unit_price": 15500},
        {"product_name": "Cát vàng xây tô sạch", "unit": "m3", "quantity": 2, "unit_price": 350000},
    ]
    pdf_mn_path = OUTPUT_DIR / "bao_gia_vlxd_mien_nam.pdf"
    build_pdf_quotation(
        target_path=pdf_mn_path,
        supplier_name="Công Ty TNHH Vật Liệu Xây Dựng Miền Nam",
        quote_code="BG-2026-VLXD-MN01",
        date_str="14/10/2026",
        delivery_time="2 ngày làm việc sau xác nhận đơn hàng",
        payment_terms="Thanh toán trong 30 ngày sau khi nghiệm thu",
        warranty="12 tháng",
        items=items_mn,
        vat_rate=0.08,
        shipping_note="Miễn phí vận chuyển tận chân công trình",
    )
    print(f"Created PDF: {pdf_mn_path.name}")

    # PDF 2: NCC Sài Gòn (Giá tốt hơn ở Xi măng & Cát, bảo hành 18 tháng, giao 4 ngày)
    items_sg = [
        {"product_name": "Xi măng bao PCB40 hiệu Hà Tiên", "unit": "Bao", "quantity": 50, "unit_price": 85000},
        {"product_name": "Thép xây dựng D10 mác CB400", "unit": "kg", "quantity": 500, "unit_price": 16000},
        {"product_name": "Cát xây tô hạt trung", "unit": "m3", "quantity": 2, "unit_price": 320000},
    ]
    pdf_sg_path = OUTPUT_DIR / "bao_gia_vlxd_sai_gon.pdf"
    build_pdf_quotation(
        target_path=pdf_sg_path,
        supplier_name="Công Ty CP Phân Phối VLXD Sài Gòn",
        quote_code="BG-2026-VLXD-SG88",
        date_str="14/10/2026",
        delivery_time="4 ngày làm việc sau xác nhận đơn hàng",
        payment_terms="Thanh toán 100% trong vòng 15 ngày",
        warranty="18 tháng",
        items=items_sg,
        vat_rate=0.08,
        shipping_note="Giao hàng xe ben chuyên dụng miễn phí",
    )
    print(f"Created PDF: {pdf_sg_path.name}")

    # =========================================================================
    # SET 2: BAO BÌ ĐÓNG GÓI (2 sản phẩm gọn nhẹ)
    # =========================================================================
    csv_baobi = (
        "Tên sản phẩm,Số lượng,Đơn vị,Ghi chú\r\n"
        "Xốp khí bọc hàng khổ 0.5m x 1m,2000,Mét,Đường kính bóng khí 10mm\r\n"
        "Màng cuốn pallet PE co giãn,50,Cuộn,Khổ rộng 50cm độ dày 17 micron\r\n"
    )
    csv_baobi_path = OUTPUT_DIR / "danh_sach_bao_bi_dong_goi.csv"
    csv_baobi_path.write_text("\ufeff" + csv_baobi, encoding="utf-8")
    print(f"Created CSV: {csv_baobi_path.name}")

    # PDF 3: Bao Bì Minh Khang
    items_mk = [
        {"product_name": "Xốp khí bọc hàng (Màng bóng khí chống sốc 10mm)", "unit": "Mét", "quantity": 2000, "unit_price": 2550},
        {"product_name": "Màng cuốn PE bọc pallet 17mic khổ 50cm", "unit": "Cuộn", "quantity": 50, "unit_price": 125000},
    ]
    pdf_mk_path = OUTPUT_DIR / "bao_gia_bao_bi_minh_khang.pdf"
    build_pdf_quotation(
        target_path=pdf_mk_path,
        supplier_name="Công Ty TNHH Sản Xuất Bao Bì Minh Khang",
        quote_code="MK-2026-10-BB",
        date_str="14/10/2026",
        delivery_time="3 ngày làm việc kể từ thời điểm ký hợp đồng",
        payment_terms="Thanh toán trong 15 ngày sau khi nhận hàng",
        warranty="12 tháng",
        items=items_mk,
        vat_rate=0.08,
        shipping_note="Miễn phí giao hàng tại Hà Nội và TP.HCM",
    )
    print(f"Created PDF: {pdf_mk_path.name}")

    # PDF 4: Nhựa Hoàng Gia
    items_hg = [
        {"product_name": "Xốp khí bọc hàng LDPE 100% hạt nhựa tinh khiết", "unit": "Mét", "quantity": 2000, "unit_price": 2500},
        {"product_name": "Màng PE quấn hàng pallet xuất khẩu 17mic", "unit": "Cuộn", "quantity": 50, "unit_price": 128000},
    ]
    pdf_hg_path = OUTPUT_DIR / "bao_gia_nhua_hoang_gia.pdf"
    build_pdf_quotation(
        target_path=pdf_hg_path,
        supplier_name="Công Ty CP Sản Xuất Nhựa & Bao Bì Hoàng Gia",
        quote_code="HG-2026-PO-77",
        date_str="14/10/2026",
        delivery_time="4 ngày làm việc sau khi chốt mẫu",
        payment_terms="Thanh toán 30 ngày sau khi nghiệm thu chứng từ",
        warranty="18 tháng",
        items=items_hg,
        vat_rate=0.08,
        shipping_note="Giao hàng tận kho bên mua miễn phí",
    )
    print(f"Created PDF: {pdf_hg_path.name}")

    print("\nSUCCESS: All sample CSVs and matching PDF quotations have been generated!")


if __name__ == "__main__":
    main()
