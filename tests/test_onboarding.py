from config import Config
from onboarding import Wizard, is_skip, parse_list


def _config(tmp_path):
    return Config(tmp_path / "config.json")


def test_parse_list():
    assert parse_list("A, B , C") == ["A", "B", "C"]
    assert parse_list("A\nB") == ["A", "B"]
    assert parse_list("A, a") == ["A"]
    assert parse_list("") == []


def test_is_skip():
    assert is_skip("xong")
    assert is_skip("Bỏ qua")
    assert not is_skip("Nhà hàng")


def test_wizard_full_flow(tmp_path):
    config = _config(tmp_path)
    config.claim_admin(999)
    wizard = Wizard(config)
    assert "Nguồn tiền" in wizard.open()
    assert wizard.active

    done, reply = wizard.feed("VCB - 046, Tiền mặt")
    assert not done and "Nhóm chi tiêu" in reply

    done, reply = wizard.feed("An uong, Luong")
    assert not done and "THU NHẬP" in reply

    done, reply = wizard.feed("Luong")
    assert not done and "An uong" in reply

    done, reply = wizard.feed("Nha hang, Cafe")
    assert not done and "Luong" in reply

    done, reply = wizard.feed("xong")
    assert not done and "Thành viên" in reply

    done, reply = wizard.feed("xong")
    assert done and "Đã lưu" in reply

    assert config.sources == ["VCB - 046", "Tiền mặt"]
    assert config.categories == {"An uong": ["Nha hang", "Cafe"], "Luong": []}
    assert config.income_groups == ["Luong"]
    assert config.is_income("Luong") and not config.is_income("An uong")
    assert config.is_ready()


def test_wizard_requires_sources_and_groups(tmp_path):
    wizard = Wizard(_config(tmp_path))
    wizard.open()
    done, reply = wizard.feed("   ")
    assert not done and "ít nhất 1 nguồn" in reply

    wizard.feed("VCB")
    done, reply = wizard.feed("")
    assert not done and "ít nhất 1 nhóm" in reply


def test_wizard_adds_family_ids(tmp_path):
    config = _config(tmp_path)
    wizard = Wizard(config)
    wizard.open()
    wizard.feed("Tiền mặt")
    wizard.feed("An uong")
    wizard.feed("xong")
    wizard.feed("xong")
    done, _ = wizard.feed("12345, 67890")
    assert done
    assert [m["id"] for m in config.family] == [12345, 67890]
    assert 12345 in config.data["allowed_users"]


def test_wizard_income_ignores_unknown_groups(tmp_path):
    config = _config(tmp_path)
    wizard = Wizard(config)
    wizard.open()
    wizard.feed("Tiền mặt")
    wizard.feed("An uong")
    wizard.feed("Khong ton tai, An uong")
    assert wizard.data["income"] == ["An uong"]
