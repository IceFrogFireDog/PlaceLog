"use client";
import { usePathname, useRouter, useSearchParams } from "next/navigation";

/** 커서 페이지 이동 기록을 URL(?pg=)에 둬서 뒤로가기·새로고침해도 같은 페이지를 보여준다. */
export function useCursorStack() {
  const sp = useSearchParams();
  const router = useRouter();
  const pathname = usePathname();
  const stack = (sp.get("pg") ?? "").split(",").filter(Boolean);
  const go = (next: string[]) => {
    const q = new URLSearchParams(sp.toString());
    if (next.length) q.set("pg", next.join(",")); else q.delete("pg");
    const qs = q.toString();
    router.push(qs ? `${pathname}?${qs}` : pathname, { scroll: false });
  };
  return {
    cursor: stack.length ? stack[stack.length - 1] : null,
    hasPrev: stack.length > 0,
    next: (c: string) => go([...stack, c]),
    prev: () => go(stack.slice(0, -1)),
  };
}
