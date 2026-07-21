import html
import re
from collections.abc import Callable, Iterable
from urllib.parse import urljoin, urlsplit

_IMAGE_EXTENSIONS = (".png", ".jpg", ".jpeg", ".webp", ".gif", ".avif")
_MARKDOWN_IMAGE = re.compile(r"!\[[^\]]*\]\((?:<)?([^)>\s]+)(?:>)?(?:\s+['\"][^'\"]*['\"])?\)")
_HTML_IMAGE = re.compile(r"<img\b[^>]*?\bsrc\s*=\s*['\"]([^'\"]+)['\"]", re.IGNORECASE)
_EXCLUDED_MARKERS = (
    "badge",
    "shield",
    "logo",
    "icon",
    "avatar",
    "favicon",
    "button",
    "sponsor",
    "coverage",
)
_PREFERRED_MARKERS = (
    "screenshot",
    "screen-shot",
    "preview",
    "demo",
    "showcase",
    "hero",
    "cover",
    "landing",
)
_MEDIA_DIRECTORIES = (
    "screenshots/",
    "screenshot/",
    "docs/",
    "public/",
    "assets/",
    "images/",
    "img/",
    "static/",
    "src/assets/",
)


def is_image_path(path: str) -> bool:
    clean = path.casefold().split("?", 1)[0].split("#", 1)[0]
    return clean.endswith(_IMAGE_EXTENSIONS)


def is_probable_template_image(path: str) -> bool:
    normalized = path.casefold().lstrip("./")
    if not is_image_path(normalized):
        return False
    filename = normalized.rsplit("/", 1)[-1]
    if any(marker in filename for marker in _EXCLUDED_MARKERS):
        return False
    return any(marker in normalized for marker in (*_PREFERRED_MARKERS, *_MEDIA_DIRECTORIES))


def is_readme_media_candidate(path: str) -> bool:
    normalized = path.casefold().split("?", 1)[0].split("#", 1)[0]
    if not is_image_path(normalized):
        return False
    filename = normalized.rsplit("/", 1)[-1]
    return not any(marker in filename for marker in _EXCLUDED_MARKERS)


def extract_readme_image_references(text: str | None) -> list[str]:
    if not text:
        return []
    decoded = html.unescape(text)
    candidates = [*(_MARKDOWN_IMAGE.findall(decoded)), *(_HTML_IMAGE.findall(decoded))]
    result: list[str] = []
    for raw in candidates:
        value = raw.strip().strip("<>")
        if not value or value.startswith(("data:", "javascript:")):
            continue
        if is_image_path(value) and value not in result:
            result.append(value)
        if len(result) >= 24:
            break
    return result


def normalize_media_urls(
    references: Iterable[str],
    *,
    absolute_base: str | None = None,
    relative_resolver: Callable[[str], str] | None = None,
    limit: int = 20,
) -> list[str]:
    result: list[str] = []
    for reference in references:
        value = reference.strip()
        parsed = urlsplit(value)
        if parsed.scheme in {"http", "https"}:
            url = value if parsed.scheme == "https" else "https://" + value.removeprefix("http://")
        elif relative_resolver:
            url = relative_resolver(value)
        elif absolute_base:
            url = urljoin(absolute_base.rstrip("/") + "/", value)
        else:
            continue
        if not url.startswith("https://") or url in result:
            continue
        result.append(url)
        if len(result) >= limit:
            break
    return result


def merge_media_urls(*groups: Iterable[str], limit: int = 20) -> list[str]:
    result: list[str] = []
    for group in groups:
        for url in group:
            if url.startswith("https://") and url not in result:
                result.append(url)
                if len(result) >= limit:
                    return result
    return result
