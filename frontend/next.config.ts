import type { NextConfig } from "next";
import { PHASE_DEVELOPMENT_SERVER } from "next/constants";

// 브라우저는 같은 출처(/api/v1)로만 호출하고 Next가 백엔드로 전달한다 → 쿠키·CSRF가 단순해진다.
// 주의: rewrites 대상과 아래 보안 헤더는 `next build` 시점에 정해진다. 배포 이미지는 빌드 인자로 넣는다.
const API_ORIGIN = process.env.API_ORIGIN ?? "http://localhost:8000";
const TILE_URL = process.env.NEXT_PUBLIC_MAP_TILE_URL || "https://tile.openstreetmap.org/{z}/{x}/{y}.png";

/** 타일 주소 템플릿 → CSP 출처. {s} 같은 하위 도메인 자리는 와일드카드로 바꾼다 */
export function tileSource(url: string): string {
  const m = url.match(/^(https?:)\/\/([^/?#]+)/);
  return m ? `${m[1]}//${m[2].replace(/\{[^}]+\}/g, "*")}` : "";
}

function contentSecurityPolicy(dev: boolean): string {
  return [
    "default-src 'self'",
    // Next는 페이지 데이터를 인라인 스크립트로 넣으므로 'unsafe-inline' 필요(외부 스크립트는 여전히 차단). 개발 서버는 eval 사용.
    `script-src 'self' 'unsafe-inline'${dev ? " 'unsafe-eval'" : ""}`,
    "style-src 'self' 'unsafe-inline'", // Leaflet·React 인라인 스타일
    `img-src 'self' data: blob: ${tileSource(TILE_URL)}`.trim(), // blob: 업로드 미리보기
    "font-src 'self' data:",
    `connect-src 'self'${dev ? " ws: wss:" : ""}`,
    "worker-src 'self' blob:",
    "object-src 'none'",
    "base-uri 'self'",
    "form-action 'self'",
    "frame-ancestors 'none'",
  ].join("; ");
}

export default function config(phase: string): NextConfig {
  const dev = phase === PHASE_DEVELOPMENT_SERVER;
  const securityHeaders = [
    { key: "Content-Security-Policy", value: contentSecurityPolicy(dev) },
    { key: "X-Content-Type-Options", value: "nosniff" },
    { key: "X-Frame-Options", value: "DENY" },
    { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
    { key: "Permissions-Policy", value: "camera=(), microphone=(), geolocation=()" },
  ];
  // 메일 링크의 토큰이 다른 사이트로 Referer에 실려 나가지 않게
  const noReferrer = [{ key: "Referrer-Policy", value: "no-referrer" }];

  return {
    // Docker 이미지용 최소 실행 파일 묶음. 로컬 `next start`와 충돌하지 않게 빌드 때만 켠다.
    output: process.env.NEXT_OUTPUT === "standalone" ? "standalone" : undefined,
    async rewrites() {
      return [{ source: "/api/v1/:path*", destination: `${API_ORIGIN}/api/v1/:path*` }];
    },
    async headers() {
      return [
        // /api/v1은 백엔드가 자체 보안 헤더를 붙인다 (운영에서는 Caddy가 백엔드로 바로 보냄)
        { source: "/((?!api/v1/).*)", headers: securityHeaders },
        { source: "/verify-email", headers: noReferrer },
        { source: "/reset-password", headers: noReferrer },
      ];
    },
    // 보호 이미지는 쿠키 권한 검사가 필요하므로 next/image 최적화기를 거치지 않고 <img>로 직접 표시한다.
    images: { unoptimized: true },
    experimental: {
      // rewrites 프록시는 기본 10MB에서 요청 본문을 잘라 큰 사진 업로드가 500으로 실패한다.
      // 백엔드 MAX_RAW_UPLOAD_BYTES(80MB, RAW) + multipart 여유분보다 크게 유지할 것. 한도 검사는 백엔드가 413으로 처리.
      proxyClientMaxBodySize: "90mb",
    },
    poweredByHeader: false,
    // Next 16.3+는 dev 실행 시 AGENTS.md·CLAUDE.md를 자동 생성한다. 사용자 저장소에 파일을 만들지 않도록 끈다.
    agentRules: false,
  };
}
