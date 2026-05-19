// Server Component (async). "use client" 미사용 — Next.js 서버에서 fetch 후 HTML 렌더.
// 백엔드 /signals/pending 조회 → 표로 표시. 실패 시 한국어 에러 박스.

import SignalActions from "./SignalActions";

type Signal = {
  id: number;
  created_at: string;
  direction: string;
  target: string;
  applied_rule: string;
  combined_score: number;
  weight_sum: string;
  supporting_log_ids: number[];
  reasoning: string;
  signal_log_id: number;
  user_status: string;
  reviewed_at: string | null;
};

const API_BASE = process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8000";

async function fetchPending(): Promise<Signal[]> {
  const res = await fetch(`${API_BASE}/signals/pending`, { cache: "no-store" });
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json();
}

function directionClass(d: string): string {
  if (d.includes("buy")) return "text-green-600 font-semibold";
  if (d.includes("sell")) return "text-red-600 font-semibold";
  return "text-gray-500";
}

function formatKst(iso: string): string {
  return new Date(iso).toLocaleString("ko-KR", {
    timeZone: "Asia/Seoul",
    hour12: false,
  });
}

export default async function Home() {
  let signals: Signal[] = [];
  let errorMsg: string | null = null;
  try {
    signals = await fetchPending();
  } catch (e) {
    errorMsg = e instanceof Error ? e.message : String(e);
  }

  return (
    <main className="max-w-6xl mx-auto p-8">
      <h1 className="text-2xl font-bold mb-4">Pending 시그널</h1>

      {errorMsg ? (
        <div className="bg-red-50 border border-red-200 text-red-800 p-4 rounded">
          <p className="font-semibold">백엔드 연결 실패</p>
          <p className="text-sm mt-1">
            uvicorn 띄워져 있는지 확인 (
            <a className="underline" href={`${API_BASE}/healthz`}>
              {API_BASE}/healthz
            </a>
            ) — {errorMsg}
          </p>
        </div>
      ) : signals.length === 0 ? (
        <p className="text-gray-500 mt-4">Pending 시그널 없음</p>
      ) : (
        <table className="w-full border-collapse text-sm">
          <thead>
            <tr className="bg-gray-100">
              <th className="border px-3 py-2 text-left">id</th>
              <th className="border px-3 py-2 text-left">방향</th>
              <th className="border px-3 py-2 text-left">대상</th>
              <th className="border px-3 py-2 text-left">룰</th>
              <th className="border px-3 py-2 text-right">점수</th>
              <th className="border px-3 py-2 text-right">가중치</th>
              <th className="border px-3 py-2 text-left">생성(KST)</th>
              <th className="border px-3 py-2 text-left">상태</th>
              <th className="border px-3 py-2 text-left">액션</th>
            </tr>
          </thead>
          <tbody>
            {signals.map((s) => (
              <tr key={s.id}>
                <td className="border px-3 py-2">{s.id}</td>
                <td className={`border px-3 py-2 ${directionClass(s.direction)}`}>
                  {s.direction}
                </td>
                <td className="border px-3 py-2">{s.target}</td>
                <td className="border px-3 py-2">{s.applied_rule}</td>
                <td className="border px-3 py-2 text-right">{s.combined_score}</td>
                <td className="border px-3 py-2 text-right">{s.weight_sum}</td>
                <td className="border px-3 py-2">{formatKst(s.created_at)}</td>
                <td className="border px-3 py-2">{s.user_status}</td>
                <td className="border px-3 py-2">
                  <SignalActions signalId={s.id} />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </main>
  );
}
