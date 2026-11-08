export type Visibility = "PUBLIC" | "FRIENDS" | "PRIVATE";
export type MapMode = "WORLD" | "FRIENDS" | "ME";
export type RelationStatus = "SELF" | "NONE" | "OUTGOING" | "INCOMING" | "FRIENDS";

/**
 * 백엔드에 따라 일부 필드(이메일 인증·프로필 사진·2단계 인증·관리자)를 보내지 않는다.
 * 필드가 없으면 그 기능이 아직 없는 백엔드이므로 화면에서 숨기거나 기본값으로 본다.
 */
export interface Me {
  id: string; email: string; username: string; display_name: string; bio: string; csrf_token: string;
  email_verified?: boolean; avatar_url?: string | null; two_factor_enabled?: boolean; is_admin?: boolean;
}
export interface UserBrief { id: string; username: string; display_name: string; avatar_url?: string | null }
export interface Relation { status: RelationStatus; friendship_id: string | null }
export interface SearchUser extends UserBrief { relation: Relation }
export interface Profile extends UserBrief {
  bio: string; created_at: string; photo_count?: number; place_count?: number; friend_count: number | null; relation: Relation;
}
export interface Friendship {
  id: string; status: "PENDING" | "ACCEPTED"; direction: "incoming" | "outgoing" | null; user: UserBrief; created_at: string; accepted_at: string | null;
}
export interface Place {
  id: string; name: string; address: string | null; city: string | null; country_code: string | null; latitude: number; longitude: number; created_at: string;
}
export interface PlaceDetail extends Place { photo_count: number }
export interface PlaceCreated extends Place { nearby_candidates: Place[] }
/** 업로드 직후 PROCESSING(원본만 저장) → 변환이 끝나면 READY, 변환할 수 없으면 FAILED. READY가 아닌 사진은 작성자에게만 보인다. */
export type PhotoStatus = "PROCESSING" | "READY" | "FAILED";
/** 변환 작업 큐가 없는 백엔드는 status를 보내지 않는다 → 등록이 끝난 사진이므로 READY */
export const photoStatus = (p: { status?: PhotoStatus }): PhotoStatus => p.status ?? "READY";
export interface PhotoListItem {
  id: string; owner: UserBrief; place: { id: string; name: string; latitude: number; longitude: number };
  caption: string; visibility: Visibility; width: number; height: number; thumbnail_url: string; taken_at: string | null; created_at: string;
  status?: PhotoStatus;
}
export interface PhotoDetail extends PhotoListItem {
  display_url: string; original_url: string | null; taken_timezone: string | null;
  shot_latitude: number | null; shot_longitude: number | null; share_exact_location: boolean;
  camera: string | null; lens: string | null; focal_length: number | null; aperture: number | null; shutter_speed: string | null; iso: number | null;
  is_owner: boolean; updated_at: string; processing_error?: string | null;
}
export interface Page<T> { items: T[]; next_cursor: string | null }

export interface MapPlace { kind: "place"; place_id: string; name: string; latitude: number; longitude: number; photo_count: number }
export interface MapCluster { kind: "cluster"; id: string; latitude: number; longitude: number; photo_count: number; place_count: number; label: string }
export type MapItem = MapPlace | MapCluster;
export interface MapResponse { mode: MapMode; zoom: number; items: MapItem[]; truncated: boolean }

/** 지구본 시점: bbox=null이면 전 지구 */
export interface GlobeView { bbox: [number, number, number, number] | null; zoom: number }

/** 장소 검색 제공자(Nominatim·카카오) 결과 */
export interface GeoResult { name: string; address: string | null; latitude: number; longitude: number; city: string | null; country_code: string | null }
export interface GeoSearch { items: GeoResult[]; next_cursor: string | null; attribution: string }
export interface Message { message: string }
