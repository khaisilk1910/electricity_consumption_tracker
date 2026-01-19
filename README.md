# ⚡ Electricity Consumption Tracker (Multi-Entry)

Tích hợp tùy chỉnh (Custom Integration) cho Home Assistant giúp quản lý, lưu trữ và tính toán tiền điện lũy tiến Việt Nam cho nhiều thiết bị hoặc công tơ điện độc lập cùng lúc.


## Cài đặt


1. Nhấn nút bên dưới để thêm vào HACS trên Home Assistant.

   [![Open your Home Assistant instance and open a repository inside the Home Assistant Community Store.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=khaisilk1910&repository=electricity_consumption_tracker&category=integration)

   - Sau khi thêm trong HACS và khởi động lại Home Assistant
     
   - Vào Settings -> Integrations -> Add integration nhập `Electricity Consumption Tracker` để thêm
  
     <img width="492" height="647" alt="image" src="https://github.com/user-attachments/assets/743ac0af-26c1-41fc-8c3c-d978ad07038a" />
  
     Điền tên muốn lưu và chọn sensor dữ liệu theo ngày đã có để theo dõi (Lưu ý chỉ chọn sensor sản lượng Ngày)

     <img width="413" height="424" alt="image" src="https://github.com/user-attachments/assets/ed9cbe21-81bc-4a01-afa2-09956d20eb8d" />


## ✨ Đường dẫn

* **Của custom_component:** `\config\custom_components\electricity_consumption_tracker`
* **File dữ liệu:** Nằm riêng biệt và ngoài thư mục config của Home assistant `\config\electricity_consumption_tracker`

  
## ✨ Tính năng nổi bật

* **Hỗ trợ đa thực thể (Multi-Entry):** Cho phép thêm không giới hạn các thiết bị theo dõi (như Tổng nhà, Điều hòa, Bếp điện...) với các file cơ sở dữ liệu SQLite (`.db`) riêng biệt cho từng thiết bị.
* **Tự động hóa hoàn toàn:** Hệ thống tự động quét dữ liệu từ sensor nguồn theo chu kỳ cấu hình (từ 1 đến 24 giờ) và lưu trữ vào database.
* **Biểu giá điện EVN:** Tích hợp sẵn lịch sử giá điện lũy tiến Việt Nam với các mốc thay đổi quan trọng từ năm 2019, 2023, 2024 đến năm 2025.
* **Xử lý lỗi thông minh:** Tự động gán giá trị `0` nếu sensor nguồn bị lỗi (`unavailable`, `unknown`) để đảm bảo hệ thống không bị ngắt quãng.
* **Thông báo hệ thống:** Tự động gửi thông báo (Persistent Notification) lên giao diện Home Assistant khi phát hiện sensor nguồn không có dữ liệu để người dùng kịp thời kiểm tra.
* **Tương thích ApexCharts:** Cung cấp thuộc tính `chi_tiet_ngay` chứa sản lượng của từng ngày trong tháng, giúp bạn vẽ biểu đồ tiêu thụ điện năng trực quan mà không cần thêm sensor phụ.
* **Ghi đè dữ liệu:** Cung cấp Service chuyên dụng để nạp hoặc sửa đổi dữ liệu sản lượng trong quá khứ thủ công khi cần thiết.

## 🛠 Cài đặt

1. Tải thư mục `custom_components/electricity_consumption_tracker` vào thư mục `/config/custom_components/` trên Home Assistant của bạn.
2. Khởi động lại Home Assistant.
3. Vào **Cài đặt (Settings)** > **Thiết bị & Dịch vụ (Devices & Services)** > **Thêm thực thể (Add Integration)**.
4. Tìm kiếm và chọn **Electricity Consumption Tracker**.

## ⚙️ Cấu hình

Trong cửa sổ cấu hình, bạn cần cung cấp:
* **Friendly Name:** Tên hiển thị cho thiết bị (ví dụ: "Điện Tổng", "Máy Lạnh").
* **Source Sensor:** Chọn thực thể đo điện năng đầu vào (đơn vị kWh) của thiết bị đó.
* **Update Interval:** Khoảng thời gian (giờ) mà hệ thống sẽ tự động chốt số liệu và tính toán tiền điện.

## 🚀 Dịch vụ (Services)

### `electricity_consumption_tracker.override_data`
Dịch vụ này cho phép bạn ghi đè hoặc bổ sung dữ liệu cho một ngày bất kỳ trong quá khứ:
* `entry_id`: ID của thiết bị cần ghi dữ liệu (Có thể tìm thấy trong thông tin cấu hình tích hợp).
* `date`: Ngày cần ghi dữ liệu (định dạng YYYY-MM-DD).
* `value`: Giá trị sản lượng điện năng (kWh) muốn ghi vào database.

## 📊 Thuộc tính Sensor (Attributes)

Các sensor được tạo ra bởi tích hợp này bao gồm các thuộc tính mở rộng để hỗ trợ vẽ biểu đồ:
* `tong_san_luong_kwh`: Tổng điện năng tiêu thụ tích lũy trong tháng hiện tại.
* `chi_tiet_ngay`: Dữ liệu sản lượng chi tiết của từng ngày trong tháng (thường dùng cho `data_generator` trong ApexCharts).

## 📝 Giấy phép

Dự án này được phát hành dưới giấy phép **MIT License**.
