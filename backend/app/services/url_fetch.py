"""Fetching a URL the user supplies, safely.

The security problem here is server-side request forgery: a user-supplied URL is a
request *this server* makes, from inside the network perimeter. So the fetcher:

  * accepts http and https only;
  * resolves the hostname itself and rejects private, loopback, link-local and
    cloud-metadata addresses before connecting;
  * re-checks after every redirect, because a public host can redirect to 169.254.169.254;
  * caps response size and time;
  * never returns raw HTML to the caller — only extracted text.
"""

from __future__ import annotations

import ipaddress
import socket
from dataclasses import dataclass
from urllib.parse import urlparse

import httpx

from app.core.config import settings
from app.core.logging import get_logger
from app.services.ingest import ExtractionResult, IngestError, validate_text

logger = get_logger(__name__)

ALLOWED_SCHEMES = frozenset({"http", "https"})
MAX_REDIRECTS = 5

#: Cloud instance-metadata endpoints. Reachable, unauthenticated, and full of credentials
#: on every major provider — the classic SSRF target.
_METADATA_HOSTS = frozenset({"169.254.169.254", "metadata.google.internal", "100.100.100.200"})


class FetchError(IngestError):
    pass


@dataclass(slots=True)
class FetchedPage:
    url: str
    final_url: str
    status_code: int
    content_type: str
    title: str | None
    text: str
    byte_size: int


def _is_blocked_address(address: str) -> bool:
    try:
        ip = ipaddress.ip_address(address)
    except ValueError:
        return True  # unparseable: refuse
    return (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_reserved
        or ip.is_multicast
        or ip.is_unspecified
        or address in _METADATA_HOSTS
    )


def validate_url(url: str) -> str:
    """Check scheme and resolve the host, rejecting anything that points inward."""
    parsed = urlparse(url)

    if parsed.scheme not in ALLOWED_SCHEMES:
        raise FetchError("Only http and https URLs can be fetched.")
    if not parsed.hostname:
        raise FetchError("That URL has no hostname.")

    hostname = parsed.hostname.lower()
    if hostname in _METADATA_HOSTS or hostname in ("localhost", "127.0.0.1", "::1"):
        raise FetchError("That address cannot be fetched.")

    try:
        resolved = socket.getaddrinfo(hostname, parsed.port or (443 if parsed.scheme == "https" else 80))
    except socket.gaierror as exc:
        raise FetchError(f"The hostname {hostname} could not be resolved.") from exc

    for family, _type, _proto, _canonname, sockaddr in resolved:
        address = sockaddr[0]
        if _is_blocked_address(address):
            logger.warning("url_fetch.blocked", url=url, resolved=address)
            raise FetchError(
                "That URL resolves to a private or reserved network address and will not "
                "be fetched."
            )
    return url


