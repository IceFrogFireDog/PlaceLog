"use client";
import Link from "next/link";
import { usePathname } from "next/navigation";

/** 지구본 화면(/)은 화면을 꽉 채우므로 바닥글을 숨긴다. */
export function SiteFooter() {
  if (usePathname() === "/") return null;
  return (
    <footer className="site-footer">
      <Link href="/privacy">개인정보 처리 안내</Link>
    </footer>
  );
}
