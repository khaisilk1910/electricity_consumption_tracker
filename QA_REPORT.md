# QA report — electricity_consumption_tracker 2026.11.1

**Ngày kiểm tra:** 2026-11-07. **Target:** HA Core 2026.11.0, Marketplace/HACS.

## Kiểm tra đã thực hiện trong môi trường tạo bản vá

- [x] Xác minh cấu trúc thư mục integration (`custom_components/<domain>`), manifest JSON, hacs.json, strings/translations.
- [x] Static Python syntax (`compileall`/`py_compile`).
- [x] 15 phép thử pytest: biểu giá 2026 5 bậc, mốc giá lịch sử, âm/NaN/Infinity, phân kỳ hóa đơn, update/reopen, ghi đồng thời, schema migration.
- [x] Node `--check` cú pháp JS.
- [x] Node smoke test thẻ: đăng ký lặp, Config Editor, rendering biểu đồ, ràng buộc entity, rename theo registry, escaping HTML, rỗng dữ liệu.
- [x] Code review: không có SQLite I/O đồng bộ trên main event loop; dữ liệu một ngày không ghi thành zero khi sensor unavailable; ghi được khóa; `unique_id` gốc và vị trí DB gốc giữ nguyên.
- [x] Đối chiếu các API Lovelace/Config Flow và Marketplace với tài liệu Home Assistant 2026.11.

## Chưa kiểm chứng, bắt buộc kiểm tra thêm khi triển khai

- [ ] Chưa chạy instance HA Core 2026.11.0 thật (không có package Home Assistant trong môi trường kiểm thử) nên chưa thể khẳng định không có lỗi runtime, lifecycle, frontend browser hoặc storage lock trong HA thật.
- [ ] Chưa chạy HACS Action/hassfest trong GitHub Actions: workflow `.github/workflows/validate.yml` đã chuẩn bị để chạy khi đẩy repository lên GitHub.
- [ ] Chưa benchmark thời gian khởi động/sử dụng RAM trên thiết bị Home Assistant và tập dữ liệu lâu năm thực tế.
- [ ] Chưa thử nghiệm mức bảo mật/kết nối trên mọi loại dashboard, mobile app, theme, accessibility và mọi nguồn sensor.
- [ ] Không đối soát số tiền với hóa đơn EVN thực tế khi chu kỳ đi qua thời điểm đổi biểu giá/VAT.

## Checklist nghiệm thu sau khi cài trên HA thực tế

1. Sao lưu và thử nâng cấp entry đang chạy với lịch sử 1–2 năm; số hàng `daily_usage` phải giữ nguyên.
2. Khởi động lại và kiểm tra log không lỗi stack trace; thẻ hiện khi mở Dashboard.
3. Mất kết nối sensor nguồn → không ghi giá trị `0` mới vào DB; warning xuất hiện đúng một lần mỗi nguyên nhân.
4. Đổi sensor/chu kỳ trong Configure → entry reload tự động, hóa đơn cập nhật, không sinh entity trùng.
5. Chèn lại một số liệu quá khứ qua action → số kWh/tháng/năm/tổng thay đổi khớp.
6. Dashboard Sections, dark/light themes, card editor, đổi tên entity trong Settings và tải lại trình duyệt.
7. Kiểm tra bằng GitHub CI với HACS Action và hassfest trước khi tạo GitHub Release.
