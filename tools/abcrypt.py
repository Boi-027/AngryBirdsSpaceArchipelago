"""Angry Birds Space file crypto.

Scripts (data/scripts, data/levels): AES-256-CBC(zero IV, PKCS7) over a 7z archive holding one file.
Saves (Steam cloud folder): plain Lua text, AES-256-CBC(zero IV), padded with newlines to the block size.
"""
import io, os, tempfile
import py7zr
from cryptography.hazmat.primitives import padding
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

KEY = b"RmgdZ0JenLFgWwkYvCL2lSahFbEhFec4"
SAVE_KEY = b"TpeczKQL07HVdPbVUhAr6FjUsmRctyc5"
IV = b"\0" * 16


def decrypt(raw: bytes) -> bytes:
    d = Cipher(algorithms.AES(KEY), modes.CBC(IV)).decryptor()
    dec = d.update(raw) + d.finalize()
    if 0 < dec[-1] <= 16:
        dec = dec[:-dec[-1]]
    with tempfile.TemporaryDirectory() as td:
        with py7zr.SevenZipFile(io.BytesIO(dec)) as z:
            z.extractall(path=td)
        inner = [os.path.join(r, f) for r, _, fs in os.walk(td) for f in fs]
        return open(inner[0], "rb").read()


def encrypt(content: bytes, name: str) -> bytes:
    buf = io.BytesIO()
    with py7zr.SevenZipFile(buf, "w") as z:
        z.writestr(content, name)
    p = padding.PKCS7(128).padder()
    data = p.update(buf.getvalue()) + p.finalize()
    e = Cipher(algorithms.AES(KEY), modes.CBC(IV)).encryptor()
    return e.update(data) + e.finalize()


def decrypt_save(raw: bytes) -> bytes:
    d = Cipher(algorithms.AES(SAVE_KEY), modes.CBC(IV)).decryptor()
    return (d.update(raw) + d.finalize()).rstrip(b"\n")


def encrypt_save(text: bytes) -> bytes:
    text += b"\n" * (-len(text) % 16)
    e = Cipher(algorithms.AES(SAVE_KEY), modes.CBC(IV)).encryptor()
    return e.update(text) + e.finalize()


if __name__ == "__main__":
    assert decrypt_save(encrypt_save(b"a = 1")) == b"a = 1"
    src = b"print('hello')\n"
    assert decrypt(encrypt(src, "x.lua")) == src
    print("roundtrip ok")
