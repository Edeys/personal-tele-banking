"""Interface chung cho backend lưu giao dịch.

Bot chỉ nói chuyện với backend qua interface này, nên thêm backend mới
(CSV, SQLite, Notion…) không phải sửa `bot.py`. Bốn việc bắt buộc:
`append`, `get_recent`, `summarize_recent`, `healthcheck`.

Hợp đồng trả về cố ý khác nhau:

- `append` trả **`None` nếu ghi được, ngược lại trả LÝ DO bằng tiếng Việt**.
  Bot phải đọc được lý do để báo cho người dùng và GIỮ LẠI giao dịch chờ
  thử lại — nếu trả `bool` thì người dùng chỉ thấy "kiểm tra log", mà họ
  không đọc được log, và giao dịch bị mất.
- `healthcheck` cũng trả `str | None`: `None` = kết nối tốt.
- `get_recent` nuốt lỗi và trả `[]` (chỉ dùng để gợi ý câu hỏi, không phải
  đường ghi dữ liệu).

`build_row` và `detect_source` ở đây là phần dùng chung để hai backend
không mỗi nơi map một kiểu — dữ liệu của người dùng chỉ có một nguồn.
"""

from __future__ import annotations

import re
from typing import Protocol, runtime_checkable

RECEIPT_COLUMN = "Chứng từ"
SOURCE_COLUMN = "Tài khoản/Quỹ"

HEADERS = [
    "Ngày giao dịch",
    "Thời gian",
    "Loại Giao Dịch",
    "Dòng tiền",
    "Số tiền VND",
    "Phân loại lớn",
    "Hạng mục Thu/Chi",
    "Nội dung chuyển khoản",
    "Nội dung chi tiết",
    "Người Nhận",
    "Ngân Hàng Nhận Tiền",
    "Mã giao dịch",
    SOURCE_COLUMN,
    "Trạng thái",
    RECEIPT_COLUMN,
]


def amount_of(value) -> int:
    if value is None or isinstance(value, bool):
        return 0
    if isinstance(value, (int, float)):
        return int(value)
    digits = "".join(c for c in str(value) if c.isdigit())
    return int(digits) if digits else 0


def date_text(value: str) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    for sep in ("/", "-", "."):
        parts = text.split(sep)
        if len(parts) == 3 and len(parts[2]) == 4 and all(p.isdigit() for p in parts):
            return f"{int(parts[0]):02d}/{int(parts[1]):02d}/{parts[2]}"
        if len(parts) == 3 and len(parts[0]) == 4 and all(p.isdigit() for p in parts):
            return f"{int(parts[2]):02d}/{int(parts[1]):02d}/{parts[0]}"
    return text


BANK_GROUPS = {
    "vietcombank": ["vietcombank", "vcb", "ngoại thương", "ngoai thuong"],
    "techcombank": ["techcombank", "tcb", "kỹ thương", "ky thuong"],
    "mb bank": ["mb bank", "mb", "quân đội", "quan doi"],
    "bidv": ["bidv", "đầu tư và phát triển", "dau tu va phat trien"],
    "vietinbank": ["vietinbank", "vtb", "ctg", "công thương", "cong thuong"],
    "vpbank": ["vpbank", "vpb"],
    "tpbank": ["tpbank", "tpb"],
    "sacombank": ["sacombank", "stb", "sài gòn thương tín", "sai gon thuong tin"],
    "agribank": ["agribank", "agr"],
    "hdbank": ["hdbank", "hdb"],
    "acb": ["acb"],
    "vib": ["vib"],
}


def _tokens_for(label: str) -> list[str]:
    """Mở rộng nhãn nguồn ("VCB") thành mọi tên gọi của cùng ngân hàng.

    Chỉ khớp CHÍNH XÁC theo token: nếu dùng substring thì "mb" sẽ khớp vào
    "techcombank" và kéo nhầm cả nhóm Techcombank vào (bug bản cũ).
    """
    key = label.strip().lower()
    tokens = {key}
    for group in BANK_GROUPS.values():
        if key in group:
            tokens.update(group)
    return sorted(tokens, key=len, reverse=True)


def detect_source(bank_text: str, sources: list[str]) -> str:
    """Khớp text ngân hàng của OCR với nguồn tiền user khai trong config.

    Nguồn trong config là chuỗi tự do ("VCB - 046", "Techcombank - 259",
    "Tiền mặt"), OCR thường trả tên đầy đủ ("Vietcombank", "NHTMCP Kỹ Thương")
    nên phải mở rộng qua BANK_GROUPS rồi khớp theo RANH GIỚI TỪ.
    """
    haystack = (bank_text or "").lower()
    if not haystack:
        return ""

    candidates = []
    for source in sources or []:
        label = str(source).split(" - ", 1)[0].strip()
        if label:
            candidates.append((label, source))
    for label, source in sorted(candidates, key=lambda c: -len(c[0])):
        if any(re.search(rf"(?<!\w){re.escape(t)}(?!\w)", haystack) for t in _tokens_for(label)):
            return source
    return ""


def build_row(txn: dict, config=None) -> dict:
    group = str(txn.get("danh_muc_lon") or "").strip()
    income = bool(config.is_income(group)) if config else False
    return {
        "Ngày giao dịch": date_text(txn.get("ngay_thang", "")),
        "Thời gian": txn.get("thoi_gian", "") or "",
        "Loại Giao Dịch": "Shoppe" if txn.get("loai") == "shoppe" else "Banking",
        "Dòng tiền": "Thu" if income else "Chi",
        "Số tiền VND": amount_of(txn.get("so_tien")),
        "Phân loại lớn": group,
        "Hạng mục Thu/Chi": txn.get("nhom_chi_phi", "") or "",
        "Nội dung chuyển khoản": txn.get("noi_dung", "") or "",
        "Nội dung chi tiết": txn.get("ghi_chu", "") or "",
        "Người Nhận": txn.get("nguoi_nhan", "") or "",
        "Ngân Hàng Nhận Tiền": txn.get("ngan_hang_nhan", "") or "",
        "Mã giao dịch": txn.get("ma_giao_dich", "") or "",
        SOURCE_COLUMN: "",
        "Trạng thái": "Đã thanh toán",
        RECEIPT_COLUMN: "",
    }


def summarize_rows(rows: list[dict], max_items: int = 5) -> str:
    if not rows:
        return "(Không có dữ liệu gần đây)"
    parts = []
    for row in rows[:max_items]:
        group = row.get("Phân loại lớn") or "?"
        date = row.get("Ngày giao dịch") or "?"
        amount = row.get("Số tiền VND") or "?"
        parts.append(f"{group}: {date} – {amount}")
    if len(rows) > max_items:
        parts.append(f"... (tổng cộng {len(rows)} giao dịch)")
    return "\n".join(parts)


@runtime_checkable
class Backend(Protocol):
    def append(self, txn: dict, image_bytes: bytes | None = None) -> str | None: ...

    def get_recent(self, limit: int = 10) -> list[dict]: ...

    def summarize_recent(self, rows: list[dict], max_items: int = 5) -> str: ...

    def healthcheck(self) -> str | None: ...
