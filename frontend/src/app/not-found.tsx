import Link from "next/link";
export default function NotFound() {
  return (
    <div className="card center">
      <p>페이지를 찾을 수 없습니다.</p>
      <Link className="btn" href="/">지구본으로</Link>
    </div>
  );
}
