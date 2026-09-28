from backends import base
from backends.lark import LarkBackend, _fmt_date
from backends.sheets import TAB_IN, TAB_OUT, SheetsBackend


class FakeConfig:
    def __init__(self, income=(), sources=()):
        self._income = list(income)
        self._sources = list(sources)

    def is_income(self, group):
        return group in self._income

    @property
    def sources(self):
        return list(self._sources)


class FakeResp:
    def __init__(self, payload, status=200):
        self._payload = payload
        self.status_code = status

    def json(self):
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


class FakeImaging:
    def __init__(self, url="https://img/x.jpg"):
        self.url = url
        self.calls = []

    def save_image(self, data, category=""):
        self.calls.append(category)
        return self.url


BANK_TXN = {
    "loai": "banking",
    "ngay_thang": "01/09/2026",
    "thoi_gian": "09:05",
    "danh_muc_lon": "An uong",
    "nhom_chi_phi": "Cafe",
    "so_tien": 50000,
    "noi_dung": "cf",
    "ngan_hang_gui": "Vietcombank",
}


def test_amount_of():
    assert base.amount_of("2.000.000") == 2000000
    assert base.amount_of(None) == 0
    assert base.amount_of(True) == 0


def test_date_text_normalises_both_orders():
    assert base.date_text("1/9/2026") == "01/09/2026"
    assert base.date_text("2026-09-01") == "01/09/2026"
    assert base.date_text("") == ""


def test_detect_source_longest_label_wins():
    sources = ["MB - 259", "Techcombank - 259", "VCB - 046"]
    assert base.detect_source("Techcombank", sources) == "Techcombank - 259"
    assert base.detect_source("MB Bank", sources) == "MB - 259"
    assert base.detect_source("", sources) == ""
    assert base.detect_source("BIDV", sources) == ""


def test_detect_source_expands_bank_aliases():
    assert base.detect_source("Vietcombank", ["VCB - 046"]) == "VCB - 046"
    assert base.detect_source("Ngân hàng TMCP Kỹ Thương", ["TCB - 259"]) == "TCB - 259"


def test_detect_source_word_boundary_avoids_false_match():
    assert base.detect_source("Techcombank", ["MB - 259"]) == ""
    assert base.detect_source("Vietcombank", ["MB - 259"]) == ""


def test_build_row_direction_from_config():
    chi = base.build_row(BANK_TXN, FakeConfig(income=[]))
    assert chi["Dòng tiền"] == "Chi"
    assert chi["Số tiền VND"] == 50000
    assert chi["Ngày giao dịch"] == "01/09/2026"

    thu = base.build_row({**BANK_TXN, "danh_muc_lon": "Luong"}, FakeConfig(income=["Luong"]))
    assert thu["Dòng tiền"] == "Thu"


def test_build_row_shoppe():
    row = base.build_row({"loai": "shoppe", "so_tien": 1}, FakeConfig())
    assert row["Loại Giao Dịch"] == "Shoppe"


def test_summarize_rows():
    rows = [{"Phân loại lớn": "An uong", "Ngày giao dịch": "01/09/2026", "Số tiền VND": 5000}]
    assert "An uong" in base.summarize_rows(rows)
    assert base.summarize_rows([]) == "(Không có dữ liệu gần đây)"


def test_sheets_append_sends_secret_and_row(monkeypatch):
    captured = {}

    def fake_post(url, json=None, timeout=None):
        captured["url"] = url
        captured["json"] = json
        return FakeResp({"ok": True})

    monkeypatch.setattr("backends.sheets.requests.post", fake_post)
    backend = SheetsBackend("https://script", "s3cr3t", FakeConfig())
    assert backend.append(BANK_TXN) is True
    assert captured["json"]["secret"] == "s3cr3t"
    assert captured["json"]["action"] == "append"
    assert captured["json"]["tab"] == TAB_OUT
    assert captured["json"]["fields"]["Số tiền VND"] == 50000
    assert backend.last_tab == TAB_OUT


