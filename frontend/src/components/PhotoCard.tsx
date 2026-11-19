import Link from "next/link";
import { photoStatus, type PhotoListItem } from "@/lib/types";
import { Avatar } from "./Avatar";

const VIS_LABEL = { PUBLIC: "전체", FRIENDS: "친구", PRIVATE: "나만" } as const;

export function PhotoCard({ photo, showOwner = true }: { photo: PhotoListItem; showOwner?: boolean }) {
  const alt = photo.caption ? photo.caption.slice(0, 120) : `${photo.place.name}에서 찍은 사진`;
  const status = photoStatus(photo);
  return (
    <Link href={`/photos/${photo.id}`} className="photo-card">
      {status === "READY" ? (
        // 권한 검사가 필요한 이미지라 <img>로 직접 요청 (쿠키 포함)
        // eslint-disable-next-line @next/next/no-img-element
        <img src={photo.thumbnail_url} alt={alt} loading="lazy" width={photo.width} height={photo.height} />
      ) : (
        <div className={`photo-placeholder ${status === "FAILED" ? "failed" : ""}`} role="img" aria-label={alt}>
          {status === "PROCESSING" ? "변환 중…" : "변환 실패"}
        </div>
      )}
      <div className="photo-meta">
        <span>{photo.place.name}</span>
        {showOwner && <span className="muted owner"><Avatar user={photo.owner} size={18} />@{photo.owner.username}</span>}
        <span className={`badge vis-${photo.visibility.toLowerCase()}`}>{VIS_LABEL[photo.visibility]}</span>
      </div>
    </Link>
  );
}
