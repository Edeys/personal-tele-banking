"""Runtime config — cấu hình do onboarding wizard tạo, lưu ở data/config.json.

Secrets (bot token, LLM key, Web App URL) nằm ở .env. File này chỉ chứa
nguồn tiền / nhóm chi tiêu / thành viên của user, nên mọi module phải đọc
qua Config thay vì hardcode danh mục hay tài khoản.

Thiết kế: một object Config dùng chung cho cả tiến trình, có khoá ghi để
onboarding (ghi) và bot handler (đọc) không đè nhau. Ghi kiểu atomic
(tmp + replace) để không bao giờ để lại config.json cụt giữa chừng.
"""

from __future__ import annotations

import json
import logging
import os
import threading
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)

CONFIG_VERSION = 1
DEFAULT_CONFIG_PATH = "data/config.json"
DEFAULT_BOT_NAME = "Sổ Thu Chi"


def default_config() -> dict:
    return {
        "version": CONFIG_VERSION,
        "admin_id": 0,
        "allowed_users": [],
        "bot_name": DEFAULT_BOT_NAME,
        "sources": [],
        "categories": {},
        "family": [],
        "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }


class Config:
    def __init__(self, path: str | Path | None = None):
        self.path = Path(path or os.getenv("TELE_CONFIG_PATH", DEFAULT_CONFIG_PATH))
        self._lock = threading.Lock()
        self.data = self._read()

    def _read(self) -> dict:
        if not self.path.exists():
            return default_config()
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as e:
            logger.warning("config.json không đọc được, dùng mặc định: %s", e)
            return default_config()
        if not isinstance(raw, dict):
            logger.warning("config.json không phải object, dùng mặc định")
            return default_config()
        return self._migrate(raw)

    @staticmethod
    def _migrate(raw: dict) -> dict:
        merged = default_config()
        merged.update({k: raw[k] for k in raw if k in merged})
        merged["created_at"] = raw.get("created_at") or merged["created_at"]
        merged["version"] = CONFIG_VERSION
        return merged

    def save(self) -> None:
        with self._lock:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.path.with_name(self.path.name + ".tmp")
            tmp.write_text(
                json.dumps(self.data, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            tmp.replace(self.path)

    def reload(self) -> None:
        self.data = self._read()

    def is_ready(self) -> bool:
        return bool(self.data.get("admin_id")) and bool(self.categories)

    def is_admin(self, user_id: int) -> bool:
        return bool(user_id) and user_id == self.data.get("admin_id")

    def is_allowed(self, user_id: int) -> bool:
        if self.is_admin(user_id):
            return True
        return user_id in (self.data.get("allowed_users") or [])

    def claim_admin(self, user_id: int) -> bool:
        if self.data.get("admin_id"):
            return False
        self.data["admin_id"] = user_id
        if user_id not in (self.data.get("allowed_users") or []):
            self.data["allowed_users"] = [user_id]
        self.save()
        return True

    @property
    def bot_name(self) -> str:
        return self.data.get("bot_name") or DEFAULT_BOT_NAME

    @property
    def sources(self) -> list[str]:
        return list(self.data.get("sources") or [])

    @property
    def categories(self) -> dict[str, list[str]]:
        return {k: list(v or []) for k, v in (self.data.get("categories") or {}).items()}

    @property
    def family(self) -> list[dict]:
        return list(self.data.get("family") or [])

    def group_names(self) -> list[str]:
        return list(self.categories.keys())

    def sub_categories(self, group: str) -> list[str]:
        return list((self.data.get("categories") or {}).get(group) or [])

    def all_sub_categories(self) -> list[str]:
        out: list[str] = []
        for subs in (self.data.get("categories") or {}).values():
            out.extend(subs or [])
        return out

    def add_user(self, user_id: int) -> bool:
        allowed = self.data.setdefault("allowed_users", [])
        if user_id in allowed:
            return False
        allowed.append(user_id)
        self.save()
        return True
