"""Handlers Telegram: ảnh → queue → OCR → xác nhận → lưu backend.

Luồng và các bài học giữ từ bản cũ (queue nhiều ảnh, cache OCR theo vị trí,
ảnh lỗi gửi lại kèm nút OCR lại, keyboard động theo config), nhưng toàn bộ
danh mục/nguồn tiền lấy từ `config` — không còn hằng số của một người.
"""

from __future__ import annotations

import asyncio
import logging
import time

from openai import OpenAI
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    PicklePersistence,
    filters,
)

import keyboards as kb
from anomaly import detect_anomaly
from onboarding import Wizard, config_text, summary_text

logger = logging.getLogger(__name__)

MAX_MSG = 4000
SAVE_WORDS = {"lưu", "luu", "xác nhận", "xac nhan", "ok", "okay", "yes", "save"}
DROP_WORDS = {"bỏ", "bo", "hủy", "huy", "cancel", "skip", "bỏ qua", "bo qua", "không lưu"}

CHAT_SYSTEM = """Bạn là trợ lý tài chính cá nhân người Việt.
Trả lời ngắn gọn, thân thiện, dưới 1500 ký tự. Dùng số liệu có trong dữ liệu
được cung cấp. Nếu câu hỏi không liên quan tài chính, trả lời bình thường."""


def fmt_money(value) -> str:
    try:
        return f"{int(value):,}".replace(",", ".") + "₫"
    except (TypeError, ValueError):
        return "?"


def format_txn(txn: dict, config) -> str:
    loai = txn.get("loai", "banking")
    lines = ["[Shoppe/TikTok]" if loai == "shoppe" else "[Banking]"]
    stamp = " ".join(x for x in [txn.get("ngay_thang"), txn.get("thoi_gian")] if x)
    lines.append(f"Ngày: {stamp or '?'}")

    if loai == "shoppe":
        orders = txn.get("don_hang") or []
        for order in orders:
            lines.append(
                f"• {order.get('ten_shop') or '?'} | {order.get('ten_san_pham') or '?'}"
                f" x{order.get('so_luong') or '?'} — {fmt_money(order.get('so_tien'))}"
            )
    else:
        bank_in = txn.get("ngan_hang_gui") or "?"
        bank_out = txn.get("ngan_hang_nhan") or "?"
        lines.append(f"Ngân hàng: {bank_in} → {bank_out}")
        lines.append(f"Người nhận: {txn.get('nguoi_nhan') or '?'} ({txn.get('stk_nhan') or '?'})")
        if txn.get("ma_giao_dich"):
            lines.append(f"Mã GD: {txn['ma_giao_dich']}")

    lines.append(f"Số tiền: {fmt_money(txn.get('so_tien'))}")
    if txn.get("noi_dung"):
        lines.append(f"Nội dung: {str(txn['noi_dung'])[:150]}")
    if txn.get("ghi_chu"):
        lines.append(f"Chi tiết: {str(txn['ghi_chu'])[:150]}")
    lines.append(f"Nhóm: {txn.get('danh_muc_lon') or '— chưa chọn'}")
    lines.append(f"Hạng mục: {txn.get('nhom_chi_phi') or '— chưa chọn'}")

    text = "\n".join(lines)
    return text if len(text) <= MAX_MSG else text[:MAX_MSG] + "…"


