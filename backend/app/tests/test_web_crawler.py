"""Crawler tests use httpx.MockTransport so no real network call is made."""

import httpx

from app.services.web_crawler import crawl_site

_PAGES = {
    "http://example.com/": (
        200,
        "text/html",
        """
        <html><body>
        <nav>Menu should be stripped</nav>
        <script>var secret = "secret_script_marker";</script>
        <h1>Home</h1>
        <p>Welcome to example.</p>
        <a href="/page2">Page 2</a>
        <a href="/page2#section">Page 2 with fragment</a>
        <a href="https://external.com/other">External</a>
        <a href="/broken">Broken link</a>
        <a href="/file.pdf">A PDF</a>
        </body></html>
        """,
    ),
    "http://example.com/page2": (
        200,
        "text/html",
        "<html><body><h1>Page 2</h1><p>More content here.</p><a href='/page3'>Page 3</a></body></html>",
    ),
    "http://example.com/page3": (
        200,
        "text/html",
        "<html><body><h1>Page 3</h1><p>Even more.</p></body></html>",
    ),
    "http://example.com/file.pdf": (200, "application/pdf", "%PDF-1.4 binary-ish content"),
    "http://example.com/broken": (500, "text/html", "Internal Server Error"),
}


def _handler(request: httpx.Request) -> httpx.Response:
    url = str(request.url)
    if url not in _PAGES:
        return httpx.Response(404, headers={"content-type": "text/html"}, text="Not found")
    status_code, content_type, body = _PAGES[url]
    return httpx.Response(status_code, headers={"content-type": content_type}, text=body)


def _make_client() -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(_handler))


def test_crawl_single_page_no_links():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            headers={"content-type": "text/html"},
            text="<html><body><h1>Solo</h1><p>Just one page.</p></body></html>",
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))
    result = crawl_site("http://solo.example/", max_pages=5, client=client)

    assert result.pages_crawled == 1
    assert result.error is None
    assert "Just one page." in result.extracted_text


def test_crawl_follows_same_domain_links_via_bfs():
    result = crawl_site("http://example.com/", max_pages=10, client=_make_client())

    assert result.pages_crawled == 3
    assert "### http://example.com/" in result.extracted_text
    assert "### http://example.com/page2" in result.extracted_text
    assert "### http://example.com/page3" in result.extracted_text
    assert "external.com" not in result.extracted_text


def test_crawl_respects_max_pages():
    result = crawl_site("http://example.com/", max_pages=1, client=_make_client())

    assert result.pages_crawled == 1
    assert "page2" not in result.extracted_text


def test_crawl_skips_non_html_and_broken_pages():
    result = crawl_site("http://example.com/", max_pages=10, client=_make_client())

    # The root page legitimately mentions "A PDF" as link text; what must NOT
    # leak in is the actual (non-HTML) PDF file body or the broken page's body.
    assert "binary-ish content" not in result.extracted_text
    assert "Internal Server Error" not in result.extracted_text


def test_crawl_strips_script_and_nav_content():
    result = crawl_site("http://example.com/", max_pages=10, client=_make_client())

    assert "secret_script_marker" not in result.extracted_text
    assert "Menu should be stripped" not in result.extracted_text


def test_crawl_deduplicates_fragment_link_variants():
    result = crawl_site("http://example.com/", max_pages=10, client=_make_client())

    assert result.extracted_text.count("### http://example.com/page2") == 1


def test_crawl_root_unreachable_returns_error_without_raising():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused", request=request)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    result = crawl_site("http://unreachable.example/", max_pages=5, client=client)

    assert result.pages_crawled == 0
    assert result.error is not None
    assert result.extracted_text == ""


def test_crawl_strips_cookie_legal_and_newsletter_noise():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            headers={"content-type": "text/html"},
            text="""
            <html><body>
            <h1>Home</h1>
            <p>Real page content.</p>
            <div id="cmplz-cookiebanner-container">
              <div class="cmplz-message">Gestionar consentimiento</div>
              <p>Utilizamos cookies para optimizar nuestro sitio web.</p>
            </div>
            <div class="cookie-consent-banner">Aceptar todas las cookies</div>
            <div class="privacy-policy-notice">Consulta nuestra política de privacidad.</div>
            <div class="newsletter-signup">Suscríbete a nuestra newsletter</div>
            <button>Enviar</button>
            <iframe src="https://maps.example.com"></iframe>
            </body></html>
            """,
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))
    result = crawl_site("http://cookies.example/", max_pages=1, client=client)

    assert "Real page content." in result.extracted_text
    assert "Gestionar consentimiento" not in result.extracted_text
    assert "Aceptar todas las cookies" not in result.extracted_text
    assert "política de privacidad" not in result.extracted_text
    assert "newsletter" not in result.extracted_text
    assert "Enviar" not in result.extracted_text


