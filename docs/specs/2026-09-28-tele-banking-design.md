# Tele-Banking — Design Spec (bản open-source rebuild)

> Ngày: 2026-09-28 · Trạng thái: Đã chốt hướng, đang build P0
> Rebuild hoàn toàn từ repo private `tele-banking-lark`. Không port code cũ — chỉ giữ ý tưởng + các bài học đã proven (OCR retry, queue ảnh, confirm keyboard).

## 0. Quyết định đã chốt (2026-09-28)

| # | Quyết định | Lý do |
|---|---|---|
| D1 | **Rebuild theo spec**, không dọn bản cũ | Bản cũ cứng vào 1 người dùng; dọn còn tốn hơn viết lại |
| D2 | **Google Sheets là backend mặc định**, Lark là optional | Ai cũng có Google account, free, không phụ thuộc Lark tenant |
| D3 | **Sheets auth = Apps Script Web App**, KHÔNG service account | Service account bắt user tự làm Google Cloud Console (SA + enable 2 API + share sheet/folder) — non-coder không làm được, AI agent cũng không click Console được. Apps Script chỉ cần copy-paste 1 đoạn script vào sheet của họ |
| D4 | **Audience = non-coder có AI agent** | Thứ quyết định giá trị không phải Docker mà là cắt bỏ bước chỉ con người làm được. AGENTS.md là runbook cho agent, docs có hướng dẫn copy-paste từng bước |
| D5 | Repo mới `Edeys/personal-tele-banking` — tách hẳn production `Edeys/banking` trên VPS | Rebuild không đụng bot đang chạy |
| D6 | Không mang git history cũ; repo bắt đầu từ commit sạch | Tránh secrets trong history |

Hệ quả của D3: `backends/sheets.py` gọi HTTP tới Web App URL (không dùng `gspread`), user cung cấp `SHEETS_WEBAPP_URL` + `SHEETS_WEBAPP_SECRET`. Script Apps Script do repo phát hành (`docs/setup-sheets.md`).

## 1. Sản phẩm

Self-hosted Telegram bot: **chụp ảnh biên lai / giao dịch banking / đơn Shopee-TikTok → OCR bằng LLM vision → user xác nhận qua nút inline → ghi vào Google Sheet hoặc Lark Base của chính user, ảnh đính kèm.**

- Mỗi người tự deploy bot của riêng họ (self-hosted, cần 1 server/VPS)
- Không hardcode danh mục/tài khoản của ai — user tự định nghĩa qua **onboarding wizard trong bot**
- Audience chính: người Việt, deploy bằng AI agent (Devin/Codex/Claude Code…)

## 2. Customer journey

```
User clone repo → đưa cho AI agent: "deploy cái này cho tôi"
   │
   ▼  Agent đọc AGENTS.md (runbook) → hướng dẫn user lấy credentials:
   ├─ @BotFather → TELE_BOT_TOKEN
   ├─ Google Sheets (D3): tạo Sheet trống → Apps Script → dán script → Deploy Web App
   │    → dán URL + secret vào .env  (KHÔNG cần Google Cloud Console)
   ├─ LLM endpoint OpenAI-compatible (OpenRouter/OpenAI/local…)
   └─ (tuỳ chọn) Lark Base app theo docs/setup-lark.md
   │
   ▼  Agent điền .env → pip install → systemd → service chạy
   │
   ▼  User /start → wizard hỏi: nguồn tiền, nhóm chi tiêu,
      hạng mục con (optional), family members → lưu data/config.json
   │
   ▼  Gửi ảnh biên lai → OCR → nút xác nhận → ghi Sheet + ảnh Drive
```

## 3. Kiến trúc

Flat layout (không package lồng — basic, agent dễ đọc):

```
tele-banking/
├── README.md              # VN — giới thiệu, yêu cầu server, quickstart
├── README.en.md           # EN
├── AGENTS.md              # Runbook cho AI agent: cần hỏi user gì, tạo resource gì, verify gì
├── LICENSE                # MIT
├── .env.example           # Mọi biến + comment hướng dẫn lấy
├── requirements.txt
├── main.py                # Entry: load env + config, khởi tạo backend + bot
├── config.py              # Runtime config ở data/config.json (wizard ghi); secrets chỉ ở .env
├── onboarding.py          # Wizard /start lần đầu + /setup + /myid
├── bot.py                 # Handlers: photo→queue→OCR→confirm→save; dynamic keyboards
├── keyboards.py           # Build inline keyboard từ config (categories, accounts)
├── ocr.py                 # OpenAI-compatible vision call + retry + validate (port logic cũ)
├── backends/
│   ├── base.py            # Protocol: append(txn, image_bytes) → row dict; get_recent(n)
│   ├── sheets.py          # Google Sheets: headers tự tạo, tab theo chiều tiền
│   └── lark.py            # Lark Base: record lookup by name (không hardcode recID)
├── imaging.py             # Chain: drive → webdav → catbox → telegraph → local
├── anomaly.py             # Rule-based bất thường (>3x median theo nhóm)
├── deploy/
│   ├── deploy.sh          # Parametrize: DEPLOY_HOST, DEPLOY_USER, SSH_KEY, REMOTE_DIR
│   └── tele-banking.service
├── docs/
│   ├── setup-sheets.md    # Tạo service account, enable Sheets+Drive API, share sheet+folder
│   ├── setup-lark.md      # Schema Lark Base (tên field, loại field)
│   ├── configuration.md   # data/config.json reference + /setup
│   └── agent-prompt.md    # Prompt mẫu user paste cho AI agent
└── .github/workflows/ci.yml   # compile check
```

### 3.1 Onboarding wizard (phần mới nhất)

State machine trong `onboarding.py`, lưu vào `data/config.json`:

