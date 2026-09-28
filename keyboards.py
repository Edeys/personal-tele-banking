"""Dựng inline keyboard TỪ config — không hardcode nhóm/hạng mục/ngân hàng.

Callback dùng CHỈ SỐ (grp:0, sub:1:2) chứ không nhúng tên, vì Telegram giới
hạn callback_data 64 byte và tên hạng mục tiếng Việt rất dễ vượt.
"""

from __future__ import annotations

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

BACK = "« Quay lại"
MAX_PER_ROW = 2


def _rows(items, prefix):
    rows, row = [], []
    for i, label in enumerate(items):
        row.append(InlineKeyboardButton(label, callback_data=f"{prefix}:{i}"))
        if len(row) == MAX_PER_ROW:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    return rows


def confirm_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("Duyệt", callback_data="confirm"),
         InlineKeyboardButton("Nguồn tiền", callback_data="src")],
        [InlineKeyboardButton("Nhóm chi tiêu", callback_data="grp"),
         InlineKeyboardButton("Hạng mục", callback_data="sub")],
        [InlineKeyboardButton("Bỏ qua", callback_data="cancel")],
    ])


def retry_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("OCR lại", callback_data="retry_ocr")],
        [InlineKeyboardButton("Bỏ qua", callback_data="skip_ocr")],
    ])


def source_kb(sources: list[str]) -> InlineKeyboardMarkup:
    rows = _rows(sources, "src")
    rows.append([InlineKeyboardButton("« Quay lại", callback_data="back")])
    return InlineKeyboardMarkup(rows)


def group_kb(groups: list[str]) -> InlineKeyboardMarkup:
    rows = _rows(groups, "grp")
    rows.append([InlineKeyboardButton("« Quay lại", callback_data="back")])
    return InlineKeyboardMarkup(rows)


def sub_kb(group_index: int, subs: list[str]) -> InlineKeyboardMarkup:
    rows = _rows(subs, f"sub:{group_index}")
    rows.append([
        InlineKeyboardButton("Bỏ hạng mục", callback_data="sub:none"),
        InlineKeyboardButton("« Quay lại", callback_data="back"),
    ])
    return InlineKeyboardMarkup(rows)


def none_kb(items: list[str], prefix: str, empty_text: str) -> InlineKeyboardMarkup:
    if not items:
        return InlineKeyboardMarkup([[InlineKeyboardButton(empty_text, callback_data="noop")]])
    return InlineKeyboardMarkup(_rows(items, prefix))
