import base64

import pytest

pytest.importorskip("flask")

from cryptogotchi.app import create_app

PNG_1X1 = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAusB9s0mU2QAAAAASUVORK5CYII=")


def test_setup_login_and_dashboard(tmp_path):
    app = create_app(
        config_path=str(tmp_path / "config.toml"),
        data_dir=str(tmp_path / "data"),
        start_worker=False,
    )
    app.config.update(TESTING=True)
    client = app.test_client()

    assert client.get("/setup").status_code == 200
    with client.session_transaction() as session:
        token = session["csrf_token"]

    response = client.post(
        "/setup",
        data={
            "csrf_token": token,
            "username": "admin",
            "password": "mot-de-passe-solide",
            "confirm": "mot-de-passe-solide",
        },
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert b"CryptoGotchi" in response.data
    assert response.headers["X-Frame-Options"] == "DENY"

    response = client.get("/health")
    assert response.status_code == 200
    assert response.json["version"] == "0.7.3"

    response = client.get("/api/status")
    assert response.status_code == 200
    assert response.json["status"]["display"]["type"] == "waveshare_lcd_1in44"

    response = client.get("/analysis")
    assert response.status_code == 200
    assert b"15 min" in response.data or b"15m" in response.data


class FakeCompletedProcess:
    def __init__(self, returncode=0, stdout="", stderr=""):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


def configured_client(tmp_path):
    app = create_app(
        config_path=str(tmp_path / "config.toml"),
        data_dir=str(tmp_path / "data"),
        start_worker=False,
    )
    app.config.update(TESTING=True)
    client = app.test_client()
    client.get("/setup")
    with client.session_transaction() as session:
        token = session["csrf_token"]
    client.post(
        "/setup",
        data={
            "csrf_token": token,
            "username": "admin",
            "password": "mot-de-passe-solide",
            "confirm": "mot-de-passe-solide",
        },
    )
    with client.session_transaction() as session:
        token = session["csrf_token"]
    return app, client, token


def test_hidden_wifi_sets_hidden_and_key_management(tmp_path, monkeypatch):
    app, client, token = configured_client(tmp_path)
    calls = []

    def fake_run(command, **kwargs):
        calls.append(command)
        return FakeCompletedProcess()

    monkeypatch.setattr("cryptogotchi.app.subprocess.run", fake_run)
    response = client.post(
        "/wifi/connect",
        data={
            "csrf_token": token,
            "wifi_ssid": "MaisonCachee",
            "wifi_password": "mot-de-passe-wifi",
            "wifi_security": "wpa-psk",
            "wifi_hidden": "on",
        },
        follow_redirects=True,
    )
    assert response.status_code == 200
    flattened = [item for command in calls for item in command]
    assert "802-11-wireless.hidden" in flattened
    assert "yes" in flattened
    assert "802-11-wireless-security.key-mgmt" in flattened
    assert "wpa-psk" in flattened
    assert any("up" in command and "MaisonCachee" in " ".join(command) for command in calls)


def test_display_defaults_stay_on(tmp_path):
    app = create_app(
        config_path=str(tmp_path / "config.toml"),
        data_dir=str(tmp_path / "data"),
        start_worker=False,
    )
    cfg = app.extensions["cryptogotchi_config"].load()
    assert cfg["display"]["backlight_timeout_seconds"] == 0
    assert cfg["display"]["screen_sleep_seconds"] == 0


def test_custom_logo_is_served_and_referenced(tmp_path):
    config_dir = tmp_path / "cfg"
    config_dir.mkdir()
    (config_dir / "logo.png").write_bytes(PNG_1X1)
    app = create_app(config_path=str(config_dir / "config.toml"), data_dir=str(tmp_path / "data"), start_worker=False)
    app.config.update(TESTING=True)
    client = app.test_client()
    response = client.get("/setup")
    assert response.status_code == 200
    assert b"/branding/logo" in response.data
    logo = client.get("/branding/logo")
    assert logo.status_code == 200
    assert logo.mimetype == "image/png"
