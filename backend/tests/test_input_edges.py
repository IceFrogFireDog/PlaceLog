"""경계값·악성 입력이 500이 아닌 4xx로 처리되고 데이터를 망가뜨리지 않는지."""
API = "/api/v1"


def test_nul_bytes_rejected_not_500(users):
    a, *_ = users
    cases = [
        a.patch(f"{API}/users/me", json={"bio": "a\x00"}),
        a.patch(f"{API}/users/me", json={"display_name": "a\x00"}),
        a.post(f"{API}/auth/login", json={"email": "a\x00@b.c", "password": "x"}),
        a.get(f"{API}/users/search?q=a%00"),
        a.get(f"{API}/users/ab%00c"),
    ]
    assert [r.status_code for r in cases] == [422] * len(cases)
