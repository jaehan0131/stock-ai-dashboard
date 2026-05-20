"""한국 시장 데이터 수집·매매 게이트웨이.

- `kis_auth`: KIS OpenAPI OAuth 토큰 발급·캐시
- `kis_price`: 현재가 조회 (dry_run 기본)

CLAUDE.md 절대 룰: 모든 주문 함수는 `dry_run=True` 기본값.
시세 조회는 주문이 아니지만 외부 API 호출이라 동일하게 dry_run 옵션을 갖춘다.
"""
