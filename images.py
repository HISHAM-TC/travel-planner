from __future__ import annotations

import base64
import hashlib
import html
import io
import json
import logging
import os
import re
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageFont, UnidentifiedImageError

logger = logging.getLogger(__name__)
CACHE_DIR = Path(__file__).resolve().parent / "data" / "image_cache"
CACHE_VERSION = "v4"
IMAGE_TIMEOUT_SECONDS = 5
MAX_IMAGE_WIDTH = 1200
BLOCKED_IMAGE_TERMS = {
    "crowd", "event", "family", "festival", "girl", "girls", "human", "man",
    "men", "party", "people", "person", "portrait", "selfie", "wedding",
    "woman", "women",
}


def get_relevant_image(place_name: str, destination: str) -> dict[str, str]:
    """Return a cached, licensed, relevant JPEG or a generated local placeholder."""
    query = " ".join(part.strip() for part in (place_name, destination) if part and part.strip())
    cache_key = hashlib.sha256(f"{CACHE_VERSION}:{query.casefold()}".encode("utf-8")).hexdigest()
    cached = _load_cache(cache_key)
    if cached:
        return cached

    sources = (
        lambda: _from_wikipedia(place_name, destination),
        lambda: _from_commons(place_name, destination),
        lambda: _from_stock_api(place_name, destination),
    )
    for source in sources:
        try:
            image = source()
            if image is not None:
                _save_cache(cache_key, image)
                return image
        except (
            OSError,
            TimeoutError,
            ValueError,
            json.JSONDecodeError,
            urllib.error.URLError,
            UnidentifiedImageError,
        ) as exc:
            logger.info("Image lookup unavailable for %s: %s", query, exc)

    placeholder = _placeholder(place_name or destination)
    _save_cache(cache_key, placeholder)
    return placeholder


def _from_wikipedia(place_name: str, destination: str) -> dict[str, str] | None:
    if not place_name.strip():
        return None
    title = urllib.parse.quote(place_name.replace(" ", "_"), safe="_")
    summary = _request_json(f"https://en.wikipedia.org/api/rest_v1/page/summary/{title}")
    if not isinstance(summary, dict) or not _title_matches(summary.get("title", ""), place_name):
        return None
    image_info = summary.get("originalimage") or summary.get("thumbnail")
    image_url = image_info.get("source") if isinstance(image_info, dict) else None
    if not image_url:
        return None
    filename = urllib.parse.unquote(Path(urllib.parse.urlsplit(image_url).path).name).replace("_", " ")
    metadata = _commons_file_metadata(filename)
    if (
        metadata is None
        or not _title_matches(metadata["title"], place_name)
        or (destination.casefold() not in place_name.casefold() and not _title_matches(metadata["title"], f"{place_name} {destination}"))
        or _has_people_terms(metadata["title"], metadata.get("description", ""))
    ):
        return None
    return _asset_from_url(image_url, metadata)


def _from_commons(place_name: str, destination: str) -> dict[str, str] | None:
    queries = []
    specific_query = " ".join(part for part in (place_name.strip(), destination.strip()) if part)
    if specific_query:
        queries.append(specific_query)
    if (
        place_name.strip()
        and place_name.strip().casefold() != specific_query.casefold()
        and destination.strip().casefold() in place_name.strip().casefold()
    ):
        queries.append(place_name.strip())
    for query in queries:
        params = urllib.parse.urlencode(
            {
                "action": "query",
                "format": "json",
                "generator": "search",
                "gsrnamespace": 6,
                "gsrlimit": 8,
                "gsrsearch": f'file:"{query}" -people -portrait -selfie',
                "prop": "imageinfo",
                "iiprop": "url|extmetadata",
                "iiurlwidth": MAX_IMAGE_WIDTH,
            }
        )
        response = _request_json(f"https://commons.wikimedia.org/w/api.php?{params}")
        pages = response.get("query", {}).get("pages", {}) if isinstance(response, dict) else {}
        candidates = sorted(
            pages.values(),
            key=lambda page: _title_similarity(page.get("title", ""), query),
            reverse=True,
        )
        for candidate in candidates:
            title = candidate.get("title", "")
            if (
                not _title_matches(title, place_name)
                or not _title_matches(title, query)
                or _has_people_terms(title)
            ):
                continue
            image_info = (candidate.get("imageinfo") or [{}])[0]
            metadata = _commons_metadata(title, image_info.get("extmetadata", {}))
            if metadata is None or _has_people_terms(metadata.get("description", "")):
                continue
            image_url = image_info.get("thumburl") or image_info.get("url")
            if image_url:
                asset = _asset_from_url(image_url, metadata)
                if asset is not None:
                    return asset
    return None


