"""Strict geography filter for region-scoped queries.

Drops companies that are *clearly* headquartered outside the requested geography
(e.g. a Chinese or Australian company in a 'Europe' or 'US' landscape). Conservative
by design: it only rejects when there is positive evidence of a different country
(HQ statement or a country-code TLD) AND no evidence of presence in the target.
Companies with no geo signal are kept (we don't prune on absence). Seeds are exempt.
"""
from __future__ import annotations

import re
from typing import Any

# country-code TLD -> canonical country name
_CCTLD_COUNTRY: dict[str, str] = {
    "au": "australia", "cn": "china", "in": "india", "us": "united states",
    "uk": "united kingdom", "de": "germany", "fr": "france", "it": "italy",
    "es": "spain", "nl": "netherlands", "se": "sweden", "pl": "poland",
    "ca": "canada", "jp": "japan", "kr": "south korea", "tw": "taiwan",
    "br": "brazil", "mx": "mexico", "ru": "russia", "tr": "turkey",
    "ch": "switzerland", "at": "austria", "be": "belgium", "dk": "denmark",
    "fi": "finland", "no": "norway", "ie": "ireland", "pt": "portugal",
    "cz": "czech republic", "ae": "uae", "za": "south africa", "sg": "singapore",
}

# Region -> member countries (lowercase canonical names)
_EUROPE = {
    "spain", "france", "italy", "germany", "united kingdom", "netherlands",
    "sweden", "poland", "switzerland", "austria", "belgium", "denmark",
    "finland", "norway", "ireland", "portugal", "czech republic", "greece",
    "hungary", "romania", "slovakia", "slovenia", "croatia", "luxembourg",
    "estonia", "latvia", "lithuania", "bulgaria",
}
_REGION_COUNTRIES: dict[str, set[str]] = {
    "europe": _EUROPE,
    "eu": _EUROPE,
    "european union": _EUROPE,
    "north america": {"united states", "canada", "mexico"},
    "apac": {"china", "japan", "south korea", "india", "taiwan", "singapore", "australia"},
    "asia": {"china", "japan", "south korea", "india", "taiwan", "singapore"},
}

_COUNTRY_ALIASES: dict[str, str] = {
    "us": "united states", "u.s.": "united states", "u.s.a": "united states",
    "usa": "united states", "america": "united states",
    "uk": "united kingdom", "gb": "united kingdom", "britain": "united kingdom",
    "uae": "uae", "prc": "china",
}

# _HQ_PATTERNS ("headquartered in X") very often captures a city, not a country name
# (e.g. "headquartered in Kolkata") - infer_company_country previously discarded any
# non-country string outright, silently losing the HQ signal for exactly the companies
# it was extracted for. Major cities for the most common source/target countries only;
# not exhaustive by design (real user report: Indian manufacturers with city-only HQ
# text were being kept in a "Europe" run because their real HQ signal got dropped here).
_CITY_COUNTRY: dict[str, str] = {
    "kolkata": "india", "calcutta": "india", "mumbai": "india", "bombay": "india",
    "delhi": "india", "new delhi": "india", "bengaluru": "india", "bangalore": "india",
    "chennai": "india", "madras": "india", "pune": "india", "hyderabad": "india",
    "ahmedabad": "india", "surat": "india", "vadodara": "india", "rajkot": "india",
    "indore": "india", "jaipur": "india", "noida": "india", "gurgaon": "india",
    "gurugram": "india", "shanghai": "china", "beijing": "china", "shenzhen": "china",
    "guangzhou": "china", "taipei": "taiwan", "tokyo": "japan", "osaka": "japan",
    "seoul": "south korea", "sydney": "australia", "melbourne": "australia",
    "berlin": "germany", "munich": "germany", "hamburg": "germany",
    "paris": "france", "milan": "italy", "rome": "italy", "madrid": "spain",
    "barcelona": "spain", "amsterdam": "netherlands", "rotterdam": "netherlands",
    "london": "united kingdom", "manchester": "united kingdom",
}


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").strip().lower()).rstrip(".")


def resolve_target_countries(geo: str) -> set[str]:
    """Set of acceptable countries for the target geography. Empty = no constraint."""
    g = _norm(geo)
    if not g or g in ("global", "worldwide", "international", "all", "world"):
        return set()
    if g in _REGION_COUNTRIES:
        return set(_REGION_COUNTRIES[g])
    g = _COUNTRY_ALIASES.get(g, g)
    return {g}