def test_sheets_income_goes_to_in_tab(monkeypatch):
    captured = {}
    monkeypatch.setattr(
        "backends.sheets.requests.post",
        lambda url, json=None, timeout=None: (captured.update(json=json), FakeResp({"ok": True}))[1],
    )
    backend = SheetsBackend("https://script", "s", FakeConfig(income=["Luong"]))
    backend.append({**BANK_TXN, "danh_muc_lon": "Luong"})
    assert captured["json"]["tab"] == TAB_IN
    assert captured["json"]["fields"]["Dòng tiền"] == "Thu"


def test_sheets_sets_source_and_receipt(monkeypatch):
    captured = {}
    monkeypatch.setattr(
        "backends.sheets.requests.post",
        lambda url, json=None, timeout=None: (captured.update(json=json), FakeResp({"ok": True}))[1],
    )
    imaging = FakeImaging()
    backend = SheetsBackend("https://script", "s", FakeConfig(sources=["VCB - 046"]), imaging=imaging)
    backend.append(BANK_TXN, image_bytes=b"jpeg")
    fields = captured["json"]["fields"]
    assert fields["Tài khoản/Quỹ"] == "VCB - 046"
    assert fields["Chứng từ"] == "https://img/x.jpg"
    assert imaging.calls == ["An uong"]


def test_sheets_append_returns_false_on_error(monkeypatch):
    monkeypatch.setattr(
        "backends.sheets.requests.post",
        lambda url, json=None, timeout=None: FakeResp({"ok": False, "error": "sai secret"}),
    )
    assert SheetsBackend("https://script", "s", FakeConfig()).append(BANK_TXN) is False


def test_sheets_get_recent(monkeypatch):
    rows = [{"Phân loại lớn": "An uong", "Số tiền VND": "1000"}]
    monkeypatch.setattr(
        "backends.sheets.requests.post",
        lambda url, json=None, timeout=None: FakeResp({"ok": True, "rows": rows}),
    )
    backend = SheetsBackend("https://script", "s", FakeConfig())
    assert backend.get_recent(5) == rows
    assert "An uong" in backend.summarize_recent(rows)


def test_sheets_get_recent_swallows_error(monkeypatch):
    monkeypatch.setattr(
        "backends.sheets.requests.post",
        lambda url, json=None, timeout=None: FakeResp({"ok": False, "error": "x"}),
    )
    assert SheetsBackend("https://script", "s", FakeConfig()).get_recent() == []


def test_lark_fmt_date():
    assert _fmt_date("01/09/2026") > 0
    assert _fmt_date("2026-09-01") == _fmt_date("01/09/2026")
    assert _fmt_date("") == 0
    assert _fmt_date("01/09/1900") == 0


def _lark(monkeypatch, config=None, source_table_id="", source_name_field=""):
    monkeypatch.setattr(
        "backends.lark.requests.post",
        lambda *a, **k: FakeResp({"code": 0, "tenant_access_token": "tok"}),
    )
    return LarkBackend("id", "secret", "app", "tbl", config or FakeConfig(), source_table_id, source_name_field)


def test_lark_fields_map_group_and_drop_empty_date(monkeypatch):
    backend = _lark(monkeypatch)
    fields = backend._fields(BANK_TXN, None)
    assert fields["Phân loại lớn"] == "An uong"
    assert fields["Hạng mục Thu/Chi"] == "Cafe"
    assert isinstance(fields["Ngày giao dịch"], int)
    assert "Tài khoản/Quỹ" not in fields

    no_date = backend._fields({**BANK_TXN, "ngay_thang": ""}, None)
    assert "Ngày giao dịch" not in no_date


def test_lark_source_lookup_by_name(monkeypatch):
    backend = _lark(
        monkeypatch,
        config=FakeConfig(sources=["VCB - 046"]),
        source_table_id="tblSrc",
        source_name_field="Tên",
    )
    monkeypatch.setattr(
        "backends.lark.requests.get",
        lambda *a, **k: FakeResp({
            "code": 0,
            "data": {"items": [{"record_id": "recABC", "fields": {"Tên": "VCB - 046"}}]},
        }),
    )
    fields = backend._fields(BANK_TXN, None)
    assert fields["Tài khoản/Quỹ"] == ["recABC"]


def test_lark_source_falls_back_to_text(monkeypatch):
    backend = _lark(monkeypatch, config=FakeConfig(sources=["VCB - 046"]))
    fields = backend._fields(BANK_TXN, None)
    assert fields["Tài khoản/Quỹ"] == "VCB - 046"