def _commons_file_metadata(filename: str) -> dict[str, str] | None:
    title = filename if filename.lower().startswith("file:") else f"File:{filename}"
    params = urllib.parse.urlencode(
        {
            "action": "query",
            "format": "json",
            "titles": title,
            "prop": "imageinfo",
            "iiprop": "url|extmetadata",
            "iiurlwidth": MAX_IMAGE_WIDTH,
        }
    )
    response = _request_json(f"https://commons.wikimedia.org/w/api.php?{params}")
    pages = response.get("query", {}).get("pages", {}) if isinstance(response, dict) else {}
    for page in pages.values():
        info = (page.get("imageinfo") or [{}])[0]
        metadata = _commons_metadata(page.get("title", title), info.get("extmetadata", {}))
        if metadata:
            return metadata
    return None


def _commons_metadata(title: str, raw: dict[str, Any]) -> dict[str, str] | None:
    license_name = _metadata_text(raw.get("LicenseShortName"))
    if not license_name:
        return None
    author = _metadata_text(raw.get("Artist")) or "Author not listed"
    description = " ".join(
        value
        for value in (
            _metadata_text(raw.get("ImageDescription")),
            _metadata_text(raw.get("Categories")),
        )
        if value
    )
    page_title = title.replace(" ", "_")
    return {
        "title": title.removeprefix("File:"),
        "author": author,
        "license": license_name,
        "source": "Wikimedia Commons",
        "credit_url": "https://commons.wikimedia.org/wiki/"
        + urllib.parse.quote(page_title, safe="_:"),
        "description": description,
    }


def _from_stock_api(place_name: str, destination: str) -> dict[str, str] | None:
    unsplash_key = os.getenv("UNSPLASH_ACCESS_KEY")
    if unsplash_key:
        params = urllib.parse.urlencode({"query": f"{place_name} {destination}", "per_page": 8})
        response = _request_json(
            f"https://api.unsplash.com/search/photos?{params}",
            headers={"Authorization": f"Client-ID {unsplash_key}"},
        )
        for photo in response.get("results", []) if isinstance(response, dict) else []:
            description = photo.get("alt_description") or photo.get("description") or ""
            if not _title_matches(description, place_name) or _has_people_terms(description):
                continue
            user = photo.get("user", {})
            asset = _asset_from_url(
                photo.get("urls", {}).get("regular", ""),
                {
                    "title": description or place_name,
                    "author": user.get("name") or "Author not listed",
                    "license": "Unsplash License",
                    "source": "Unsplash",
                    "credit_url": user.get("links", {}).get("html", "https://unsplash.com/"),
                },
            )
            if asset:
                return asset

    pexels_key = os.getenv("PEXELS_API_KEY")
    if pexels_key:
        params = urllib.parse.urlencode({"query": f"{place_name} {destination}", "per_page": 8})
        response = _request_json(
            f"https://api.pexels.com/v1/search?{params}",
            headers={"Authorization": pexels_key},
        )
        for photo in response.get("photos", []) if isinstance(response, dict) else []:
            description = photo.get("alt") or ""
            if not _title_matches(description, place_name) or _has_people_terms(description):
                continue
            asset = _asset_from_url(
                photo.get("src", {}).get("large", ""),
                {
                    "title": description or place_name,
                    "author": photo.get("photographer") or "Author not listed",
                    "license": "Pexels License",
                    "source": "Pexels",
                    "credit_url": photo.get("url", "https://www.pexels.com/"),
                },
            )
            if asset:
                return asset
    return None


