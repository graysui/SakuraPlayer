from __future__ import annotations

from datetime import datetime, timezone
from urllib.parse import parse_qs

import httpx
import pytest

from sakuraplayer.cloud_cache.infrastructure.cloud115.adapter import Cloud115Adapter
from sakuraplayer.cloud_cache.ports.cloud115 import (
    Cloud115Problem,
    CloudCredentialStatus,
    OfflineStatus,
    OriginalUrl,
    QrStatus,
    QrToken,
)

COOKIE = "UID=123_A1_1700000000; CID=cid; SEID=seid"


def _http_client(handler) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


@pytest.mark.parametrize("errno", [20121, 20125, 990002, 4100003, 4100008])
def test_offline_submit_known_not_found_errno_has_precise_stable_code(
    errno: int,
) -> None:
    problem = Cloud115Adapter._payload_problem(
        {"state": False, "errno": errno, "error": "upstream body"},
        "offline_submit",
    )

    assert problem.code == "cloud115_source_unavailable"
    assert "upstream body" not in str(problem)


def test_offline_submit_generic_request_errno_is_protocol_error() -> None:
    problem = Cloud115Adapter._payload_problem(
        {"state": False, "errno": 990005, "error": "generic request"},
        "offline_submit",
    )

    assert problem.code == "cloud115_protocol_error"


@pytest.mark.parametrize("status", [400, 422])
def test_offline_submit_ambiguous_http_status_is_protocol_error(status: int) -> None:
    with pytest.raises(Cloud115Problem) as raised:
        Cloud115Adapter._raise_http_problem(httpx.Response(status), "offline_submit")

    assert raised.value.code == "cloud115_protocol_error"


@pytest.mark.asyncio
async def test_offline_submit_missing_info_hash_is_protocol_error() -> None:
    client = _http_client(
        lambda request: httpx.Response(
            200,
            json={"state": True, "result": [{}]},
            request=request,
        )
    )
    adapter = Cloud115Adapter(cookies=COOKIE, http_client=client)
    try:
        with pytest.raises(Cloud115Problem) as raised:
            await adapter.submit_offline("magnet:?xt=urn:btih:redacted", "task")
        assert raised.value.code == "cloud115_protocol_error"
    finally:
        await client.aclose()


@pytest.mark.asyncio
async def test_qr_flow_uses_fixed_hosts_and_rejects_unknown_status() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/token/"):
            return httpx.Response(
                200,
                json={"data": {"uid": "qr-1", "time": 7, "sign": "sig"}},
            )
        if request.url.path.endswith("/qrcode"):
            return httpx.Response(200, content=b"\x89PNG\r\n\x1a\nfixture")
        if request.url.path == "/get/status/":
            return httpx.Response(200, json={"data": {"status": 99}})
        raise AssertionError(f"unexpected request path: {request.url.path}")

    client = _http_client(handler)
    adapter = Cloud115Adapter(http_client=client)
    try:
        session = await adapter.create_qr_session()
        assert session.token == QrToken(uid="qr-1", time=7, sign="sig")
        assert session.image_png.startswith(b"\x89PNG")
        with pytest.raises(Cloud115Problem) as raised:
            await adapter.poll_qr_session(session.token)
        assert raised.value.code == "cloud115_protocol_error"
    finally:
        await client.aclose()


@pytest.mark.asyncio
async def test_qr_long_poll_timeout_is_waiting() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("long poll", request=request)

    client = _http_client(handler)
    adapter = Cloud115Adapter(http_client=client)
    try:
        status = await adapter.poll_qr_session(QrToken("qr-1", 7, "sig"))
        assert status is QrStatus.WAITING
    finally:
        await client.aclose()


@pytest.mark.asyncio
async def test_qr_finish_uses_fixed_alipaymini_slot_and_returns_snapshot() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/app/1.0/alipaymini/1.0/login/qrcode/"
        assert parse_qs(request.content.decode("ascii"))["account"] == ["qr-1"]
        return httpx.Response(
            200,
            json={
                "state": True,
                "data": {
                    "user_id": "123",
                    "cookie": {"UID": "123_A1_1", "SEID": "secret"},
                },
            },
        )

    client = _http_client(handler)
    adapter = Cloud115Adapter(http_client=client)
    try:
        result = await adapter.finish_qr_session(QrToken("qr-1", 7, "sig"))
        assert result.account_key == "123"
        assert result.cookie_snapshot == "UID=123_A1_1; SEID=secret"
    finally:
        await client.aclose()


