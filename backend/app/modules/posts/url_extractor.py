"""SSRF-safe URL fetching for blog capture (T036).

The extractor enforces defence-in-depth against server-side request forgery:

* scheme allow-list (http/https only) and no embedded credentials;
* per-hop DNS resolution with rejection of private / loopback / link-local /
  reserved / multicast IPv4 and IPv6 targets;
* a bounded redirect chain, each hop re-validated;
* connect/read timeouts and a streamed response-size cap so a hostile or huge
  target cannot exhaust memory;
* a content-type allow-list (HTML/text only) — media and binaries are refused.

``fetch_url`` returns raw HTML/text for the caller (worker) to hand to
Trafilatura.  All rejections raise :class:`UrlSecurityError` with a stable code.
"""

from __future__ import annotations

import ipaddress
import socket
from dataclasses import dataclass, field
from urllib.parse import urlparse, urlunparse

import httpx

MAX_REDIRECTS = 5
CONNECT_TIMEOUT = 5.0
READ_TIMEOUT = 10.0
MAX_BYTES = 5 * 1024 * 1024  # 5 MiB streamed cap
_ALLOWED_SCHEMES = {"http", "https"}
_ALLOWED_CONTENT_TYPES = ("text/html", "application/xhtml+xml", "text/plain")
_USER_AGENT = "aiassist-blog-capture/1.0 (+https://aiassist.local)"


