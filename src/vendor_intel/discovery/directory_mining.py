"""Directory / listicle / association / exhibitor mining — web-grounded company discovery.

Finds pages that LIST many companies (directories, "top N" listicles, industry-association member
pages, conference exhibitor lists), fetches each page, and extracts the real companies named on it.
This is genuine discovery (reading real pages), not LLM recall.

Domain resolution uses the directory's OWN links: we read the page's <a href> tags and map each
extracted company name to the URL the list author linked it to — so the domain is the real one,
not a guess. Names without a matched link are returned domain-less for the caller to resolve.

GUARANTEE: the SOURCE pages themselves are never returned as companies. Only companies named INSIDE
them are returned, and any source/aggregator domain is filtered out.
"""
from __future__ import annotations

import re
from typing import Any

from vendor_intel.discovery.entity_extract import is_blocked_domain, is_listicle_domain

# A result is treated as a "source" (list page to mine) if its title looks like a roundup/directory.
_SOURCE_TITLE = re.compile(
    r"\b(top|list|leading|best|directory|members?|exhibitors?|companies|manufacturers?|"
    r"suppliers?|vendors?|providers?|operators?|players|ranking|guide|landscape|comparison|"
    r"compared?|reviews?|roundup|options|brands|alternatives)\b",
    re.I,
)

_A_TAG = re.compile(r'<a\s[^>]*href=["\']([^"\']+)["\'][^>]*>(.*?)</a>', re.I | re.S)
_MD_LINK = re.compile(r"\[([^\]]+)\]\((https?://[^)\s]+)\)")  # [anchor](url) in markdown
_TAG = re.compile(r"<[^>]+>")
_WS = re.compile(r"\s+")

# never treat these as a company's "own" link
_NON_COMPANY_LINK = (
    "facebook.com", "twitter.com", "x.com", "linkedin.com", "youtube.com", "instagram.com",
    "google.com", "apple.com", "microsoft.com", "amazon.com", "wikipedia.org", "mailto:",
    "tel:", "javascript:", "#",
)

_EXTRACT_SYS = (
    "You are given the text of a web page that LISTS companies or products in a market. Extract "
    "EVERY real COMPANY named on the page — actual businesses, vendors, operators, or manufacturers.\n"
    "IMPORTANT: when the page names a PRODUCT, BRAND, platform, or assay rather than the company "
    "(e.g. 'BD MAX', 'Abbott RealTime', 'Xpert C. diff', 'cobas'), return the COMPANY that makes it "
    "(Becton Dickinson, Abbott, Cepheid, Roche) — this is how big multi-product makers get named on "
    "comparison and buyer-guide pages. If the maker is stated or unambiguous, include it.\n"
    "EXCLUDE: the website/publisher itself, market-research firms (e.g. MarketsandMarkets, Grand "
    "View Research), news outlets, authors, universities, government bodies, and any non-company "
    "term. Return the company's plain name only.\n"
    'Return ONLY JSON: {"companies":["<name>", ...]}'
)


def _clean_dom(d: str) -> str:
    d = str(d or "").strip().lower()
    d = d.removeprefix("http://").removeprefix("https://").removeprefix("www.").split("/")[0]
    # normalize non-corporate subdomains the directory may link to (ir./investors./...) to the apex
    for pre in ("ir.", "investors.", "investor.", "corporate.", "ww2."):
        if d.startswith(pre):
            d = d[len(pre):]
            break
    return d


def _nkey(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", str(s or "").lower())


def _fetch_html(url: str) -> str:
    """Full raw HTML (untruncated) so the whole link list is available. Best-effort."""
    try:
        import httpx

        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) VendorIntel/1.0"}
        with httpx.Client(timeout=12.0, follow_redirects=True, headers=headers) as c:
            r = c.get(url)
            if r.status_code < 400:
                return r.text or ""
    except Exception:
        pass
    return ""


def _add_anchor(out: dict[str, str], anchor_text: str, href: str, source_dom: str) -> None:
    from vendor_intel.utils.domains import domain_from_url

    low = href.strip().lower()
    if any(b in low for b in _NON_COMPANY_LINK):
        return
    dom = _clean_dom(domain_from_url(href))
    if not dom or "." not in dom or dom == source_dom:
        return
    if is_blocked_domain(dom) or is_listicle_domain(dom):
        return
    k = _nkey(_WS.sub(" ", _TAG.sub(" ", anchor_text)).strip())
    if len(k) >= 3 and k not in out:
        out[k] = dom


