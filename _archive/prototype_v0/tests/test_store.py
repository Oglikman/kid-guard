"""Unit tests for the DPAPI-encrypted template store."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from store import dpapi_decrypt, dpapi_encrypt, load_templates, save_templates  # noqa: E402


def test_dpapi_round_trip():
    """Encrypting then decrypting returns the original bytes, and ciphertext differs from plaintext."""
    data = b"hello kidguard"
    enc = dpapi_encrypt(data)
    assert enc != data and dpapi_decrypt(enc) == data


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