def fetch_url(url: str) -> FetchedPage:
    validate_url(url)

    headers = {
        "User-Agent": (
            "Starcode/1.0 (ancient text analysis; +https://github.com/starcode)"
        ),
        "Accept": "text/html,application/xhtml+xml,text/plain,application/pdf;q=0.9",
        "Accept-Language": "en,*;q=0.5",
    }

    current = url
    # Redirects are followed manually so each hop can be re-validated. httpx's own
    # follow_redirects would jump to a private address without asking.
    for _ in range(MAX_REDIRECTS):
        with httpx.Client(
            timeout=settings.URL_FETCH_TIMEOUT_SECONDS,
            follow_redirects=False,
            headers=headers,
        ) as client:
            try:
                response = client.get(current)
            except httpx.TimeoutException as exc:
                raise FetchError(f"The request to {current} timed out.") from exc
            except httpx.HTTPError as exc:
                raise FetchError(f"Could not fetch {current}: {exc}") from exc

        if response.status_code in (301, 302, 303, 307, 308):
            location = response.headers.get("location")
            if not location:
                raise FetchError("The server sent a redirect with no destination.")
            current = str(httpx.URL(current).join(location))
            validate_url(current)
            continue
        break
    else:
        raise FetchError(f"Too many redirects (more than {MAX_REDIRECTS}).")

    if response.status_code >= 400:
        raise FetchError(f"The server returned HTTP {response.status_code} for {current}.")

    content = response.content
    if len(content) > settings.URL_FETCH_MAX_BYTES:
        raise FetchError(
            f"That page is larger than the {settings.URL_FETCH_MAX_BYTES / 1_048_576:.0f} MB "
            "fetch limit."
        )

    content_type = response.headers.get("content-type", "").split(";")[0].strip()

    if content_type == "application/pdf":
        from app.services.ingest import extract_from_pdf

        extracted = extract_from_pdf(content, urlparse(current).path or "document.pdf")
        return FetchedPage(
            url=url,
            final_url=current,
            status_code=response.status_code,
            content_type=content_type,
            title=extracted.title,
            text=extracted.text,
            byte_size=len(content),
        )

    charset = response.encoding or "utf-8"
    try:
        html = content.decode(charset, errors="replace")
    except LookupError:
        html = content.decode("utf-8", errors="replace")

    if content_type in ("text/plain", "text/markdown"):
        return FetchedPage(
            url=url,
            final_url=current,
            status_code=response.status_code,
            content_type=content_type,
            title=None,
            text=validate_text(html),
            byte_size=len(content),
        )

    title, text = extract_readable_text(html)
    return FetchedPage(
        url=url,
        final_url=current,
        status_code=response.status_code,
        content_type=content_type or "text/html",
        title=title,
        text=validate_text(text),
        byte_size=len(content),
    )


def extract_readable_text(html: str) -> tuple[str | None, str]:
    """Strip markup and chrome, keeping the readable body.

    Uses selectolax when available (fast, lenient with the malformed markup that archives
    and library sites tend to serve) and falls back to a regex strip otherwise.
    """
    try:
        from selectolax.parser import HTMLParser
    except ImportError:
        return _regex_strip(html)

    tree = HTMLParser(html)
    title = None
    if tree.head is not None:
        node = tree.css_first("title")
        if node:
            title = node.text(strip=True)

    for selector in (
        "script", "style", "noscript", "nav", "header", "footer", "aside",
        "form", "iframe", "svg", "button", "[aria-hidden='true']",
    ):
        for node in tree.css(selector):
            node.decompose()

    # Prefer a semantic content container when the page offers one; these pages are
    # usually mostly navigation.
    body = None
    for selector in ("article", "main", "[role='main']", "#content", ".content"):
        node = tree.css_first(selector)
        if node and len(node.text(strip=True)) > 200:
            body = node
            break
    body = body or tree.body or tree

    text = body.text(separator="\n", strip=True)
    return title, text


def _regex_strip(html: str) -> tuple[str | None, str]:
    import re

    title_match = re.search(r"<title[^>]*>(.*?)</title>", html, re.IGNORECASE | re.DOTALL)
    title = title_match.group(1).strip() if title_match else None
    cleaned = re.sub(
        r"<(script|style|noscript)[^>]*>.*?</\1>", " ", html, flags=re.IGNORECASE | re.DOTALL
    )
    cleaned = re.sub(r"<br\s*/?>|</p>|</div>|</h[1-6]>", "\n", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"<[^>]+>", " ", cleaned)

    import html as html_module

    cleaned = html_module.unescape(cleaned)
    return title, re.sub(r"\n\s*\n\s*\n+", "\n\n", cleaned)


def fetch_as_extraction(url: str) -> ExtractionResult:
    page = fetch_url(url)
    return ExtractionResult(
        text=page.text,
        source_kind="url",
        mime_type=page.content_type,
        title=page.title,
        metadata={
            "url": page.url,
            "final_url": page.final_url,
            "status_code": page.status_code,
            "byte_size": page.byte_size,
        },
        warnings=(
            [
                "The text was extracted from a web page. Page transcriptions vary in "
                "quality and may differ from a critical edition; check the site's stated "
                "source before relying on the wording."
            ]
        ),
    )


__all__ = ["FetchError", "FetchedPage", "validate_url", "fetch_url", "fetch_as_extraction",
           "extract_readable_text"]