_MULTI_CCTLD: tuple[tuple[str, str], ...] = (
    (".com.au", "au"), (".co.uk", "uk"), (".org.uk", "uk"), (".co.in", "in"),
    (".com.cn", "cn"), (".co.jp", "jp"), (".com.br", "br"), (".com.mx", "mx"),
    (".co.za", "za"), (".com.sg", "sg"), (".com.tw", "tw"), (".com.tr", "tr"),
)


def _country_from_domain(domain: str) -> str:
    dom = (domain or "").lower().strip().rstrip(".")
    for suf, cc in _MULTI_CCTLD:
        if dom.endswith(suf):
            return _CCTLD_COUNTRY.get(cc, "")
    m = re.search(r"\.([a-z]{2})$", dom)
    if m:
        # .us/.in/.de etc. — generic .com/.org/.net won't match the map
        return _CCTLD_COUNTRY.get(m.group(1), "")
    return ""


def infer_company_country(verdict: dict[str, Any], signals: dict[str, Any] | None) -> str:
    """Best guess of the company's home country, or '' if unknown."""
    sig = signals or verdict.get("signals") or {}
    hq = _norm(str(sig.get("hq_country") or ""))
    hq = _COUNTRY_ALIASES.get(hq, hq)
    if hq:
        # only trust a recognised country name, or a major city we can map to one
        known = set(_CCTLD_COUNTRY.values()) | {"united states", "united kingdom", "uae"}
        if hq in known or hq in _EUROPE:
            return hq
        if hq in _CITY_COUNTRY:
            return _CITY_COUNTRY[hq]
    domain = str(verdict.get("domain") or verdict.get("website") or "")
    from_domain = _country_from_domain(domain)
    if from_domain:
        return from_domain
    # Real bug (repeated user reports): several Indian manufacturers never got caught
    # because hq_country/mentioned_countries were empty for their specific crawl — the
    # company's own registered legal name is a reliable, always-available signal that
    # doesn't depend on what the crawler happened to find. "Pvt. Ltd." / "Private
    # Limited" is an Indian company-law suffix, essentially never used outside India.
    name = str(verdict.get("company") or verdict.get("name") or "")
    if re.search(r"\bpvt\.?\s*ltd\b|\bprivate\s+limited\b", name, re.I):
        return "india"
    # Real bug found via live run: a company whose site never states "headquartered in
    # X" (no hq_country signal) but whose crawl text mentions exactly one country
    # (signals["mentioned_countries"]) is very likely describing where it actually
    # operates from, not a foreign market it merely exports to — this is a weaker signal
    # than hq_country/domain (a note-worthy but rare false-positive risk: a genuinely
    # foreign-HQ'd exporter whose site only mentions its one target market), so it's only
    # used as a last resort when nothing stronger was found, not to override a real signal.
    mentioned = [str(c).strip().lower() for c in (sig.get("mentioned_countries") or [])]
    mentioned = [_COUNTRY_ALIASES.get(c, c) for c in mentioned if c]
    if len(set(mentioned)) == 1:
        only = mentioned[0]
        known = set(_CCTLD_COUNTRY.values()) | {"united states", "united kingdom", "uae"}
        if only in known or only in _EUROPE:
            return only
    return ""


# Terms that indicate operating presence in a country (name + native name + ccTLD).
_PRESENCE_TERMS: dict[str, list[str]] = {
    "brazil": ["brazil", "brasil", ".com.br", ".br"],
    "spain": ["spain", "españa", "espana", ".es"],
    "germany": ["germany", "deutschland", ".de"],
    "france": ["france", ".fr"],
    "italy": ["italy", "italia", ".it"],
    "japan": ["japan", "日本", ".jp", ".co.jp"],
    "china": ["china", "中国", ".cn"],
    "india": ["india", ".in", ".co.in"],
    "united states": ["united states", "usa", "u.s.", "america", ".us"],
    "united kingdom": ["united kingdom", " uk ", "britain", "england", ".co.uk", ".uk"],
    "mexico": ["mexico", "méxico", ".mx"],
    "canada": ["canada", ".ca"],
    "australia": ["australia", ".com.au", ".au"],
}