def _anchors(html: str, source_dom: str) -> dict[str, str]:
    """Map normalized anchor-text -> company domain, from the page's <a href> links."""
    out: dict[str, str] = {}
    for href, inner in _A_TAG.findall(html):
        _add_anchor(out, inner, href, source_dom)
    return out


def _markdown_anchors(text: str, source_dom: str) -> dict[str, str]:
    """Map normalized anchor-text -> company domain, from markdown [name](url) links."""
    out: dict[str, str] = {}
    for anchor, url in _MD_LINK.findall(text):
        _add_anchor(out, anchor, url, source_dom)
    return out


def _match_domain(name: str, anchors: dict[str, str]) -> str:
    """Find the directory link whose anchor text matches this company name."""
    k = _nkey(name)
    if not k:
        return ""
    if k in anchors:
        return anchors[k]
    for ak, dom in anchors.items():
        if (len(k) >= 4 and k in ak) or (len(ak) >= 4 and ak in k):
            return dom
    return ""


def _core_market_term(market: str) -> str:
    """A clean noun phrase for natural listicle queries: drop a leading geography and a trailing
    'Market'/'Industry'/'Sector' so 'U.S. Clostridium difficile Testing Market' -> 'Clostridium
    difficile Testing'. Real buyer-guide / comparison / directory pages are titled by the PRODUCT,
    not 'X Market', so the raw market string searches poorly."""
    m = (market or "").strip()
    m = re.sub(
        r"^(?:the\s+)?(?:u\.?\s?s\.?a?|usa|united\s+states|global|worldwide|europe(?:an)?|uk|"
        r"asia(?:[\s-]pacific)?)\s+",
        "", m, flags=re.I,
    )
    m = re.sub(r"\s+(?:market|industry|sector|space)\s*$", "", m, flags=re.I)
    return m.strip() or (market or "").strip()


def _build_queries(
    market: str, geo: str, sections: list[str], industry_terms: list[str] | None = None
) -> list[str]:
    m = market.strip()
    core = _core_market_term(m)
    qs: list[str] = []
    # Component-level directories FIRST — "top VSAT antenna / satellite modem / BUC manufacturers"
    # pages list the equipment SPECIALISTS (KVH, ThinKom, WORK Microwave, Comtech) that market-level
    # listicles omit. These are the pages that surface the equipment-maker tail.
    for t in [str(x).strip() for x in (industry_terms or []) if str(x).strip()][:7]:
        qs.append(f"top {t} manufacturers")
        qs.append(f"list of {t} companies")
    qs += [
        f"list of {core} companies",
        f"top {core} companies",
        f"{core} manufacturers directory",
        f"{core} industry association members",
        f"{core} exhibitor list",
        f"leading {core} suppliers and providers",
        # Product / buyer-guide / comparison pages name the PRODUCTS of diversified majors
        # (e.g. 'BD MAX', 'Abbott RealTime', 'Xpert C. diff') that a plain 'top companies' list
        # omits — this is how the big multi-product incumbents get surfaced from real evidence.
        f"best {core} products",
        f"{core} product comparison",
        f"{core} vendor comparison",
        f"leading {core} brands",
        # Authoritative directories — trade bodies / trade shows / buyer guides tend to enumerate
        # the FULL membership (incl. the regional tail that never ranks for generic queries).
        f"{core} trade association member directory",
        f"{core} trade show exhibitor directory",
        f"{core} member companies list",
        f"{core} buyers guide directory",
        f"{core} operator directory",
        f"{core} vendor directory",
    ]
    for s in [str(x).strip() for x in (sections or []) if str(x).strip()][:4]:
        qs.append(f"list of {s} companies")
    geo_l = (geo or "").strip().lower()
    if not geo_l or geo_l in ("global", "worldwide", "world"):
        for r in ("Asia Pacific", "Europe", "Middle East", "Africa", "Latin America"):
            qs.append(f"{core} companies in {r}")
    else:
        qs.append(f"{core} companies in {geo}")
    return qs