class UrlSecurityError(Exception):
    def __init__(self, message: str, *, code: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass
class FetchResult:
    final_url: str
    status_code: int
    content_type: str
    text: str
    truncated: bool = False
    redirect_chain: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


def canonicalize_url(raw: str) -> str:
    """Validate scheme, strip credentials/fragment, and return a canonical URL."""
    parsed = urlparse(raw.strip())
    if parsed.scheme.lower() not in _ALLOWED_SCHEMES:
        raise UrlSecurityError(
            f"scheme '{parsed.scheme}' not allowed (http/https only)", code="scheme_not_allowed"
        )
    if parsed.username or parsed.password:
        raise UrlSecurityError("credentials in URL are not allowed", code="credentials_in_url")
    if not parsed.hostname:
        raise UrlSecurityError("URL has no host", code="no_host")
    # Drop fragment; keep query. Rebuild netloc without userinfo.
    netloc = parsed.hostname
    if parsed.port:
        netloc = f"{netloc}:{parsed.port}"
    return urlunparse(
        (
            parsed.scheme.lower(),
            netloc,
            parsed.path or "/",
            parsed.params,
            parsed.query,
            "",
        )
    )


def _ip_is_forbidden(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    return (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_multicast
        or ip.is_reserved
        or ip.is_unspecified
        or (
            isinstance(ip, ipaddress.IPv6Address)
            and ip.ipv4_mapped is not None
            and _ip_is_forbidden(ip.ipv4_mapped)
        )
    )


def assert_host_is_public(hostname: str) -> list[str]:
    """Resolve *hostname* and reject if any A/AAAA record is non-public.

    Returns the list of resolved IPs (as strings) for logging.  Rejects hosts
    that are themselves literal private IPs and hosts that resolve to any
    private/loopback/link-local/reserved address (DNS-rebinding defence).
    """
    # Literal IP host?
    try:
        literal = ipaddress.ip_address(hostname)
        if _ip_is_forbidden(literal):
            raise UrlSecurityError(f"host IP {hostname} is not public", code="ip_not_public")
        return [str(literal)]
    except ValueError:
        pass  # not a literal IP; resolve via DNS

    try:
        infos = socket.getaddrinfo(hostname, None, proto=socket.IPPROTO_TCP)
    except socket.gaierror as exc:
        raise UrlSecurityError(f"DNS resolution failed for {hostname}", code="dns_failure") from exc

    ips: list[str] = []
    for info in infos:
        addr = info[4][0]
        ip = ipaddress.ip_address(addr)
        if _ip_is_forbidden(ip):
            raise UrlSecurityError(
                f"host {hostname} resolves to non-public address {addr}", code="ip_not_public"
            )
        ips.append(str(ip))
    if not ips:
        raise UrlSecurityError(f"no addresses for {hostname}", code="dns_failure")
    return ips


# ---------------------------------------------------------------------------
# Fetch
# ---------------------------------------------------------------------------


def fetch_url(raw_url: str, *, max_bytes: int = MAX_BYTES) -> FetchResult:
    """Fetch *raw_url* safely, following at most ``MAX_REDIRECTS`` re-validated hops."""
    current = canonicalize_url(raw_url)
    chain: list[str] = []
    timeout = httpx.Timeout(READ_TIMEOUT, connect=CONNECT_TIMEOUT)

    with httpx.Client(follow_redirects=False, timeout=timeout, trust_env=False) as client:
        for _hop in range(MAX_REDIRECTS + 1):
            parsed = urlparse(current)
            assert_host_is_public(parsed.hostname or "")
            chain.append(current)
            try:
                with client.stream(
                    "GET",
                    current,
                    headers={
                        "User-Agent": _USER_AGENT,
                        "Accept": "text/html,*/*;q=0.1",
                    },
                ) as resp:
                    if resp.is_redirect:
                        location = resp.headers.get("location")
                        if not location:
                            raise UrlSecurityError("redirect without Location", code="bad_redirect")
                        current = canonicalize_url(httpx.URL(current).join(location).__str__())
                        continue
                    ctype = resp.headers.get("content-type", "").split(";")[0].strip().lower()
                    if ctype and not any(ctype == a for a in _ALLOWED_CONTENT_TYPES):
                        raise UrlSecurityError(
                            f"content-type '{ctype}' not extractable",
                            code="unsupported_content_type",
                        )
                    declared = resp.headers.get("content-length")
                    if declared and declared.isdigit() and int(declared) > max_bytes:
                        raise UrlSecurityError("response too large", code="response_too_large")
                    chunks: list[bytes] = []
                    total = 0
                    truncated = False
                    for chunk in resp.iter_bytes():
                        total += len(chunk)
                        if total > max_bytes:
                            truncated = True
                            chunks.append(chunk[: max_bytes - (total - len(chunk))])
                            break
                        chunks.append(chunk)
                    body = b"".join(chunks)
                    encoding = resp.encoding or "utf-8"
                    text = body.decode(encoding, errors="replace")
                    return FetchResult(
                        final_url=str(resp.url),
                        status_code=resp.status_code,
                        content_type=ctype or "text/html",
                        text=text,
                        truncated=truncated,
                        redirect_chain=chain,
                    )
            except httpx.TimeoutException as exc:
                raise UrlSecurityError("request timed out", code="timeout") from exc
            except httpx.HTTPError as exc:
                raise UrlSecurityError(f"fetch failed: {exc}", code="fetch_failed") from exc

    raise UrlSecurityError("too many redirects", code="too_many_redirects")


def extract_article(html: str, url: str) -> dict[str, str | None]:
    """Extract title/text/markdown from HTML via Trafilatura (best effort)."""
    import trafilatura

    result: dict[str, str | None] = {
        "title": None,
        "text": None,
        "markdown": None,
        "author": None,
        "site": None,
    }
    md = trafilatura.extract(
        html,
        url=url,
        output_format="markdown",
        include_links=True,
        include_images=True,
        favor_precision=True,
    )
    result["markdown"] = md
    txt = trafilatura.extract(html, url=url, output_format="txt", favor_precision=True)
    result["text"] = txt
    meta = trafilatura.extract_metadata(html, default_url=url)
    if meta is not None:
        result["title"] = getattr(meta, "title", None)
        result["author"] = getattr(meta, "author", None)
        result["site"] = getattr(meta, "sitename", None)
    return result
