"""Bounded public-web chapter image discovery and staged page imports."""
import ipaddress
import socket
import time
import warnings
from html.parser import HTMLParser
from io import BytesIO
from pathlib import Path
import tempfile
from urllib.parse import urljoin, urlsplit, urlunsplit

import urllib3
from PIL import Image, ImageOps
from django.core import signing

MAX_PAGES = 300
MAX_IMAGE = 20 * 1024 * 1024
MAX_TOTAL = 500 * 1024 * 1024


def public_url(url):
    if not isinstance(url, str) or len(url) > 2048 or any(ord(c) < 33 for c in url):
        raise ValueError("Invalid URL")
    parts = urlsplit(url)
    if parts.scheme not in ("http", "https") or not parts.hostname or parts.username or parts.password:
        raise ValueError("Use a public HTTP or HTTPS chapter URL")
    if parts.port not in (None, 80, 443):
        raise ValueError("Only standard web ports are supported")
    return parts


def fetch_public(url, limit):
    """Pin validated DNS addresses on the connection, retaining TLS hostname checks."""
    deadline = time.monotonic() + 30
    for _ in range(5):
        parts = public_url(url)
        host = parts.hostname.encode("idna").decode("ascii")
        port = parts.port or (443 if parts.scheme == "https" else 80)
        addresses = {item[4][0] for item in socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)}
        if not addresses or any(not ipaddress.ip_address(ip).is_global for ip in addresses):
            raise ValueError("Only public internet addresses are allowed")
        address = sorted(addresses)[0]
        options = {"timeout": urllib3.Timeout(connect=8, read=8), "maxsize": 1}
        if parts.scheme == "https":
            pool = urllib3.HTTPSConnectionPool(address, port, server_hostname=host,
                assert_hostname=host, cert_reqs="CERT_REQUIRED", **options)
        else:
            pool = urllib3.HTTPConnectionPool(address, port, **options)
        response = None
        try:
            path = urlunsplit(("", "", parts.path or "/", parts.query, ""))
            response = pool.urlopen("GET", path, headers={"Host": parts.netloc,
                "User-Agent": "TranslatorStudio/1.0", "Accept-Encoding": "identity"},
                preload_content=False, redirect=False, retries=False)
            if response.status in (301, 302, 303, 307, 308):
                location = response.headers.get("Location")
                if not location:
                    raise ValueError("Invalid redirect")
                url = urljoin(url, location)
                continue
            if response.status != 200:
                raise ValueError(f"Website returned HTTP {response.status}")
            if response.headers.get("Content-Encoding", "identity") != "identity":
                raise ValueError("Compressed responses are not supported")
            chunks, size = [], 0
            while True:
                if time.monotonic() > deadline:
                    raise ValueError("Download timed out")
                chunk = response.read(65536, decode_content=False)
                if not chunk:
                    break
                size += len(chunk)
                if size > limit:
                    raise ValueError("Download exceeds the size limit")
                chunks.append(chunk)
            return b"".join(chunks), url, response.headers.get("Content-Type", "")
        finally:
            if response:
                response.close()
            pool.close()
    raise ValueError("Too many redirects")


class ChapterImages(HTMLParser):
    def __init__(self, base):
        super().__init__(convert_charrefs=True)
        self.base = base
        self.images = []
        self.seen = set()
        self.total_found = 0
        self.truncated = False

    def handle_starttag(self, tag, attrs):
        if tag != "img":
            return
        attrs = dict(attrs)
        source = next((attrs.get(k, "").strip() for k in
            ("data-src", "data-lazy-src", "data-original", "data-url", "src")
            if attrs.get(k, "").strip() and not attrs[k].startswith("data:")), "")
        if not source:
            srcset = attrs.get("data-srcset") or attrs.get("srcset") or ""
            source = srcset.split(",")[-1].strip().split(" ")[0]
        if not source:
            return
        url = urljoin(self.base, source)
        try:
            public_url(url)
        except ValueError:
            return
        if url in self.seen:
            return
        self.seen.add(url)
        self.total_found += 1
        if len(self.images) < MAX_PAGES:
            self.images.append({"url": url, "label": attrs.get("alt", "")[:150]})
        else:
            self.truncated = True