@pytest.mark.asyncio
async def test_probe_distinguishes_expired_and_merges_cookie_snapshot() -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if calls == 1:
            return httpx.Response(
                200,
                json={"state": True},
                headers={"Set-Cookie": "acw_tc=fresh; Max-Age=1800; HttpOnly"},
            )
        return httpx.Response(302, headers={"Location": "https://115.com/login"})

    client = _http_client(handler)
    adapter = Cloud115Adapter(cookies=COOKIE, http_client=client)
    try:
        alive = await adapter.probe_credentials()
        assert alive.status is CloudCredentialStatus.ALIVE
        assert alive.cookie_snapshot is not None
        assert "acw_tc=fresh" in alive.cookie_snapshot
        assert adapter.credential_snapshot() == alive.cookie_snapshot
        expired = await adapter.probe_credentials()
        assert expired.status is CloudCredentialStatus.EXPIRED
    finally:
        await client.aclose()


@pytest.mark.asyncio
async def test_cookie_deletion_and_injected_client_redirect_policy_are_enforced() -> (
    None
):
    visited: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        visited.append(request.url.host)
        if len(visited) == 1:
            return httpx.Response(
                200,
                json={"state": True},
                headers={
                    "Set-Cookie": "SEID=stale; Max-Age=0; Path=/",
                },
            )
        return httpx.Response(
            302,
            headers={"Location": "https://attacker.invalid/steal"},
        )

    client = httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        follow_redirects=True,
    )
    adapter = Cloud115Adapter(cookies=COOKIE, http_client=client)
    try:
        alive = await adapter.probe_credentials()
        assert alive.status is CloudCredentialStatus.ALIVE
        assert "SEID=" not in (alive.cookie_snapshot or "")
        expired = await adapter.probe_credentials()
        assert expired.status is CloudCredentialStatus.EXPIRED
        assert visited == ["my.115.com", "my.115.com"]
    finally:
        await client.aclose()


@pytest.mark.asyncio
async def test_find_or_create_rejects_ambiguous_directory() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "state": True,
                "count": 2,
                "data": [
                    {"cid": "10", "pid": "0", "n": "cache"},
                    {"cid": "11", "pid": "0", "n": "cache"},
                ],
            },
        )

    client = _http_client(handler)
    adapter = Cloud115Adapter(cookies=COOKIE, http_client=client)
    try:
        with pytest.raises(Cloud115Problem) as raised:
            await adapter.find_or_create_directory("0", "cache")
        assert raised.value.code == "cloud115_directory_ambiguous"
    finally:
        await client.aclose()


@pytest.mark.asyncio
async def test_directory_pagination_cannot_silently_finish_early() -> None:
    client = _http_client(
        lambda request: httpx.Response(
            200,
            json={"state": True, "count": 2, "data": []},
        )
    )
    adapter = Cloud115Adapter(cookies=COOKIE, http_client=client)
    try:
        with pytest.raises(Cloud115Problem) as raised:
            await adapter.find_or_create_directory("0", "cache")
        assert raised.value.code == "cloud115_protocol_error"
    finally:
        await client.aclose()


@pytest.mark.asyncio
async def test_offline_submit_timeout_is_uncertain_and_cancel_never_deletes_files() -> (
    None
):
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        action = request.url.params.get("ac")
        if action == "add_task_urls":
            raise httpx.ReadTimeout("unknown result", request=request)
        if action == "task_del":
            form = parse_qs(request.content.decode("ascii"))
            assert form["flag"] == ["0"]
            return httpx.Response(200, json={"state": True})
        raise AssertionError(f"unexpected action: {action}")

    client = _http_client(handler)
    adapter = Cloud115Adapter(cookies=COOKIE, http_client=client)
    magnet = "magnet:?xt=urn:btih:sensitive"
    try:
        with pytest.raises(Cloud115Problem) as raised:
            await adapter.submit_offline(magnet, "20")
        assert raised.value.code == "cloud115_submit_uncertain"
        assert magnet not in str(raised.value)
        await adapter.cancel_offline("a" * 40)
    finally:
        await client.aclose()


