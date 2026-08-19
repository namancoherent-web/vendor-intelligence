import re
from urllib.parse import urlparse


def fix_mojibake(text: str) -> str:
    """Repair UTF-8 text that was mis-decoded as Latin-1 (GalÃ¨nica -> Galènica,
    EspaÃ±a -> España, AromÃ¡tica -> Aromática). No-op when no mojibake markers."""
    if not text or not any(m in text for m in ("Ã", "Â", "â€")):
        return text
    try:
        repaired = text.encode("latin-1").decode("utf-8")
    except (UnicodeEncodeError, UnicodeDecodeError):
        return text
    return text if "�" in repaired else repaired


def domain_from_url(url: str) -> str:
    try:
        host = urlparse(url).netloc.lower()
        if host.startswith("www."):
            host = host[4:]
        return host
    except Exception:
        return ""


_LEGAL_SUFFIXES = (
    "incorporated", "inc",
    "limited", "ltd",
    "llc", "llp",
    "gmbh", "ag", "se",
    "pvt ltd", "private limited", "pvt", "private",
    "corporation", "corp",
    "company", "co",
    "plc",
    "s.a", "sa", "s.p.a", "spa",
    "n.v", "nv", "b.v", "bv",
    "pty ltd", "pty",
    "s.l", "sl", "s.r.l", "srl",
    "k.k", "kk", "kabushiki kaisha",
    "oy", "oyj", "ab", "as", "a/s",
)


def normalize_name(name: str) -> str:
    n = fix_mojibake(name).strip()
    # Strip legal-entity suffixes repeatedly (e.g. "Acme Pvt Ltd Co." has two) and normalize
    # punctuation/spacing so "Acme, Inc." / "Acme Incorporated" / "Acme S.A." / "Acme  Inc" all
    # converge — this only affects duplicate-detection comparisons, never the displayed name.
    changed = True
    while changed:
        changed = False
        # Drop trailing punctuation/whitespace before comparing, so "Inc." and "Inc" both match
        # the same bare suffix, and internal dots in abbreviations (S.A., N.V.) are ignored too.
        n = re.sub(r"[.,]+$", "", n).strip()
        core = re.sub(r"\.", "", n)
        for suffix in _LEGAL_SUFFIXES:
            # Only strip when the suffix follows an actual preceding word — never let the
            # whole name (e.g. a company literally named "Corp" or "AB") collapse to empty.
            if core.lower().endswith(" " + suffix):
                n = core[: len(core) - len(suffix)].strip()
                changed = True
                break
    return n.strip()


def company_dedupe_key(name: str) -> str:
    """Stable merge key — collapses Dr. Reddy's / Dr Reddys Laboratories, etc."""
    import re

    raw = normalize_name(name).lower()
    compact = re.sub(r"[^a-z0-9]", "", raw)
    aliases = {
        "drreddys": "drreddyslaboratories",
        "drreddy": "drreddyslaboratories",
        "drreddylaboratories": "drreddyslaboratories",
        "drreddyslaboratories": "drreddyslaboratories",
        "drreddyslaboratory": "drreddyslaboratories",
        "drreddyslabs": "drreddyslaboratories",
        "drreddyslab": "drreddyslaboratories",
        "sunpharma": "sunpharmaceuticalindustries",
        "sunpharmaceutical": "sunpharmaceuticalindustries",
        "zyduscadila": "cadilahealthcare",
    }
    return aliases.get(compact, raw)