def test_crawl_prefers_main_content_container_over_sidebar():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            headers={"content-type": "text/html"},
            text="""
            <html><body>
            <div class="sidebar-widget">Artículos relacionados: A, B, C</div>
            <main>
              <h1>Producto</h1>
              <p>Descripción real del producto.</p>
            </main>
            <div id="related-posts">Quizá también te interese...</div>
            </body></html>
            """,
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))
    result = crawl_site("http://withmain.example/", max_pages=1, client=client)

    assert "Descripción real del producto." in result.extracted_text
    assert "Artículos relacionados" not in result.extracted_text
    assert "Quizá también te interese" not in result.extracted_text


def test_crawl_respects_max_stored_text_chars(monkeypatch):
    long_text = "A" * 1000

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            headers={"content-type": "text/html"},
            text=f"<html><body><p>{long_text}</p></body></html>",
        )

    monkeypatch.setattr("app.services.web_crawler.MAX_STORED_TEXT_CHARS", 50)
    client = httpx.Client(transport=httpx.MockTransport(handler))
    result = crawl_site("http://big.example/", max_pages=1, client=client)

    assert len(result.extracted_text) <= 50


def test_crawl_skips_english_page_when_spanish_alternate_exists():
    pages = {
        "http://multilang.example/": (
            "<html lang='es-ES'><head>"
            "<link rel='alternate' hreflang='es' href='http://multilang.example/'>"
            "<link rel='alternate' hreflang='en' href='http://multilang.example/en/'>"
            "</head><body><p>Contenido en español.</p>"
            "<a href='/en/'>English</a></body></html>"
        ),
        "http://multilang.example/en/": (
            "<html lang='en-US'><head>"
            "<link rel='alternate' hreflang='es' href='http://multilang.example/'>"
            "<link rel='alternate' hreflang='en' href='http://multilang.example/en/'>"
            "</head><body><p>Duplicate content in English.</p></body></html>"
        ),
    }

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, headers={"content-type": "text/html"}, text=pages[str(request.url)])

    client = httpx.Client(transport=httpx.MockTransport(handler))
    result = crawl_site("http://multilang.example/", max_pages=10, client=client)

    # Both pages are visited (so links reachable only from the English page
    # would still be discovered), but only the Spanish text is kept.
    assert result.pages_crawled == 2
    assert "Contenido en español." in result.extracted_text
    assert "Duplicate content in English." not in result.extracted_text


def test_crawl_never_fetches_privacy_policy_or_other_noise_pages():
    fetched_urls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        fetched_urls.append(url)
        if url == "http://noisepages.example/":
            return httpx.Response(
                200,
                headers={"content-type": "text/html"},
                text="""
                <html><body>
                <h1>Home</h1>
                <p>Real content.</p>
                <a href="/politica-privacidad/">Privacidad</a>
                <a href="/aviso-legal/">Aviso legal</a>
                <a href="/en/privacy-policy/">Privacy policy</a>
                <a href="/contacto/">Contacto</a>
                </body></html>
                """,
            )
        if url == "http://noisepages.example/contacto/":
            return httpx.Response(
                200,
                headers={"content-type": "text/html"},
                text="<html><body><h1>Contacto</h1><p>Escríbenos.</p></body></html>",
            )
        raise AssertionError(f"Should never fetch {url}")

    client = httpx.Client(transport=httpx.MockTransport(handler))
    result = crawl_site("http://noisepages.example/", max_pages=10, client=client)

    assert "politica-privacidad" not in " ".join(fetched_urls)
    assert "aviso-legal" not in " ".join(fetched_urls)
    assert "privacy-policy" not in " ".join(fetched_urls)
    assert result.pages_crawled == 2
    assert "Escríbenos." in result.extracted_text


def test_crawl_keeps_english_only_page_without_spanish_alternate():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            headers={"content-type": "text/html"},
            text="<html lang='en-US'><body><p>Only available in English.</p></body></html>",
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))
    result = crawl_site("http://onlyenglish.example/", max_pages=1, client=client)

    assert "Only available in English." in result.extracted_text
