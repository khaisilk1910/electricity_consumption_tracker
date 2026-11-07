# Electricity Consumption Tracker — Home Assistant / Marketplace

[![Validate Marketplace integration](https://github.com/khaisilk1910/electricity_consumption_tracker/actions/workflows/validate.yml/badge.svg)](https://github.com/khaisilk1910/electricity_consumption_tracker/actions/workflows/validate.yml)

Tích hợp tùy chỉnh theo dõi **điện năng tiêu thụ theo ngày**, tính **ước tính tiền điện sinh hoạt theo biểu giá lũy tiến Việt Nam**, tạo các sensor tháng, năm, tổng và thẻ Lovelace có trình chỉnh sửa trực quan. Mỗi config entry có cơ sở dữ liệu SQLite riêng.

**Phiên bản dự án:** `2026.11.1` · **Mục tiêu:** Home Assistant Core **2026.11.0+** và **Marketplace** (trước đây là HACS). Tích hợp được thiết kế và kiểm tra tĩnh theo API 2026.11; chưa phải bản được chứng nhận bởi Home Assistant.

## Nâng cấp an toàn từ bản trước

1. Tạo **Home Assistant Full Backup**. Đặc biệt sao lưu thư mục `/config/electricity_consumption_tracker/` chứa các tệp `electricity_data_<entry_id>.db` (bao gồm `-wal`, `-shm` nếu đang có và cần sao chép nhất quán). Nên dừng Home Assistant trước khi sao chép trực tiếp SQLite hoặc dùng tính năng backup tích hợp.
2. **Không xóa integration/config entry** cũ, không xóa cơ sở dữ liệu. Giữ nguyên tên thư mục `custom_components/electricity_consumption_tracker`.
3. Cập nhật qua **Settings → Marketplace** (nếu bản phát hành mới đã được đẩy lên repository trên GitHub), hoặc chép đè **chỉ** thư mục `custom_components/electricity_consumption_tracker/` từ mã nguồn này vào `/config/custom_components/`.
4. Khởi động lại Home Assistant, mở **Settings → Devices & services → Electricity Consumption Tracker** và kiểm tra các entity. Làm mới trình duyệt (Ctrl+F5 / refresh app) để nạp JavaScript mới.
5. Kiểm tra Log và một số hóa đơn trong **11/2026**. Tiền điện lịch sử sẽ được **tính lại trong tác vụ nền** khi thay đổi biểu giá hoặc chu kỳ, còn dữ liệu tiêu thụ theo ngày được giữ nguyên.

> Cảnh báo: các entity tiền điện và số liệu tính toán có thể thay đổi sau khi nâng cấp do cập nhật biểu giá; đây không phải mất dữ liệu. Cơ sở dữ liệu cũ giữ nguyên vị trí và các `unique_id` của các sensor hiện có được duy trì. Trước khi khôi phục bản cũ, hãy khôi phục cả các bản sao lưu cơ sở dữ liệu tương ứng.

## Cài đặt mới

### Marketplace (Home Assistant 2026.11+)

Mở **Settings → Marketplace**, tìm `Electricity Consumption Tracker`. Nếu repository chưa xuất hiện trong danh mục, thêm custom repository:

`https://github.com/khaisilk1910/electricity_consumption_tracker`

Chọn loại **Integration**, cài đặt, rồi **Settings → Devices & services → Add integration** → tìm `Electricity Consumption Tracker`. Marketplace chỉ cài thư mục `custom_components/electricity_consumption_tracker`, không cài các automation hoặc tệp `pyscript_hass` minh họa trong repository.

Nút mở repository trong Marketplace: [Open Electricity Consumption Tracker](https://my.home-assistant.io/redirect/marketplace_repository/?owner=khaisilk1910&repository=electricity_consumption_tracker&category=integration)

**Cài thủ công:** chép `custom_components/electricity_consumption_tracker` vào `/config/custom_components/`, khởi động lại Home Assistant và thêm integration như trên. Đây là mã nguồn để tự xuất bản; việc đặt file ZIP trong máy không tự tạo một phiên bản phát hành trên Marketplace.

### Cấu hình integration

| Trường | Ý nghĩa |
|---|---|
| Tên bộ theo dõi | Tên entity ban đầu, nhập khi tạo entry. |
| Sensor nguồn | **Sản lượng điện tiêu thụ theo ngày** (`kWh` hoặc `Wh`). **Không** chọn công suất `W`, số công tơ cộng dồn hoặc kWh tổng tích lũy. |
| Chu kỳ đọc | Mỗi 1–24 giờ; cộng thêm lần đọc lúc `23:59:55` (giờ địa phương). |
| Ngày đầu kỳ hóa đơn | Ngày 1–28, quy ước ngày này là đầu chu kỳ hóa đơn **tháng sau**. |
| Ngày áp dụng quy tắc chu kỳ | Các ngày trước mốc được gán vào tháng lịch, từ mốc mới áp dụng chu kỳ tùy chỉnh. |
| Ngày của sensor | `0`: số đo hiện tại là của **hôm nay**; `1`: số đo hiện tại là của **hôm qua**. Chọn khớp với sensor/automation nguồn. |

Vào **Settings → Devices & services → Electricity Consumption Tracker → Configure** để đổi sensor nguồn, lịch đọc, ngày hóa đơn, ngày áp dụng và độ lệch ngày. Options Flow tự reload entry và tính lại khi cần. Không hỗ trợ đổi tên ban đầu bằng Options Flow để tránh vô tình đổi ID của entity; có thể đổi friendly name/entity ID trong giao diện Entities.

**Lưu ý tính chính xác:** tích hợp **ghi giá trị trạng thái sensor vào ngày được cấu hình**, không tự trừ hai chỉ số công tơ cộng dồn. Sensor ngày phải thực sự đo sản lượng của ngày đó và còn hiển thị số đo cuối ngày lúc tích hợp đọc. Sensor mất kết nối, `unknown`, `unavailable`, giá trị âm, NaN hoặc đơn vị không phải `Wh`/`kWh` **sẽ không ghi dữ liệu** và có warning trong log; không thay bằng `0`. Dữ liệu chưa từng được ghi không thể tự khôi phục từ sensor chỉ có trạng thái hiện tại — hãy dùng automation hoặc thao tác nhập bù.

## Thẻ Lovelace

1. Tạo/chỉnh sửa dashboard → **Add card** → tìm **Thống kê Điện năng**.
2. Chọn bộ theo dõi trong visual editor. Tùy chỉnh tiêu đề, biểu tượng, nền, màu, độ trong suốt, viền, đổ bóng, tự tương phản, màu cột và màu biểu đồ.
3. Các tab **Tổng quan** và **Tra cứu** hỗ trợ duyệt tháng/năm. Thẻ hỗ trợ Sections (grid options), trạng thái rỗng, ánh xạ entity ID đổi tên trong entity registry và các biểu đồ chi tiết theo kỳ hóa đơn.

Thẻ có URL tích hợp: `/electricity_consumption_ui/electricity-consumption-card.js?v=2026.11.1`.

Trong chế độ resource mặc định **storage**, integration sẽ cố gắng đăng ký hoặc cập nhật JavaScript resource **một lần khi Home Assistant khởi động** (không phải mỗi entry). Nếu tự động đăng ký thất bại, vào **Settings → Dashboards → Resources** và thêm URL trên với type `JavaScript module`. Với chế độ Lovelace resources YAML, khai báo thủ công:

```yaml
lovelace:
  resource_mode: yaml
  resources:
    - url: /electricity_consumption_ui/electricity-consumption-card.js?v=2026.11.1
      type: module
```

Nếu thẻ báo chưa có sensor, hãy xác nhận integration đã tải, có một entity tổng `_total_all_time` với attribute `chi_tiet_tung_nam`, rồi refresh trình duyệt. Không thêm URL resource trùng lặp, cũng không cần cài thẻ này như một **Marketplace dashboard plugin riêng**.

## Ghi đè số liệu lịch sử

Trong **Developer tools → Actions**, chọn `electricity_consumption_tracker.override_data`:

```yaml
action: electricity_consumption_tracker.override_data
data:
  entry_id: YOUR_CONFIG_ENTRY_ID
  date: "2026-11-06"
  value: 12.5
```

`value` là số kWh trong ngày (không âm, không NaN/Infinity); không ghi vào ngày tương lai. Việc sửa sẽ cập nhật hóa đơn tháng, năm, tổng và thẻ. Nếu sensor nguồn vẫn còn báo một số khác cho chính ngày ấy, lần đọc tiếp theo **có thể ghi đè chỉnh sửa**; chỉ sửa ngày đã qua hoặc điều chỉnh sensor nguồn/độ lệch ngày phù hợp.

## Biểu giá và phạm vi ước tính

- Từ **01/11/2026**, áp dụng **5 bậc giá điện sinh hoạt**: 100 kWh đầu × 1.901 đ; 100 kWh tiếp × 2.289 đ; 200 kWh tiếp × 2.894 đ; 300 kWh tiếp × 3.456 đ; trên 700 kWh × 3.844 đ (chưa VAT), theo quy định EVN/Bộ Công Thương.
- Lịch sử 6 bậc từ 2019, 2023, 2024, 2025 tiếp tục được hỗ trợ để tính lại dữ liệu các năm cũ.
- Giá trị tính toán là **ước tính hóa đơn sinh hoạt**, không phải bản sao tuyệt đối hóa đơn điện lực. Giá áp dụng theo **ngày kết thúc chu kỳ**; nếu một kỳ vắt qua thời điểm đổi biểu giá, cần đối chiếu thực tế cách EVN phân bổ sản lượng. VAT được ước tính theo lịch sử thuế đã cấu hình; các khoản phụ phí/hợp đồng đặc biệt chưa được mô hình hóa. Chỉ sử dụng cho **điện sinh hoạt thông thường**, không dùng để đối soát hóa đơn kinh doanh, ba giá hoặc bù trừ điện mặt trời.

## Cấu trúc và khả năng xử lý

- **SQLite:** `/config/electricity_consumption_tracker/electricity_data_<entry_id>.db`; duy trì bảng cũ `daily_usage`, `monthly_bill`, `yearly_bill`, `total_usage`.
- **I/O:** tất cả thao tác SQLite và tạo thư mục chạy trong HA executor; mỗi entry có `asyncio.Lock` để tránh ghi/đọc đồng thời; một lần đọc snapshot cập nhật tất cả sensor trong entry. Khởi tạo schema cần hoàn tất trước khi đưa platform sensor vào hoạt động, còn tính lại lịch sử chạy ở background task.
- **Logging:** xem `Settings → System → Logs`, hoặc bật debug:

```yaml
logger:
  default: warning
  logs:
    custom_components.electricity_consumption_tracker: debug
```

Warning sensor nguồn được khử trùng lặp đến khi thông báo lỗi thay đổi, để không làm đầy log. Khi file SQLite bị hỏng/quyền ghi bị từ chối, stack trace nằm trong log.

## Phát hành lên Marketplace

Repository phải có `hacs.json`, `custom_components/electricity_consumption_tracker/manifest.json`, các file Python, `strings.json`/`translations`, frontend và README. Luôn tạo **GitHub release/tag** cho phiên bản `2026.11.1` sau khi chạy CI `hacs/action`, `hassfest`, pytest và Node tests. Tên version trong manifest, README và URL resource cần được đồng bộ. Workflow cũ tự ghi commit/tag không an toàn đã bị thay bằng workflow chỉ xác thực.

## Kiểm thử & giới hạn xác thực

Chạy từ thư mục gốc dự án:

```bash
python -m pytest -q tests/
node --check custom_components/electricity_consumption_tracker/frontend/electricity-consumption-card.js
node tests/test_card.cjs
```

Các kiểm thử kho dữ liệu chạy được khi **không cài Home Assistant**. Kiểm thử JavaScript là smoke test với DOM giả, **không tương đương** mở thẻ trong trình duyệt thật. GitHub Actions kiểm thử Marketplace/hassfest sau khi đẩy mã lên. Nên chạy thêm thử nghiệm trên instance Home Assistant 2026.11 thực tế trước khi dùng cho dữ liệu quan trọng. Xem `CHANGELOG.md` và `QA_REPORT.md`.

## Giấy phép

MIT License. Các mẫu `Automations/`, `Lovelace UI/`, `pyscript_hass/` ngoài thư mục integration là tài liệu/dữ liệu mẫu kế thừa; tự kiểm tra trước khi dùng, không phải chức năng được Marketplace cài đặt.
