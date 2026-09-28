"""Entrypoint: load .env + Config, kiểm tra nối backend, rồi chạy polling."""

from __future__ import annotations

import asyncio
import logging
import os
import time

from dotenv import load_dotenv

import imaging
from bot import BotHandler
from config import Config
from ocr import OCRExtractor

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

PREFLIGHT_ATTEMPTS = 3


def _llm_config() -> dict:
    base_url = os.getenv("LLM_BASE_URL", "").strip()
    api_key = os.getenv("LLM_API_KEY", "").strip()
    if not base_url or not api_key:
        raise RuntimeError("Thiếu LLM_BASE_URL / LLM_API_KEY trong .env")
    return {
        "base_url": base_url,
        "api_key": api_key,
        "ocr_model": os.getenv("LLM_OCR_MODEL", "OCR"),
        "chat_model": os.getenv("LLM_CHAT_MODEL", "gpt-4o-mini"),
    }


def _backend(config):
    url = os.getenv("SHEETS_WEBAPP_URL", "").strip()
    if url:
        from backends.sheets import SheetsBackend

        secret = os.getenv("SHEETS_WEBAPP_SECRET", "").strip()
        if not secret:
            raise RuntimeError("Có SHEETS_WEBAPP_URL nhưng thiếu SHEETS_WEBAPP_SECRET")
        logger.info("Backend: Google Sheets (Apps Script)")
        return SheetsBackend(url, secret, config, imaging=imaging)

    if os.getenv("LARK_APP_ID", "").strip():
        from backends.lark import LarkBackend

        logger.info("Backend: Lark Base")
        try:
            return LarkBackend(
                os.getenv("LARK_APP_ID", ""),
                os.getenv("LARK_APP_SECRET", ""),
                os.getenv("LARK_APP_TOKEN", ""),
                os.getenv("LARK_TABLE_ID", ""),
                config,
                source_table_id=os.getenv("LARK_SOURCE_TABLE_ID", ""),
                source_name_field=os.getenv("LARK_SOURCE_NAME_FIELD", ""),
            )
        except Exception as e:
            raise RuntimeError(f"Không đăng nhập được Lark: {e}") from e

    raise RuntimeError(
        "Chưa cấu hình backend. Điền SHEETS_WEBAPP_URL (khuyến nghị, xem docs/setup-sheets.md) "
        "hoặc LARK_APP_ID vào .env."
    )


def _preflight(backend) -> None:
    """Gọi thử backend TRƯỚC khi bot nhận việc.

    Không có bước này thì lỗi URL/secret chỉ lộ ra khi người dùng đã làm xong
    hết các bước rồi mới bấm Duyệt — quá muộn. Thử tối đa `PREFLIGHT_ATTEMPTS`
    lần để chịu được Google chập chờn.
    """
    last = None
    for attempt in range(1, PREFLIGHT_ATTEMPTS + 1):
        last = backend.healthcheck()
        if last is None:
            logger.info("Kiểm tra backend: OK")
            return
        if attempt < PREFLIGHT_ATTEMPTS:
            logger.warning("Chưa nối được (lần %d/%d): %s", attempt, PREFLIGHT_ATTEMPTS, last)
            time.sleep(1.5)
    raise RuntimeError(
        "Sổ (backend) chưa dùng được nên bot chưa khởi động:\n"
        f"  {last}\n"
        "Sửa xong trong .env rồi chạy lại `python main.py`."
    )


def _preflight_llm(ocr) -> None:
    """Kiểm tra model ĐỌC ĐƯỢC ẢNH — sai model là lỗi hay gặp nhất.

    Gọi 1 lần với ảnh 160x48, chi phí ~một phần trăm cent, nhưng đổi lại
    người dùng biết ngay lúc cài chứ không phải sau khi gửi 10 tấm ảnh.
    """
    last = None
    for attempt in range(1, PREFLIGHT_ATTEMPTS + 1):
        last = ocr.ping()
        if last is None:
            logger.info("Kiểm tra model đọc ảnh: OK")
            return
        if attempt < PREFLIGHT_ATTEMPTS:
            logger.warning("Chưa đọc được ảnh (lần %d/%d): %s", attempt, PREFLIGHT_ATTEMPTS, last)
            time.sleep(1.5)
    raise RuntimeError(
        "Model đọc ảnh chưa dùng được nên bot chưa khởi động:\n"
        f"  {last}\n"
        "Sửa xong trong .env rồi chạy lại `python main.py`."
    )


async def _run(handler: BotHandler) -> None:
    await handler.app.initialize()
    await handler.app.updater.start_polling()
    await handler.app.start()
    logger.info("Bot '%s' đang chạy", handler.name)
    try:
        while True:
            await asyncio.sleep(3600)
    finally:
        await handler.app.updater.stop()
        await handler.app.stop()
        await handler.app.shutdown()


async def main() -> None:
    load_dotenv()

    token = os.getenv("TELE_BOT_TOKEN", "").strip()
    if not token:
        raise RuntimeError("Thiếu TELE_BOT_TOKEN trong .env (lấy từ @BotFather)")

    config = Config()
    logger.info(
        "Config: %s | nguồn=%d nhóm=%d ready=%s",
        config.path, len(config.sources), len(config.categories), config.is_ready(),
    )

    llm_config = _llm_config()
    ocr = OCRExtractor(llm_config, config)
    backend = _backend(config)

    _preflight(backend)
    _preflight_llm(ocr)

    handler = BotHandler(token, ocr, backend, config, llm_config, name="main")
    await _run(handler)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except RuntimeError as e:
        # Người dùng cuối không đọc được traceback — in đúng thứ phải sửa.
        print(f"\nKHÔNG KHỞI ĐỘNG ĐƯỢC:\n{e}\n", flush=True)
        raise SystemExit(1) from None
