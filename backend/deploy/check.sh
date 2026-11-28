#!/usr/bin/env bash
# 배포 후 점검.   사용: ./deploy/check.sh photos.example.com
#                 내 PC에서 DOMAIN=localhost로 띄웠다면: ./deploy/check.sh localhost --insecure
set -u
DOMAIN="${1:?도메인을 넣어 주세요. 예: ./deploy/check.sh photos.example.com}"
CURL=(curl -sS --max-time 20)
[ "${2:-}" = "--insecure" ] && CURL+=(-k)   # localhost는 Caddy 내부 인증서라 브라우저·curl이 신뢰하지 않음
fail=0
ok()  { printf '  ✓ %s\n' "$1"; }
bad() { printf '  ✗ %s\n' "$1"; fail=1; }
status() { "${CURL[@]}" -o /dev/null -w '%{http_code}' "$1" 2>/dev/null || echo 000; }

echo "https://$DOMAIN 점검"
[ "$(status "https://$DOMAIN/api/v1/health")" = 200 ] && ok "API 응답 (/api/v1/health)" || bad "API 응답 없음 — docker compose logs backend 확인"
[ "$(status "https://$DOMAIN/")" = 200 ] && ok "화면 응답 (/)" || bad "화면 응답 없음 — docker compose logs frontend 확인"
[ "$(status "https://$DOMAIN/privacy")" = 200 ] && ok "개인정보 안내 (/privacy)" || bad "개인정보 안내 화면 없음"

headers=$("${CURL[@]}" -D - -o /dev/null "https://$DOMAIN/" 2>/dev/null | tr -d '\r')
grep -qi '^strict-transport-security:' <<<"$headers" && ok "HSTS" || bad "HSTS 헤더 없음 (deploy/Caddyfile 확인)"
grep -qi '^content-security-policy:' <<<"$headers" && ok "CSP" || bad "CSP 헤더 없음"
grep -qi '^server:' <<<"$headers" && bad "Server 헤더가 노출됨" || ok "Server 헤더 숨김"

api_headers=$("${CURL[@]}" -D - -o /dev/null "https://$DOMAIN/api/v1/health" 2>/dev/null | tr -d '\r')
grep -qi "^content-security-policy: default-src 'none'" <<<"$api_headers" && ok "API 보안 헤더 (백엔드로 직접 전달됨)" || bad "API 응답에 백엔드 보안 헤더 없음 (Caddy의 /api 경로 확인)"

redirect=$(curl -sS --max-time 20 -o /dev/null -w '%{http_code} %{redirect_url}' "http://$DOMAIN/" 2>/dev/null || true)
case "$redirect" in
  30[178]\ https://*) ok "http → https 이동" ;;
  *) bad "http → https 이동 안 됨 ($redirect)" ;;
esac

if [ $fail -eq 0 ]; then echo "모두 정상"; else echo "확인이 필요한 항목이 있습니다"; fi
exit $fail
