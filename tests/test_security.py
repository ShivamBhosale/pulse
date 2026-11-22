from pulse import security


def test_passcode_hash_roundtrip_and_salt():
    h1, h2 = security.hash_passcode("2468"), security.hash_passcode("2468")
    assert h1 != h2 and h1.startswith("scrypt$")
    assert security.verify_passcode("2468", h1)
    assert not security.verify_passcode("2469", h1)
    assert not security.verify_passcode("2468", "garbage")
    assert not security.verify_passcode("2468", "md5$1$1$1$00$00")


def test_signer_tamper_expiry_and_fingerprint():
    t = [1_000_000.0]
    signer = security.SessionSigner(b"k" * 32, now=lambda: t[0])
    token = signer.issue("fp1")
    assert signer.verify(token, "fp1")
    assert not signer.verify(token, "fp2")
    assert not signer.verify(token[:-1] + ("0" if token[-1] != "0" else "1"), "fp1")
    assert not signer.verify(None, "fp1") and not signer.verify("junk", "fp1")
    assert not security.SessionSigner(b"x" * 32, now=lambda: t[0]).verify(token, "fp1")
    t[0] += security.SESSION_MAX_AGE_S + 1
    assert not signer.verify(token, "fp1")


def test_limiter_window():
    lim = security.AttemptLimiter(limit=2, window_s=60)
    assert lim.allowed("ip", now=0)
    lim.fail("ip", now=0)
    lim.fail("ip", now=1)
    assert not lim.allowed("ip", now=30)
    assert lim.allowed("ip", now=62)
    assert lim.allowed("other", now=30)
    lim.fail("ip", now=100)
    lim.reset("ip")
    assert lim.allowed("ip", now=100)


def test_secret_file_private(tmp_path):
    p = tmp_path / "secret_key"
    assert security.load_secret(p) == security.load_secret(p)
    assert p.stat().st_mode & 0o777 == 0o600