@pytest.mark.asyncio
async def test_offline_page_omits_source_url_and_maps_status() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "page": 1,
                "page_count": 1,
                "page_size": 100,
                "total": 1,
                "tasks": [
                    {
                        "info_hash": "a" * 40,
                        "name": "task",
                        "size": 10,
                        "status": 1,
                        "percentDone": 12.5,
                        "file_id": "",
                        "pick_code": "",
                        "wp_path_id": "20",
                        "url": "magnet:?xt=urn:btih:must-not-escape",
                    }
                ],
            },
        )

    client = _http_client(handler)
    adapter = Cloud115Adapter(cookies=COOKIE, http_client=client)
    try:
        page = await adapter.list_offline_tasks()
        assert page.tasks[0].status is OfflineStatus.RUNNING
        assert "magnet:" not in repr(page.tasks[0])
    finally:
        await client.aclose()


@pytest.mark.asyncio
async def test_hls_parses_variants_and_rejects_unapproved_capability_host() -> None:
    master = (
        "#EXTM3U\n"
        '#EXT-X-STREAM-INF:BANDWIDTH=1800000,RESOLUTION=1280x720,NAME="HD"\n'
        "https://cpats01.115.com/video/hd.m3u8\n"
    )

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "webapi.115.com":
            return httpx.Response(
                200,
                json={
                    "state": True,
                    "file_status": 1,
                    "video_url": "https://cpats01.115.com/video/master.m3u8",
                },
            )
        return httpx.Response(200, text=master)

    client = _http_client(handler)
    adapter = Cloud115Adapter(cookies=COOKIE, http_client=client)
    try:
        info = await adapter.resolve_hls("pick", "SakuraPlayer-Test/1")
        assert info.variants[0].bandwidth == 1_800_000
        assert info.variants[0].user_agent == "SakuraPlayer-Test/1"

        adapter.validate_capability_url(
            "https://cdnfhnfile.115cdn.net/video/file?capability=redacted"
        )

        for rejected_url in (
            "https://attacker.invalid/video.m3u8",
            "https://115cdn.net.attacker.invalid/video.m3u8",
            "https://attacker115cdn.net/video.m3u8",
        ):
            with pytest.raises(Cloud115Problem) as raised:
                adapter.validate_capability_url(rejected_url)
            assert raised.value.code == "cloud115_protocol_error"
    finally:
        await client.aclose()


def test_problem_and_logs_do_not_expose_sensitive_inputs(caplog) -> None:
    adapter = Cloud115Adapter(cookies=COOKIE)
    secret_url = "https://attacker.invalid/?token=top-secret"

    with pytest.raises(Cloud115Problem) as raised:
        adapter.validate_capability_url(secret_url)
    assert str(raised.value) == "cloud115_protocol_error"
    assert "top-secret" not in caplog.text


@pytest.mark.asyncio
async def test_directory_info_recursive_files_and_managed_delete() -> None:
    deleted = False

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal deleted
        if request.url.path == "/category/get":
            return httpx.Response(
                200,
                json={
                    "state": True,
                    "file_name": "task",
                    "paths": [
                        {"file_id": 0, "file_name": "root"},
                        {"file_id": "10", "file_name": "cache"},
                    ],
                },
            )
        if request.url.path == "/files":
            return httpx.Response(
                200,
                json={
                    "state": True,
                    "count": 1,
                    "data": [
                        {
                            "fid": "30",
                            "cid": "20",
                            "n": "subtitle.srt",
                            "s": 12,
                            "pc": "pick",
                        }
                    ],
                },
            )
        if request.url.path == "/rb/delete":
            form = parse_qs(request.content.decode("ascii"))
            assert form["pid"] == ["20"]
            assert form["fid[0]"] == ["30"]
            deleted = True
            return httpx.Response(200, json={"state": True})
        raise AssertionError(f"unexpected request: {request.url}")

    client = _http_client(handler)
    adapter = Cloud115Adapter(cookies=COOKIE, http_client=client)
    try:
        info = await adapter.directory_info("20")
        assert info.parent_cid == "10"
        files = [entry async for entry in adapter.list_files_recursive("20")]
        assert files[0].parent_cid == "20"
        await adapter.delete_managed_entries(("30",), "20")
        assert deleted is True
    finally:
        await client.aclose()