1. `/start` lần đầu → "Setup 2 phút" → hỏi tuần tự:
   - **Nguồn tiền** (nhập nhiều, phẩy/xuống dòng): VD `VCB *046, Tiền mặt, MoMo`
   - **Nhóm chi tiêu lớn**: VD `Ăn uống, Gia đình, Kinh doanh`
   - **Hạng mục con** cho từng nhóm (optional, skip được): `Ăn uống → Nhà hàng, Cafe`
   - **Family**: "thêm người dùng chung?" → họ chạy `/myid` lấy ID → admin nhập
2. Xong → tóm tắt → "Gửi ảnh biên lai để bắt đầu"
3. `/setup` mở lại wizard bất cứ lúc nào; `/myid` in Telegram user ID

**Quyền**: user đầu tiên chạy /start sau deploy = admin. `allowed_users` rỗng = chỉ admin. Bot reply lịch sự khi user không whitelist nhắn vào.

**Chưa setup xong mà gửi ảnh** → bot nhắc "chạy /start để setup trước".

### 3.2 Config data model (`data/config.json`)

```json
{
  "admin_id": 123456789,
  "allowed_users": [123456789],
  "bot_name": "Bot Nhà",
  "sources": ["VCB - 046", "Tiền mặt", "MoMo"],
  "categories": {
    "Ăn uống": ["Nhà hàng", "Cafe"],
    "Gia đình": [],
    "Kinh doanh": ["Nguyên liệu"]
  },
  "created_at": "...",
  "version": 1
}
```

`.env` chỉ giữ secrets/endpoints (TELE_BOT_TOKEN, LLM_*, SHEETS_*, LARK_*, WEBDAV_*).

### 3.3 OCR (`ocr.py`)

- Prompt **build động** từ `config.categories` — inject tên nhóm/hạng mục của user, không còn 14 prefix Firefly
- Giữ nguyên tên field JSON output (`loai`, `so_tien`, `ngay_thang`, `nhom_chi_phi`…) — schema đã proven
- Port logic: `_extract_json` chịu SSE stream, `_normalize`, `_validate` + 1 retry fix-call, ảnh trắng → error sớm
- Danh mục OCR trả không khớp config → bỏ trống để user chọn bằng nút

### 3.4 Bot flow (`bot.py` + `keyboards.py`)

Port từ bản cũ (đã ổn): queue ảnh, "Ảnh x/y", OCR-cache theo file_id, ảnh lỗi → gửi lại kèm nút "OCR lại / Bỏ qua" + tóm tắt cuối queue.

Confirm keyboard (động theo config):
```
[Duyệt] [Sửa nguồn tiền] [Phân loại] [Hạng mục] [Bỏ qua]
```

### 3.5 Backends

**SheetsBackend** (primary, D2+D3):
- User tạo 1 Sheet trống → Extensions → Apps Script → dán script repo cung cấp → Deploy as Web App (Execute as *me*, Access *Anyone*) → copy URL + secret vào `.env` (`SHEETS_WEBAPP_URL`, `SHEETS_WEBAPP_SECRET`)
- Script tự tạo headers 15 cột + tab `Tiền chuyển`/`Tiền nhận` theo dòng tiền; bot chỉ POST JSON, script `appendRow`
- Cột "Chứng từ" = URL ảnh (catbox/telegraph/webdav) — hiển thị bằng `=IMAGE(url)` khi user muốn
- Ưu điểm: không GCP project, không service account, không share folder, không xin Google verification

**LarkBackend** (option):
- `.env`: `LARK_APP_ID/SECRET/APP_TOKEN/TABLE_ID` theo docs/setup-lark.md
- "Nguồn tiền" — nếu user có bảng Sổ Quỹ liên kết: config thêm `lark_source_table_id` + `lark_source_name_field`; bot **lookup record theo tên** (không hardcode recID). Không cấu hình → ghi text thường.

**Interface chung**: `append(txn: dict, image_bytes: bytes) -> bool`, `get_recent(n) -> list`, `summarize_recent(rows) -> str`.

### 3.6 Image chain (`imaging.py`)

Thứ tự cấu hình `IMAGE_STORE` (mặc định `drive,catbox,telegraph,local`):

1. **Google Drive**: folder user share cho SA → upload → `anyone-with-link` permission → trả `drive.google.com/uc?id=` URL (Sheets `=IMAGE()` hiển thị được)
2. **WebDAV** (optional env)
3. **Catbox → Telegraph** (free fallback, zero config)
4. **Local** `receipts/` (last resort)

### 3.7 Anomaly

Port `anomaly.py`: cảnh báo khi amount > 3× median cùng nhóm (đọc `get_recent`).

## 4. Docs & deploy

- `AGENTS.md` viết cho agent: "hỏi user X → tạo resource Y → verify Z" — kèm schema Lark, link docs
- `docs/setup-sheets.md`: từng bước Google Cloud Console (service account, enable Sheets API + Drive API, share sheet + folder)
- `deploy/deploy.sh`: rsync qua env `DEPLOY_HOST`…; `tele-banking.service` mẫu
- README ghi rõ **yêu cầu: 1 server/VPS Linux** (hoặc máy chạy Python 3.10+ 24/7)

## 5. Bảo mật

- Không secret trong repo/history; `.env` + `data/` + `*.json` credentials gitignored
- Repo public từ `git init` mới — không mang history cũ
- Whitelist: mặc định chỉ admin; log không in token

## 6. Non-goals (v1)

Docker, CSV/SQLite backend, tests, Firefly III, multi-platform (Zalo/Discord), multi-bot, web UI, i18n đầy đủ (UI bot tiếng Việt).

## 7. Phase sau

P2: Dockerfile+compose, CSV backend (demo zero-account), pytest cơ bản. P3: Firefly III, Channel interface → Zalo OA.