class BotHandler:
    def __init__(self, token: str, ocr, backend, config, llm_config: dict, name: str = "bot"):
        safe = "".join(c for c in (name or "bot") if c.isalnum() or c in "-_") or "bot"
        self.app = (
            Application.builder()
            .token(token)
            .persistence(PicklePersistence(filepath=f"pickle_{safe}.pkl"))
            .build()
        )
        self.ocr = ocr
        self.backend = backend
        self.config = config
        self.chat_client = OpenAI(
            base_url=llm_config["base_url"],
            api_key=llm_config["api_key"],
        )
        self.chat_model = llm_config.get("chat_model", "gpt-4o-mini")
        self.name = name
        self._register()

    def _register(self) -> None:
        self.app.add_handler(CommandHandler("start", self.cmd_start))
        self.app.add_handler(CommandHandler("setup", self.cmd_setup))
        self.app.add_handler(CommandHandler("myid", self.cmd_myid))
        self.app.add_handler(CommandHandler("id", self.cmd_myid))
        self.app.add_handler(CommandHandler("config", self.cmd_config))
        self.app.add_handler(CommandHandler("test", self.cmd_test))
        self.app.add_handler(CommandHandler("invite", self.cmd_invite))
        self.app.add_handler(MessageHandler(filters.PHOTO, self.handle_photo))
        self.app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_text))
        self.app.add_handler(CallbackQueryHandler(self.handle_callback))

    # ── tiện ích ────────────────────────────────────────────────

    def _allowed(self, update: Update) -> bool:
        user = update.effective_user
        return bool(user and self.config.is_allowed(user.id))

    async def _deny(self, update: Update) -> None:
        user = update.effective_user
        await update.effective_message.reply_text(
            "Bot này là bản riêng của chủ sở hữu.\n"
            f"ID Telegram của bạn: `{user.id}` — gửi cho chủ bot nếu muốn được thêm."
        )

    def _wizard(self, ctx: ContextTypes.DEFAULT_TYPE) -> Wizard:
        wizard = ctx.user_data.get("_wizard_obj")
        if wizard is None or not wizard.active:
            wizard = Wizard(self.config)
            ctx.user_data["_wizard_obj"] = wizard
        return wizard

    async def _run_ocr(self, image_bytes: bytes) -> dict:
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self.ocr.extract, image_bytes)

    # ── lệnh ────────────────────────────────────────────────────

    async def cmd_start(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
        if not self._allowed(update):
            if not self.config.data.get("admin_id"):
                self.config.claim_admin(update.effective_user.id)
            else:
                await self._deny(update)
                return

        if not self.config.is_ready():
            wizard = self._wizard(ctx)
            await update.message.reply_text(
                "Chào bạn! Cùng cấu hình bot trong 2 phút.", reply_markup=None
            )
            await update.message.reply_text(wizard.open(), parse_mode="Markdown")
            return

        await update.message.reply_text(
            f"*{self.config.bot_name}* đã sẵn sàng.\n"
            "- Gửi **ảnh** biên lai / màn hình chuyển khoản → bot đọc và hỏi xác nhận\n"
            "- Gửi **tin nhắn** → hỏi về chi tiêu\n"
            "- `/setup` → sửa cấu hình\n"
            "- `/myid` → xem ID Telegram\n",
            parse_mode="Markdown",
        )

    async def cmd_setup(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
        if not self._allowed(update):
            await self._deny(update)
            return
        wizard = self._wizard(ctx)
        await update.message.reply_text(wizard.open(), parse_mode="Markdown")

    async def cmd_myid(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
        await update.message.reply_text(f"ID Telegram của bạn: `{update.effective_user.id}`", parse_mode="Markdown")

    async def cmd_config(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
        if not self._allowed(update):
            if not self.config.data.get("admin_id"):
                self.config.claim_admin(update.effective_user.id)
            else:
                await self._deny(update)
                return
        if not self.config.is_ready():
            await update.message.reply_text("Chưa cấu hình. Gõ /start để làm 5 bước cấu hình.")
            return
        await update.message.reply_text(config_text(self.config) + "\nGõ /setup để sửa.")

    async def cmd_test(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
        """Chạy được ngay sau khi bot lên — thay cho việc đọc log."""
        if not self._allowed(update):
            if not self.config.data.get("admin_id"):
                self.config.claim_admin(update.effective_user.id)
            else:
                await self._deny(update)
                return
        await update.message.reply_text("Đang kiểm tra kết nối, chờ vài giây…")
        loop = asyncio.get_running_loop()
        # Cả hai đều là HTTP — bỏ vào executor để không chặn bot
        # xử lý tin nhắn của người khác trong lúc chờ Google trả lời.
        backend_err = await loop.run_in_executor(None, self.backend.healthcheck)
        ocr_err = await loop.run_in_executor(None, self.ocr.ping)

        lines = [
            "✅ Sổ (backend): OK" if not backend_err else f"❌ Sổ (backend): {backend_err}",
            "✅ Model đọc ảnh: OK" if not ocr_err else f"❌ Model đọc ảnh: {ocr_err}",
        ]
        if not backend_err and not ocr_err:
            lines += ["", "Tất cả ổn — gửi thử 1 ảnh biên lai để bắt đầu."]
        await update.message.reply_text("\n".join(lines))

    async def cmd_invite(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
        if not self.config.is_admin(update.effective_user.id):
            await update.effective_message.reply_text("Chỉ admin mới được mời người khác.")
            return
        parts = (update.message.text or "").split(maxsplit=1)
        arg = parts[1].strip() if len(parts) > 1 else ""
        if not arg:
            await update.message.reply_text(
                "Cách dùng: /invite 123456789\n"
                "(Người kia gõ /myid để lấy số ID, rồi gửi cho bạn.)"
            )
            return

        added, already, invalid = [], [], []
        # Tách theo cả dấu phẩy lẫn khoảng trắng: "111, 222" và "111 222"
        # đều phải hiểu là 2 người. Dùng parse_list của wizard sẽ dính 2 ID
        # lại thành một số sai.
        for item in arg.replace(",", " ").split():
            digits = "".join(c for c in item if c.isdigit())
            if not digits:
                invalid.append(item)
                continue
            user_id = int(digits)
            if self.config.add_user(user_id):
                added.append(str(user_id))
            else:
                already.append(str(user_id))

        lines = []
        if added:
            lines.append("✅ Đã thêm: " + ", ".join(added))
        if already:
            lines.append("Đã có sẵn từ trước: " + ", ".join(already))
        if invalid:
            lines.append("Bỏ qua (không phải số ID): " + ", ".join(invalid))
        if not lines:
            lines.append("Không nhận ra ID nào. Cách dùng: /invite 123456789")
        await update.message.reply_text("\n".join(lines))

    # ── ảnh ─────────────────────────────────────────────────────

    async def handle_photo(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
        if not self._allowed(update):
            await self._deny(update)
            return
        if not self.config.is_ready():
            await update.message.reply_text("Chạy /start để cấu hình trước đã nhé.")
            return
        try:
            photo = await update.message.photo[-1].get_file()
            image_bytes = bytes(await photo.download_as_bytearray())
            queue = ctx.user_data.setdefault("queue", [])
            queue.append({"image": image_bytes, "caption": (update.message.caption or "").strip()})
            total = len(queue)
            if ctx.user_data.get("processing"):
                await update.message.reply_text(f"Đã xếp hàng ảnh #{total}, đang xử lý dần…")
                return
            await self._drain(ctx, update.message.chat_id)
        except Exception as e:
            logger.exception("Photo error")
            await update.message.reply_text(f"Lỗi xử lý ảnh: {e}")

    async def _drain(self, ctx: ContextTypes.DEFAULT_TYPE, chat_id: int) -> None:
        if ctx.user_data.get("processing"):
            return
        ctx.user_data["processing"] = True
        try:
            while ctx.user_data.get("queue"):
                entry = ctx.user_data["queue"].pop(0)
                image_bytes = entry["image"]
                caption = entry.get("caption", "")
                status = await self.app.bot.send_message(chat_id=chat_id, text="Đang đọc ảnh…")
                txn = await self._run_ocr(image_bytes)

                if txn.get("error"):
                    await status.edit_text(f"Không đọc được ảnh: {txn['error']}")
                    ctx.user_data["last_failed"] = {"image": image_bytes, "caption": caption}
                    ctx.user_data["failed_count"] = ctx.user_data.get("failed_count", 0) + 1
                    await self.app.bot.send_photo(
                        chat_id=chat_id,
                        photo=image_bytes,
                        caption="Ảnh này lỗi. Bấm OCR lại, hoặc gửi ảnh rõ hơn.",
                        reply_markup=kb.retry_kb(),
                    )
                    continue

                if caption:
                    txn["ghi_chu"] = txn.get("ghi_chu") or caption
                if txn.get("loai") == "shoppe":
                    self._sum_shoppe(txn)

                ctx.user_data["pending"] = {"txn": txn, "image": image_bytes}
                await status.edit_text(
                    format_txn(txn, self.config), reply_markup=kb.confirm_kb()
                )

            failed = ctx.user_data.pop("failed_count", 0)
            if failed:
                await self.app.bot.send_message(
                    chat_id=chat_id,
                    text=f"Xong hàng đợi — {failed} ảnh lỗi. Bấm OCR lại hoặc gửi lại ảnh đó.",
                )
        finally:
            ctx.user_data["processing"] = False

    @staticmethod
    def _sum_shoppe(txn: dict) -> None:
        orders = txn.get("don_hang") or []
        total = sum(int(o.get("so_tien") or 0) for o in orders)
        if total:
            txn["so_tien"] = total
        if not txn.get("ngan_hang_nhan"):
            txn["ngan_hang_nhan"] = "Shoppe"
        if not txn.get("noi_dung"):
            shop = next((o.get("ten_shop") for o in orders if o.get("ten_shop")), "")
            items = ", ".join(
                f"{o.get('ten_san_pham') or '?'} x{o.get('so_luong') or 1}" for o in orders
            )
            txn["noi_dung"] = (f"Shop {shop}: " if shop else "") + items

    # ── callback ────────────────────────────────────────────────

    async def handle_callback(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
        query = update.callback_query
        try:
            await query.answer()
        except Exception:
            pass
        if not self._allowed(update):
            await query.edit_message_text("Bạn không có quyền dùng bot này.")
            return

        data = query.data or ""
        pending = ctx.user_data.get("pending")

        if data in ("retry_ocr", "skip_ocr"):
            if data == "skip_ocr":
                ctx.user_data.pop("last_failed", None)
                await query.edit_message_text("Đã bỏ qua ảnh lỗi.")
                return
            failed = ctx.user_data.pop("last_failed", None)
            if not failed:
                await query.edit_message_text("Ảnh đã hết hạn, gửi lại ảnh nhé.")
                return
            ctx.user_data.setdefault("queue", []).insert(0, failed)
            await query.edit_message_text("Đang đọc lại…")
            await self._drain(ctx, query.message.chat_id)
            return

        if not pending:
            if data == "noop":
                return
            await query.edit_message_text("Phiên đã hết, gửi lại ảnh nhé.")
            return

        txn = pending["txn"]

        if data == "confirm":
            err = await self._save(txn, pending["image"])
            if err:
                # KHÔNG pop pending: giao dịch + ảnh phải sống sót để bấm thử
                # lại được, và người dùng phải biết đúng chỗ cần sửa.
                await query.edit_message_text(
                    "❌ Chưa ghi vào sổ được.\n\n"
                    f"Lý do: {err}\n\n"
                    "Giao dịch vẫn còn ở đây — bấm Duyệt để thử lại, "
                    "hoặc Bỏ qua nếu không cần lưu.",
                    reply_markup=kb.confirm_kb(),
                )
                return
            ctx.user_data.pop("pending", None)
            await query.edit_message_text("✅ Đã ghi vào sổ.")
            await self._drain(ctx, query.message.chat_id)
            return

        if data == "cancel":
            ctx.user_data.pop("pending", None)
            await query.edit_message_text("Đã bỏ qua giao dịch này.")
            await self._drain(ctx, query.message.chat_id)
            return

        if data == "back":
            await query.edit_message_text(format_txn(txn, self.config), reply_markup=kb.confirm_kb())
            return

        if data == "src":
            await query.edit_message_text(
                "Chọn nguồn tiền:", reply_markup=kb.source_kb(self.config.sources)
            )
            return

        if data.startswith("src:"):
            try:
                index = int(data.split(":", 1)[1])
                txn["source_name"] = self.config.sources[index]
            except (ValueError, IndexError):
                pass
            await query.edit_message_text(format_txn(txn, self.config), reply_markup=kb.confirm_kb())
            return

        if data == "grp":
            await query.edit_message_text(
                "Chọn nhóm chi tiêu:", reply_markup=kb.group_kb(self.config.group_names())
            )
            return

        if data.startswith("grp:"):
            try:
                group = self.config.group_names()[int(data.split(":", 1)[1])]
            except (ValueError, IndexError):
                await query.edit_message_text("Nhóm không hợp lệ.")
                return
            txn["danh_muc_lon"] = group
            subs = self.config.sub_categories(group)
            if subs:
                idx = self.config.group_names().index(group)
                await query.edit_message_text(
                    f"Nhóm: {group}\nChọn hạng mục:",
                    reply_markup=kb.sub_kb(idx, subs),
                )
            else:
                txn["nhom_chi_phi"] = ""
                await query.edit_message_text(format_txn(txn, self.config), reply_markup=kb.confirm_kb())
            return

        if data == "sub":
            group = txn.get("danh_muc_lon")
            if not group or group not in self.config.categories:
                await query.edit_message_text(
                    "Chọn nhóm chi tiêu trước:", reply_markup=kb.group_kb(self.config.group_names())
                )
                return
            idx = self.config.group_names().index(group)
            await query.edit_message_text(
                f"Nhóm: {group}\nChọn hạng mục:",
                reply_markup=kb.sub_kb(idx, self.config.sub_categories(group)),
            )
            return

        if data.startswith("sub:"):
            payload = data.split(":")
            if payload[1] == "none":
                txn["nhom_chi_phi"] = ""
            else:
                try:
                    group = self.config.group_names()[int(payload[1])]
                    txn["nhom_chi_phi"] = self.config.sub_categories(group)[int(payload[2])]
                    txn["danh_muc_lon"] = group
                except (ValueError, IndexError):
                    pass
            await query.edit_message_text(format_txn(txn, self.config), reply_markup=kb.confirm_kb())
            return

        if data == "noop":
            return

        await query.edit_message_text(format_txn(txn, self.config), reply_markup=kb.confirm_kb())

    # ── text ────────────────────────────────────────────────────

    async def handle_text(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
        if not self._allowed(update):
            if not self.config.data.get("admin_id"):
                self.config.claim_admin(update.effective_user.id)
            else:
                await self._deny(update)
                return

        text = (update.message.text or "").strip()
        if not text:
            return

        wizard = self._wizard(ctx)
        if wizard.active:
            done, reply = wizard.feed(text)
            if done:
                await update.message.reply_text(reply, parse_mode="Markdown")
                self.ocr.refresh_prompt()
            else:
                await update.message.reply_text(reply, parse_mode="Markdown")
            return

        if not self.config.is_ready():
            await update.message.reply_text("Chạy /start để cấu hình trước đã nhé.")
            return

        pending = ctx.user_data.get("pending")
        low = text.lower()
        if pending and low in SAVE_WORDS:
            err = await self._save(pending["txn"], pending["image"])
            if err:
                await update.message.reply_text(
                    f"❌ Chưa ghi vào sổ được.\nLý do: {err}\n\n"
                    "Giao dịch vẫn còn — gửi `lưu` để thử lại, hoặc `bỏ qua`."
                )
                return
            ctx.user_data.pop("pending", None)
            await update.message.reply_text("✅ Đã ghi vào sổ.")
            await self._drain(ctx, update.message.chat_id)
            return
        if pending and low in DROP_WORDS:
            ctx.user_data.pop("pending", None)
            await update.message.reply_text("Đã bỏ qua giao dịch này.")
            await self._drain(ctx, update.message.chat_id)
            return

        await self._chat(update, ctx, text)

    async def _chat(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE, text: str) -> None:
        thinking = await update.message.reply_text("Đang xem…")
        try:
            history = ctx.user_data.get("chat") or [{"role": "system", "content": CHAT_SYSTEM}]
            if len(history) == 1:
                rows = self.backend.get_recent(limit=10)
                if rows:
                    text = f"[Dữ liệu gần đây]\n{self.backend.summarize_recent(rows)}\n\n{text}"
            history.append({"role": "user", "content": text})
            resp = self.chat_client.chat.completions.create(
                model=self.chat_model, messages=history, temperature=0.6, max_tokens=1500
            )
            reply = resp.choices[0].message.content or "…"
            history.append({"role": "assistant", "content": reply})
            ctx.user_data["chat"] = [history[0], *history[-20:]]
            await thinking.edit_text(reply[:MAX_MSG])
        except Exception as e:
            logger.exception("Chat error")
            await thinking.edit_text(f"Lỗi trả lời: {e}")

    # ── lưu ─────────────────────────────────────────────────────

    async def _save(self, txn: dict, image_bytes: bytes | None) -> str | None:
        """Trả `None` nếu đã ghi vào sổ, ngược lại trả LÝ DO bằng tiếng Việt."""
        try:
            rows = self.backend.get_recent(limit=30)
            is_anomaly, reason = detect_anomaly(txn, rows)
            if is_anomaly:
                logger.info("Bất thường: %s", reason)
        except Exception as e:
            logger.debug("Anomaly check skipped: %s", e)

        loop = asyncio.get_running_loop()
        err = await loop.run_in_executor(None, self.backend.append, txn, image_bytes)
        if err:
            logger.error("Ghi thất bại: %s | %s", str(txn.get("noi_dung"))[:60], err)
        return err
