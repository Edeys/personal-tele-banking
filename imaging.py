"""Lưu ảnh biên lai theo chuỗi provider dự phòng.

Thứ tự đọc từ env IMAGE_STORE (mặc định "catbox,telegraph,local"). Mỗi
provider trả URL công khai, hoặc "" để thử provider kế tiếp; local là chốt cuối
nên chuỗi luôn có kết quả.

Không dùng Google Drive: upload lên Drive cần OAuth client đã verify, trái với
quyết định D3 (không bắt user đi qua Google Cloud Console).
"""

from __future__ import annotations

import logging
import os
import re
import unicodedata
import uuid
from datetime import datetime
from pathlib import Path

import requests

logger = logging.getLogger(__name__)

CATBOX_UPLOAD = "https://catbox.moe/user/api.php"
TELEGRAPH_UPLOAD = "https://telegra.ph/upload"
LOCAL_DIR = "receipts"
DEFAULT_ORDER = ("catbox", "telegraph", "local")


def slugify(name: str) -> str:
    if not name:
        return "khac"
    s = name.lower().replace("đ", "d")
    s = unicodedata.normalize("NFD", s)
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    return s or "khac"


def store_order() -> list[str]:
    raw = os.getenv("IMAGE_STORE", ",".join(DEFAULT_ORDER))
    return [p.strip().lower() for p in raw.split(",") if p.strip()]


def _catbox(image_bytes: bytes, category: str = "") -> str:
    resp = requests.post(
        CATBOX_UPLOAD,
        data={"reqtype": "fileupload"},
        files={"fileToUpload": ("receipt.jpg", image_bytes, "image/jpeg")},
        timeout=30,
    )
    url = resp.text.strip()
    if resp.status_code == 200 and url.startswith("http"):
        return url
    logger.warning("Catbox upload failed: %s", url[:200])
    return ""


def _telegraph(image_bytes: bytes, category: str = "") -> str:
    resp = requests.post(
        TELEGRAPH_UPLOAD,
        files={"file": ("receipt.jpg", image_bytes, "image/jpeg")},
        timeout=30,
    )
    data = resp.json()
    if isinstance(data, list) and data and data[0].get("src"):
        return "https://telegra.ph" + data[0]["src"]
    logger.warning("Telegraph upload failed: %s", str(data)[:200])
    return ""


def _webdav(image_bytes: bytes, category: str = "") -> str:
    base = (os.getenv("WEBDAV_URL") or "").rstrip("/")
    user = os.getenv("WEBDAV_USER") or ""
    password = os.getenv("WEBDAV_PASS") or ""
    folder = (os.getenv("WEBDAV_FOLDER") or "tele-banking").strip("/")
    if not base or not user:
        return ""
    url_path = f"/{folder}/{slugify(category)}/{datetime.now():%Y%m%d_%H%M%S}_{uuid.uuid4().hex[:8]}.jpg"
    parent = url_path.rsplit("/", 1)[0]
    try:
        requests.request("MKCOL", f"{base}{parent}", auth=(user, password), timeout=20)
        resp = requests.put(f"{base}{url_path}", data=image_bytes, auth=(user, password), timeout=30)
    except Exception as e:
        logger.warning("WebDAV upload error: %s", e)
        return ""
    if resp.status_code in (200, 201, 204):
        return f"{base}{url_path}"
    logger.warning("WebDAV PUT %s failed: %s", url_path, resp.status_code)
    return ""


def _local(image_bytes: bytes, category: str = "") -> str:
    try:
        target = Path(LOCAL_DIR) / slugify(category)
        target.mkdir(parents=True, exist_ok=True)
        fname = target / f"{datetime.now():%Y%m%d_%H%M%S}_{uuid.uuid4().hex[:8]}.jpg"
        fname.write_bytes(image_bytes)
        return str(fname.resolve())
    except Exception as e:
        logger.warning("Local image save failed: %s", e)
        return ""


PROVIDERS = {
    "catbox": _catbox,
    "telegraph": _telegraph,
    "webdav": _webdav,
    "local": _local,
}


def save_image(image_bytes: bytes, category: str = "") -> str:
    for name in store_order():
        fn = PROVIDERS.get(name)
        if fn is None:
            logger.warning("IMAGE_STORE có provider lạ: %s", name)
            continue
        try:
            url = fn(image_bytes, category)
        except Exception as e:
            logger.warning("imaging %s error: %s", name, e)
            url = ""
        if url:
            logger.info("Đã lưu ảnh qua %s", name)
            return url
    return ""
