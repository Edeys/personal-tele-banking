# Prompt mẫu — dán cho AI agent

Người dùng không biết code: copy toàn bộ khung dưới đây, dán vào Claude Code /
Codex / Devin / Cursor đang mở trong thư mục repo, rồi trả lời các câu agent hỏi.

---

Tôi muốn cài đặt bot Tele-Banking này để tự động ghi ảnh biên lai vào Google
Sheet của tôi. Tôi **không biết code**, nên bạn hãy làm thay tôi và hướng dẫn
tôi theo kiểu "bấm vào đâu, dán gì".

Hãy đọc `AGENTS.md` trước. Sau đó:

1. Hỏi tôi lần lượt 3 thứ và hướng dẫn tôi lấy từng thứ:
   - Token Telegram bot (tôi chat `@BotFather`)
   - Endpoint LLM + API key (tôi đang dùng ______)
   - Web App URL + secret của Google Sheets (hướng dẫn tôi theo
     `docs/setup-sheets.md`, copy-paste Apps Script)
2. Tạo file `.env` từ `.env.example` và điền những gì tôi cung cấp.
3. Cài dependencies và chạy thử `python main.py`. Phải thấy
   `Kiểm tra backend: OK` và `Kiểm tra model đọc ảnh: OK` — nếu bot từ chối
   chạy thì làm theo đúng dòng lỗi nó in ra, đừng đoán.
4. Xác nhận bot đã chạy, rồi nhắc tôi mở Telegram gõ `/start` để cấu hình
   danh mục chi tiêu.
5. Sau khi tôi gõ `/start` xong, nhắc tôi gõ `/test` (phải ra 2 dòng ✅), rồi
   gửi thử 1 ảnh biên lai và kiểm tra Google Sheet có đúng 1 dòng mới.

Lưu ý cho bạn:
- **Không** in token/API key ra màn hình hay vào file log.
- **Không** tự bịa danh mục chi tiêu của tôi — để tôi tự khai trong `/start`.
- Nếu có bước nào tôi phải tự bấm trên trình duyệt, hãy ghi rõ từng bước và
  dừng lại chờ tôi làm xong.

---

## Gợi ý trả lời khi agent hỏi

- **LLM**: nếu chưa có tài khoản, dễ nhất là OpenRouter (nạp 5–10 USD, dùng
  được nhiều model). Cần model **đọc được ảnh**, ví dụ
  `qwen/qwen2.5-vl-72b-instruct`.
- **Nguồn tiền**: liệt kê tài khoản thật của bạn, ví dụ
  `VCB - 046, MB - 259, Tiền mặt, MoMo`.
- **Nhóm chi tiêu**: những nhóm bạn hay dùng, ví dụ
  `Ăn uống, Gia đình, Kinh doanh, Lương`.
