import json

import ocr

CATS = {"An uong": ["Nha hang", "Cafe"], "Gia dinh": []}


def test_build_prompt_injects_groups():
    p = ocr.build_prompt(CATS)
    assert '"An uong"' in p
    assert '"Nha hang"' in p and '"Cafe"' in p
    assert '"Gia dinh"' in p
    assert "không có hạng mục con" in p


def test_build_prompt_empty_categories():
    p = ocr.build_prompt({})
    assert "chưa cấu hình" in p


def test_extract_json_plain():
    assert ocr._extract_json('{"loai":"banking"}') == {"loai": "banking"}


def test_extract_json_with_prose_and_fence():
    raw = 'Đây là kết quả:\n```json\n{"loai":"banking","so_tien":1000}\n```'
    assert ocr._extract_json(raw) == {"loai": "banking", "so_tien": 1000}


def test_extract_json_sse_stream():
    raw = (
        'data: {"choices":[{"delta":{"content":"{\\"loai\\":"}}]}\n'
        'data: {"choices":[{"delta":{"content":"\\"banking\\"}"}}]}\n'
        "data: [DONE]\n"
    )
    assert ocr._extract_json(raw) == {"loai": "banking"}


def test_extract_json_garbage_returns_none():
    assert ocr._extract_json("") is None
    assert ocr._extract_json("data: [DONE]\n") is None
    assert ocr._extract_json("no json here") is None


def test_extract_json_truncated_returns_none():
    assert ocr._extract_json('{"loai": "bank') is None


def test_to_amount():
    assert ocr._to_amount("2.000.000") == 2000000
    assert ocr._to_amount(None) == 0
    assert ocr._to_amount(True) == 0
    assert ocr._to_amount(1500.9) == 1500


def test_normalize():
    d = {
        "so_tien": "2.000.000",
        "ngay_thang": "5/9/2026",
        "thoi_gian": "9h05",
        "loai": "Shopee",
    }
    ocr._normalize(d)
    assert d["so_tien"] == 2000000
    assert d["ngay_thang"] == "05/09/2026"
    assert d["thoi_gian"] == "09:05"
    assert d["loai"] == "shoppe"


def test_normalize_single_digit_minutes():
    d = {"thoi_gian": "9h5"}
    ocr._normalize(d)
    assert d["thoi_gian"] == "09:05"


def test_validate_banking_ok():
    ok = {
        "loai": "banking",
        "so_tien": 1000,
        "ngay_thang": "05/09/2026",
        "thoi_gian": "09:05",
        "danh_muc_lon": "An uong",
        "nhom_chi_phi": "Cafe",
    }
    assert ocr._validate(ok, CATS) == []


def test_validate_reports_bad_fields():
    bad = {
        "loai": "banking",
        "so_tien": 0,
        "ngay_thang": "x",
        "danh_muc_lon": "Khong co",
        "nhom_chi_phi": "La",
    }
    problems = ocr._validate(bad, CATS)
    assert len(problems) == 4


def test_validate_sub_against_group():
    bad = {
        "loai": "banking",
        "so_tien": 1000,
        "ngay_thang": "05/09/2026",
        "danh_muc_lon": "An uong",
        "nhom_chi_phi": "Sai nhom",
    }
    assert any("Sai nhom" in p for p in ocr._validate(bad, CATS))


def test_validate_shoppe_needs_orders_or_content():
    bad = {"loai": "shoppe"}
    assert any("don_hang" in p for p in ocr._validate(bad, CATS))
    ok = {"loai": "shoppe", "noi_dung": "Shop ABC"}
    assert ocr._validate(ok, CATS) == []