def mine_directories(
    market: str,
    geo: str,
    sections: list[str],
    settings: Any,
    claude: Any,
    *,
    industry_terms: list[str] | None = None,
    max_sources: int = 18,
    max_queries: int = 26,
    max_names: int = 220,
) -> list[dict]:
    """Return [{"name", "domain"}] for companies listed on directory pages. `domain` is the company's
    OWN link taken from the directory (verified, not guessed) when available, else "" for the caller
    to resolve. Source/aggregator domains are never returned. Best-effort; never raises."""
    if not str(market or "").strip() or not getattr(claude, "available", False):
        return []
    from vendor_intel.clients.duckduckgo import _search_sync
    from vendor_intel.scraping.ddgs_extract import fetch_page_via_ddgs_extract

    queries = _build_queries(market, geo, sections, industry_terms)[:max_queries]

    # 1) collect candidate SOURCE pages (list/directory pages), deduped by domain
    sources: list[tuple[str, str]] = []
    seen_dom: set[str] = set()
    for q in queries:
        try:
            hits = _search_sync(q, 6)
        except Exception:
            continue
        for h in hits:
            url = getattr(h, "link", "") or ""
            dom = _clean_dom(url)
            title = getattr(h, "title", "") or ""
            if not url or not dom or dom in seen_dom:
                continue
            if is_listicle_domain(dom) or _SOURCE_TITLE.search(title):
                seen_dom.add(dom)
                sources.append((url, title))
        if len(sources) >= max_sources * 2:
            break
    sources = sources[:max_sources]
    if not sources:
        return []
    print(f"  [directory] mining {len(sources)} list/directory page(s) for company names + links", flush=True)

    # 2) for each source: read the page, LLM-extract the company names, and map each to the
    #    directory's own <a href> link (real domain, no guessing)
    found: dict[str, str] = {}  # normalized name -> {domain or ""}; keeps best (linked) result
    display: dict[str, str] = {}  # normalized name -> display name
    linked_ct = 0
    for url, title in sources:
        source_dom = _clean_dom(url)
        # Primary: ddgs.extract (proxy pool, reliable) → markdown text WITH [name](url) links.
        text = ""
        try:
            text = fetch_page_via_ddgs_extract(url).text or ""
        except Exception:
            text = ""
        anchors = _markdown_anchors(text, source_dom)
        # Always also pull raw HTML for its <a href> links (the directory's real company URLs).
        # Best-effort: blocked on some sites, but ddgs above still gave us the names.
        html = _fetch_html(url)
        if html:
            anchors.update(_anchors(html, source_dom))
            if len(text) < 200:
                text = _WS.sub(" ", _TAG.sub(" ", html)).strip()
        if len(text) < 200:
            continue
        # Member/exhibitor/trade-body directories can list HUNDREDS of companies far past the
        # first 9000 chars. Chunk the page so we extract the WHOLE membership, not just the top —
        # this is what surfaces the regional/specialist tail. Short pages stay a single call.
        _CHUNK, _MAX_CHUNKS = 9000, 3
        chunks = [text[i : i + _CHUNK] for i in range(0, min(len(text), _CHUNK * _MAX_CHUNKS), _CHUNK)]
        names: list[str] = []
        for ci, chunk in enumerate(chunks):
            try:
                out = claude.complete_json(
                    _EXTRACT_SYS,
                    f"MARKET: {market}\nPAGE TITLE: {title}\n\n"
                    f"PAGE TEXT (part {ci + 1}/{len(chunks)}):\n{chunk}",
                    max_tokens=1500,
                )
            except Exception:
                out = {}
            arr = out.get("companies") if isinstance(out, dict) else out
            names.extend(str(n).strip() for n in (arr or []))
        for nm in names:
            if not (2 <= len(nm) <= 80):
                continue
            k = _nkey(nm)
            if not k:
                continue
            dom = _match_domain(nm, anchors)
            display.setdefault(k, nm)
            # prefer a linked domain; don't overwrite a found link with a blank
            if dom and not found.get(k):
                found[k] = dom
                linked_ct += 1
            else:
                found.setdefault(k, "")

    if not found:
        return []
    rows = [{"name": display[k], "domain": found.get(k, "")} for k in list(found)[:max_names]]
    print(
        f"  [directory] extracted {len(rows)} company name(s) — {linked_ct} with a real link "
        f"from the directory (no guess), rest resolved by the caller",
        flush=True,
    )
    return rows


