/** 프로필 사진. 없으면 표시명 첫 글자를 원 안에 보여 준다. */
export function Avatar({ user, size = 32 }: { user: { display_name: string; avatar_url?: string | null }; size?: number }) {
  const style = { width: size, height: size, fontSize: Math.round(size * 0.45) };
  if (user.avatar_url) {
    // 프로필 사진 주소는 바꿀 때마다 달라지고 공개 캐시되므로 <img>로 바로 쓴다
    // eslint-disable-next-line @next/next/no-img-element
    return <img className="avatar" src={user.avatar_url} alt="" width={size} height={size} style={style} />;
  }
  const initial = Array.from(user.display_name.trim())[0] ?? "?";
  return <span className="avatar avatar-empty" style={style} aria-hidden="true">{initial.toUpperCase()}</span>;
}
