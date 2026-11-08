import Link from "next/link";

export function ErrorState({ message }: { message: string }) {
  return (
    <div className="card center">
      <p className="error">{message}</p>
      <Link className="btn" href="/">지구본으로</Link>
    </div>
  );
}
