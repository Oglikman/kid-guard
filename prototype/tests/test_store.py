"""Unit tests for the DPAPI-encrypted template store and delete (PRD F12)."""
from kidguard.store import delete_all, dpapi_decrypt, dpapi_encrypt, load_templates, save_templates


def test_dpapi_round_trip():
    """Encrypting then decrypting returns the original bytes, and ciphertext differs from plaintext."""
    enc = dpapi_encrypt(b"hello kidguard")
    assert enc != b"hello kidguard" and dpapi_decrypt(enc) == b"hello kidguard"


def test_save_load_round_trip(tmp_path):
    """Templates saved to disk load back with the same role and values."""
    p = tmp_path / "t.bin"
    save_templates({"dad": {"role": "adult", "embeddings": [[0.5, -0.25, 1.0]]}}, p)
    out = load_templates(p)
    assert out["dad"]["role"] == "adult" and out["dad"]["embeddings"] == [[0.5, -0.25, 1.0]]


def test_file_on_disk_is_not_plaintext(tmp_path):
    """The stored file must not contain readable names or roles."""
    p = tmp_path / "t.bin"
    save_templates({"dad": {"role": "adult", "embeddings": [[1.0]]}}, p)
    raw = p.read_bytes()
    assert b"dad" not in raw and b"adult" not in raw


def test_load_missing_file_is_empty(tmp_path):
    """Loading a file that does not exist returns an empty dict."""
    assert load_templates(tmp_path / "nope.bin") == {}


def test_delete_all_removes_file(tmp_path):
    """delete_all removes the templates file and a later load is empty."""
    p = tmp_path / "t.bin"
    save_templates({"a": {"role": "child", "embeddings": [[1.0]]}}, p)
    assert delete_all(p) is True and not p.exists() and load_templates(p) == {}


def test_delete_all_when_nothing_stored(tmp_path):
    """delete_all returns False when there was nothing to delete."""
    assert delete_all(tmp_path / "none.bin") is False
