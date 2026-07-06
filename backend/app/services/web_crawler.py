"""Same-domain BFS crawler used to build a WebSource's knowledge text.

Isolated from WebSourceService so it can be unit tested with a mocked/fake
httpx.Client (e.g. via httpx.MockTransport) without touching the database or
the network.
"""

import re
from dataclasses import dataclass, field
from urllib.parse import urldefrag, urljoin, urlparse

import httpx
from bs4 import BeautifulSoup

from app.core.logging import get_logger

logger = get_logger(__name__)

# Independent of settings.max_knowledge_context_chars (which governs final
# LLM prompt truncation). This only prevents unbounded DB bloat from crawling
# a very large site.
MAX_STORED_TEXT_CHARS = 200_000
REQUEST_TIMEOUT_SECONDS = 10.0

# Tags that are never page content, regardless of what's inside them: nav
# menus, chrome, embeds, buttons and forms (newsletter signups, etc.).
_STRIP_TAGS = (
    "script",
    "style",
    "nav",
    "header",
    "footer",
    "noscript",
    "aside",
    "form",
    "iframe",
    "svg",
    "button",
)

# Cookie banners, legal/privacy notices, and newsletter/social widgets are
# ordinary markup (not one of the tags above), but the platforms that render
# them (Complianz, Cookiebot, OneTrust, cookieconsent.js, WordPress legal
# plugins, Mailchimp embeds, share-button widgets...) almost always tag their
# container with an id/class containing one of these words, so we drop those
# containers heuristically rather than trying to enumerate every platform.
_NOISE_CONTAINER_PATTERN = re.compile(
    r"cookie|consent|gdpr|cmplz|cky-consent|privacy|privacidad|aviso-legal|legal-notice"
    r"|terms-and-conditions|newsletter|subscribe|social-share|share-buttons",
    re.IGNORECASE,
)
_NOISE_CONTAINER_CANDIDATE_TAGS = ("div", "section")

# Preferred containers for the actual page content, checked in order. Most
# modern (and WordPress/accessibility-ready) themes wrap the real content in
# one of these, which lets us skip sidebars/widgets/related-posts blocks
# entirely instead of trying to blocklist them one by one.
_MAIN_CONTENT_SELECTORS = ("main", "[role='main']", "article")


def _looks_like_noise_container(tag) -> bool:
    css_classes = tag.get("class") or []
    identifiers = " ".join([tag.get("id", ""), *css_classes])
    return bool(_NOISE_CONTAINER_PATTERN.search(identifiers))


@dataclass
class CrawlResult:
    pages_crawled: int
    extracted_text: str
    error: str | None = None
    visited_urls: list[str] = field(default_factory=list)


def _normalize_link(base_url: str, href: str) -> str | None:
    """Resolve `href` relative to `base_url`, strip the fragment, and return
    None if it isn't an http(s) URL."""
    resolved = urljoin(base_url, href)
    resolved, _fragment = urldefrag(resolved)
    if not resolved.startswith(("http://", "https://")):
        return None
    return resolved


def _is_spanish_page(soup: BeautifulSoup) -> bool:
    """True if this page is Spanish, or if it isn't but the site doesn't
    offer a Spanish translation of it.

    Keeping both language versions of the same page would duplicate content
    in the LLM's knowledge context for no benefit. Multilingual WordPress
    sites (Polylang/WPML, which this site uses) mark the page's own language
    via `<html lang="...">` and link sibling translations via
    `<link rel="alternate" hreflang="...">` tags in `<head>` — both are
    checked here instead of guessing from the URL, since translated slugs
    don't necessarily share any structure across languages.
    """
    html_tag = soup.find("html")
    lang = ((html_tag.get("lang") if html_tag else None) or "").lower()
    if lang.startswith("es"):
        return True

    for link in soup.find_all("link"):
        rel = link.get("rel") or []
        if isinstance(rel, str):
            rel = [rel]
        hreflang = (link.get("hreflang") or "").lower()
        if "alternate" in rel and hreflang.startswith("es"):
            return False  # a Spanish version of this page exists elsewhere

    return True  # no language info at all, or no Spanish alternate: keep it


