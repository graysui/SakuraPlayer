from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
BACKEND_ROOT = REPOSITORY_ROOT / "backend"


def test_deployment_document_freezes_private_network_boundary() -> None:
    text = (BACKEND_ROOT / "README.md").read_text(encoding="utf-8").lower()

    assert "127.0.0.1" in text
    assert "https" in text
    assert "vpn" in text
    assert "public internet" in text
    assert "automatic backup" in text
    assert "private installer" in text


def test_license_and_third_party_notice_skeleton_exist() -> None:
    license_text = (REPOSITORY_ROOT / "LICENSE").read_text(encoding="utf-8")
    notices = (REPOSITORY_ROOT / "THIRD_PARTY_NOTICES.md").read_text(encoding="utf-8")

    assert "GNU GENERAL PUBLIC LICENSE" in license_text
    assert "Version 3" in license_text
    assert "source" in notices.lower()
    assert "license" in notices.lower()
