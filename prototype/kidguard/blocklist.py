"""URL parsing and domain blocklists (one text file per category)."""
from __future__ import annotations

from pathlib import Path
from urllib.parse import urlsplit

from . import config

_NO_SLASH_SCHEMES = ("about:", "data:", "javascript:", "mailto:", "blob:")
_SKIP_HOSTS = {"localhost", "localhost.localdomain", "broadcasthost", "local", "0.0.0.0", "127.0.0.1", "::1"}


def parse_url(url: str):
    """Returns (scheme, host) for a URL or bare domain, with host lower-cased and punycoded, or None where absent."""
    s = (url or "").strip()
    if not s:
        return "", None
    if "://" not in s and not s.lower().startswith(_NO_SLASH_SCHEMES):
        s = "http://" + s
    try:
        parts = urlsplit(s)
        host = parts.hostname
    except ValueError:
        return "", None
    if not host:
        return parts.scheme.lower(), None
    host = host.rstrip(".").lower()
    try:
        host = host.encode("idna").decode("ascii")
    except UnicodeError:
        pass
    return parts.scheme.lower(), host or None


def host_in(host: str, domains) -> bool:
    """Returns True if the host equals a listed domain or is a subdomain of one (matching on whole labels only)."""
    labels = host.split(".")
    return any(".".join(labels[i:]) in domains for i in range(len(labels)))


class Blocklist:
    """Maps categories (adult, gambling, drugs, ...) to sets of blocked domains."""

    def __init__(self, categories: dict | None = None) -> None:
        """Creates a blocklist from a {category: iterable of domains} mapping."""
        self.categories = {c: set(d) for c, d in (categories or {}).items()}

    def category_of(self, host: str):
        """Returns the first category whose list contains the host or a parent domain, or None."""
        for category, domains in self.categories.items():
            if host_in(host, domains):
                return category
        return None

    def size(self) -> int:
        """Returns the total number of listed domains across all categories."""
        return sum(len(d) for d in self.categories.values())


def parse_list_line(line: str):
    """Extracts one domain from a list line (plain domain, hosts-file format, or *.domain), or None for blank/comment lines."""
    tokens = line.split("#", 1)[0].split()
    if not tokens:
        return None
    token = tokens[1] if len(tokens) >= 2 and tokens[0] in ("0.0.0.0", "127.0.0.1", "::") else tokens[0]
    token = token.lower().lstrip("*.").rstrip(".")
    return None if (not token or token in _SKIP_HOSTS) else token


def load_blocklist(directory: Path = config.BLOCKLIST_DIR) -> Blocklist:
    """Loads every <category>.txt file in a directory into a Blocklist (empty if the directory is missing)."""
    cats: dict = {}
    d = Path(directory)
    if d.is_dir():
        for f in sorted(d.glob("*.txt")):
            cats[f.stem] = {dom for dom in (parse_list_line(l) for l in f.read_text(encoding="utf-8", errors="ignore").splitlines()) if dom}
    return Blocklist(cats)
