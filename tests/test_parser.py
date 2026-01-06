from expedition.parser import parse_html


def test_parse_html_summary():
    html = """
    <html>
      <head><title>Hello</title></head>
      <body>
        <h1>Main</h1>
        <p>One two three.</p>
      </body>
    </html>
    """
    parsed = parse_html(html, extract_links=False, max_links=None, extract_text=False)
    assert parsed.title == "Hello"
    assert parsed.h1 == "Main"
    assert parsed.word_count == 4
    assert parsed.text is None
