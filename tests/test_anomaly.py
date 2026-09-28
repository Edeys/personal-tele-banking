from anomaly import detect_anomaly


def _row(group, amount):
    return {"Phân loại lớn": group, "Số tiền VND": amount}


def test_no_history_no_anomaly():
    assert detect_anomaly({"danh_muc_lon": "An uong", "so_tien": 10_000_000}, []) == (False, "")


def test_amount_outlier_same_group():
    rows = [_row("An uong", 500_000), _row("An uong", 600_000)]
    is_anomaly, reason = detect_anomaly({"danh_muc_lon": "An uong", "so_tien": 5_000_000}, rows)
    assert is_anomaly
    assert "cao bất thường" in reason


def test_amount_normal_same_group():
    rows = [_row("An uong", 500_000), _row("An uong", 600_000)]
    assert detect_anomaly({"danh_muc_lon": "An uong", "so_tien": 550_000}, rows) == (False, "")


def test_new_group_is_anomaly():
    rows = [_row("An uong", 500_000), _row("An uong", 600_000)]
    is_anomaly, reason = detect_anomaly({"danh_muc_lon": "Du lich", "so_tien": 100_000}, rows)
    assert is_anomaly
    assert "chưa xuất hiện" in reason


def test_reads_ocr_shape():
    rows = [
        {"danh_muc_lon": "An uong", "so_tien": "100000"},
        {"danh_muc_lon": "An uong", "so_tien": "200000"},
    ]
    is_anomaly, _ = detect_anomaly({"danh_muc_lon": "An uong", "so_tien": 9_000_000}, rows)
    assert is_anomaly


def test_multiplier_configurable():
    rows = [_row("An uong", 100_000)]
    assert detect_anomaly({"danh_muc_lon": "An uong", "so_tien": 250_000}, rows, multiplier=3.0) == (False, "")
    is_anomaly, _ = detect_anomaly({"danh_muc_lon": "An uong", "so_tien": 250_000}, rows, multiplier=2.0)
    assert is_anomaly


def test_no_group_falls_through():
    rows = [_row("An uong", 100_000)]
    assert detect_anomaly({"so_tien": 999_999_999}, rows) == (False, "")
