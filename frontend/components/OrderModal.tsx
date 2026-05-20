"use client";

// 시그널 승인 → 주문 모달. CLAUDE.md "2단계 동의"의 두 번째 단계.
// 모달은 target_stocks 있을 때만 열림. dry_run OFF 시 빨간 경고 + window.confirm.

import { useState } from "react";

const API_BASE = "http://localhost:8000";

type Props = {
  signalId: number;
  stockCode: string;
  defaultDirection: "buy" | "sell";
  onClose: () => void;
  onSubmitted: (msg: string, ok: boolean) => void;
};

export default function OrderModal({
  signalId,
  stockCode,
  defaultDirection,
  onClose,
  onSubmitted,
}: Props) {
  const [direction, setDirection] = useState<"buy" | "sell">(defaultDirection);
  const [quantity, setQuantity] = useState(1);
  const [price, setPrice] = useState("");
  const [orderType, setOrderType] = useState<"market" | "limit">("market");
  const [dryRun, setDryRun] = useState(true);
  const [submitting, setSubmitting] = useState(false);

  async function handleSubmit() {
    if (!dryRun) {
      const ok = window.confirm(
        "실거래 모드입니다. 정말 주문을 전송하시겠습니까?"
      );
      if (!ok) return;
    }
    setSubmitting(true);
    try {
      // 2단계 동의 완료 — 승인 + 주문 동시 호출
      await fetch(`${API_BASE}/signals/${signalId}/approve`, { method: "POST" });
      const res = await fetch(`${API_BASE}/trading/order`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          signal_id: signalId,
          stock_code: stockCode,
          direction,
          quantity,
          price: price || null,
          order_type: orderType,
          dry_run: dryRun,
        }),
      });
      const json = (await res.json()) as {
        success: boolean;
        error: string | null;
      };
      if (json.success) {
        onSubmitted(dryRun ? "✅ 모의 실행 완료" : "✅ 주문 접수", true);
      } else {
        onSubmitted(`❌ ${json.error ?? "실패"}`, false);
      }
      onClose();
    } catch {
      onSubmitted("❌ 네트워크 오류", false);
      setSubmitting(false);
    }
  }

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
      <div className="bg-white rounded-lg p-6 w-96 space-y-3">
        <h2 className="text-lg font-bold">주문 — {stockCode}</h2>

        <label className="block text-sm">
          방향
          <select
            value={direction}
            onChange={(e) => setDirection(e.target.value as "buy" | "sell")}
            className="w-full border rounded px-2 py-1 mt-1"
          >
            <option value="buy">매수</option>
            <option value="sell">매도</option>
          </select>
        </label>

        <label className="block text-sm">
          수량
          <input
            type="number"
            min={1}
            value={quantity}
            onChange={(e) => setQuantity(parseInt(e.target.value, 10) || 1)}
            className="w-full border rounded px-2 py-1 mt-1"
          />
        </label>

        <label className="block text-sm">
          주문 유형
          <select
            value={orderType}
            onChange={(e) =>
              setOrderType(e.target.value as "market" | "limit")
            }
            className="w-full border rounded px-2 py-1 mt-1"
          >
            <option value="market">시장가</option>
            <option value="limit">지정가</option>
          </select>
        </label>

        {orderType === "limit" && (
          <label className="block text-sm">
            가격
            <input
              type="text"
              inputMode="decimal"
              value={price}
              onChange={(e) => setPrice(e.target.value)}
              className="w-full border rounded px-2 py-1 mt-1"
              placeholder="예: 82000"
            />
          </label>
        )}

        <label className="flex items-center gap-2 text-sm pt-2">
          <input
            type="checkbox"
            checked={dryRun}
            onChange={(e) => setDryRun(e.target.checked)}
          />
          <span>모의 실행 (dry_run)</span>
        </label>

        {!dryRun && (
          <div className="bg-red-50 border border-red-200 text-red-800 text-xs p-2 rounded">
            ⚠️ 실거래 모드 — 실제 주문이 전송됩니다.
          </div>
        )}

        <div className="flex gap-2 pt-2">
          <button
            type="button"
            onClick={onClose}
            disabled={submitting}
            className="flex-1 px-3 py-2 rounded border text-sm hover:bg-gray-50 disabled:bg-gray-100"
          >
            취소
          </button>
          <button
            type="button"
            onClick={handleSubmit}
            disabled={submitting}
            className={`flex-1 px-3 py-2 rounded text-white text-sm font-medium ${
              dryRun
                ? "bg-blue-600 hover:bg-blue-700"
                : "bg-red-600 hover:bg-red-700"
            } disabled:bg-gray-400`}
          >
            {submitting
              ? "전송 중..."
              : dryRun
              ? "[모의 실행]"
              : "[실제 주문]"}
          </button>
        </div>
      </div>
    </div>
  );
}
