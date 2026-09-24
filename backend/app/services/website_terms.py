from __future__ import annotations

import hashlib
import ipaddress
import socket
from dataclasses import dataclass
from html.parser import HTMLParser
from urllib.parse import urljoin, urlparse

import httpx


@dataclass
class WebsiteTermsResult:
    status: str
    url: str
    final_url: str = ""
    text: str = ""
    content_hash: str = ""
    message: str = ""


class _TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []
        self.ignored = 0

    def handle_starttag(self, tag: str, attrs) -> None:
        if tag.lower() in {"script", "style", "noscript", "svg"}:
            self.ignored += 1

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() in {"script", "style", "noscript", "svg"} and self.ignored:
            self.ignored -= 1

    def handle_data(self, data: str) -> None:
        if not self.ignored and data.strip():
            self.parts.append(data.strip())


def _validate_public_url(url: str) -> None:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError("仅允许有效的 HTTP/HTTPS 官网地址")
    if parsed.username or parsed.password:
        raise ValueError("官网地址不得包含登录凭据")
    for info in socket.getaddrinfo(parsed.hostname, parsed.port or (443 if parsed.scheme == "https" else 80), type=socket.SOCK_STREAM):
        address = ipaddress.ip_address(info[4][0])
        if address.is_private or address.is_loopback or address.is_link_local or address.is_reserved or address.is_multicast or address.is_unspecified:
            raise ValueError("官网地址解析到非公网地址，已阻止抓取")


def fetch_website_terms(url: str, max_bytes: int = 2_000_000) -> WebsiteTermsResult:
    current = url.strip()
    try:
        with httpx.Client(timeout=20, follow_redirects=False, headers={"User-Agent": "QixiContractReview/1.0"}) as client:
            for _ in range(4):
                _validate_public_url(current)
                with client.stream("GET", current) as response:
                    if response.status_code in {301, 302, 303, 307, 308}:
                        location = response.headers.get("location")
                        if not location:
                            raise ValueError("官网条款重定向缺少目标地址")
                        current = urljoin(current, location)
                        continue
                    response.raise_for_status()
                    content_type = response.headers.get("content-type", "").lower()
                    if not any(kind in content_type for kind in ("text/", "application/xhtml+xml")):
                        raise ValueError(f"官网条款返回不支持的内容类型：{content_type or 'unknown'}")
                    chunks: list[bytes] = []
                    size = 0
                    for chunk in response.iter_bytes():
                        size += len(chunk)
                        if size > max_bytes:
                            raise ValueError("官网条款页面超过2MB抓取上限")
                        chunks.append(chunk)
                    raw = b"".join(chunks)
                    encoding = response.encoding or "utf-8"
                    body = raw.decode(encoding, errors="replace")
                    if "html" in content_type or "<html" in body[:1000].lower():
                        parser = _TextExtractor()
                        parser.feed(body)
                        text = "\n".join(parser.parts)
                    else:
                        text = body
                    text = "\n".join(line.strip() for line in text.splitlines() if line.strip())[:120_000]
                    if len(text) < 30:
                        raise ValueError("官网条款未抽取到足够文本")
                    return WebsiteTermsResult(status="已抓取", url=url, final_url=current, text=text, content_hash=hashlib.sha256(text.encode("utf-8")).hexdigest(), message=f"已固化 {len(text)} 字符")
            raise ValueError("官网条款重定向次数过多")
    except Exception as exc:
        return WebsiteTermsResult(status="抓取失败", url=url, final_url=current, message=str(exc)[:480])
