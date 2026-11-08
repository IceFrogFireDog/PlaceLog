import type { PhotoListItem } from "@/lib/types";
import { PhotoCard } from "./PhotoCard";

export function PhotoGrid({ photos, empty = "볼 수 있는 사진이 없습니다.", showOwner }: { photos: PhotoListItem[]; empty?: string; showOwner?: boolean }) {
  if (photos.length === 0) return <p className="muted center">{empty}</p>;
  return <div className="photo-grid">{photos.map((p) => <PhotoCard key={p.id} photo={p} showOwner={showOwner} />)}</div>;
}