def discover_chapter(url, project=None):
    """Preview-first discovery: no project required.

    When `project` is given (workspace Link modal), the token is bound to
    that project id as before. When None (Add Project modal), the token
    carries only the URL list so it can be used after the project is
    created — avoiding the chicken-egg double-fetch.
    """
    public_url(url)
    data, final_url, content_type = fetch_public(url, 2 * 1024 * 1024)
    if "html" not in content_type.lower():
        raise ValueError("Expected a chapter webpage containing images")
    parser = ChapterImages(final_url)
    parser.feed(data.decode("utf-8", errors="replace"))
    if not parser.images:
        raise ValueError("No page images found. Login-protected or JavaScript-only readers may not be supported.")
    payload: dict = {"urls": [im["url"] for im in parser.images]}
    if project is not None:
        payload["project"] = str(project.pk)
    token = signing.dumps(payload, salt="chapter-pages", compress=True)
    result: dict = {"images": parser.images, "token": token}
    if parser.truncated:
        result["truncated"] = True
        result["total_found"] = parser.total_found
    return result


def discover(project, url):
    return discover_chapter(url, project=project)


def selected_urls(project, token, indices):
    try:
        data = signing.loads(token, salt="chapter-pages", max_age=1800)
    except signing.BadSignature as exc:
        raise ValueError("Page selection expired; load the link again") from exc
    # Tokens minted by the global preview flow carry no project binding —
    # accept them for any project. Project-bound tokens must still match.
    if data.get("project") is not None and data["project"] != str(project.pk):
        raise ValueError("Page selection belongs to another project")
    if not indices or len(indices) > MAX_PAGES or len(set(indices)) != len(indices):
        raise ValueError("Select unique page images")
    if any(i < 0 or i >= len(data["urls"]) for i in indices):
        raise ValueError("Invalid page selection")
    return [data["urls"][i] for i in indices]


def _original_extension(data: bytes, url: str, pil_format: str | None) -> str:
    """Best-effort original extension so archival copies keep their type."""
    fmt = (pil_format or "").upper()
    if fmt in ("JPEG", "JPG"):
        return ".jpg"
    if fmt in ("PNG", "WEBP", "GIF"):
        return "." + fmt.lower()
    low = url.split("?")[0].lower()
    for ext in (".jpg", ".jpeg", ".png", ".webp", ".gif"):
        if low.endswith(ext):
            return ".jpg" if ext == ".jpeg" else ext
    # Magic-byte fallback when URL and PIL disagree.
    if data[:3] == b"\xff\xd8\xff":
        return ".jpg"
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return ".png"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return ".webp"
    if data[:6] in (b"GIF87a", b"GIF89a"):
        return ".gif"
    return ".jpg"


def run_import_pages(ctx):
    from .page_sources import append_pages
    total = 0
    deadline = time.monotonic() + 600
    urls = ctx.job.params["urls"]
    with tempfile.TemporaryDirectory() as stage:
        files = []
        originals = []
        for index, url in enumerate(urls):
            ctx.progress(index / len(urls) * .9, f"Downloading page {index + 1}/{len(urls)}")
            if time.monotonic() > deadline:
                raise ValueError("Chapter import timed out")
            data, _, _ = fetch_public(url, MAX_IMAGE)
            total += len(data)
            if total > MAX_TOTAL:
                raise ValueError("Chapter exceeds 500 MB")
            with warnings.catch_warnings():
                warnings.simplefilter("error", Image.DecompressionBombWarning)
                with Image.open(BytesIO(data)) as image:
                    if image.format not in ("JPEG", "PNG", "WEBP", "GIF") or image.width * image.height > 40_000_000:
                        raise ValueError("Unsupported or oversized page image")
                    pil_format = image.format
                    image.load()
                    image = ImageOps.exif_transpose(image).convert("RGB")
                    image.thumbnail((4000, 16000), Image.Resampling.LANCZOS)
                    path = Path(stage) / f"{index}.jpg"
                    image.save(path, quality=95)
                    files.append(path)
            # Keep the exact source bytes alongside the standardized JPG so
            # the project preserves original quality for download/export.
            ext = _original_extension(data, url, pil_format)
            opath = Path(stage) / f"{index}_original{ext}"
            opath.write_bytes(data)
            originals.append(opath)
        ctx.check_cancelled()
        pages = append_pages(ctx.job.project, files, originals)
    return {"imported": pages}
