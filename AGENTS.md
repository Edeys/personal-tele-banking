# AGENTS.md — Tele-Banking (bản open-source)

> **Đọc file này trước khi làm bất cứ gì.** Đây là runbook cho AI agent
> (Claude Code / Codex / Devin / Cursor…). Người dùng cuối thường **không biết
> code** — agent chịu trách nhiệm hỏi đúng thứ, tạo đúng resource, verify rồi
> mới báo xong.
>
> Trạng thái: **v1 chạy được**, 68 test. Thiết kế + quyết định ở
> [`docs/specs/2026-09-28-tele-banking-design.md`](docs/specs/2026-09-28-tele-banking-design.md).

## Sản phẩm

Telegram bot: user gửi ảnh biên lai / màn hình chuyển khoản → OCR bằng LLM
vision → user bấm nút xác nhận → ghi vào **Google Sheets của chính user** kèm
ảnh. Mỗi người tự deploy bản riêng; repo không chứa danh mục/tài khoản của ai.

## Nguyên tắc bắt buộc

1. **Không commit secret.** `.env`, `data/config.json`, `receipts/`,
   `*.private.md` đã gitignore. Không bao giờ hardcode token/key/mật khẩu vào
   code, docs hay test. Không in token ra log.
2. **Không hardcode dữ liệu của một người.** Nguồn tiền, nhóm chi tiêu, hạng
   mục con, thành viên — tất cả lấy từ `config.py` (`data/config.json`), do
   wizard `/start` sinh ra. Nếu thấy mình đang viết một danh sách cứng như
   `["VCB", "MB", "TCB"]` trong code → dừng lại, đó là bug.
3. **Nguồn sự thật là `config.py` + `data/config.json`.** Đừng thêm bảng map
   song song trong module khác.
4. **Người dùng không đọc được code, không đọc được log.** Mọi hướng dẫn phải
   ở dạng "bấm vào đâu, dán gì, copy gì". Lỗi phải trả về **việc cần làm**
   bằng tiếng Việt chứ không phải stacktrace. Nếu một bước bắt user tự suy
   luận kỹ thuật thì bước đó đang sai.

## Việc agent cần lấy từ user khi setup

| # | Thứ cần | Cách lấy | Độ khó |
|---|---|---|---|
| 1 | `TELE_BOT_TOKEN` | Chat `@BotFather` → `/newbot` → copy token | Dễ |
| 2 | `LLM_BASE_URL` + `LLM_API_KEY` + model | Hỏi user đang dùng OpenRouter / OpenAI / Groq / LLM local. Phải là endpoint OpenAI-compatible, model OCR phải **đọc được ảnh** | Dễ |
| 3 | `SHEETS_WEBAPP_URL` + `SHEETS_WEBAPP_SECRET` | Theo `docs/setup-sheets.md` — copy-paste Apps Script, **không** cần Google Cloud Console | Trung bình |
| 4 | (tuỳ chọn) Lark Base | Theo `docs/setup-lark.md` | Khó — chỉ khi user yêu cầu |

Sau khi có 1–3: điền `.env` → `pip install -r requirements.txt` → chạy
`python main.py`.

**Bot tự kiểm tra trước khi nhận việc**: `main.py` gọi thử backend và thử đọc
1 ảnh bằng model OCR. Sai URL / sai secret / sai model → bot **từ chối chạy**
và in đúng việc phải sửa. Không cần bạn tự đoán.

Xong bước đó mới bảo user mở Telegram gõ `/start` để hoàn tất wizard (nguồn
tiền, nhóm chi tiêu, hạng mục con, thành viên).

## Lệnh trong bot

| Lệnh | Việc |
|---|---|
| `/start` | Chạy wizard cấu hình (lần đầu) hoặc chào |
| `/setup` | Chạy lại wizard từ đầu để sửa cấu hình |
| `/config` | In cấu hình hiện tại (chỉ đọc) |
| `/test` | Kiểm tra lại nối Sổ + model đọc ảnh, báo ✅/❌ ngay trong chat |
| `/invite 123` | Admin thêm thành viên theo ID (không cần chạy lại wizard) |
| `/myid` | In ID Telegram (để đưa cho admin mời) |

## Kiến trúc (theo spec)

```
main.py            entrypoint: load .env + Config, preflight backend/OCR, chạy polling
config.py          runtime config (data/config.json) — wizard ghi, mọi module đọc
onboarding.py      wizard /start lần đầu + summary_text/config_text
keyboards.py       dựng inline keyboard TỪ config (không hardcode)
bot.py             handlers: photo → queue → OCR → confirm → save; /test /config /invite
ocr.py             LLM vision + _extract_json/_normalize/_validate + ping() (prompt động theo config)
imaging.py         chuỗi lưu ảnh: catbox → telegraph → webdav → local
anomaly.py         rule-based cảnh báo bất thường theo nhóm cấu hình
backends/base.py   Protocol: append → str|None / get_recent / summarize_recent / healthcheck
backends/sheets.py Google Sheets qua Apps Script Web App (HTTP, không gspread)
backends/lark.py   Lark Base (tuỳ chọn), lookup record theo TÊN, không recID
```

### Hợp đồng backend — đọc kỹ trước khi sửa

- `append(txn, image_bytes)` trả **`None` nếu ghi được, ngược lại trả lý do
  bằng tiếng Việt.** `bot.py` dựa vào đó để **giữ giao dịch lại** và cho bấm
  thử lại. Đừng đổi về `bool` — sẽ làm người dùng mất biên lai.
- `healthcheck()` trả `str | None`, dùng cho preflight lúc khởi động.
- `append` **không tự retry**: nếu Google đã nhận request mà mất kết nối trước
  khi trả lời, retry sẽ tạo dòng trùng trong sổ. Thao tác **đọc** thì có retry
  (idempotent, `READ_ATTEMPTS`).

## Verify trước khi báo xong

1. `python -m pytest -q` — tất cả pass
2. `python -m py_compile main.py config.py onboarding.py keyboards.py bot.py ocr.py imaging.py anomaly.py backends/*.py`
3. `python main.py` — phải thấy `Kiểm tra backend: OK` và
   `Kiểm tra model đọc ảnh: OK`. Nếu bot từ chối chạy thì **lỗi trong .env**,
   sửa theo đúng dòng nó in ra.
4. Chạy thật: `/start` → wizard xong → gõ `/test` (2 dòng ✅) → gửi 1 ảnh biên
   lai → bấm Duyệt → mở Google Sheet kiểm tra có đúng 1 dòng mới + link ảnh
   mở được.
5. Kiểm tra không có secret nào trong diff: `git diff` rồi tìm token/key/URL.

## Chạy 24/7 (tuỳ chọn, khi user có VPS)

`README.md` mục "Chạy liên tục trên VPS". Script `deploy/deploy.sh` parameterise
qua `DEPLOY_HOST`/`REMOTE_DIR`/`SSH_KEY`; `deploy/tele-banking.service` là unit
mẫu cho systemd. Không có host nào hardcode trong repo.

## Tài liệu

- Thiết kế + quyết định: `docs/specs/2026-09-28-tele-banking-design.md`
- Setup Google Sheets (Apps Script): `docs/setup-sheets.md`
- Setup Lark Base: `docs/setup-lark.md`
- Tham chiếu `data/config.json` + `/setup`: `docs/configuration.md`
- Prompt mẫu để user dán cho agent: `docs/agent-prompt.md`
