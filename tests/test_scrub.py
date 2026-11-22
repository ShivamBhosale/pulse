import json

from pulse.scrub import Scrubber


def test_scrubs_identity_ids_and_keeps_shape(load_fixture):
    s = Scrubber(b"salt")
    out = s.scrub(load_fixture("identity.json"))
    assert out["name"] == "users/me/identity"
    assert out["legacyUserId"].startswith("scrubbed-")
    assert out["healthUserId"].startswith("scrubbed-")
    assert "A1B2C3" not in json.dumps(out)
    assert "111111256096816351" not in json.dumps(out)


def test_resource_names_and_values(load_fixture):
    s = Scrubber(b"salt")
    raw = load_fixture("daily_rhr_list.json")
    out = s.scrub(raw)
    name = out["dataPoints"][0]["name"]
    assert "4417" not in name and "abc123" not in name
    assert name.startswith("users/scrubbed-") and "/dataTypes/daily-resting-heart-rate/" in name
    assert (
        out["dataPoints"][0]["dailyRestingHeartRate"]
        == raw["dataPoints"][0]["dailyRestingHeartRate"]
    )
    sleep = s.scrub(load_fixture("sleep_reconcile.json"))
    assert "s-991" not in sleep["dataPoints"][0]["dataPointName"]


def test_deterministic_per_salt_and_different_across_salts():
    a, b = Scrubber(b"one"), Scrubber(b"two")
    assert a.token("X") == a.token("X")
    assert a.token("X") != b.token("X")
    # Same ID in two places maps to the same placeholder so joins survive.
    out = a.scrub({"healthUserId": "U1", "name": "users/U1/profile"})
    assert out["name"] == f"users/{out['healthUserId']}/profile"


def test_keeps_device_display_metadata_but_scrubs_client_ids():
    s = Scrubber(b"salt")
    out = s.scrub(
        {
            "dataSource": {
                "device": {"displayName": "Fitbit Air", "serialNumber": "SN1"},
                "application": {"webClientId": "123.apps"},
            }
        }
    )
    assert out["dataSource"]["device"]["displayName"] == "Fitbit Air"
    assert out["dataSource"]["device"]["serialNumber"] != "SN1"
    assert out["dataSource"]["application"]["webClientId"] != "123.apps"


def test_salt_file_created_private(tmp_path):
    p = tmp_path / "salt"
    s1 = Scrubber.from_salt_file(p)
    s2 = Scrubber.from_salt_file(p)
    assert s1.token("x") == s2.token("x")
    assert p.stat().st_mode & 0o777 == 0o600
