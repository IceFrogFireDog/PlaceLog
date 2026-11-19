from tests.conftest import befriend, rand_uuid

API = "/api/v1"


def test_request_accept_remove(users):
    a, b, c = users
    r = a.post(f"{API}/friends/requests", json={"target_user_id": b.id})
    assert r.status_code == 201 and r.json()["direction"] == "outgoing"
    assert "email" not in r.json()["user"]
    fid = r.json()["id"]
    assert [x["id"] for x in b.get(f"{API}/friends/requests?direction=incoming").json()["items"]] == [fid]
    assert [x["id"] for x in a.get(f"{API}/friends/requests?direction=outgoing").json()["items"]] == [fid]

    assert a.post(f"{API}/friends/{fid}/accept").status_code == 403  # 보낸 사람은 수락 불가
    assert c.post(f"{API}/friends/{fid}/accept").status_code == 404  # 제삼자
    assert c.delete(f"{API}/friends/{fid}").status_code == 404
    assert b.post(f"{API}/friends/{fid}/accept").status_code == 200
    assert [x["user"]["id"] for x in a.get(f"{API}/friends").json()["items"]] == [b.id]

    assert b.delete(f"{API}/friends/{fid}").status_code == 204  # 양쪽 해제 가능
    assert a.get(f"{API}/friends").json()["items"] == []
    # 해제 후 재신청은 새 PENDING
    r = a.post(f"{API}/friends/requests", json={"target_user_id": b.id})
    assert r.status_code == 201 and r.json()["status"] == "PENDING"


def test_self_and_duplicate_and_reverse(users):
    a, b, _ = users
    assert a.post(f"{API}/friends/requests", json={"target_user_id": a.id}).status_code == 422
    assert a.post(f"{API}/friends/requests", json={"target_user_id": rand_uuid()}).status_code == 404
    assert a.post(f"{API}/friends/requests", json={"target_user_id": b.id}).status_code == 201
    r = a.post(f"{API}/friends/requests", json={"target_user_id": b.id})
    assert r.status_code == 409 and r.json()["code"] == "ALREADY_REQUESTED"
    r = b.post(f"{API}/friends/requests", json={"target_user_id": a.id})
    assert r.status_code == 409 and r.json()["code"] == "INCOMING_REQUEST_EXISTS"  # 자동 수락 없음
    assert b.get(f"{API}/friends").json()["items"] == []


def test_reject_and_cancel(users):
    a, b, _ = users
    fid = a.post(f"{API}/friends/requests", json={"target_user_id": b.id}).json()["id"]
    assert a.post(f"{API}/friends/{fid}/reject").status_code == 403  # 보낸 사람은 거절 불가
    assert b.delete(f"{API}/friends/{fid}").status_code == 403  # 받은 요청은 reject 사용
    assert b.post(f"{API}/friends/{fid}/reject").status_code == 204
    fid = a.post(f"{API}/friends/requests", json={"target_user_id": b.id}).json()["id"]
    assert a.delete(f"{API}/friends/{fid}").status_code == 204  # 취소
    assert b.get(f"{API}/friends/requests").json()["items"] == []


def test_search_relation_no_email(users):
    a, b, _ = users
    befriend(a, b)
    res = a.get(f"{API}/users/search?q=bo").json()["items"]
    assert res[0]["username"] == "bob" and res[0]["relation"]["status"] == "FRIENDS"
    assert "email" not in res[0]


def test_friend_list_pagination(users):
    a, b, c = users
    befriend(a, b)
    befriend(a, c)
    p1 = a.get(f"{API}/friends?limit=1").json()
    assert len(p1["items"]) == 1 and p1["next_cursor"]
    p2 = a.get(f"{API}/friends?limit=1&cursor={p1['next_cursor']}").json()
    assert len(p2["items"]) == 1 and p2["next_cursor"] is None
    assert {p1["items"][0]["user"]["id"], p2["items"][0]["user"]["id"]} == {b.id, c.id}
