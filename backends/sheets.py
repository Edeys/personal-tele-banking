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

import requests

from backends.base import RECEIPT_COLUMN, SOURCE_COLUMN, build_row, detect_source, summarize_rows

logger = logging.getLogger(__name__)

TAB_OUT = "Tiền chuyển"
TAB_IN = "Tiền nhận"
API_TIMEOUT = 30


class SheetsBackend:
    def __init__(self, url: str, secret: str, config, imaging=None):
        self.url = (url or "").strip()
        self.secret = secret or ""
        self.config = config
        self.imaging = imaging
        self.last_tab = ""

    def _post(self, payload: dict) -> dict:
        body = {"secret": self.secret, **payload}
        resp = requests.post(self.url, json=body, timeout=API_TIMEOUT)
        resp.raise_for_status()
        data = resp.json()
        if not isinstance(data, dict) or not data.get("ok"):
            raise RuntimeError((data or {}).get("error") or "Apps Script trả lỗi")
        return data

    def _tab_for(self, txn: dict) -> str:
        group = str(txn.get("danh_muc_lon") or "").strip()
        return TAB_IN if self.config.is_income(group) else TAB_OUT

    def append(self, txn: dict, image_bytes: bytes | None = None) -> bool:
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
            return True
        except Exception:
            logger.exception("Sheets append error")
            return False

    def get_recent(self, limit: int = 10) -> list[dict]:
        try:
            data = self._post({"action": "recent", "limit": limit})
            rows = data.get("rows") or []
            return [r for r in rows if isinstance(r, dict)]
        except Exception as e:
            logger.warning("Sheets get_recent failed: %s", e)
            return []

    def summarize_recent(self, rows: list[dict], max_items: int = 5) -> str:
        return summarize_rows(rows, max_items)
