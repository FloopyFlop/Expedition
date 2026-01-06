from expedition.dedupe import content_hash, url_fingerprint


def test_url_fingerprint_stable():
    url = "https://example.com/a"
    assert url_fingerprint(url) == url_fingerprint(url)
    assert url_fingerprint(url) != url_fingerprint("https://example.com/b")


def test_content_hash():
    body = b"hello"
    assert content_hash(body) == content_hash(body)
    assert content_hash(body) != content_hash(b"world")
