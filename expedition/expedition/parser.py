from __future__ import annotations

from dataclasses import dataclass

from bs4 import BeautifulSoup


@dataclass
class ParsedPage:
    title: str | None
    links: list[str]
    text: str | None
    h1: str | None
    word_count: int | None


def parse_html(
    html: str,
    extract_links: bool,
    max_links: int | None,
    extract_text: bool,
) -> ParsedPage:
    soup = BeautifulSoup(html, "html.parser")

    title = None
    if soup.title and soup.title.string:
        title = soup.title.string.strip()

    links: list[str] = []
    if extract_links:
        for tag in soup.find_all(["a", "link"], href=True):
            href = tag.get("href")
            if not href:
                continue
            href = href.strip()
            if href:
                links.append(href)
            if max_links is not None and len(links) >= max_links:
                break

    h1 = None
    h1_tag = soup.find("h1")
    if h1_tag and h1_tag.get_text(strip=True):
        h1 = h1_tag.get_text(strip=True)

    text = None
    word_count = None
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()
    text_root = soup.body or soup
    summary_text = " ".join(text_root.get_text(separator=" ", strip=True).split())
    if summary_text:
        word_count = len(summary_text.split())
    if extract_text:
        text = summary_text

    return ParsedPage(title=title, links=links, text=text, h1=h1, word_count=word_count)
