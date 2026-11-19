"""경계값·악성 입력이 500이 아닌 4xx로 처리되고 데이터를 망가뜨리지 않는지."""
import logging

import pytest

from tests.conftest import create_place, jpeg_bytes, upload

API = "/api/v1"


@pytest.mark.parametrize("taken_at", ["9999-12-31T23:59:59Z", "0001-01-01T00:00:00+14:00", "9999-12-31T23:59:59-14:00", "1700-01-01T00:00:00Z", "2150-01-01T00:00:00+09:00"])
def test_out_of_range_taken_at_rejected(users, anon, taken_at):
    a, *_ = users
    pid = create_place(a)
    upload(a, pid, "PUBLIC")
    r = upload(a, pid, "PUBLIC", taken_at=taken_at)
    assert r.status_code == 422 and "taken_at" in r.json()["field_errors"]
    ok = upload(a, pid, "PUBLIC").json()["id"]
    assert a.patch(f"{API}/photos/{ok}", json={"taken_at": taken_at}).status_code == 422
    # 장소 목록이 계속 정상 동작
    assert anon.get(f"{API}/places/{pid}/photos").status_code == 200


def test_valid_taken_at_edges(users):
    a, *_ = users
    pid = create_place(a)
    for t in ("1900-01-01T00:00:00+09:00", "2099-12-31T12:00:00-03:30"):
        r = upload(a, pid, taken_at=t, taken_timezone=t[-6:])
        assert r.status_code == 201, (t, r.text)


def test_exif_absurd_date_ignored(users):
    a, *_ = users
    pid = create_place(a)
    r = upload(a, pid, data=jpeg_bytes(dt="9999:12:31 23:00:00", offset="+00:00"))
    assert r.status_code == 201 and r.json()["taken_at"] is None
    assert a.get(f"{API}/places/{pid}/photos").status_code == 200


def test_nul_bytes_rejected_not_500(users):
    a, *_ = users
    pid = create_place(a)
    phid = upload(a, pid).json()["id"]
    cases = [
        a.post(f"{API}/places", json={"name": "a\x00b", "latitude": 1, "longitude": 1}),
        a.patch(f"{API}/users/me", json={"bio": "a\x00"}),
        a.patch(f"{API}/users/me", json={"display_name": "a\x00"}),
        a.patch(f"{API}/photos/{phid}", json={"caption": "x\x00"}),
        upload(a, pid, caption="x\x00"),
        a.post(f"{API}/auth/login", json={"email": "a\x00@b.c", "password": "x"}),
        a.get(f"{API}/places?q=a%00"),
        a.get(f"{API}/users/search?q=a%00"),
        a.get(f"{API}/users/ab%00c"),
    ]
    assert [r.status_code for r in cases] == [422] * len(cases)


@pytest.mark.parametrize("cc", ["ßa", "K1", "KOR", "한국"])
def test_bad_country_code(users, cc):
    a, *_ = users
    r = a.post(f"{API}/places", json={"name": "x", "latitude": 1, "longitude": 1, "country_code": cc})
    assert r.status_code == 422


def test_db_error_does_not_log_gps(users, caplog, monkeypatch):
    """DB 오류 시에도 정확한 좌표가 로그에 남지 않아야 한다 (지시서 3.5)."""
    from sqlalchemy import event

    from app.core.database import engine

    a, *_ = users
    pid = create_place(a)

    def fail_photo_insert(conn, cursor, statement, params, context, executemany):
        if statement.lstrip().upper().startswith("INSERT INTO PHOTOS"):
            raise RuntimeError("simulated db failure")

    event.listen(engine, "before_cursor_execute", fail_photo_insert)
    try:
        with caplog.at_level(logging.DEBUG):
            with pytest.raises(Exception):
                upload(a, pid, shot_latitude=37.123456, shot_longitude=127.654321)
    finally:
        event.remove(engine, "before_cursor_execute", fail_photo_insert)
    from app.core.database import engine as e
    assert e.hide_parameters is True
    assert "37.123456" not in caplog.text and "127.654321" not in caplog.text
