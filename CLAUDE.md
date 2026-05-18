# Project: 주식 AI 대시보드 (한국 KRX 통합 트레이딩 대시보드)

한국 주식 시장 대상 통합 AI 대시보드 — (1) 시장 모니터링 + (2) AI 시그널 + (3) 실거래 실행.

## Critical Rules (절대 규칙)

- **기본 모드는 모의투자** (`TRADING_MODE=paper`) — `live` 전환은 사용자 명시 승인 후에만
- **KIS 모의/실전 키 분리** — `KIS_PAPER_*` / `KIS_LIVE_*` 별도 환경변수, 한 파일 공존 금지
- **AI 시그널 → 자동 주문 금지** — 시그널 → 사용자 승인 → 주문 순서 강제
- **모든 주문 함수는 `dry_run: bool = True` 기본값** — 실 API 미호출 + 페이로드 로깅만
- **시크릿 커밋 금지** — `.env`, `*.key`, `secrets/`는 `.gitignore` 명시
- **주문/체결 이벤트 영구 로그** — 타임스탬프·페이로드·응답 전체 DB 저장
- **레이트 리밋 가드** — KIS REST 초당 20req 한도, 코드 레벨 throttle 필수, 초과 시 큐잉
- **타인 자금 운용 금지** — 본인 계좌·학습용 한정. 타인 자금/상품화 코드 작성 거부
- **장 운영 외 주문 차단** — 정규장(09:00–15:30 KST) + 영업일 체크 후 발주. 시간외 단일가는 별도 플래그

## Architecture (아키텍처)

```
주식 AI 대시보드/
├── CLAUDE.md
├── .env.example          # 키 이름만, 값 비움
├── .gitignore            # .env, secrets/, *.key 포함
├── backend/
│   ├── app/
│   │   ├── main.py       # FastAPI 엔트리
│   │   ├── core/         # 설정(pydantic-settings), 환경변수, KIS 토큰 캐시
│   │   ├── api/          # FastAPI 라우터 (main.py 비대 방지)
│   │   ├── market/       # 시세·종목 수집
│   │   ├── signals/      # AI/지표 시그널
│   │   ├── trading/      # KIS OpenAPI 래퍼, 주문
│   │   └── storage/      # DB 모델
│   ├── tests/            # pytest
│   └── alembic/          # DB 마이그레이션
└── frontend/
    ├── app/              # Next.js App Router
    ├── components/
    ├── lib/              # API 클라이언트, 유틸
    └── hooks/            # React 커스텀 훅
```

## Tech Stack (기술 스택)

- Frontend: Next.js (App Router), TypeScript, Tailwind, TradingView Lightweight Charts, TanStack Query(서버 상태), Zustand(클라 상태), Vitest(테스트)
- Backend: Python 3.11+, FastAPI, APScheduler, SQLAlchemy 2.x + Alembic, `websockets`(KIS WS), `structlog`, `pydantic-settings`
- Data: `pykrx`, `finance-datareader`, KIS OpenAPI (REST+WS), DART OpenAPI
- AI: Anthropic API — `claude-sonnet-4-6` (요약/판단), `claude-opus-4-7` (최종 시그널)
- DB: SQLite (MVP) → Postgres/Supabase (확장)
- Secrets: 로컬 `.env`, 운영 OS keyring 또는 Supabase Vault

## Build & Test Commands (빌드/테스트)

> 첫 모듈 구현 후 실제 동작 확인하며 갱신. 현재는 계획값.

```bash
# 초기 세팅 (최초 1회)
cp .env.example .env                           # 환경변수 파일 생성, 값 채우기
cd backend && alembic upgrade head             # DB 마이그레이션

# 백엔드
cd backend && uvicorn app.main:app --reload   # 개발 서버
pytest                                         # 테스트
ruff check . && ruff format .                  # 린트 + 포맷
mypy .                                         # 타입 체크

# 프론트엔드
cd frontend && pnpm dev                        # 개발 서버
pnpm test                                      # 테스트 (Vitest)
pnpm lint                                      # 린트
tsc --noEmit                                   # 타입 체크
```

