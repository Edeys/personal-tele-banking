# Setup Google Sheets (không cần Google Cloud)

Bot ghi vào Google Sheet của **chính bạn** qua một Apps Script Web App. Bạn chỉ
cần copy-paste 1 đoạn script — **không** cần Google Cloud Console, không service
account, không share folder.

Mất khoảng 3 phút.

---

## 1. Tạo một Google Sheet trống

Mở https://sheets.new → đặt tên tuỳ ý (ví dụ `Sổ thu chi`). Không cần tạo cột,
bot + script sẽ tự tạo.

## 2. Mở Apps Script

Trong Sheet vừa tạo: menu **Extensions → Apps Script**.
Một tab mới mở ra với file `Code.gs` chứa `function myFunction() {}`.

## 3. Dán đoạn script này

Xoá toàn bộ nội dung `Code.gs`, dán đoạn dưới đây.

**Đổi dòng `SECRET`** thành một chuỗi bí mật do bạn tự nghĩ (càng dài càng tốt,
ví dụ `so-thu-chi-2026-abcxyz`). Chuỗi này là mật khẩu để bot được phép ghi —
**đừng dùng lại mật khẩu nào khác của bạn**.

```javascript
// ĐỔI DÒNG NÀY thành chuỗi bí mật của riêng bạn
const SECRET = 'doi-thanh-chuoi-bi-mat-cua-ban';

function doPost(e) {
  try {
    const body = JSON.parse(e.postData.contents);
    if (!body || body.secret !== SECRET) {
      return json({ ok: false, error: 'sai secret' });
    }
    if (body.action === 'append') {
      return json(appendRow(body.tab || 'Sổ thu chi', body.fields || {}));
    }
    if (body.action === 'recent') {
      return json(recentRows(body.limit || 10));
    }
    return json({ ok: false, error: 'action khong ho tro' });
  } catch (err) {
    return json({ ok: false, error: String(err) });
  }
}

function json(obj) {
  return ContentService
    .createTextOutput(JSON.stringify(obj))
    .setMimeType(ContentService.MimeType.JSON);
}

function sheetFor(tab) {
  const ss = SpreadsheetApp.getActiveSpreadsheet();
  return ss.getSheetByName(tab) || ss.insertSheet(tab);
}

function appendRow(tab, fields) {
  const sh = sheetFor(tab);
  let headers = [];
  if (sh.getLastColumn() > 0) {
    headers = sh.getRange(1, 1, 1, sh.getLastColumn()).getValues()[0];
  }
  if (headers.length === 0 || headers.join('') === '') {
    headers = Object.keys(fields);
    sh.getRange(1, 1, 1, headers.length).setValues([headers]);
  }
  const row = headers.map(function (h) {
    return fields[h] !== undefined && fields[h] !== null ? fields[h] : '';
  });
  sh.appendRow(row);
  return { ok: true, tab: tab, row: row.length };
}

function recentRows(limit) {
  const ss = SpreadsheetApp.getActiveSpreadsheet();
  const out = [];
  ss.getSheets().forEach(function (sh) {
    const values = sh.getDataRange().getValues();
    if (values.length < 2) return;
    const headers = values[0];
    for (let i = 1; i < values.length; i++) {
      const row = {};
      headers.forEach(function (h, j) { row[h] = values[i][j]; });
      out.push(row);
    }
  });
  return { ok: true, rows: out.slice(-limit) };
}
```

Nhấn biểu tượng 💾 (Save).

## 4. Deploy thành Web App

1. Bấm **Deploy → New deployment**
2. Bấm bánh răng ⚙️ cạnh "Select type" → chọn **Web app**
3. Điền:
   - **Description**: `tele-banking`
   - **Execute as**: **Me** (chính bạn)
   - **Who has access**: **Anyone**  ← bắt buộc, nếu chọn "Only myself" bot không gọi được
4. Bấm **Deploy** → **Authorize access** → chọn tài khoản Google của bạn
5. Google hiện cảnh báo "This app isn't verified" → bấm **Advanced → Go to ... (unsafe)**. Đây là script của chính bạn, cảnh báo là bình thường vì script chưa qua Google review.
6. Copy **Web app URL** — dạng `https://script.google.com/macros/s/AKfy.../exec`

## 5. Điền vào `.env`

```env
SHEETS_WEBAPP_URL=https://script.google.com/macros/s/AKfy.../exec
SHEETS_WEBAPP_SECRET=doi-thanh-chuoi-bi-mat-cua-ban
```

(`SHEETS_WEBAPP_SECRET` phải **giống hệt** chuỗi `SECRET` ở bước 3.)

## 6. Kiểm tra

```bash
curl -s -X POST "$SHEETS_WEBAPP_URL" \
  -H 'Content-Type: application/json' \
  -d '{"secret":"doi-thanh-chuoi-bi-mat-cua-ban","action":"recent","limit":5}'
```

Kết quả mong đợi: `{"ok":true,"rows":[]}`.

Sau đó gửi thử 1 ảnh biên lai cho bot → bấm **Duyệt** → mở Sheet, phải thấy tab
`Tiền chuyển` (hoặc `Tiền nhận`) với 1 dòng mới.

---

## Bot ghi những cột gì?

Tab được tạo tự động theo chiều tiền: `Tiền chuyển` cho chi tiêu, `Tiền nhận`
cho các nhóm bạn khai là thu nhập ở bước 3 của wizard.

| Cột | Ý nghĩa |
|---|---|
| Ngày giao dịch | `DD/MM/YYYY` |
| Thời gian | `HH:MM` |
| Loại Giao Dịch | `Banking` hoặc `Shoppe` |
| Dòng tiền | `Thu` / `Chi` |
| Số tiền VND | số nguyên |
| Phân loại lớn | nhóm chi tiêu (từ config của bạn) |
| Hạng mục Thu/Chi | hạng mục con |
| Nội dung chuyển khoản | nguyên văn từ biên lai |
| Nội dung chi tiết | ghi chú |
| Người Nhận | tên người nhận |
| Ngân Hàng Nhận Tiền | ngân hàng nhận |
| Mã giao dịch | mã từ biên lai |
| Tài khoản/Quỹ | nguồn tiền đã nhận diện |
| Trạng thái | `Đã thanh toán` |
| Chứng từ | URL ảnh biên lai |

Muốn ảnh hiển thị thẳng trong ô: thêm cột phụ với công thức
`=IMAGE(O2)` (giả sử cột Chứng từ là cột O).

## Xử lý sự cố

| Triệu chứng | Nguyên nhân thường gặp |
|---|---|
| `{"ok":false,"error":"sai secret"}` | `SHEETS_WEBAPP_SECRET` trong `.env` khác `SECRET` trong script |
| Bot báo lỗi khi ghi, log có HTTP 401/403 | **Who has access** chưa đặt là `Anyone` |
| Sửa script nhưng bot vẫn chạy bản cũ | Phải **Deploy → Manage deployments → Edit → New version** — sửa code không tự cập nhật Web App |
| Không thấy dòng nào trong Sheet | Kiểm tra biến `SHEETS_WEBAPP_URL` có đuôi `/exec` (không phải `/dev`) |
