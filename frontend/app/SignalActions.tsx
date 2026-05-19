"use client";

// 시그널 한 건의 [승인]/[거부] 두 버튼. 클릭 시 백엔드 호출 후 router.refresh로 표 갱신.
// CLAUDE.md 절대 룰: 이 컴포넌트는 user_status 변경 API만 호출. 주문 API 호출 0행.

import { useRouter } from "next/navigation";
import { useTransition } from "react";

type Props = { signalId: number };
type Action = "approve" | "reject";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8000";

export default function SignalActions({ signalId }: Props) {
  const router = useRouter();
  const [isPending, startTransition] = useTransition();

  async function handleAction(action: Action) {
    try {
      const res = await fetch(`${API_BASE}/signals/${signalId}/${action}`, {
        method: "POST",
      });
      if (res.status === 409) {
        alert("이미 처리된 시그널입니다");
        return;
      }
      if (!res.ok) {
        alert(`처리 실패: HTTP ${res.status}`);
        return;
      }
      startTransition(() => router.refresh());
    } catch {
      alert("백엔드 연결 실패. uvicorn 확인.");
    }
  }

  const baseBtn =
    "px-3 py-1 rounded text-white text-xs font-medium disabled:bg-gray-400 disabled:cursor-not-allowed";

  return (
    <div className="flex gap-2">
      <button
        type="button"
        disabled={isPending}
        onClick={() => handleAction("approve")}
        className={`${baseBtn} bg-green-600 hover:bg-green-700`}
      >
        {isPending ? "처리 중..." : "승인"}
      </button>
      <button
        type="button"
        disabled={isPending}
        onClick={() => handleAction("reject")}
        className={`${baseBtn} bg-red-600 hover:bg-red-700`}
      >
        {isPending ? "처리 중..." : "거부"}
      </button>
    </div>
  );
}
