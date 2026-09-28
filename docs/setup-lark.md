# Setup Lark Base (tuỳ chọn)

Chỉ dùng nếu bạn làm việc trong hệ sinh thái Lark. Nếu chỉ muốn bot chạy nhanh,
hãy dùng Google Sheets — xem [`setup-sheets.md`](setup-sheets.md).

So với Sheets, Lark khó hơn: bạn phải tạo app, cấp quyền, tạo bảng và khai
đúng tên cột.

## 1. Tạo app Lark

1. Vào https://open.larksuite.com/app → **Create custom app**
2. Vào **Credentials & Basic Info** → copy **App ID** và **App Secret**
3. Vào **Permissions & Scopes**, thêm quyền cho Bitable:
   - `bitable:app` (đọc/ghi bản ghi)
   - `drive:drive` (upload ảnh biên lai)
4. **Create version** → **Publish** để quyền có hiệu lực

## 2. Tạo bảng dữ liệu

Tạo một Bitable (Base) với bảng giao dịch, các cột **đúng tên** sau:

| Tên cột | Kiểu |
|---|---|
| `Ngày giao dịch` | Date |
| `Thời gian` | Text |
| `Loại Giao Dịch` | Text |
| `Dòng tiền` | Single select (`Thu`, `Chi`) |
| `Số tiền VND` | Number |
| `Phân loại lớn` | Single select (các nhóm bạn khai trong `/start`) |
| `Hạng mục Thu/Chi` | Single select (các hạng mục con) |
| `Nội dung chuyển khoản` | Text |
| `Nội dung chi tiết` | Text |
| `Người Nhận` | Text |
| `Ngân Hàng Nhận Tiền` | Text |
| `Mã giao dịch` | Text |
| `Tài khoản/Quỹ` | Text **hoặc** Link tới bảng Sổ Quỹ |
| `Trạng thái` | Text |
| `Chứng từ/ Hoá đơn` | Attachment |

Lấy `app_token` và `table_id` từ URL của bảng:

```
https://xxx.larksuite.com/base/<APP_TOKEN>?table=<TABLE_ID>&view=...
```

## 3. (Tuỳ chọn) Lookup nguồn tiền theo tên

Nếu `Tài khoản/Quỹ` là cột **Link** tới một bảng Sổ Quỹ riêng:

- `LARK_SOURCE_TABLE_ID` = id bảng Sổ Quỹ
- `LARK_SOURCE_NAME_FIELD` = tên cột chứa tên quỹ (ví dụ `Tên quỹ`)

Bot sẽ tìm bản ghi có tên khớp với nguồn tiền bạn khai, rồi gắn link — thay vì
hardcode record id như các bản cũ.

Không cấu hình hai biến này thì bot ghi tên quỹ dạng text bình thường.

## 4. Điền `.env`

```env
LARK_APP_ID=cli_xxxxxxxx
LARK_APP_SECRET=xxxxxxxx
LARK_APP_TOKEN=xxxxxxxx
LARK_TABLE_ID=tblxxxxxxxx

# tuỳ chọn
LARK_SOURCE_TABLE_ID=tblxxxxxxxx
LARK_SOURCE_NAME_FIELD=Tên quỹ
```

Để bot dùng Lark thay vì Sheets, **đừng** điền `SHEETS_WEBAPP_URL`.

## Xử lý sự cố

| Triệu chứng | Nguyên nhân |
|---|---|
| `Lark auth failed` | Sai App ID/Secret, hoặc app chưa Publish |
| Ghi được nhưng cột trống | Tên cột trong bảng khác bảng trên (phân biệt cả dấu cách) |
| Ảnh không lên | Thiếu scope `drive:drive` |
| `Tài khoản/Quỹ` ghi ra text dù đã cấu hình link | `LARK_SOURCE_NAME_FIELD` không khớp tên cột, hoặc tên quỹ trong Sổ Quỹ khác `sources` trong config |
