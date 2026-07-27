from __future__ import annotations

import os

import pytest


@pytest.fixture(scope="session")
def real115_configuration() -> tuple[str, str]:
    if os.environ.get("SAKURAPLAYER_RUN_REAL115") != "1":
        pytest.skip("real 115 probe requires SAKURAPLAYER_RUN_REAL115=1")
    cookie = os.environ.get("SAKURAPLAYER_115_COOKIE", "")
    root_cid = os.environ.get("SAKURAPLAYER_115_TEST_ROOT_CID", "")
    if not cookie or not root_cid:
        pytest.skip("real 115 probe requires external credential and managed root")
    return cookie, root_cid
