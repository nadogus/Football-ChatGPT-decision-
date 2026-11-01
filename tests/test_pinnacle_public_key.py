import data_adapters
from data_adapters import PinnaclePrematchClient


def test_explicit_key_wins():
    c=PinnaclePrematchClient(api_key="explicit")
    assert c._headers()["X-API-Key"]=="explicit"
    assert c.key_source=="explicit_or_env"


def test_public_web_config_key_discovery(monkeypatch):
    monkeypatch.delenv("PINNACLE_GUEST_API_KEY",raising=False)
    monkeypatch.setattr(data_adapters,"_json",lambda url,**kwargs:{"api":{"haywire":{"apiKey":"public-web-key"}}})
    c=PinnaclePrematchClient()
    assert c._headers()["X-API-Key"]=="public-web-key"
    assert c.key_source=="pinnacle_public_web_config"


def test_missing_public_key_fails_closed(monkeypatch):
    monkeypatch.delenv("PINNACLE_GUEST_API_KEY",raising=False)
    monkeypatch.setattr(data_adapters,"_json",lambda url,**kwargs:{"api":{}})
    c=PinnaclePrematchClient()
    try:c._headers()
    except RuntimeError as e:assert str(e)=="PINNACLE_PUBLIC_WEB_KEY_UNAVAILABLE"
    else:raise AssertionError("expected fail-closed RuntimeError")
