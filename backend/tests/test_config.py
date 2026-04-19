import pytest


def test_kis_virtual_settings_are_selected():
    from backend.app.config import Settings

    settings = Settings(
        KIS_ENV="virtual",
        KIS_VIRTUAL_APP_KEY="virtual-key",
        KIS_VIRTUAL_APP_SECRET="virtual-secret",
        KIS_REAL_APP_KEY="real-key",
        KIS_REAL_APP_SECRET="real-secret",
    )

    assert settings.kis_mode == "virtual"
    assert settings.kis_base_url == "https://openapivts.koreainvestment.com:29443"
    assert settings.kis_token_url == "https://openapivts.koreainvestment.com:29443/oauth2/tokenP"
    assert settings.kis_app_key == "virtual-key"
    assert settings.kis_app_secret == "virtual-secret"


def test_kis_real_settings_are_selected():
    from backend.app.config import Settings

    settings = Settings(
        KIS_ENV="real",
        KIS_VIRTUAL_APP_KEY="virtual-key",
        KIS_VIRTUAL_APP_SECRET="virtual-secret",
        KIS_REAL_APP_KEY="real-key",
        KIS_REAL_APP_SECRET="real-secret",
    )

    assert settings.kis_mode == "real"
    assert settings.kis_base_url == "https://openapi.koreainvestment.com:9443"
    assert settings.kis_token_url == "https://openapi.koreainvestment.com:9443/oauth2/tokenP"
    assert settings.kis_app_key == "real-key"
    assert settings.kis_app_secret == "real-secret"


def test_invalid_kis_env_is_rejected():
    from backend.app.config import Settings

    settings = Settings(KIS_ENV="unknown")

    with pytest.raises(ValueError, match="KIS_ENV"):
        _ = settings.kis_mode
