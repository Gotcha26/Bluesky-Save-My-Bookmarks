"""Tests de core/secrets.py : App Password via keyring, repli sur config.json (issue #12)."""
import sys
import types
from unittest.mock import patch

import pytest

from core import secrets as sec

HANDLE = "user.bsky.social"
PWD = "abcd-efgh-ijkl-mnop"


class FakeKeyring(types.ModuleType):
    """Module keyring factice : dictionnaire en mémoire."""

    def __init__(self):
        super().__init__("keyring")
        self.store = {}

    def set_password(self, service, user, pwd):
        self.store[(service, user)] = pwd

    def get_password(self, service, user):
        return self.store.get((service, user))

    def delete_password(self, service, user):
        if (service, user) not in self.store:
            raise RuntimeError("absent")
        del self.store[(service, user)]


class BrokenKeyring(FakeKeyring):
    def set_password(self, service, user, pwd):
        raise RuntimeError("no backend")

    def get_password(self, service, user):
        raise RuntimeError("no backend")

    def delete_password(self, service, user):
        raise RuntimeError("no backend")


@pytest.fixture
def fake_kr(monkeypatch):
    kr = FakeKeyring()
    monkeypatch.setitem(sys.modules, "keyring", kr)
    return kr


@pytest.fixture
def no_kr(monkeypatch):
    # None dans sys.modules : « import keyring » lève ImportError
    monkeypatch.setitem(sys.modules, "keyring", None)


@pytest.fixture
def cfg():
    return {"bsky_handle": HANDLE, "bsky_app_password": ""}


class TestAvecKeyring:
    def test_stockage_dans_keyring_et_pas_dans_config(self, fake_kr, cfg):
        assert sec.store_app_password(cfg, HANDLE, PWD) == "keyring"
        assert fake_kr.store[("bsmb", HANDLE)] == PWD
        assert cfg["bsky_app_password"] == ""

    def test_lecture(self, fake_kr, cfg):
        sec.store_app_password(cfg, HANDLE, PWD)
        assert sec.load_app_password(cfg, HANDLE) == PWD

    def test_suppression(self, fake_kr, cfg):
        sec.store_app_password(cfg, HANDLE, PWD)
        sec.delete_app_password(cfg, HANDLE)
        assert ("bsmb", HANDLE) not in fake_kr.store
        assert sec.load_app_password(cfg, HANDLE) == ""

    def test_suppression_sans_secret_ne_leve_pas(self, fake_kr, cfg):
        sec.delete_app_password(cfg, HANDLE)

    def test_suppression_vide_aussi_la_config(self, fake_kr):
        cfg = {"bsky_app_password": PWD}
        sec.delete_app_password(cfg, HANDLE)
        assert cfg["bsky_app_password"] == ""

    def test_backend_name(self, fake_kr):
        assert sec.backend_name() == "keyring"

    def test_lecture_retombe_sur_config_si_keyring_vide(self, fake_kr):
        cfg = {"bsky_app_password": PWD}
        assert sec.load_app_password(cfg, HANDLE) == PWD


class TestSansKeyring:
    def test_backend_name(self, no_kr):
        assert sec.backend_name() == "config.json"

    def test_stockage_dans_config(self, no_kr, cfg):
        assert sec.store_app_password(cfg, HANDLE, PWD) == "config.json"
        assert cfg["bsky_app_password"] == PWD

    def test_lecture_depuis_config(self, no_kr):
        assert sec.load_app_password({"bsky_app_password": PWD}, HANDLE) == PWD

    def test_suppression(self, no_kr):
        cfg = {"bsky_app_password": PWD}
        sec.delete_app_password(cfg, HANDLE)
        assert cfg["bsky_app_password"] == ""

    def test_lecture_sans_cle(self, no_kr):
        assert sec.load_app_password({}, HANDLE) == ""


class TestKeyringDefaillant:
    @pytest.fixture(autouse=True)
    def _broken(self, monkeypatch):
        monkeypatch.setitem(sys.modules, "keyring", BrokenKeyring())

    def test_stockage_repli_config(self, cfg):
        assert sec.store_app_password(cfg, HANDLE, PWD) == "config.json"
        assert cfg["bsky_app_password"] == PWD

    def test_lecture_repli_config(self):
        assert sec.load_app_password({"bsky_app_password": PWD}, HANDLE) == PWD

    def test_suppression_ne_leve_pas(self):
        cfg = {"bsky_app_password": PWD}
        sec.delete_app_password(cfg, HANDLE)
        assert cfg["bsky_app_password"] == ""

    def test_backend_name_repli(self):
        assert sec.backend_name() == "config.json"


class TestMigration:
    def test_deplace_le_secret_vers_keyring(self, fake_kr, tmp_config):
        tmp_config.update(bsky_handle=HANDLE, bsky_app_password=PWD)
        with patch("core.secrets.save_config") as save:
            assert sec.migrate_secret_to_keyring(tmp_config) is True
        assert fake_kr.store[("bsmb", HANDLE)] == PWD
        assert tmp_config["bsky_app_password"] == ""
        save.assert_called_once_with(tmp_config)

    def test_sans_keyring_rien_ne_change(self, no_kr, tmp_config):
        tmp_config.update(bsky_handle=HANDLE, bsky_app_password=PWD)
        with patch("core.secrets.save_config") as save:
            assert sec.migrate_secret_to_keyring(tmp_config) is False
        assert tmp_config["bsky_app_password"] == PWD
        save.assert_not_called()

    def test_keyring_defaillant_ne_plante_pas(self, monkeypatch, tmp_config):
        monkeypatch.setitem(sys.modules, "keyring", BrokenKeyring())
        tmp_config.update(bsky_handle=HANDLE, bsky_app_password=PWD)
        with patch("core.secrets.save_config") as save:
            assert sec.migrate_secret_to_keyring(tmp_config) is False
        assert tmp_config["bsky_app_password"] == PWD
        save.assert_not_called()

    def test_config_vide_rien_a_faire(self, fake_kr, tmp_config):
        tmp_config.update(bsky_handle=HANDLE, bsky_app_password="")
        with patch("core.secrets.save_config") as save:
            assert sec.migrate_secret_to_keyring(tmp_config) is False
        save.assert_not_called()
        assert fake_kr.store == {}

    def test_sans_handle_rien_a_faire(self, fake_kr, tmp_config):
        tmp_config.update(bsky_handle="", bsky_app_password=PWD)
        assert sec.migrate_secret_to_keyring(tmp_config) is False
        assert tmp_config["bsky_app_password"] == PWD