@pytest.mark.asyncio
async def test_recursive_listing_descends_into_directories_and_only_yields_files() -> (
    None
):
    requested_cids: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/files"
        assert request.url.params["show_dir"] == "1"
        cid = request.url.params["cid"]
        requested_cids.append(cid)
        if cid == "20":
            return httpx.Response(
                200,
                json={
                    "state": True,
                    "count": 2,
                    "data": [
                        {"cid": "21", "pid": "20", "n": "nested"},
                        {
                            "fid": "30",
                            "cid": "20",
                            "n": "root.mkv",
                            "s": 300_000_000,
                            "pc": "root-pick",
                            "iv": 1,
                        },
                    ],
                },
            )
        if cid == "21":
            return httpx.Response(
                200,
                json={
                    "state": True,
                    "count": 1,
                    "data": [
                        {
                            "fid": "31",
                            "cid": "21",
                            "n": "nested.ass",
                            "s": 1000,
                            "pc": "nested-pick",
                        }
                    ],
                },
            )
        raise AssertionError(f"unexpected cid: {cid}")

    client = _http_client(handler)
    adapter = Cloud115Adapter(cookies=COOKIE, http_client=client)
    try:
        files = [item async for item in adapter.list_files_recursive("20")]
    finally:
        await client.aclose()

    assert requested_cids == ["20", "21"]
    assert [item.file_id for item in files] == ["30", "31"]
    assert all(not item.is_directory for item in files)


@pytest.mark.asyncio
async def test_recursive_listing_rejects_parent_cid_mismatch() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "state": True,
                "count": 1,
                "data": [
                    {
                        "fid": "30",
                        "cid": "outside",
                        "n": "movie.mkv",
                        "s": 300_000_000,
                        "pc": "pick",
                    }
                ],
            },
        )

    client = _http_client(handler)
    adapter = Cloud115Adapter(cookies=COOKIE, http_client=client)
    try:
        with pytest.raises(Cloud115Problem) as raised:
            _ = [item async for item in adapter.list_files_recursive("20")]
    finally:
        await client.aclose()

    assert raised.value.code == "cloud115_protocol_error"


@pytest.mark.asyncio
async def test_recursive_listing_rejects_page_larger_than_requested_limit() -> None:
    oversized_page = [
        {
            "fid": str(index),
            "cid": "20",
            "n": f"movie-{index}.mkv",
            "s": 300_000_000,
            "pc": f"pick-{index}",
        }
        for index in range(1001)
    ]
    client = _http_client(
        lambda request: httpx.Response(
            200,
            json={"state": True, "count": len(oversized_page), "data": oversized_page},
        )
    )
    adapter = Cloud115Adapter(cookies=COOKIE, http_client=client)
    try:
        with pytest.raises(Cloud115Problem) as raised:
            _ = [item async for item in adapter.list_files_recursive("20")]
    finally:
        await client.aclose()

    assert raised.value.code == "cloud115_protocol_error"


@pytest.mark.asyncio
async def test_recursive_listing_rejects_declared_total_beyond_remaining_budget() -> (
    None
):
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        assert calls == 1
        return httpx.Response(
            200,
            json={
                "state": True,
                "count": 101_024,
                "data": [
                    {
                        "fid": "30",
                        "cid": "20",
                        "n": "movie.mkv",
                        "s": 300_000_000,
                        "pc": "pick",
                    }
                ],
            },
        )

    client = _http_client(handler)
    adapter = Cloud115Adapter(cookies=COOKIE, http_client=client)
    try:
        with pytest.raises(Cloud115Problem) as raised:
            _ = [item async for item in adapter.list_files_recursive("20")]
    finally:
        await client.aclose()

    assert raised.value.code == "cloud115_protocol_error"
    assert calls == 1


@pytest.mark.asyncio
async def test_recursive_listing_rejects_directory_cycle() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        cid = request.url.params["cid"]
        return httpx.Response(
            200,
            json={
                "state": True,
                "count": 1,
                "data": [{"cid": "20", "pid": cid, "n": "cycle"}],
            },
        )

    client = _http_client(handler)
    adapter = Cloud115Adapter(cookies=COOKIE, http_client=client)
    try:
        with pytest.raises(Cloud115Problem) as raised:
            _ = [item async for item in adapter.list_files_recursive("20")]
    finally:
        await client.aclose()

    assert raised.value.code == "cloud115_protocol_error"


