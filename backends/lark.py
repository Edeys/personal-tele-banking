"""Backend Lark Base (tuỳ chọn).

Khác bản cũ ở đúng một chỗ quan trọng: **không hardcode record_id**. Bản cũ
nhét sẵn `rec27pu7AavcKs` cho từng ngân hàng, nên chỉ chạy được với một người.
Ở đây "Nguồn tiền" được lookup theo TÊN trong bảng Sổ Quỹ mà user cấu hình
(`source_table_id` + `source_name_field`); không cấu hình thì ghi tên dạng text.
"""

from __future__ import annotations

import logging
import time
from datetime import datetime

import requests

from backends.base import build_row, detect_source, summarize_rows

logger = logging.getLogger(__name__)

LARK_API = "https://open.larksuite.com/open-apis/bitable/v1"
AUTH_API = "https://open.larksuite.com/open-apis/auth/v3/tenant_access_token/internal"
DRIVE_UPLOAD = "https://open.larksuite.com/open-apis/drive/v1/medias/upload_all"

SOURCE_FIELD = "Tài khoản/Quỹ"
DATE_FIELD = "Ngày giao dịch"
RECEIPT_FIELD = "Chứng từ/ Hoá đơn"
API_TIMEOUT = 30


def _fmt_date(value: str) -> int:
    parts = str(value or "").replace("/", "-").split("-")
    if len(parts) != 3 or not all(p.isdigit() for p in parts):
        return 0
    if len(parts[0]) == 4:
        year, month, day = int(parts[0]), int(parts[1]), int(parts[2])
    elif len(parts[2]) == 4:
        day, month, year = int(parts[0]), int(parts[1]), int(parts[2])
    else:
        return 0
    if not 2000 <= year <= 2100:
        return 0
    try:
        return int(datetime(year, month, day).timestamp()) * 1000
    except ValueError:
        return 0


class LarkBackend:
    def __init__(
        self,
        app_id: str,
        app_secret: str,
        app_token: str,
        table_id: str,
        config,
        source_table_id: str = "",
        source_name_field: str = "",
    ):
        self.app_id = app_id
        self.app_secret = app_secret
        self.app_token = app_token
        self.table_id = table_id
        self.config = config
        self.source_table_id = source_table_id
        self.source_name_field = source_name_field
        self._token = ""
        self._token_expiry = 0.0
        self._source_map: dict[str, str] | None = None
        self._refresh_token()

    def _refresh_token(self) -> None:
        resp = requests.post(
            AUTH_API,
            json={"app_id": self.app_id, "app_secret": self.app_secret},
            timeout=15,
        )
        data = resp.json()
        if data.get("code") != 0:
            raise RuntimeError(f"Lark auth failed: {data.get('msg')}")
        self._token = data["tenant_access_token"]
        self._token_expiry = time.time() + 7000

    def _headers(self) -> dict:
        if time.time() >= self._token_expiry:
            self._refresh_token()
        return {"Authorization": f"Bearer {self._token}"}

    def _load_source_map(self) -> dict[str, str]:
        if self._source_map is not None:
            return self._source_map
        self._source_map = {}
        if not (self.source_table_id and self.source_name_field):
            return self._source_map
        try:
            resp = requests.get(
                f"{LARK_API}/apps/{self.app_token}/tables/{self.source_table_id}/records",
                headers=self._headers(),
                params={"page_size": 100},
                timeout=15,
            )
            data = resp.json()
            if data.get("code") != 0:
                logger.warning("Lark source lookup failed: %s", data.get("msg"))
                return self._source_map
            for rec in data.get("data", {}).get("items", []):
                name = rec.get("fields", {}).get(self.source_name_field)
                if isinstance(name, list):
                    name = name[0].get("text") if name and isinstance(name[0], dict) else ""
                if name:
                    self._source_map[str(name).strip()] = rec.get("record_id", "")
        except Exception as e:
            logger.warning("Lark source lookup error: %s", e)
        return self._source_map

    def _upload_image(self, image_bytes: bytes) -> str:
        try:
            resp = requests.post(
                DRIVE_UPLOAD,
                headers=self._headers(),
                data={
                    "file_name": "receipt.jpg",
                    "parent_type": "bitable_image",
                    "parent_node": self.app_token,
                    "size": str(len(image_bytes)),
                },
                files={"file": ("receipt.jpg", image_bytes, "image/jpeg")},
                timeout=API_TIMEOUT,
            )
            data = resp.json()
            if data.get("code") == 0:
                return data["data"]["file_token"]
            logger.warning("Lark upload failed: %s", data.get("msg"))
        except Exception as e:
            logger.warning("Lark upload error: %s", e)
        return ""

    def _fields(self, txn: dict, image_bytes: bytes | None) -> dict:
        row = build_row(txn, self.config)
        fields = {k: v for k, v in row.items() if v not in ("", 0, None)}
        fields.pop(SOURCE_FIELD, None)

        stamp = _fmt_date(row[DATE_FIELD])
        if stamp:
            fields[DATE_FIELD] = stamp
        else:
            fields.pop(DATE_FIELD, None)

        source = txn.get("source_name") or detect_source(
            txn.get("ngan_hang_gui") or txn.get("ngan_hang_nhan") or "",
            self.config.sources,
        )
        if source:
            record_id = self._load_source_map().get(source)
            fields[SOURCE_FIELD] = [record_id] if record_id else source

        if image_bytes:
            token = self._upload_image(image_bytes)
            if token:
                fields[RECEIPT_FIELD] = [{"file_token": token}]
        return fields

    def append(self, txn: dict, image_bytes: bytes | None = None) -> bool:
        try:
            payload = {"fields": self._fields(txn, image_bytes)}
            resp = requests.post(
                f"{LARK_API}/apps/{self.app_token}/tables/{self.table_id}/records",
                headers=self._headers(),
                json=payload,
                timeout=API_TIMEOUT,
            )
            data = resp.json()
            if data.get("code") == 0:
                logger.info("Lark append OK")
                return True
            logger.error("Lark append failed: %s", data.get("msg"))
            return False
        except Exception:
            logger.exception("Lark append error")
            return False

    def get_recent(self, limit: int = 10) -> list[dict]:
        try:
            resp = requests.get(
                f"{LARK_API}/apps/{self.app_token}/tables/{self.table_id}/records",
                headers=self._headers(),
                params={"page_size": min(limit, 100)},
                timeout=15,
            )
            data = resp.json()
            if data.get("code") != 0:
                logger.warning("Lark get_recent failed: %s", data.get("msg"))
                return []
            rows = []
            for rec in data.get("data", {}).get("items", []):
                fields = rec.get("fields", {})
                rows.append({
                    "Ngày giao dịch": fields.get(DATE_FIELD, ""),
                    "Số tiền VND": fields.get("Số tiền VND", ""),
                    "Phân loại lớn": fields.get("Phân loại lớn", ""),
                    "Hạng mục Thu/Chi": fields.get("Hạng mục Thu/Chi", ""),
                })
            return rows
        except Exception as e:
            logger.warning("Lark get_recent error: %s", e)
            return []

    def summarize_recent(self, rows: list[dict], max_items: int = 5) -> str:
        return summarize_rows(rows, max_items)
