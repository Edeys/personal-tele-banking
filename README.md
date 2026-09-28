# Tele-Banking

Bot Telegram: gửi **ảnh biên lai / màn hình chuyển khoản** → bot đọc bằng LLM
vision → bạn bấm **Duyệt** → bot ghi vào **Google Sheet của chính bạn**, kèm ảnh.

- **Không cần biết code.** Đưa repo này cho một AI agent (Claude Code, Codex,
  Devin, Cursor…) và dán prompt ở [`docs/agent-prompt.md`](docs/agent-prompt.md).
- **Không cần Google Cloud Console.** Chỉ copy-paste một đoạn Apps Script —
  xem [`docs/setup-sheets.md`](docs/setup-sheets.md).
- **Dữ liệu là của bạn.** Ghi thẳng vào Sheet của bạn; không qua server trung gian.
- **Không hardcode dữ liệu của ai.** Nguồn tiền, nhóm chi tiêu, hạng mục con,
  thành viên — bạn tự khai trong bot bằng `/start`.

> Trạng thái: v1, 68 test. Lark Base là backend tuỳ chọn.

## Bot làm được gì

- Đọc ảnh chuyển khoản ngân hàng: ngày giờ, ngân hàng, người nhận, số tiền, mã GD, nội dung
- Đọc ảnh đơn Shopee/TikTok nhiều sản phẩm
- Tự phân loại vào nhóm/hạng mục bạn đã khai; bạn sửa được bằng nút bấm
- Gửi nhiều ảnh một lúc (xếp hàng đợi), ảnh lỗi có nút **OCR lại**
- Cảnh báo giao dịch bất thường (số tiền gấp >3× trung vị cùng nhóm)
- Hỏi đáp về chi tiêu dựa trên dữ liệu gần đây trong sổ

## Cần gì

| Thứ | Ghi chú |
|---|---|
| Python 3.10+ | máy chạy 24/7: VPS Linux, hoặc PC bật thường xuyên |
| Telegram bot token | chat `@BotFather` → `/newbot` |
| Endpoint LLM đọc được ảnh | OpenRouter / OpenAI / Groq / Ollama, vLLM… (OpenAI-compatible) |
| 1 Google Sheet | bạn tự tạo, xem `docs/setup-sheets.md` |

## Cách 1 — để AI agent làm (khuyến nghị)

Mở repo này bằng agent của bạn và dán:

> Đọc `AGENTS.md`, rồi giúp tôi cài đặt bot này. Tôi chưa biết code, hãy hỏi tôi
> từng thứ cần lấy và hướng dẫn tôi bấm vào đâu.

Agent sẽ hỏi bạn 3 thứ (token Telegram, LLM key, Web App URL) rồi tự cài đặt.

Bot **tự kiểm tra trước khi nhận việc** — thiếu/sai bất kỳ thứ gì trong `.env`
là nó từ chối chạy và in đúng dòng phải sửa, thay vì để bạn gửi ảnh xong mới
phát hiện lỗi.

## Cách 2 — tự làm

```bash
git clone https://github.com/Edeys/personal-tele-banking.git && cd personal-tele-banking
python -m venv .venv
# Windows:   .venv\Scripts\activate
# macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env      # Windows: copy .env.example .env
# rồi điền 5 dòng bắt buộc (xem dưới)
python main.py
```

Thấy 2 dòng này là ổn:

```
Kiểm tra backend: OK
Kiểm tra model đọc ảnh: OK
```

Điền `.env` (xem chú thích ngay trong file):

```env
TELE_BOT_TOKEN=...        # @BotFather
LLM_BASE_URL=...
LLM_API_KEY=...
LLM_OCR_MODEL=...         # model đọc được ảnh
SHEETS_WEBAPP_URL=...     # docs/setup-sheets.md
SHEETS_WEBAPP_SECRET=...
```

Sau đó mở Telegram, chat với bot và gõ `/start` → wizard hỏi 5 bước.
Xong wizard gõ `/test` → phải thấy 2 dòng ✅.

## Lệnh trong bot

| Lệnh | Việc |
|---|---|
| `/start` | Chạy wizard cấu hình (lần đầu) hoặc chào |
| `/setup` | Chạy lại wizard từ đầu để sửa cấu hình |
| `/config` | Xem cấu hình hiện tại (chỉ đọc) |
| `/test` | Kiểm tra nối Sổ + model đọc ảnh, báo ✅/❌ ngay trong chat |
| `/invite 123` | Thêm thành viên theo ID, không phải chạy lại wizard |
| `/myid` | In ID Telegram của bạn (để đưa cho admin mời) |

Gửi tin nhắn văn bản bất kỳ → hỏi trợ lý về chi tiêu. Đang ở màn xác nhận thì
gõ `lưu` hoặc `bỏ qua` cũng được.

Nếu bấm **Duyệt** mà báo lỗi, bot **giữ lại giao dịch** và nêu đúng lý do
(sai secret, sai URL, hết tiền LLM…) — bạn bấm **Duyệt** lần nữa để thử lại,
không mất ảnh.

## Chạy liên tục trên VPS

Bot phải chạy 24/7 thì mới nhận được ảnh. Trên máy cá nhân thì mở terminal
bật `python main.py` và để đó là được.

Trên VPS Linux có sẵn `deploy/`:

```bash
# máy bạn đẩy code lên server rồi cài systemd
DEPLOY_HOST=root@1.2.3.4 REMOTE_DIR=/opt/tele-banking ./deploy/deploy.sh
```

`deploy/tele-banking.service` là unit mẫu — copy vào
`/etc/systemd/system/`, sửa `WorkingDirectory` nếu bạn đặt chỗ khác, rồi
`systemctl enable --now tele-banking`. Xem log: `journalctl -u tele-banking -f`.

`.env` phải nằm trong thư mục đó (script sẽ cảnh báo nếu thiếu).

## Cấu hình

- Secrets + endpoint: `.env` (copy từ `.env.example`)
- Danh mục / nguồn tiền / thành viên: `data/config.json`, do wizard sinh ra —
  **đừng sửa tay**, hãy dùng `/setup`
- Chi tiết từng biến: [`docs/configuration.md`](docs/configuration.md)

## Tài liệu

- Runbook cho AI agent: [`AGENTS.md`](AGENTS.md)
- Setup Google Sheets (Apps Script): [`docs/setup-sheets.md`](docs/setup-sheets.md)
- Setup Lark Base (tuỳ chọn): [`docs/setup-lark.md`](docs/setup-lark.md)
- Prompt mẫu cho agent: [`docs/agent-prompt.md`](docs/agent-prompt.md)
- Thiết kế + quyết định: [`docs/specs/2026-09-28-tele-banking-design.md`](docs/specs/2026-09-28-tele-banking-design.md)

## Giấy phép

MIT — xem [`LICENSE`](LICENSE).