def _extract_visible_text(html: str) -> tuple[str, list[str], bool]:
    """Returns (visible_text, discovered_link_hrefs, is_spanish_or_untranslated).

    Links are collected from the *full* page (before trimming to main
    content) so navigation menus are still followed for crawling purposes,
    even though the menu text itself is excluded from the extracted text.
    """
    soup = BeautifulSoup(html, "html.parser")
    links = [a.get("href") for a in soup.find_all("a", href=True)]
    keep_language = _is_spanish_page(soup)

    for tag in soup(_STRIP_TAGS):
        tag.decompose()
    for tag in soup.find_all(_NOISE_CONTAINER_CANDIDATE_TAGS):
        # A tag whose ancestor was already decomposed earlier in this loop
        # (e.g. a nested div inside a cookie-banner container) is left in an
        # invalid state; skip it instead of inspecting its (cleared) attrs.
        if tag.decomposed:
            continue
        if _looks_like_noise_container(tag):
            tag.decompose()

    main_content = None
    for selector in _MAIN_CONTENT_SELECTORS:
        main_content = soup.select_one(selector)
        if main_content is not None:
            break

    text = (main_content or soup).get_text(separator="\n", strip=True)
    return text, links, keep_language


def crawl_site(root_url: str, max_pages: int, *, client: httpx.Client | None = None) -> CrawlResult:
    """BFS from `root_url`, same-domain only, up to `max_pages`. Never raises:
    all failures are captured into `CrawlResult.error`, mirroring
    MailboxService.test_connection's best-effort style."""
    root_netloc = urlparse(root_url).netloc
    owns_client = client is None
    client = client or httpx.Client(timeout=REQUEST_TIMEOUT_SECONDS, follow_redirects=True)

    queue: list[str] = [root_url]
    seen: set[str] = {root_url}
    sections: list[str] = []
    visited: list[str] = []
    total_chars = 0
    error: str | None = None

    try:
        while queue and len(visited) < max_pages:
            url = queue.pop(0)
            try:
                response = client.get(url)
                response.raise_for_status()
            except httpx.HTTPError as exc:
                logger.warning("web_source_page_fetch_failed url=%s error=%s", url, exc)
                continue

            content_type = response.headers.get("content-type", "")
            if "text/html" not in content_type:
                continue

            visited.append(url)
            text, hrefs, keep_language = _extract_visible_text(response.text)

            if keep_language and text and total_chars < MAX_STORED_TEXT_CHARS:
                remaining = MAX_STORED_TEXT_CHARS - total_chars
                chunk = f"### {url}\n{text}"[:remaining]
                sections.append(chunk)
                total_chars += len(chunk)

            for href in hrefs:
                link = _normalize_link(url, href)
                if link is None or link in seen:
                    continue
                if urlparse(link).netloc != root_netloc:
                    continue
                if _NOISE_CONTAINER_PATTERN.search(link):
                    # Whole pages dedicated to cookies/privacy/legal/T&C/
                    # newsletter noise never add value to the LLM context;
                    # reuse the same keyword pattern used for noise
                    # *containers* within a page, applied to the URL itself,
                    # so these pages aren't fetched at all (they're typically
                    # linked from every page's footer, hence `seen` here too).
                    seen.add(link)
                    continue
                seen.add(link)
                queue.append(link)

        if not visited:
            error = "No se pudo extraer contenido HTML de ninguna página a partir de la URL raíz."
    except Exception as exc:  # noqa: BLE001 - a crawl failure must never propagate
        logger.error("web_source_crawl_failed root_url=%s error=%s", root_url, exc)
        error = f"Error durante el rastreo: {exc}"
    finally:
        if owns_client:
            client.close()

    return CrawlResult(
        pages_crawled=len(visited),
        extracted_text="\n\n".join(sections),
        error=error,
        visited_urls=visited,
    )
