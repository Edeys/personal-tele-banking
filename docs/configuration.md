# Cấu hình

Hai nơi cấu hình, tách theo mục đích:

| File | Chứa gì | Ai ghi |
|---|---|---|
| `.env` | Secrets + endpoint (token, API key, Web App URL) | Bạn điền |
| `data/config.json` | Nguồn tiền, nhóm chi tiêu, hạng mục con, thành viên | Wizard `/start` ghi |

Đừng trộn: `config.json` **không** chứa secret, `.env` **không** chứa danh mục.

---

## `.env`

Xem `.env.example` để có bản mẫu đầy đủ.

### Bắt buộc

| Biến | Ý nghĩa |
|---|---|
| `TELE_BOT_TOKEN` | Token từ `@BotFather` → `/newbot` |
| `LLM_BASE_URL` | Endpoint OpenAI-compatible, ví dụ `https://openrouter.ai/api/v1` |
| `LLM_API_KEY` | API key của endpoint đó |
| `LLM_OCR_MODEL` | Model **đọc được ảnh** (vision), ví dụ `qwen/qwen2.5-vl-72b-instruct` |
| `LLM_CHAT_MODEL` | Model trả lời chat, ví dụ `openai/gpt-4o-mini` |
| `SHEETS_WEBAPP_URL` | URL Web App sau khi Deploy Apps Script |
| `SHEETS_WEBAPP_SECRET` | Chuỗi bí mật trùng với `SECRET` trong script |

### Tuỳ chọn

| Biến | Mặc định | Ý nghĩa |
|---|---|---|
| `IMAGE_STORE` | `catbox,telegraph,local` | Thứ tự lưu ảnh biên lai, thử lần lượt cho tới khi được |
| `WEBDAV_URL` / `WEBDAV_USER` / `WEBDAV_PASS` / `WEBDAV_FOLDER` | — | Lưu ảnh lên NAS/Nextcloud tự host |
| `LARK_APP_ID` / `LARK_APP_SECRET` / `LARK_APP_TOKEN` / `LARK_TABLE_ID` | — | Dùng Lark Base thay Google Sheets |
| `LARK_SOURCE_TABLE_ID` / `LARK_SOURCE_NAME_FIELD` | — | Bảng Sổ Quỹ để lookup nguồn tiền theo tên |
| `TELE_CONFIG_PATH` | `data/config.json` | Đổi vị trí file config |
| `TZ` | hệ thống | Múi giờ cho log |

Backend được chọn tự động: nếu có `SHEETS_WEBAPP_URL` → Google Sheets; nếu
không mà có `LARK_APP_ID` → Lark Base. Không có cả hai → bot báo lỗi lúc khởi động.

---

## `data/config.json`

Wizard `/start` sinh ra. Ví dụ:

```json
{
  "version": 1,
  "admin_id": 123456789,
  "allowed_users": [123456789, 987654321],
  "bot_name": "Sổ Thu Chi",
  "sources": ["VCB - 046", "MB - 259", "Tiền mặt", "MoMo"],
  "categories": {
    "Ăn uống": ["Nhà hàng", "Cafe"],
    "Gia đình": [],
    "Kinh doanh": ["Nguyên liệu"],
    "Lương": []
  },
  "income_groups": ["Lương"],
  "family": [{"id": 987654321}],
  "created_at": "2026-09-28T02:00:00+00:00"
}
```

| Khoá | Ý nghĩa |
|---|---|
| `admin_id` | Người đầu tiên gõ `/start` sau khi cài — có toàn quyền |
| `allowed_users` | Ai được dùng bot. Rỗng = chỉ admin |
| `sources` | Nguồn tiền. Phần trước dấu `-` là nhãn dùng để nhận diện từ ảnh |
| `categories` | Nhóm chi tiêu → danh sách hạng mục con (mảng rỗng = không có hạng mục con) |
| `income_groups` | Nhóm nào ghi vào tab `Tiền nhận` thay vì `Tiền chuyển` |
| `family` | Thành viên dùng chung; tự thêm vào `allowed_users` |

Muốn sửa danh mục/nguồn tiền: gõ `/setup` trong bot, **đừng sửa tay** — sửa tay
dễ làm JSON hỏng và bot sẽ quay về mặc định.

| Việc | Lệnh |
|---|---|
| Xem cấu hình hiện tại | `/config` |
| Sửa danh mục / nguồn tiền / thành viên | `/setup` (chạy lại wizard từ đầu) |
| Thêm 1 thành viên mà không phải chạy lại wizard | `/invite 123456789` (admin) |
| Kiểm tra nối Sổ + model đọc ảnh | `/test` |

Sửa `data/config.json` xong thì không cần khởi động lại bot: wizard lưu thẳng
vào object đang chạy và làm mới prompt OCR.

---

## Phân loại hoạt động thế nào

1. Prompt OCR được build từ `categories` của bạn, nên model chỉ chọn trong đúng
   nhóm/hạng mục bạn đã khai.
2. Nếu model trả về nhóm/hạng mục không có trong config → bot bỏ trống để bạn
   chọn bằng nút, thay vì ghi dữ liệu rác.
3. Nguồn tiền được nhận diện bằng cách so tên ngân hàng trong ảnh với `sources`
   (có mở rộng tên viết tắt: `VCB` ↔ `Vietcombank`), hoặc bạn chọn tay bằng nút
   **Nguồn tiền**.