_PARTNER_HINT = re.compile(r"partner|reseller|distributor|dealer|integrator|where[- ]to[- ]buy|channel", re.I)


def mine_partner_pages(
    anchors: list[str],
    market: str,
    geo: str,
    settings: Any,
    claude: Any,
    *,
    max_anchors: int = 10,
    max_sources: int = 16,
    max_names: int = 160,
) -> list[dict]:
    """Mine the PARTNER / RESELLER / DISTRIBUTOR pages of known players. The regional integrator
    tail (Q-KON, iSAT Africa, Paratus, Satcom Networks Africa, X2nSat) is listed as partners/
    resellers of the majors (iDirect, Hughes, Comtech, Gilat...), so reading those pages surfaces
    exactly the companies generic search misses. Reuses the directory extractor. Never raises."""
    anchors = [str(a).strip() for a in (anchors or []) if str(a).strip()]
    if not anchors or not getattr(claude, "available", False):
        return []
    from vendor_intel.clients.duckduckgo import _search_sync
    from vendor_intel.scraping.ddgs_extract import fetch_page_via_ddgs_extract

    # 1) find partner-list pages for each anchor company
    sources: list[tuple[str, str]] = []
    seen_url: set[str] = set()
    for a in anchors[:max_anchors]:
        for q in (f"{a} authorized partners", f"{a} resellers distributors", f"{a} partner directory"):
            try:
                hits = _search_sync(q, 5)
            except Exception:
                continue
            for h in hits:
                url = getattr(h, "link", "") or ""
                title = getattr(h, "title", "") or ""
                if not url or url.lower() in seen_url:
                    continue
                if _PARTNER_HINT.search(url) or _PARTNER_HINT.search(title):
                    seen_url.add(url.lower())
                    sources.append((url, title))
            if len(sources) >= max_sources:
                break
        if len(sources) >= max_sources:
            break
    sources = sources[:max_sources]
    if not sources:
        return []
    print(f"  [partner] mining {len(sources)} partner/reseller page(s) for the regional integrator tail", flush=True)

    found: dict[str, str] = {}
    display: dict[str, str] = {}
    linked_ct = 0
    for url, title in sources:
        source_dom = _clean_dom(url)
        text = ""
        try:
            text = fetch_page_via_ddgs_extract(url).text or ""
        except Exception:
            text = ""
        amap = _markdown_anchors(text, source_dom)
        html = _fetch_html(url)
        if html:
            amap.update(_anchors(html, source_dom))
            if len(text) < 200:
                text = _WS.sub(" ", _TAG.sub(" ", html)).strip()
        if len(text) < 200:
            continue
        chunks = [text[i : i + 9000] for i in range(0, min(len(text), 18000), 9000)]
        names: list[str] = []
        for ci, chunk in enumerate(chunks):
            try:
                out = claude.complete_json(
                    _EXTRACT_SYS,
                    f"MARKET: {market}\nPAGE TITLE: {title}\n\n"
                    f"PARTNER / RESELLER LIST (part {ci + 1}/{len(chunks)}):\n{chunk}",
                    max_tokens=1500,
                )
            except Exception:
                out = {}
            arr = out.get("companies") if isinstance(out, dict) else out
            names.extend(str(n).strip() for n in (arr or []))
        for nm in names:
            if not (2 <= len(nm) <= 80):
                continue
            k = _nkey(nm)
            if not k:
                continue
            dom = _match_domain(nm, amap)
            display.setdefault(k, nm)
            if dom and not found.get(k):
                found[k] = dom
                linked_ct += 1
            else:
                found.setdefault(k, "")
    if not found:
        return []
    rows = [{"name": display[k], "domain": found.get(k, "")} for k in list(found)[:max_names]]
    print(f"  [partner] extracted {len(rows)} partner/reseller compan(ies) ({linked_ct} with a real link)", flush=True)
    return rows
