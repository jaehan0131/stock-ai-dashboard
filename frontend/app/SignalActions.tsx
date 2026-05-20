"use client";

// 시그널 한 건의 [승인]/[거부] 두 버튼 + 인라인 toast.
// CLAUDE.md 절대 룰: 이 컴포넌트는 user_status 변경 API만 호출. 주문 API 호출 0행.

import { useRouter } from "next/navigation";
import { useEffect, useState, useTransition } from "react";

type Props = { signalId: number };
type Action = "approve" | "reject";

const API_BASE = "http://localhost:8000";

export default function SignalActions({ signalId }: Props) {
  const router = useRouter();
  const [isPending, startTransition] = useTransition();
  const [toast, setToast] = useState<{ msg: string; ok: boolean } | null>(null);

  useEffect(() => {
    if (!toast) return;
    const t = setTimeout(() => setToast(null), 2000);
    return () => clearTimeout(t);
  }, [toast]);

  async function handleAction(action: Action) {
    try {
      const res = await fetch(`${API_BASE}/signals/${signalId}/${action}`, {
        method: "POST",
      });
      if (res.status === 409) {
        setToast({ msg: "이미 처리됨", ok: false });
        return;
      }
      if (!res.ok) {
        setToast({ msg: `실패: HTTP ${res.status}`, ok: false });
        return;
      }
      setToast({ msg: action === "approve" ? "✅ 승인됨" : "❌ 거부됨", ok: true });
      startTransition(() => router.refresh());
    } catch {
      setToast({ msg: "백엔드 연결 실패", ok: false });
    }
  }

  const baseBtn =
    "px-3 py-1 rounded text-white text-xs font-medium disabled:bg-gray-400 disabled:cursor-not-allowed";

  return (
    <div className="flex items-center gap-2 relative">
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
      {toast && (
        <span
          className={`text-xs px-2 py-1 rounded ${
            toast.ok ? "bg-green-100 text-green-800" : "bg-red-100 text-red-800"
          }`}
        >
          {toast.msg}
        </span>
      )}
    </div>
  );
}