def _asset_from_url(image_url: str, metadata: dict[str, str]) -> dict[str, str] | None:
    if not image_url:
        return None
    request = urllib.request.Request(
        image_url,
        headers={"User-Agent": "TravelPlannerAgent/1.0 (licensed itinerary image; contact local app owner)"},
    )
    with urllib.request.urlopen(request, timeout=IMAGE_TIMEOUT_SECONDS) as response:
        raw_image = response.read()
    with Image.open(io.BytesIO(raw_image)) as source:
        source.thumbnail((MAX_IMAGE_WIDTH, MAX_IMAGE_WIDTH), Image.Resampling.LANCZOS)
        converted = source.convert("RGB")
        output = io.BytesIO()
        converted.save(output, format="JPEG", quality=80, optimize=True)
    return {
        "image_base64": base64.b64encode(output.getvalue()).decode("ascii"),
        **{key: value for key, value in metadata.items() if key != "description"},
    }


def _request_json(
    url: str,
    *,
    headers: dict[str, str] | None = None,
) -> Any:
    request_headers = {
        "User-Agent": "TravelPlannerAgent/1.0 (licensed itinerary images)",
        **(headers or {}),
    }
    request = urllib.request.Request(url, headers=request_headers)
    with urllib.request.urlopen(request, timeout=IMAGE_TIMEOUT_SECONDS) as response:
        return json.loads(response.read().decode("utf-8"))


def _metadata_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, dict):
        value = value.get("value", "")
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", "", str(value)))).strip()


def _normalized_tokens(value: str) -> set[str]:
    return {
        token
        for token in re.findall(r"[a-z0-9]+", value.casefold())
        if len(token) > 2 and token not in {"the", "and", "for", "from", "india"}
    }


def _title_matches(title: str, place_name: str) -> bool:
    return _title_similarity(title, place_name) >= 0.6


def _title_similarity(title: str, place_name: str) -> float:
    expected = _normalized_tokens(place_name)
    actual = _normalized_tokens(title)
    return len(expected & actual) / len(expected) if expected and actual else 0


def _has_people_terms(*values: str) -> bool:
    tokens = set().union(*(_normalized_tokens(value) for value in values))
    return bool(tokens & BLOCKED_IMAGE_TERMS)


def _placeholder(label: str) -> dict[str, str]:
    image = Image.new("RGB", (1200, 675), "#EEF2F6")
    draw = ImageDraw.Draw(image)
    for x in range(-675, 1300, 96):
        for y in range(-675, 800, 96):
            draw.arc((x, y, x + 192, y + 192), 0, 360, fill="#C7D2E0", width=4)
    font = _placeholder_font(56)
    draw.rounded_rectangle((56, 466, 1144, 606), radius=20, fill="#1D4ED8")
    safe_label = label.encode("ascii", "replace").decode("ascii")[:42]
    draw.text((82, 502), safe_label or "Travel itinerary", fill="#FFFFFF", font=font)
    output = io.BytesIO()
    image.save(output, format="JPEG", quality=80, optimize=True)
    return {
        "image_base64": base64.b64encode(output.getvalue()).decode("ascii"),
        "title": f"Generated placeholder for {label}",
        "author": "Generated locally",
        "license": "Local generated artwork",
        "source": "Generated placeholder",
        "credit_url": "",
    }


def _placeholder_font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    for font_path in (
        r"C:\Windows\Fonts\segoeui.ttf",
        r"C:\Windows\Fonts\arial.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ):
        try:
            return ImageFont.truetype(font_path, size)
        except OSError:
            continue
    return ImageFont.load_default()


def _load_cache(cache_key: str) -> dict[str, str] | None:
    image_path = CACHE_DIR / f"{cache_key}.jpg"
    metadata_path = CACHE_DIR / f"{cache_key}.json"
    try:
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        image_data = image_path.read_bytes()
        with Image.open(io.BytesIO(image_data)) as image:
            image.verify()
        return {"image_base64": base64.b64encode(image_data).decode("ascii"), **metadata}
    except (OSError, ValueError, json.JSONDecodeError, UnidentifiedImageError):
        return None


def _save_cache(cache_key: str, asset: dict[str, str]) -> None:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    image_path = CACHE_DIR / f"{cache_key}.jpg"
    metadata_path = CACHE_DIR / f"{cache_key}.json"
    image_path.write_bytes(base64.b64decode(asset["image_base64"]))
    metadata = {key: value for key, value in asset.items() if key != "image_base64"}
    metadata_path.write_text(json.dumps(metadata, ensure_ascii=False), encoding="utf-8")
