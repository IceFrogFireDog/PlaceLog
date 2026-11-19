"use client";
import { PhotoUploadForm } from "@/components/PhotoUploadForm";
import { RequireAuth } from "@/components/RequireAuth";

export default function UploadPage() {
  return (
    <RequireAuth keepOnLogout>
      <div className="narrow">
        <h1>사진 등록</h1>
        <PhotoUploadForm />
      </div>
    </RequireAuth>
  );
}
