from __future__ import annotations

from collections.abc import Iterable, Mapping
from urllib.parse import urlsplit


_SOURCE_ICON_BY_HOST = {
    "store.steampowered.com": "brand-steam",
    "steampowered.com": "brand-steam",
    "wiki.supercombo.gg": "brand-supercombo",
    "supercombo.gg": "brand-supercombo",
    "blazblue.wiki": "brand-blazblue",
    "dustloop.com": "brand-dustloop",
    "wiki.gbl.gg": "brand-gbl",
    "gbl.gg": "brand-gbl",
    "tekken.com": "brand-tekken",
    "playstation.com": "brand-playstation",
    "blog.playstation.com": "brand-playstation",
    "game.capcom.com": "brand-capcom",
    "capcom.com": "brand-capcom",
    "supabase.com": "brand-supabase",
}

_BRAND_NAME_BY_ICON = {
    "brand-steam": "Steam",
    "brand-supercombo": "SuperCombo",
    "brand-blazblue": "BlazBlue Wiki",
    "brand-dustloop": "Dustloop",
    "brand-gbl": "GBL Wiki",
    "brand-tekken": "TEKKEN",
    "brand-playstation": "PlayStation",
    "brand-capcom": "Capcom",
    "brand-supabase": "Supabase",
}


def _source_host(url: str | None) -> str | None:
    if not url:
        return None
    try:
        host = (urlsplit(url).hostname or "").casefold().rstrip(".")
    except ValueError:
        return None
    if host.startswith("www."):
        host = host[4:]
    return host or None


def source_icon_name(url: str | None) -> str:
    """Return the local brand icon for a source URL, or the generic link icon."""
    return _SOURCE_ICON_BY_HOST.get(_source_host(url), "external-link")


def source_brand_name(url: str | None) -> str:
    """Return the concise brand name used for source-link context and tooltips."""
    icon_name = source_icon_name(url)
    return _BRAND_NAME_BY_ICON.get(icon_name, _source_host(url) or "external site")


def game_reference_label(url: str | None) -> str:
    """Name Steam destinations explicitly while preserving honest fallback copy."""
    return "Open on Steam" if source_icon_name(url) == "brand-steam" else "Open game reference"


def _source_collapse_key(url: str) -> str:
    """Group only known alternate URLs that describe the same source destination."""
    parsed = urlsplit(url)
    host = _source_host(url)
    path = parsed.path.rstrip("/").casefold()

    if host == "tekken.com" and (path == "/fighters" or path.startswith("/fighters/")):
        return "tekken:fighters"

    if host in {"playstation.com", "blog.playstation.com"} and "marvel-tokon-fighting-souls" in path:
        return "playstation:marvel-tokon-fighting-souls"

    return url


def _source_display_label(collapse_key: str, labels: list[str]) -> str:
    if collapse_key == "tekken:fighters":
        return "Official fighter page"
    if collapse_key == "playstation:marvel-tokon-fighting-souls":
        return "Official game page"
    if {"Description source", "Artwork source"}.issubset(labels):
        return "Character source"
    return labels[0] if len(labels) == 1 else "Source"


def _source_detail_label(labels: list[str]) -> str:
    detail_labels = list(labels)
    if {"Description source", "Artwork source"}.issubset(detail_labels):
        detail_labels = [
            "Description and artwork source",
            *(
                label
                for label in detail_labels
                if label not in {"Description source", "Artwork source"}
            ),
        ]
    return "; ".join(detail_labels)


def collapse_source_links(
    items: Iterable[Mapping[str, str | None]],
) -> list[dict[str, str]]:
    """Render one source link per exact or known-equivalent URL group."""
    collapsed: list[dict[str, str]] = []
    index_by_key: dict[str, int] = {}
    labels_by_index: list[list[str]] = []

    for item in items:
        url = item.get("url")
        label = item.get("label")
        if not url or not label:
            continue

        collapse_key = _source_collapse_key(url)
        existing_index = index_by_key.get(collapse_key)
        if existing_index is None:
            index_by_key[collapse_key] = len(collapsed)
            labels = [label]
            collapsed.append(
                {
                    "url": url,
                    "label": _source_display_label(collapse_key, labels),
                    "detail_label": _source_detail_label(labels),
                }
            )
            labels_by_index.append(labels)
            continue

        current = collapsed[existing_index]
        labels = labels_by_index[existing_index]
        labels.append(label)
        current["label"] = _source_display_label(collapse_key, labels)
        current["detail_label"] = _source_detail_label(labels)

    return collapsed
