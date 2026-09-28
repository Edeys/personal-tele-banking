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

> Trạng thái: v1, đang phát triển. Lark Base là backend tuỳ chọn.

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

## Cách 2 — tự làm

```bash
git clone <repo> && cd tele-banking
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env      # rồi điền 5 dòng bắt buộc (xem dưới)
python main.py
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

## Lệnh trong bot

| Lệnh | Việc |
|---|---|
| `/start` | Chạy wizard cấu hình (lần đầu) hoặc chào |
| `/setup` | Mở lại wizard để sửa cấu hình |
| `/myid` | In ID Telegram của bạn (để thêm thành viên) |

Gửi tin nhắn văn bản bất kỳ → hỏi trợ lý về chi tiêu. Đang ở màn xác nhận thì
gõ `lưu` hoặc `bỏ qua` cũng được.

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
