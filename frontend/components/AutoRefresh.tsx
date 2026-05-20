"use client";

// 30초마다 router.refresh() 호출. 남은 초 카운트다운 표시.

import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

const INTERVAL_SEC = 30;

export default function AutoRefresh() {
  const router = useRouter();
  const [remaining, setRemaining] = useState(INTERVAL_SEC);

  useEffect(() => {
    const tick = setInterval(() => {
      setRemaining((r) => {
        if (r <= 1) {
          router.refresh();
          return INTERVAL_SEC;
        }
        return r - 1;
      });
    }, 1000);
    return () => clearInterval(tick);
  }, [router]);

  return (
    <span className="text-xs text-gray-500">
      다음 갱신: <span className="font-mono">{remaining}s</span>
    </span>
  );
}
