# Changelog

## 2026.11.1 (2026-11-07)

- Chuẩn bị cho Home Assistant 2026.11.0 và Marketplace (thay cho HACS): manifest có category hợp lệ; `hacs.json`; action CI cho Marketplace, hassfest, pytest và Node.
- Áp dụng API 2026.11 cho `async_setup_entry` / `async_unload_entry`, `DeviceInfo`, `OptionsFlowWithReload` và Lovelace resources.
- Giữ Config Flow version 1 để bảo toàn entry cũ; thêm tiếng Việt, tiếng Anh và trường `source_day_offset`.
- Đưa I/O SQLite về executor, tuần tự hóa qua lock, chia sẻ snapshot giữa các sensor; chuyển quá trình tính lại lịch sử sang background task.
- Kiểm tra số ngày không hợp lệ, NaN, Infinity, giá trị âm, đơn vị sensor không phù hợp; giữ số liệu ngày cũ nếu nguồn bị lỗi; logging đầy đủ hơn.
- Hỗ trợ biểu giá điện sinh hoạt 5 bậc từ 01/11/2026, điều chỉnh mốc giá 2023; tái tính toán hóa đơn dựa trên dữ liệu ngày đã lưu.
- Sửa đổi Lovelace card với các hook chuẩn UI, đổi entity, UX trạng thái rỗng, dashboard Sections, escaping HTML và fallback khi rename entity.
- Bổ sung test SQLite, migration, ghi đồng thời và runtime JavaScript; thêm hướng dẫn backup/rollback.

### Có thể thay đổi dữ liệu hiển thị

Do biểu giá thuế và quy tắc tính tiền được cập nhật, các sensor tiền điện có thể nhận giá trị mới sau nâng cấp. Số đo ngày giữ nguyên; hãy sao lưu trước khi áp dụng.
