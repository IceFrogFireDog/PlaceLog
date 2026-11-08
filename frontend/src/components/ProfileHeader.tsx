import type { Profile } from "@/lib/types";
import { Avatar } from "./Avatar";

export function ProfileHeader({ profile }: { profile: Profile }) {
  return (
    <section className="card profile-header">
      <div className="profile-title">
        <Avatar user={profile} size={72} />
        <h1>{profile.display_name} <span className="muted">@{profile.username}</span></h1>
      </div>
      {profile.bio && <p className="bio">{profile.bio}</p>}
      <ul className="stats">
        <li><strong>{profile.photo_count ?? 0}</strong> 사진</li>
        <li><strong>{profile.place_count ?? 0}</strong> 장소</li>
        {profile.friend_count !== null && <li><strong>{profile.friend_count}</strong> 친구</li>}
      </ul>
    </section>
  );
}
