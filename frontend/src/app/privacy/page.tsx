import type { Metadata } from "next";

export const metadata: Metadata = { title: "개인정보 처리 안내 · 지구본 사진 기록" };

/**
 * 개인정보 처리 안내 초안.
 * 운영자 정보·위탁 업체·시행일은 빌드 때 환경변수로 넣는다(frontend/.env.example 참고).
 * 실제로 서비스를 공개하기 전에 법률 검토를 받아야 한다.
 */
const OFFICER = process.env.NEXT_PUBLIC_PRIVACY_OFFICER || "";
const CONTACT = process.env.NEXT_PUBLIC_PRIVACY_EMAIL || "";
const PROCESSORS = process.env.NEXT_PUBLIC_PRIVACY_PROCESSORS || "";
const EFFECTIVE = process.env.NEXT_PUBLIC_PRIVACY_EFFECTIVE_DATE || "";
const todo = (what: string) => <em className="muted">({what}을(를) 운영 설정에 넣어 주세요)</em>;

export default function PrivacyPage() {
  return (
    <article className="card narrow prose">
      <h1>개인정보 처리 안내</h1>
      <p className="notice">이 문서는 학교 프로젝트용 <strong>초안</strong>입니다. 실제 서비스로 공개하기 전에 운영자 정보와 위탁 업체를 채우고
        개인정보 보호법·위치정보법 검토를 받아야 합니다.</p>

      <h2>1. 수집하는 정보</h2>
      <ul>
        <li><strong>계정:</strong> 이메일, 닉네임, 표시명, 소개, 프로필 사진. 비밀번호는 복원할 수 없는 해시로만 저장합니다.</li>
        <li><strong>사진:</strong> 올린 사진 파일과 사진 속 정보(촬영 일시·시간대, 카메라·렌즈 정보, <strong>GPS 촬영 좌표</strong>), 설명, 공개 범위.</li>
        <li><strong>장소:</strong> 직접 만든 장소의 이름·좌표·주소·도시·국가.</li>
        <li><strong>친구 관계:</strong> 친구 요청과 수락 기록.</li>
        <li><strong>로그인 상태:</strong> 로그인 세션(쿠키)과 만료 시각. 세션 값 자체는 해시로만 저장합니다.</li>
        <li><strong>서버 기록:</strong> 오류 확인용 접속 기록(IP 주소, 요청 주소, 시각)이 서버 로그에 남을 수 있습니다. 비밀번호·인증 링크·원본 좌표는 기록하지 않습니다.</li>
      </ul>

      <h2>2. 이용 목적</h2>
      <ul>
        <li>회원 확인과 이메일 인증, 비밀번호 재설정 메일 발송</li>
        <li>사진을 장소별로 지구본 위에 기록하고, 정한 공개 범위(전체·친구·나만)에 따라 보여 주기</li>
        <li>무단 접근·과도한 요청 같은 부정 이용 방지. 운영자는 신고 처리 등을 위해 사진을 삭제하거나 계정 이용을 정지할 수 있습니다.</li>
      </ul>

      <h2>3. 위치정보 처리</h2>
      <ul>
        <li>사진의 GPS 좌표는 기본적으로 <strong>본인만</strong> 볼 수 있습니다. &lsquo;정확한 촬영 좌표 공개&rsquo;를 켠 경우에만 사진을 볼 수 있는 사람에게 보입니다.</li>
        <li>다른 사람에게 보이는 표시용 사진·썸네일에서는 GPS를 포함한 사진 속 정보를 모두 지웁니다. 원본 파일은 본인만 내려받을 수 있습니다.</li>
        <li>장소의 이름·좌표·주소는 그 장소의 사진을 볼 수 있는 사람에게 공개됩니다. 집 등 개인 장소는 정확한 좌표를 넣지 마세요.</li>
        <li>운영자 검토 사항: 이용자의 위치정보를 다루므로 실제 서비스 전에 위치정보법상 신고·약관 동의 필요 여부를 확인해야 합니다.</li>
      </ul>

      <h2>4. 외부 서비스로 전달되는 정보</h2>
      <ul>
        <li><strong>지도 타일:</strong> 지도에서 위치를 고를 때 브라우저가 지도 이미지 제공자(기본: OpenStreetMap)에 직접 요청하므로 접속 IP와 보고 있는 지도 범위가 전달됩니다.</li>
        <li><strong>장소 검색:</strong> 주소·장소 검색어와 &lsquo;도시·국가 채우기&rsquo;에 쓰는 좌표가 서버를 거쳐 검색 제공자(OpenStreetMap Nominatim 또는 카카오)에 전달됩니다. 이용자 계정 정보는 보내지 않습니다.</li>
        <li><strong>메일 발송·파일 저장(처리 위탁):</strong> {PROCESSORS || <>메일 발송 업체와 사진 저장소(객체 저장소를 쓰는 경우)에 처리를 맡길 수 있습니다. {todo("위탁 업체")}</>}</li>
      </ul>

      <h2>5. 보관 기간과 삭제</h2>
      <ul>
        <li>계정과 사진은 이용자가 지울 때까지 보관합니다. 사진을 지우면 원본·표시용·썸네일 파일도 함께 지웁니다.</li>
        <li><strong>계정 삭제:</strong> 설정 화면에서 비밀번호를 확인한 뒤 바로 지울 수 있습니다. 사진(원본 포함)·프로필 사진·친구 관계·로그인 기록·인증 링크를 즉시 지우며, 내가 만든 장소 중 다른 사람의 사진이 있는 곳은 공유 장소로 남기고 만든 사람 정보만 지웁니다.</li>
        <li>만료된 로그인 세션과 인증·재설정 링크, 지우지 못하고 남은 파일은 정리 작업으로 주기적으로 지웁니다.</li>
      </ul>

      <h2>6. 이용자의 권리</h2>
      <p>본인 정보의 열람·정정·삭제·처리 정지를 요청할 수 있습니다. 프로필·사진·계정은 화면에서 직접 고치거나 지울 수 있고, 그 밖의 요청은 아래 연락처로 보내 주세요.</p>

      <h2>7. 안전하게 지키는 방법</h2>
      <ul>
        <li>비밀번호·세션·인증 링크는 해시로만 저장하고, 로그인 쿠키는 자바스크립트가 읽을 수 없게(HttpOnly) 설정합니다.</li>
        <li>사진 파일은 공개 주소 없이 비공개로 저장하고, 매번 공개 범위를 확인한 뒤 전달합니다.</li>
        <li>원하면 2단계 인증(휴대폰 인증 앱)을 켤 수 있습니다. 인증 키는 서버 비밀값 없이는 만들 수 없는 형태로, 복구 코드는 해시로만 저장합니다.</li>
        <li>운영 환경에서는 HTTPS로만 통신합니다.</li>
      </ul>

      <h2>8. 문의</h2>
      <p>개인정보 보호 책임자: {OFFICER || todo("책임자 이름")} · 연락처: {CONTACT ? <a href={`mailto:${CONTACT}`}>{CONTACT}</a> : todo("연락처 이메일")}</p>
      <p className="muted">시행일: {EFFECTIVE || todo("시행일")}</p>
    </article>
  );
}
