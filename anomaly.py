"""Phát hiện giao dịch bất thường (rule-based, không cần model).

Hai luật:
1. Số tiền > ngưỡng lần trung vị của CÙNG nhóm (danh_muc_lon).
2. Nhóm chưa từng xuất hiện trong N giao dịch gần nhất.

Nhóm lấy từ cấu hình người dùng, không hardcode prefix Firefly như bản cũ.
Nhận cả dict kết quả OCR (`danh_muc_lon`) lẫn row đọc từ backend
("Phân loại lớn") nên dùng chung được cho cả hai phía.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

AMOUNT_MULTIPLIER = 3.0
RECENT_LOOKBACK = 30

_GROUP_KEYS = ("danh_muc_lon", "Phân loại lớn", "Nhóm chi phí")
_AMOUNT_KEYS = ("so_tien", "Số tiền VND", "Số tiền")


def _parse_amount(value) -> int:
    if value is None:
        return 0
    if isinstance(value, bool):
        return 0
    if isinstance(value, (int, float)):
        return int(value)
    digits = "".join(c for c in str(value) if c.isdigit())
    return int(digits) if digits else 0


def _group_of(row: dict) -> str:
    for key in _GROUP_KEYS:
        value = row.get(key)
        if value:
            return str(value).strip()
    return ""


def _amount_of(row: dict) -> int:
    for key in _AMOUNT_KEYS:
        if key in row:
            amount = _parse_amount(row.get(key))
            if amount:
                return amount
    return 0


def _median(values: list[int]) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    n = len(ordered)
    mid = n // 2
    if n % 2:
        return float(ordered[mid])
    return (ordered[mid - 1] + ordered[mid]) / 2.0


def detect_anomaly(
    entry: dict,
    recent_rows: list[dict],
    multiplier: float = AMOUNT_MULTIPLIER,
    lookback: int = RECENT_LOOKBACK,
) -> tuple[bool, str]:
    if not recent_rows:
        return False, ""

    amount = _amount_of(entry)
    group = _group_of(entry)

    if group:
        group_amounts = [a for r in recent_rows if _group_of(r) == group and (a := _amount_of(r)) > 0]
        if group_amounts and amount > 0:
            med = _median(group_amounts)
            if med > 0 and amount > med * multiplier:
                return (
                    True,
                    f"Số tiền {amount:,}₫ cao bất thường (>{multiplier:.0f}× trung vị "
                    f"{int(med):,}₫ của nhóm {group}).",
                )

    recent_groups = [_group_of(r) for r in recent_rows[-lookback:]]
    if group and group not in recent_groups:
        return True, f"Nhóm '{group}' chưa xuất hiện trong {lookback} giao dịch gần nhất."

    return False, ""
