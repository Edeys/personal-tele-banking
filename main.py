"""Entrypoint: load .env + Config, khởi tạo OCR + backend + bot rồi chạy polling."""

from __future__ import annotations

import asyncio
import logging
import os

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
        return LarkBackend(
            os.getenv("LARK_APP_ID", ""),
            os.getenv("LARK_APP_SECRET", ""),
            os.getenv("LARK_APP_TOKEN", ""),
            os.getenv("LARK_TABLE_ID", ""),
            config,
            source_table_id=os.getenv("LARK_SOURCE_TABLE_ID", ""),
            source_name_field=os.getenv("LARK_SOURCE_NAME_FIELD", ""),
        )

    raise RuntimeError(
        "Chưa cấu hình backend. Điền SHEETS_WEBAPP_URL (khuyến nghị, xem docs/setup-sheets.md) "
        "hoặc LARK_APP_ID vào .env."
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

    handler = BotHandler(token, ocr, backend, config, llm_config, name="main")
    await _run(handler)


if __name__ == "__main__":
    asyncio.run(main())
