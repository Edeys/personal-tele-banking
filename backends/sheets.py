"""Backend Google Sheets qua Apps Script Web App.

Vì sao không dùng service account: tạo SA bắt người dùng đi qua Google Cloud
Console (enable 2 API, share sheet + folder) — người không biết code không làm
được, mà AI agent cũng không click Console thay được. Apps Script chỉ cần
copy-paste 1 đoạn script vào sheet của họ rồi Deploy Web App.

Hợp đồng với script (xem docs/setup-sheets.md):
  POST {secret, action:"append", tab, fields:{<header>: <value>}}
  POST {secret, action:"recent", limit}
  → {"ok": true, ...} | {"ok": false, "error": "..."}

`fields` khoá theo TÊN CỘT. Script tự tạo tab + header ở lần ghi đầu, nên bot
không cần biết sheet đang có gì.
"""

from __future__ import annotations

import logging
import time

import requests

from backends.base import RECEIPT_COLUMN, SOURCE_COLUMN, build_row, detect_source, summarize_rows

logger = logging.getLogger(__name__)

TAB_OUT = "Tiền chuyển"
TAB_IN = "Tiền nhận"
API_TIMEOUT = 30
READ_ATTEMPTS = 3
_TRANSIENT_KEYS = (
    "timeout", "timed out", "connection", "temporary failure",
    "502", "503", "504", "max retries", "reset by peer",
)


def _transient(text: str) -> bool:
    low = (text or "").lower()
    return any(k in low for k in _TRANSIENT_KEYS)


def _human_error(exc: Exception) -> str:
    """Dịch lỗi kỹ thuật thành việc người dùng phải làm.

    Người dùng cuối không đọc được log, nên mọi lỗi trả về phải chỉ đúng
    bước cần sửa (xem AGENTS.md nguyên tắc 4).
    """
    text = str(exc)
    low = text.lower()
    if "sai secret" in low:
        return "Sai SHEETS_WEBAPP_SECRET — chuỗi này phải giống hệt dòng SECRET trong Apps Script (setup-sheets.md bước 3)."
    if "403" in low or "401" in low:
        return "Google chặn truy cập — trong Apps Script đặt Who has access = Anyone rồi Deploy lại (setup-sheets.md bước 4)."
    if "404" in low:
        return "SHEETS_WEBAPP_URL sai — phải là URL kết thúc bằng /exec (bước 6)."
    if _transient(text):
        return "Không gọi được Google (mạng hoặc Google đang chậm) — thử lại sau ít phút."
    return text[:300]


class SheetsBackend:
    def __init__(self, url: str, secret: str, config, imaging=None):
        self.url = (url or "").strip()
        self.secret = secret or ""
        self.config = config
        self.imaging = imaging
        self.last_tab = ""

    def _post(self, payload: dict, attempts: int = 1) -> dict:
        """Gọi Apps Script. `attempts` > 1 chỉ dùng cho thao tác ĐỌC.

        Ghi thì KHÔNG tự thử lại: nếu Google đã nhận được request mà mất
        kết nối trước khi trả lời, thử lại sẽ tạo dòng trùng. Người dùng
        tự bấm thử lại thì họ biết mình đang làm gì.
        """
        body = {"secret": self.secret, **payload}
        last: Exception | None = None
        for attempt in range(1, max(1, attempts) + 1):
            try:
                resp = requests.post(self.url, json=body, timeout=API_TIMEOUT)
                resp.raise_for_status()
                data = resp.json()
            except Exception as e:
                last = e
                if attempt < attempts and _transient(str(e)):
                    logger.warning("Sheets thử lại %d/%d: %s", attempt, attempts, str(e)[:120])
                    time.sleep(1.0 * attempt)
                    continue
                raise
            if not isinstance(data, dict) or not data.get("ok"):
                raise RuntimeError((data or {}).get("error") or "Apps Script trả lỗi")
            return data
        raise last if last else RuntimeError("Apps Script trả lỗi")

    def _tab_for(self, txn: dict) -> str:
        group = str(txn.get("danh_muc_lon") or "").strip()
        return TAB_IN if self.config.is_income(group) else TAB_OUT

    def healthcheck(self) -> str | None:
        """Gọi thử 1 lần để biết Sổ có dùng được không TRƯỚC khi nhận việc."""
        if not self.url:
            return "Thiếu SHEETS_WEBAPP_URL trong .env (xem docs/setup-sheets.md)."
        if not self.secret:
            return "Thiếu SHEETS_WEBAPP_SECRET trong .env — phải trùng dòng SECRET trong Apps Script."
        try:
            self._post({"action": "recent", "limit": 1}, attempts=READ_ATTEMPTS)
            return None
        except Exception as e:
            return _human_error(e)

    def append(self, txn: dict, image_bytes: bytes | None = None) -> str | None:
        """Trả None nếu ghi được, ngược lại trả lý do lỗi (tiếng Việt)."""
        try:
            row = build_row(txn, self.config)
            if image_bytes and self.imaging is not None:
                row[RECEIPT_COLUMN] = self.imaging.save_image(image_bytes, row["Phân loại lớn"])
            bank_text = txn.get("ngan_hang_gui") or txn.get("ngan_hang_nhan") or ""
            source = txn.get("source_name") or detect_source(bank_text, self.config.sources)
            if source:
                row[SOURCE_COLUMN] = source
            tab = self._tab_for(txn)
            self._post({"action": "append", "tab": tab, "fields": row})
            self.last_tab = tab
            logger.info("Sheets append OK (tab %s)", tab)
            return None
        except Exception as e:
            logger.exception("Sheets append error")
            return _human_error(e)

    def get_recent(self, limit: int = 10) -> list[dict]:
        try:
            data = self._post({"action": "recent", "limit": limit}, attempts=READ_ATTEMPTS)
            rows = data.get("rows") or []
            return [r for r in rows if isinstance(r, dict)]
        except Exception as e:
            logger.warning("Sheets get_recent failed: %s", e)
            return []

    def summarize_recent(self, rows: list[dict], max_items: int = 5) -> str:
        return summarize_rows(rows, max_items)
