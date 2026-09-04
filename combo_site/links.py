from __future__ import annotations

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
