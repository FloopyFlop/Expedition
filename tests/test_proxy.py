from expedition.config import ProxyConfig
from expedition.fetcher import ProxySelector


def test_proxy_auto_enable():
    config = ProxyConfig.from_dict({"http": "http://proxy:8080"})
    assert config.enabled is True


def test_proxy_selector_fallback_to_single_proxy():
    config = ProxyConfig(enabled=True, http="http://proxy:8080")
    selector = ProxySelector(config)
    proxies, used = selector.next_proxy()
    assert proxies == {"http": "http://proxy:8080", "https": "http://proxy:8080"}
    assert used == "http://proxy:8080"


def test_proxy_pool_without_rotation():
    config = ProxyConfig(enabled=True, pool=["http://one:8080", "http://two:8080"])
    selector = ProxySelector(config)
    proxies, used = selector.next_proxy()
    assert proxies == {"http": "http://one:8080", "https": "http://one:8080"}
    assert used == "http://one:8080"