def _operates_in_target(verdict: dict[str, Any], signals: dict[str, Any], targets: set[str]) -> bool:
    """True if the company shows operating presence in (or serves) any target country."""
    mentioned = " ".join(str(x) for x in (signals.get("mentioned_countries") or []))
    blob = " ".join(
        [
            str(verdict.get("operational_presence") or ""),
            str(verdict.get("company_summary") or ""),
            str(verdict.get("role_description") or ""),
            str(verdict.get("domain") or verdict.get("website") or ""),
            str(verdict.get("company") or ""),
            mentioned,
        ]
    ).lower()
    for country in targets:
        for term in _PRESENCE_TERMS.get(country, [country]):
            if term and term in blob:
                return True
    return False


def geo_mismatch_reason(
    verdict: dict[str, Any], signals: dict[str, Any] | None, target_geo: str
) -> str | None:
    """Drop a company only if it is clearly foreign AND shows no presence in the target.

    Keeps: companies HQ'd in the target, OR that operate/serve there (site mentions the
    country / native name / ccTLD), OR whose country is unknown. Drops: clearly foreign-HQ
    companies with no detected presence in the target geography. Seeds are always kept.
    """
    targets = resolve_target_countries(target_geo)
    if not targets:
        return None  # global / unconstrained
    if verdict.get("is_seed"):
        return None
    sig = signals or verdict.get("signals") or {}
    company_country = infer_company_country(verdict, sig)
    if company_country and company_country in targets:
        return None
    if _operates_in_target(verdict, sig, targets):
        return None  # serves / operates in the target geography → keep
    if company_country:  # clearly foreign-HQ and no detected presence in target
        return f"geo_mismatch:{company_country}"
    return None  # country unknown and no foreign signal → keep (benefit of the doubt)


async def verify_unknown_geo_companies(
    rows: list[dict[str, Any]], target_geo: str, settings: Any
) -> list[dict[str, Any]]:
    """Live HQ lookup for companies the text-based filter couldn't place.

    geo_mismatch_reason's text-based signals (hq_country / mentioned_countries / name /
    domain) have a hard ceiling: a real company whose own site never states its country
    can't be caught by any regex (verified case: a company whose summary only said
    "serving Europe and other regions" while genuinely HQ'd elsewhere). This runs one
    real web search per still-ambiguous company and fills in signals["hq_country"] from
    the search results, so geo_mismatch_reason can re-decide with real evidence instead
    of the "unknown -> keep" default. Only called for the (usually small) subset with no
    signal at all — bounded, concurrent, so it adds real but limited time to a run.
    """
    import asyncio

    from vendor_intel.clients.search_router import FreeSearchRouter
    from vendor_intel.intelligence.signal_extractor import (
        _extract_hq_country,
        _extract_mentioned_countries,
    )

    targets = resolve_target_countries(target_geo)
    if not targets:
        return rows

    ambiguous: list[dict[str, Any]] = []
    for r in rows:
        if r.get("is_seed"):
            continue
        sig = r.get("signals") or {}
        if infer_company_country(r, sig):
            continue  # already resolved by text signals — no lookup needed
        ambiguous.append(r)
    if not ambiguous:
        return rows

    router = FreeSearchRouter(settings)

    async def _verify_one(row: dict[str, Any]) -> None:
        name = str(row.get("company") or "").strip()
        if not name:
            return
        query = f'"{name}" headquarters country'
        try:
            results = await router.search(query, market=name, discovery_mode=False)
        except Exception as exc:
            # Don't let one company's lookup failure (network hiccup, a search backend
            # being down) crash the whole export — but do surface it, since a bare
            # silent except here previously hid a real UnicodeEncodeError inside the
            # search router's own logging and made this function look like it ran fine
            # while actually failing on every call.
            print(f"  [geo_verify] lookup failed for {name!r}: {type(exc).__name__}: {exc}", flush=True)
            return
        blob = " ".join(f"{r.title} {r.snippet}" for r in (results or [])[:5])
        if not blob.strip():
            return
        hq = _extract_hq_country(blob)
        mentioned = _extract_mentioned_countries(blob)
        sig = dict(row.get("signals") or {})
        if hq:
            sig["hq_country"] = hq
        if mentioned:
            sig["mentioned_countries"] = list(
                {*(sig.get("mentioned_countries") or []), *mentioned}
            )
        row["signals"] = sig

    await asyncio.gather(*[_verify_one(r) for r in ambiguous])
    return rows
