import imaging


def test_slugify_vietnamese():
    assert imaging.slugify("Gia Đình (H)") == "gia-dinh-h"
    assert imaging.slugify("Ăn uống") == "an-uong"
    assert imaging.slugify("") == "khac"
    assert imaging.slugify("!!!") == "khac"


def test_store_order_default(monkeypatch):
    monkeypatch.delenv("IMAGE_STORE", raising=False)
    assert imaging.store_order() == ["catbox", "telegraph", "local"]


def test_store_order_custom(monkeypatch):
    monkeypatch.setenv("IMAGE_STORE", "local, catbox")
    assert imaging.store_order() == ["local", "catbox"]


def test_save_image_uses_first_success(monkeypatch):
    monkeypatch.setenv("IMAGE_STORE", "a,b,c")
    calls = []

    def fake_a(data, category=""):
        calls.append("a")
        return ""

    def fake_b(data, category=""):
        calls.append("b")
        return "https://example.com/b.jpg"

    monkeypatch.setitem(imaging.PROVIDERS, "a", fake_a)
    monkeypatch.setitem(imaging.PROVIDERS, "b", fake_b)
    assert imaging.save_image(b"x", "An uong") == "https://example.com/b.jpg"
    assert calls == ["a", "b"]


def test_save_image_skips_raising_provider(monkeypatch):
    monkeypatch.setenv("IMAGE_STORE", "boom,ok")
    monkeypatch.setitem(imaging.PROVIDERS, "boom", lambda d, c="": (_ for _ in ()).throw(RuntimeError("x")))
    monkeypatch.setitem(imaging.PROVIDERS, "ok", lambda d, c="": "u")
    assert imaging.save_image(b"x") == "u"


def test_save_image_all_fail(monkeypatch):
    monkeypatch.setenv("IMAGE_STORE", "x,y")
    monkeypatch.setitem(imaging.PROVIDERS, "x", lambda d, c="": "")
    monkeypatch.setitem(imaging.PROVIDERS, "y", lambda d, c="": "")
    assert imaging.save_image(b"x") == ""


def test_save_image_unknown_provider(monkeypatch):
    monkeypatch.setenv("IMAGE_STORE", "khong-ton-tai")
    assert imaging.save_image(b"x") == ""