## Domain Context (도메인 컨텍스트)

- **모의투자(Paper Trading)**: 가상 잔고로 KIS 시스템 매매 시뮬레이션. 키·엔드포인트 실전과 분리
- **시그널(Signal)**: 매수/매도/관망 추천. 가격·재무·뉴스 → 의사결정
- **드라이런(Dry-run)**: 외부 API 미호출, 페이로드 로깅만 (테스트 모드)
- **호가**: 매수/매도 대기 가격대. KIS WebSocket으로 실시간 수신

### 한국 시장 규칙 (Korea Market Rules)

- **종목 코드**: 6자리 **문자열** (`'005930'`). DB·API·타입 전부 string, int 저장 금지 (앞 0 손실)
- **타임존**: DB 저장은 **UTC**, 표시·입력은 **KST**(`Asia/Seoul`). 경계에서만 변환
- **장 운영 시간**: 정규장 09:00–15:30 KST, 동시호가 08:30–09:00 / 15:20–15:30
- **휴장일**: `pykrx`로 영업일 검증, 주문 전 필수 체크. 주말·공휴일·임시휴장 포함
- **상하한가**: 코스피/코스닥 ±30%. VI(변동성완화장치) 발동 시 일시정지 — 주문 거부 처리
- **매매단위**: 기본 1주. ETF/우선주 호가단위(틱) 상이 — KIS API 응답값 신뢰

```
데이터 흐름:
KRX/네이버/DART → market/ → storage/(DB) → signals/ → frontend/
                                                        ↓
                                        사용자 승인 → trading/ → KIS OpenAPI
```

## Coding Conventions (코딩 컨벤션)

- Python: `snake_case` (함수/변수), `PascalCase` (클래스), `SCREAMING_SNAKE` (상수)
- TypeScript: `camelCase` (함수/변수), `PascalCase` (컴포넌트/타입)
- DB 테이블/컬럼: `snake_case`
- 환경변수: `SCREAMING_SNAKE`, 모의/실전 접두사 (`KIS_PAPER_APP_KEY` vs `KIS_LIVE_APP_KEY`)
- 커밋: `<type>: <한국어 설명>` — `feat | fix | refactor | docs | test | chore`
- 코드 식별자는 영어, 코멘트/docstring은 한국어 허용

## Key Patterns (핵심 패턴)

- 주문 함수 시그니처: 항상 `def place_order(..., dry_run: bool = True)`
- 외부 API 호출: `try/except` + 구조화 로그, 실패 시 명시적 에러 메시지
- 시크릿: 환경변수에서만 read, 하드코딩 금지
- 시세 폴링: KIS API 일일/초당 호출 한도 고려, 캐시 우선
- 네이버 금융: 공식 API 아님 — 요청 빈도 제한 + robots.txt 준수
- API 응답 포맷: `{ success, data, error }` 형태로 통일
- 금액·수량 타입: Python `Decimal`만 (`float` 금지). TS는 `string` 또는 `bigint` (`number` 부동소수점 회피)
- KIS OAuth 토큰: 24h 만료, 만료 5분 전 자동 재발급. 토큰 캐시는 `core/`에서 모의/실전 분리 저장
- 에러 알림: 주문 실패·체결 이상 시 사용자 즉시 알림 (UI 토스트 최소, 추후 푸시/메일)
- 타임스탬프 일관성: 모든 `datetime`은 `tz-aware`. naive datetime DB 저장 금지

## Trigger Keywords (트리거 키워드)

- `"백테스트 돌려줘"` → `backend/app/signals/backtest.py` 실행, 결과 리포트 출력
- `"실거래 모드 켜줘"` → `TRADING_MODE=live` 전환 전 **명시 경고 + 재확인** 필수 (한 번 더 yes/no)

## Learning Mode

학습 프로젝트 — 새 개념(라이브러리·API·도구) 등장 시 한두 줄 풀이 곁들임. 전역 CLAUDE.md의 "결과 먼저, 분석은 요청 시" 원칙은 그대로 유지.
