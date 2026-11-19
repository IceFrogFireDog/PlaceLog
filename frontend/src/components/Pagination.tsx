"use client";
/** 커서 기반: 이전 페이지는 방문한 커서 스택으로 처리 */
export function Pagination({ hasPrev, hasNext, loading, onPrev, onNext }: { hasPrev: boolean; hasNext: boolean; loading: boolean; onPrev: () => void; onNext: () => void }) {
  if (!hasPrev && !hasNext) return null;
  return (
    <div className="pagination">
      <button className="btn" disabled={!hasPrev || loading} onClick={onPrev}>이전</button>
      {loading && <span className="muted">불러오는 중…</span>}
      <button className="btn" disabled={!hasNext || loading} onClick={onNext}>다음</button>
    </div>
  );
}
