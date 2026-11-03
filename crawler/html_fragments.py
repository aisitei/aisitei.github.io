"""Normalize generated body fragments before inserting them into a page layout."""
from bs4 import BeautifulSoup


def normalize_body_html(fragment: str) -> str:
    """Balance a standalone fragment and keep layout containers outside content.

    Parsing without the surrounding page discards stray closing tags instead of
    letting translated HTML close a language wrapper or the article itself.
    Container tags have no role in a body fragment; retain their children.
    """
    soup = BeautifulSoup(fragment, 'html.parser')
    for container in list(soup.find_all(['div', 'main', 'article', 'aside', 'section', 'header', 'footer', 'html', 'head', 'body'])):
        container.unwrap()
    return str(soup)
