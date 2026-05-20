// 한 종목의 현재가 카드. 백엔드 /market/prices/{code} 캐시 읽기 (KIS 직접 호출 X).
// 캐시는 APScheduler가 장중 5분마다 갱신. 미스(404) 시 "시세 준비 중" 카드.

type PriceData = {
  stock_code: string;
  name: string;
  current_price: string;
  change_rate: string;
  fetched_at?: string;
};

type PriceResponse = {
  success: boolean;
  data: PriceData | null;
  error: string | null;
};

type FetchResult =
  | { kind: "ok"; data: PriceData }
  | { kind: "not-cached" }
  | { kind: "error" };

const API_BASE = "http://localhost:8000";

async function fetchPrice(code: string): Promise<FetchResult> {
  try {
    const res = await fetch(`${API_BASE}/market/prices/${code}`, {
      cache: "no-store",
    });
    if (res.status === 404) return { kind: "not-cached" };
    if (!res.ok) return { kind: "error" };
    const json = (await res.json()) as PriceResponse;
    if (json.success && json.data) return { kind: "ok", data: json.data };
    return { kind: "error" };
  } catch {
    return { kind: "error" };
  }
}

function changeClass(rate: string): string {
  const n = parseFloat(rate);
  if (n > 0) return "text-green-600";
  if (n < 0) return "text-red-600";
  return "text-gray-500";
}

function formatRate(rate: string): string {
  const n = parseFloat(rate);
  const sign = n > 0 ? "+" : "";
  return `${sign}${(n * 100).toFixed(2)}%`;
}

function formatPrice(price: string): string {
  return parseInt(price, 10).toLocaleString("ko-KR");
}

export default async function PriceCard({ stockCode }: { stockCode: string }) {
  const result = await fetchPrice(stockCode);

  if (result.kind === "not-cached") {
    return (
      <div className="border rounded p-4 bg-gray-50">
        <p className="text-sm text-gray-500">{stockCode}</p>
        <p className="text-sm text-gray-400 mt-2">시세 준비 중</p>
      </div>
    );
  }

  if (result.kind === "error") {
    return (
      <div className="border rounded p-4 bg-gray-50">
        <p className="text-sm text-gray-500">{stockCode}</p>
        <p className="text-sm text-gray-400 mt-2">시세 조회 실패</p>
      </div>
    );
  }

  const data = result.data;
  return (
    <div className="border rounded p-4 bg-white">
      <div className="flex justify-between items-baseline">
        <p className="text-sm text-gray-500">{data.stock_code}</p>
        <p className="text-xs text-gray-400">KRW</p>
      </div>
      <p className="text-lg font-semibold mt-1">{data.name}</p>
      <p className="text-2xl font-bold mt-2">{formatPrice(data.current_price)}</p>
      <p className={`text-sm font-medium mt-1 ${changeClass(data.change_rate)}`}>
        {formatRate(data.change_rate)}
      </p>
    </div>
  );
}
