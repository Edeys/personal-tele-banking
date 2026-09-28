import keyboards as kb


def _callbacks(markup):
    return [b.callback_data for row in markup.inline_keyboard for b in row]


def test_confirm_kb_has_core_actions():
    data = _callbacks(kb.confirm_kb())
    for expected in ("confirm", "cancel", "src", "grp", "sub"):
        assert expected in data


def test_source_kb_indexes_sources():
    data = _callbacks(kb.source_kb(["VCB - 046", "Tiền mặt"]))
    assert "src:0" in data and "src:1" in data and "back" in data


def test_group_kb_indexes_groups():
    data = _callbacks(kb.group_kb(["An uong", "Luong"]))
    assert data[:2] == ["grp:0", "grp:1"]


def test_sub_kb_encodes_group_index():
    data = _callbacks(kb.sub_kb(1, ["A", "B"]))
    assert "sub:1:0" in data and "sub:1:1" in data
    assert "sub:none" in data


def test_group_kb_empty():
    data = _callbacks(kb.group_kb([]))
    assert data == ["back"]


def test_none_kb_placeholder():
    data = _callbacks(kb.none_kb([], "grp", "Chưa có"))
    assert len(data) == 1


def test_callback_data_within_telegram_limit():
    long_names = ["Nhóm chi tiêu rất dài tên " + "x" * 40 for _ in range(3)]
    for markup in (kb.group_kb(long_names), kb.source_kb(long_names)):
        for data in _callbacks(markup):
            assert len(data.encode("utf-8")) <= 64
