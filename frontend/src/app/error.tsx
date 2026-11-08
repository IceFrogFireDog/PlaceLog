"use client";
// 내부 예외 내용은 화면에 노출하지 않는다.
export default function ErrorPage({ reset }: { error: Error; reset: () => void }) {
  return (
    <div className="card center">
      <p>문제가 발생했습니다.</p>
      <button className="btn primary" onClick={reset}>다시 시도</button>
    </div>
  );
}
