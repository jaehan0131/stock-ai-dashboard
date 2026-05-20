"use client";

// 시그널 [승인]/[거부] 액션 + 토스트.
// CLAUDE.md 절대 룰: 이 컴포넌트는 user_status 변경 API만 호출 (직접 주문 0행).
// 종목 매칭된 시그널은 OrderModal로 라우팅 — 2단계 동의 흐름.

import { useRouter } from "next/navigation";
import { useEffect, useState, useTransition } from "react";

import OrderModal from "@/components/OrderModal";

type Props = {
  signalId: number;
  direction: string;
  targetStocks: string[];
};

const API_BASE = "http://localhost:8000";


export default function SignalActions({ signalId, direction, targetStocks }: Props) {
  const router = useRouter();
  const [isPending, startTransition] = useTransition();
  const [toast, setToast] = useState<{ msg: string; ok: boolean } | null>(null);
  const [modalOpen, setModalOpen] = useState(false);

  useEffect(() => {
    if (!toast) return;
    const t = setTimeout(() => setToast(null), 2000);
    return () => clearTimeout(t);
  }, [toast]);

  async function approveWithoutOrder() {
    // 매크로 시그널(종목 없음) — 주문할 게 없으므로 상태만 변경.
    try {
      const res = await fetch(`${API_BASE}/signals/${signalId}/approve`, {
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
      setToast({ msg: "✅ 승인됨 (주문 없음)", ok: true });
      startTransition(() => router.refresh());
    } catch {
      setToast({ msg: "백엔드 연결 실패", ok: false });
    }
  }

  async function rejectSignal() {
    try {
      const res = await fetch(`${API_BASE}/signals/${signalId}/reject`, {
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
      setToast({ msg: "❌ 거부됨", ok: true });
      startTransition(() => router.refresh());
    } catch {
      setToast({ msg: "백엔드 연결 실패", ok: false });
    }
  }

  function handleApprove() {
    if (targetStocks.length === 0) {
      // 매크로 시그널 — 모달 없이 승인만
      approveWithoutOrder();
    } else {
      // 종목 시그널 — 주문 모달로 2단계 동의
      setModalOpen(true);
    }
  }

  const orderDirection: "buy" | "sell" =
    direction.includes("buy") || direction === "watch" ? "buy" : "sell";

  const baseBtn =
    "px-3 py-1 rounded text-white text-xs font-medium disabled:bg-gray-400 disabled:cursor-not-allowed";

  return (
    <div className="flex items-center gap-2 relative">
      <button
        type="button"
        disabled={isPending}
        onClick={handleApprove}
        className={`${baseBtn} bg-green-600 hover:bg-green-700`}
      >
        {isPending ? "처리 중..." : "승인"}
      </button>
      <button
        type="button"
        disabled={isPending}
        onClick={rejectSignal}
        className={`${baseBtn} bg-red-600 hover:bg-red-700`}
      >
        {isPending ? "처리 중..." : "거부"}
      </button>
      {toast && (
        <span
          className={`text-xs px-2 py-1 rounded ${
            toast.ok
              ? "bg-green-100 text-green-800"
              : "bg-red-100 text-red-800"
          }`}
        >
          {toast.msg}
        </span>
      )}
      {modalOpen && targetStocks.length > 0 && (
        <OrderModal
          signalId={signalId}
          stockCode={targetStocks[0]}
          defaultDirection={orderDirection}
          onClose={() => setModalOpen(false)}
          onSubmitted={(msg, ok) => {
            setToast({ msg, ok });
            startTransition(() => router.refresh());
          }}
        />
      )}
    </div>
  );
}
