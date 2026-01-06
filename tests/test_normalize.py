from expedition.normalize import normalize_url


def test_normalize_basic():
    url = "HTTP://Example.COM:80/Path/?b=2&a=1#section"
    assert normalize_url(url) == "http://example.com/Path/?a=1&b=2"


def test_normalize_drop_tracking_params():
    url = "https://example.com/?utm_source=x&b=1&fbclid=abc"
    assert normalize_url(url) == "https://example.com/?b=1"


def test_normalize_relative_resolution():
    base = "https://example.com/dir/page.html"
    assert normalize_url("/a", base_url=base) == "https://example.com/a"


def test_normalize_trailing_slash():
    url = "https://example.com/dir/"
    assert normalize_url(url) == "https://example.com/dir/"
