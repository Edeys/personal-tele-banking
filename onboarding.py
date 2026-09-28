"""Wizard /start lần đầu và /setup — nơi duy nhất sinh ra data/config.json.

Wizard là state machine tuyến tính, mỗi bước nhận 1 tin nhắn văn bản và trả
lại câu hỏi kế tiếp. Toàn bộ danh mục/nguồn tiền của người dùng sinh ra ở đây,
nên không module nào khác được phép hardcode chúng.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

SKIP_WORDS = {"xong", "skip", "bỏ qua", "bo qua", "-", "không", "khong"}

PROMPT_SOURCES = (
    "Bước 1/5 — *Nguồn tiền*\n"
    "Nhập các nguồn tiền cách nhau dấu phẩy.\n"
    "Ví dụ: `VCB - 046, MB - 259, Tiền mặt, MoMo`"
)

PROMPT_GROUPS = (
    "Bước 2/5 — *Nhóm chi tiêu*\n"
    "Nhập các nhóm lớn cách nhau dấu phẩy.\n"
    "Ví dụ: `Ăn uống, Gia đình, Kinh doanh, Lương`"
)

PROMPT_INCOME = (
    "Bước 3/5 — *Nhóm nào là THU NHẬP?*\n"
    "Chọn đúng tên trong danh sách trên, cách nhau dấu phẩy.\n"
    "Gõ `xong` nếu tất cả đều là chi tiêu."
)


def parse_list(text: str) -> list[str]:
    parts = []
    for chunk in (text or "").replace("\n", ",").split(","):
        item = chunk.strip().strip("-•").strip()
        if item:
            parts.append(item)
    seen, out = set(), []
    for item in parts:
        if item.lower() not in seen:
            seen.add(item.lower())
            out.append(item)
    return out


def is_skip(text: str) -> bool:
    return (text or "").strip().lower() in SKIP_WORDS


class Wizard:
    def __init__(self, config):
        self.config = config
        self.data: dict | None = None

    def open(self) -> str:
        self.data = {
            "step": "sources",
            "sources": [],
            "groups": [],
            "income": [],
            "subs": {},
            "idx": 0,
        }
        return PROMPT_SOURCES

    @property
    def active(self) -> bool:
        return self.data is not None

    def _prompt_subs(self) -> str:
        group = self.data["groups"][self.data["idx"]]
        return (
            f"Bước 4/5 — *Hạng mục con của «{group}»*\n"
            "Nhập cách nhau dấu phẩy, hoặc gõ `xong` để bỏ qua.\n"
            f"Ví dụ cho «{group}»: `Mục 1, Mục 2`"
        )

    def feed(self, text: str) -> tuple[bool, str]:
        """Nhận 1 tin nhắn. Trả (đã xong, câu trả lời)."""
        step = self.data["step"]

        if step == "sources":
            items = parse_list(text)
            if not items:
                return False, "Cần ít nhất 1 nguồn tiền.\n\n" + PROMPT_SOURCES
            self.data["sources"] = items
            self.data["step"] = "groups"
            return False, PROMPT_GROUPS

        if step == "groups":
            items = parse_list(text)
            if not items:
                return False, "Cần ít nhất 1 nhóm chi tiêu.\n\n" + PROMPT_GROUPS
            self.data["groups"] = items
            self.data["subs"] = {g: [] for g in items}
            self.data["step"] = "income"
            return False, PROMPT_INCOME

        if step == "income":
            picked = [g for g in parse_list(text) if g in self.data["groups"]]
            self.data["income"] = picked
            self.data["idx"] = 0
            if not self.data["groups"]:
                return self._finish()
            self.data["step"] = "subs"
            return False, self._prompt_subs()

        if step == "subs":
            group = self.data["groups"][self.data["idx"]]
            self.data["subs"][group] = [] if is_skip(text) else parse_list(text)
            self.data["idx"] += 1
            if self.data["idx"] < len(self.data["groups"]):
                return False, self._prompt_subs()
            self.data["step"] = "family"
            return False, (
                "Bước 5/5 — *Thành viên*\n"
                "Gửi ID Telegram của người dùng chung (họ gõ /myid để lấy), "
                "cách nhau dấu phẩy. Gõ `xong` nếu chỉ mình bạn."
            )

        if step == "family":
            ids = []
            if not is_skip(text):
                for item in parse_list(text):
                    digits = "".join(c for c in item if c.isdigit())
                    if digits:
                        ids.append(int(digits))
            self.data["family"] = ids
            return self._finish()

        return self._finish()

    def _finish(self) -> tuple[bool, str]:
        cfg = self.config.data
        cfg["sources"] = self.data["sources"]
        cfg["categories"] = self.data["subs"]
        cfg["income_groups"] = self.data["income"]
        cfg["family"] = [{"id": i} for i in self.data["family"]]
        allowed = cfg.get("allowed_users") or []
        for member in self.data["family"]:
            if member not in allowed:
                allowed.append(member)
        cfg["allowed_users"] = allowed
        self.config.save()
        self.data = None
        logger.info(
            "Wizard xong: %d nguồn, %d nhóm, %d thu nhập",
            len(cfg["sources"]), len(cfg["categories"]), len(cfg["income_groups"]),
        )
        return True, summary_text(self.config)


def summary_text(config) -> str:
    lines = ["✅ *Đã lưu cấu hình!*", ""]
    lines.append("*Nguồn tiền:* " + (", ".join(config.sources) or "(chưa có)"))
    lines.append("")
    lines.append("*Nhóm chi tiêu:*")
    for group, subs in config.categories.items():
        tag = " (thu nhập)" if config.is_income(group) else ""
        sub_text = ", ".join(subs) if subs else "—"
        lines.append(f"• {group}{tag}: {sub_text}")
    if config.family:
        lines.append("")
        lines.append("*Thành viên:* " + ", ".join(str(m.get("id")) for m in config.family))
    lines.append("")
    lines.append("Giờ gửi ảnh biên lai / màn hình chuyển khoản để bắt đầu.")
    return "\n".join(lines)
