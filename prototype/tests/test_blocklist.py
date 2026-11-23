"""Unit tests for URL parsing, domain matching and blocklist loading."""
from kidguard.blocklist import Blocklist, host_in, load_blocklist, parse_list_line, parse_url


def test_parse_full_url():
    """A full URL yields its scheme and lower-cased host, ignoring port, path and credentials."""
    assert parse_url("HTTPS://User:pw@WWW.Example.COM:8443/a/b?q=1") == ("https", "www.example.com")


def test_parse_bare_domain():
    """A bare domain is treated as http and parsed."""
    assert parse_url("example.com/path") == ("http", "example.com")


def test_parse_bare_domain_with_port():
    """A bare domain with a port is not mistaken for a scheme."""
    assert parse_url("example.com:8080") == ("http", "example.com")


def test_parse_trailing_dot_stripped():
    """A fully-qualified trailing dot does not let a host dodge matching."""
    assert parse_url("http://bad.test./")[1] == "bad.test"


def test_parse_internal_and_non_web():
    """Internal and non-web URLs return their scheme and no host."""
    assert parse_url("chrome://settings") == ("chrome", "settings")
    assert parse_url("about:blank") == ("about", None)
    assert parse_url("javascript:alert(1)") == ("javascript", None)


def test_parse_empty():
    """Empty input returns no scheme and no host."""
    assert parse_url("") == ("", None) and parse_url("   ") == ("", None)


def test_parse_idn_to_punycode():
    """Unicode hosts are converted to punycode so they match list entries."""
    assert parse_url("http://bücher.test")[1] == "xn--bcher-kva.test"


def test_host_in_matches_subdomains_on_label_boundary():
    """A listed domain matches itself and subdomains, but not a different domain that merely ends with the same letters."""
    d = {"bad.test"}
    assert host_in("bad.test", d) and host_in("www.bad.test", d) and host_in("a.b.bad.test", d)
    assert not host_in("notbad.test", d) and not host_in("bad.test.evil.com", d)


def test_parse_list_line_formats():
    """Plain, wildcard, hosts-file, commented and blank lines are all parsed correctly."""
    assert parse_list_line("Example.COM") == "example.com"
    assert parse_list_line("*.example.com") == "example.com"
    assert parse_list_line("0.0.0.0 example.com # note") == "example.com"
    assert parse_list_line("# just a comment") is None
    assert parse_list_line("   ") is None
    assert parse_list_line("127.0.0.1 localhost") is None


def test_category_of_and_size():
    """category_of finds the right category for subdomains and None for unlisted hosts."""
    bl = Blocklist({"adult": ["a.test"], "gambling": ["g.test"]})
    assert bl.category_of("www.a.test") == "adult" and bl.category_of("g.test") == "gambling"
    assert bl.category_of("fine.test") is None and bl.size() == 2


def test_load_blocklist_from_directory(tmp_path):
    """Each <category>.txt file becomes a category; other files and missing directories are handled."""
    (tmp_path / "adult.txt").write_text("# c\nbad.test\n0.0.0.0 worse.test\n")
    (tmp_path / "README.md").write_text("bad.test")
    bl = load_blocklist(tmp_path)
    assert set(bl.categories) == {"adult"} and bl.categories["adult"] == {"bad.test", "worse.test"}
    assert load_blocklist(tmp_path / "missing").size() == 0
