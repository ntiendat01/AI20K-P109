# Benchmark payload Decision LLM (P3-T4)

## Cách đo

Đo payload JSON của fixture có 2, 5 và 10 NCC bằng hàm
`estimate_payload_tokens()`. Đây là phép đếm offline ổn định theo từ và dấu
JSON để so sánh trước/sau; **không phải** số token tính phí của một provider.
Không gọi LLM thật vì chưa có uỷ quyền dùng API/chi phí cho benchmark này.

| Số NCC | Payload trước | Payload sau | Giảm |
| ---: | ---: | ---: | ---: |
| 2 | 6.613 | 5.004 | 24,33% |
| 5 | 7.726 | 5.634 | 27,08% |
| 10 | 9.581 | 6.684 | 30,24% |

Payload mới vẫn có sáu input chính: schema, `top_n`, `tco_results`,
`comparison_matrix`, `risk_flags`, `confirmed_context`. Mọi fact claimable vẫn
giữ `supplier_id`, metric, value, unit và `time_origin` khi có; phần bỏ đi là
`null`/rỗng, chi tiết `items_tco` và metadata ma trận chỉ phục vụ UI
(`deviation_pct`, `highlight`, `note`, `means`). Schema prompt giữ nguyên JSON
Schema đầy đủ của `DecisionProposal` (bao gồm nested claim/predicate rules) và
chỉ bỏ `title`, `description`, `default`, `examples`; Pydantic vẫn xác thực
contract đầy đủ ở runtime.

## Chất lượng

Trên fixture proposal xác định, parse `DecisionProposal` và strict evaluation
đều pass trước/sau (cùng output hợp lệ, 1/1). Bộ test integration dùng payload
mới cũng pass toàn bộ evidence/constraint guard. Chưa có số liệu 3–5 lần với
LLM thật, nên chưa kết luận được tỷ lệ parse hay chất lượng ngôn ngữ thực tế;
đó là bước rollout cần chạy sau khi có uỷ quyền provider.

Tái chạy kiểm tra offline:

```sh
.venv/bin/python3 -m pytest tests/test_agents/test_decision_payload.py -q
```
