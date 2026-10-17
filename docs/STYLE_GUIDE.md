# DotCom style guide

Đây là chuẩn bắt buộc cho mọi màn hình vận hành trong `frontend/`. Mục tiêu là
ngăn typography bị phân mảnh giữa các component và các lần triển khai.

## Font

Dùng duy nhất Manrope qua `--font-sans`. Không dùng serif, monospace hoặc font
trang trí trong giao diện tác nghiệp. Chỉ tải các weight 400, 600 và 700.

## Typography tokens

| Token | Cỡ / line-height | Weight | Dùng cho |
| --- | --- | --- | --- |
| `text-display` | 36px / 44px | 700 | Tiêu đề đặc biệt |
| `text-h1` | 32px / 40px | 700 | Một tiêu đề trang |
| `text-h2` | 24px / 32px | 700 | Khu vực lớn |
| `text-h3` | 20px / 28px | 600 | Nhóm nội dung |
| `text-h4` | 18px / 26px | 600 | Phần nhỏ |
| `text-title` | 16px / 24px | 600 | Card, bảng, form |
| `text-body-lg` | 16px / 24px | 400 | Mô tả quan trọng |
| `text-body` | 14px / 20px | 400 | Nội dung mặc định |
| `text-body-strong` | 14px / 20px | 600 | Giá trị và thao tác |
| `text-small` | 13px / 18px | 400 | Metadata, lỗi, thời gian |
| `text-label` | 12px / 16px | 600 | Field, chip, cột |
| `text-caption` | 12px / 16px | 400 | Chú thích biểu đồ |
| `text-overline` | 11px / 16px | 600 | Nhãn nhóm viết hoa |
| `text-kpi` | 28px / 34px | 700 | Số liệu tổng quan |
| `text-metric` | 20px / 28px | 700 | Số liệu phụ |

Các class tiện ích cùng tên (`.text-h1`, `.text-body`, v.v.) và CSS custom
properties đã nằm trong `frontend/styles.css`. Không thêm cỡ 15px, 17px, 19px,
21px, 22px hoặc 23px. Không dùng chữ nhỏ hơn 12px.

## Nút và thao tác

- Dùng biến thể dùng chung trong `frontend/styles.css`: `.inline-primary` cho
  thao tác chính, `.secondary` cho thao tác phụ, `.danger-button` cho thao tác
  phá hủy và `.table-action` cho thao tác biểu tượng trong bảng. Tab, nút cuộn
  và nút tăng giảm dùng biến thể điều hướng hoặc điều khiển tương ứng.
- Các nút hành động đặt cùng hàng phải có cùng chiều cao. Dùng tối thiểu 44px,
  padding 10px 14px, bo góc 6px và `inline-flex` để căn giữa biểu tượng cùng
  nội dung. Dùng token `text-body-strong` cho chữ trên nút.
- Trong trang Cấu hình hệ thống, mọi `.inline-primary` dùng chung kiểu xanh lá
  phẳng và kích thước 44px đã định nghĩa trong `.settings-container`; không thêm
  kiểu nút riêng cho từng thao tác như “Thêm từ” hay “Lưu thay đổi”.
- Các nút cùng vai trò trên một màn hình phải dùng chung biến thể. Màu sắc,
  bóng đổ, trạng thái hover, active và disabled được định nghĩa tập trung trong
  `frontend/styles.css`; không tạo kiểu riêng cho từng nút hoặc dùng style inline.
- Nếu một luồng có biến thể nút đã được thiết lập, hãy dùng lại biến thể đó cho
  thao tác cùng vai trò. Chỉ tách kiểu cho điều hướng, nút biểu tượng, thao tác
  phá hủy hoặc trạng thái nghiệp vụ khi khác biệt đó có chủ đích.

## Quy ước triển khai

- Mỗi màn hình có đúng một `h1`; tiêu đề card, bảng và khối form dùng
  `text-title`.
- Nút, navigation và tên đối tượng dùng `text-body-strong`; input và cell bảng
  dùng `text-body`; nhãn field, chip trạng thái và header cột dùng `text-label`.
- Không đưa `font-family`, `font-size`, `font-weight` hoặc `line-height` vào
  `style="…"` hay thẻ `<style>` được render từ JavaScript. Thêm class vào
  stylesheet trung tâm thay thế.
- Chữ chính dùng `--navy`/`--ink`, chữ phụ dùng `--ink-soft`. Trạng thái luôn
  có nhãn hoặc biểu tượng, không chỉ dựa vào màu. Giữ tương phản văn bản ít
  nhất 4.5:1.

## Responsive

Chỉ heading giảm dưới 768px: display 30/38, h1 28/36, h2 22/30, h3 18/26.
Body, label, small và chữ thao tác giữ nguyên để không ảnh hưởng khả năng đọc.