def test_original_payload_is_typed_and_capability_url_is_validated() -> None:
    original = Cloud115Adapter.parse_original_payload(
        {
            "30": {
                "file_name": "movie.mkv",
                "file_size": "1024",
                "pick_code": "pick",
                "sha1": "ABC",
                "url": {"url": "https://cdn.115.com/movie.mkv?t=1893456000&f=signed"},
            }
        },
        pickcode="pick",
        user_agent="SakuraPlayer-Test/1",
    )

    assert original.file_id == "30"
    assert original.file_size_bytes == 1024
    assert original.expires_at == datetime(2030, 1, 1, tzinfo=timezone.utc)


@pytest.mark.asyncio
async def test_small_file_download_stops_at_byte_limit(monkeypatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"12345")

    async def resolve_original(pickcode: str, user_agent: str) -> OriginalUrl:
        return OriginalUrl(
            url="https://cdn.115.com/subtitle.srt",
            expires_at=None,
            file_id="30",
            file_name="subtitle.srt",
            file_size_bytes=5,
            sha1="ABC",
            pickcode=pickcode,
            user_agent=user_agent,
        )

    client = _http_client(handler)
    adapter = Cloud115Adapter(cookies=COOKIE, http_client=client)
    monkeypatch.setattr(adapter, "resolve_original", resolve_original)
    try:
        with pytest.raises(Cloud115Problem) as raised:
            await adapter.download_small_file("pick", "SakuraPlayer-Test/1", 4)
        assert raised.value.code == "cloud115_small_file_too_large"
    finally:
        await client.aclose()


@pytest.mark.asyncio
async def test_errno_mapping_keeps_membership_quota_and_unknown_distinct() -> None:
    payloads = iter(
        [
            {"state": False, "errno": 406},
            {"state": False, "errno": 10008},
            {"state": False, "errno": 987654},
        ]
    )

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=next(payloads))

    client = _http_client(handler)
    adapter = Cloud115Adapter(cookies=COOKIE, http_client=client)
    try:
        with pytest.raises(Cloud115Problem) as membership:
            await adapter.resolve_hls("pick", "SakuraPlayer-Test/1")
        assert membership.value.code == "cloud115_hls_membership_required"

        with pytest.raises(Cloud115Problem) as quota:
            await adapter.submit_offline("magnet:?xt=urn:btih:test", "20")
        assert quota.value.code == "cloud115_offline_quota_exceeded"

        with pytest.raises(Cloud115Problem) as unknown:
            await adapter.directory_info("20")
        assert unknown.value.code == "cloud115_protocol_error"
    finally:
        await client.aclose()


@pytest.mark.asyncio
async def test_upstream_body_is_not_retained_in_failure() -> None:
    secret = "response-cookie-and-url-must-not-escape"
    client = _http_client(lambda request: httpx.Response(503, text=secret))
    adapter = Cloud115Adapter(cookies=COOKIE, http_client=client)
    try:
        with pytest.raises(Cloud115Problem) as raised:
            await adapter.list_offline_tasks()
        assert raised.value.code == "cloud115_unavailable"
        assert secret not in str(raised.value)
        assert secret not in repr(raised.value)
    finally:
        await client.aclose()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("operation", "expected"),
    [
        ("qr", "cloud115_protocol_error"),
        ("directory", "cloud115_directory_not_found"),
        ("offline_list", "cloud115_protocol_error"),
    ],
)
async def test_http_not_found_is_mapped_per_operation(
    operation: str,
    expected: str,
) -> None:
    client = _http_client(lambda request: httpx.Response(404))
    adapter = Cloud115Adapter(cookies=COOKIE, http_client=client)
    try:
        with pytest.raises(Cloud115Problem) as raised:
            if operation == "qr":
                await adapter.create_qr_session()
            elif operation == "directory":
                await adapter.directory_info("20")
            else:
                await adapter.list_offline_tasks()
        assert raised.value.code == expected
    finally:
        await client.aclose()
