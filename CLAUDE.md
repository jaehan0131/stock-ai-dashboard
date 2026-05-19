# Project: 주식 AI 대시보드 (한국 KRX 통합 트레이딩 대시보드)

한국 주식 시장 대상 통합 AI 대시보드 — (1) **글로벌 매크로 모니터링** + (2) 시그널 생성 + (3) 한국 주식 매매 실행. 매매는 한국 시장만, 분석은 글로벌.

## Critical Rules (절대 규칙)

- **기본 모드는 모의투자** (`TRADING_MODE=paper`) — `live` 전환은 사용자 명시 승인 후에만
- **KIS 모의/실전 키 분리** — `KIS_PAPER_*` / `KIS_LIVE_*` 별도 환경변수, 한 파일 공존 금지
- **AI 시그널 → 자동 주문 금지** — 시그널 → 사용자 승인 → 주문 순서 강제
- **모든 주문 함수는 `dry_run: bool = True` 기본값** — 실 API 미호출 + 페이로드 로깅만
- **시크릿 커밋 금지** — `.env`, `*.key`, `secrets/`는 `.gitignore` 명시
- **주문/체결 이벤트 영구 로그** — 타임스탬프·페이로드·응답 전체 DB 저장
- **레이트 리밋 가드** — KIS REST 초당 20req 한도, 코드 레벨 throttle 필수
- **타인 자금 운용 금지** — 본인 계좌·학습용 한정
- **장 운영 외 주문 차단** — 정규장(09:00–15:30 KST) + 영업일 체크 후 발주
- **모든 LLM 호출은 모델 라우터를 거친다** — Sonnet/Opus 직접 호출 금지 (작업 난이도별 라우팅)
- **룰북·시스템 프롬프트는 캐시 가능한 prefix 위치에 둔다** — Prompt Caching 1시간 TTL 활용
- **룰북에 없는 즉흥 시그널 거부** — LLM이 `backend/app/intel/rulebook.md` 외 근거로 판단 시 출력 거부

## Architecture (아키텍처)

```
주식 AI 대시보드/
├── CLAUDE.md
├── .env.example
├── .gitignore
├── backend/
│   ├── app/
│   │   ├── main.py           # FastAPI 엔트리
│   │   ├── core/             # 설정, 환경변수, KIS 토큰 캐시
│   │   ├── api/              # FastAPI 라우터
│   │   ├── market/           # 한국 시세·종목 수집 (pykrx, 네이버)
│   │   ├── intel/            # 글로벌 매크로 수집·분석
│   │   │   ├── rulebook.md   # 분석 룰북 (LLM 컨텍스트)
│   │   │   ├── collectors/   # RSS, FRED, EDGAR 등 수집기
│   │   │   ├── summarizer/   # 영문 → 한글 요약
│   │   │   └── signals/      # 시그널 생성
│   │   ├── llm/              # 모델 라우터, 캐시 매니저, 비용 추적
│   │   ├── trading/          # KIS OpenAPI 래퍼, 주문
│   │   └── storage/          # DB 모델 (시그널·회고·주문 로그)
│   ├── tests/
│   └── alembic/
└── frontend/
    ├── app/                  # Next.js App Router
    ├── components/
    ├── lib/
    └── hooks/
```

## Tech Stack (기술 스택)

- Frontend: Next.js (App Router), TypeScript, Tailwind, TradingView Lightweight Charts, TanStack Query, Zustand, Vitest
- Backend: Python 3.11+, FastAPI, APScheduler, SQLAlchemy 2.x + Alembic, `websockets`, `structlog`, `pydantic-settings`
- Korean Data: `pykrx`, `finance-datareader`, KIS OpenAPI (REST+WS), DART OpenAPI
- Global Intel: RSS(`feedparser`), FRED API, SEC EDGAR API, Yahoo Finance (`yfinance`)
- AI / RAG: Anthropic API (Haiku / Sonnet 4.6 / Opus 4.7), 벡터 DB (Chroma 또는 pgvector), `anthropic` SDK with **Prompt Caching**
- DB: SQLite (MVP) → Postgres/Supabase (확장)
- Secrets: 로컬 `.env`, 운영 OS keyring 또는 Supabase Vault

## Build & Test Commands (빌드/테스트)

> 첫 모듈 구현 후 실제 동작 확인하며 갱신.

```bash
# 초기 세팅 (최초 1회)
cp .env.example .env
cd backend && alembic upgrade head

# 백엔드
cd backend && uvicorn app.main:app --reload   # 개발 서버
pytest                                         # 테스트
ruff check . && ruff format .                  # 린트 + 포맷
mypy .                                         # 타입 체크

# 프론트엔드
cd frontend && pnpm dev
pnpm test
pnpm lint
tsc --noEmit
```

## Domain Context (도메인 컨텍스트)

### 매매 시장 (한국 한정)
- **모의투자(Paper Trading)**: 가상 잔고로 KIS 시스템 매매 시뮬레이션
- **시그널(Signal)**: 룰북 기반 매수/매도/관망 추천. `{사실, 룰, 점수, 출처}` 구조 강제
- **드라이런(Dry-run)**: 외부 API 미호출, 페이로드 로깅만
- **호가**: 매수/매도 대기 가격대. KIS WebSocket으로 실시간 수신

### 글로벌 매크로 모니터링 (분석 영역)
- **인과 사슬 8축** (룰북 참조): 미국 시장 / 환율 / 미국 금리 / 반도체 / 중국 / 유가 / 지정학 / 국내
- **분석 룰북**: `backend/app/intel/rulebook.md` — LLM 컨텍스트로 매 호출 주입
- **출처 신뢰도 가중치**: 1차 공식 1.0 / 메이저 0.6~0.8 / KOL 0.3 / 익명 0.1
- **시간대 운영** (KST): 05:30~08:50 집중 분석 / 09:00~15:30 모니터링 / 15:30~ 회고 / 야간 수집

### 한국 시장 규칙
- **종목 코드**: 6자리 **문자열** (`'005930'`). int 저장 금지 (앞 0 손실)
- **타임존**: DB 저장은 **UTC**, 표시·입력은 **KST**(`Asia/Seoul`). 경계에서만 변환
- **장 운영 시간**: 정규장 09:00–15:30 KST, 동시호가 08:30–09:00 / 15:20–15:30
- **휴장일**: `pykrx`로 영업일 검증, 주문 전 필수 체크
- **상하한가**: ±30%. VI 발동 시 일시정지 — 주문 거부
- **매매단위**: 기본 1주. ETF/우선주 호가단위 상이 — KIS API 응답값 신뢰

```
데이터 흐름:
글로벌 출처(EDGAR/FRED/RSS) → intel/ 수집·요약·점수 → storage/(시그널 DB)
KRX/네이버/DART → market/ → storage/(시세 DB)
                              ↓
               두 DB → signals/ 종합 → frontend/ 대시보드
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

### 주문·시크릿·시간
- 주문 함수 시그니처: 항상 `def place_order(..., dry_run: bool = True)`
- 시크릿: 환경변수에서만 read, 하드코딩 금지
- 모든 `datetime`은 `tz-aware`. naive datetime DB 저장 금지
- 금액·수량: Python `Decimal`만 (`float` 금지). TS는 `string` 또는 `bigint`

### 외부 API
- 호출: `try/except` + 구조화 로그, 실패 시 명시적 에러 메시지
- 시세 폴링: KIS API 일일/초당 호출 한도 고려, 캐시 우선
- 네이버 금융: 공식 API 아님 — 요청 빈도 제한 + robots.txt 준수
- API 응답 포맷: `{ success, data, error }` 형태로 통일

### LLM 호출 (토큰 최적화)
- **모델 라우터 강제**: 단순 작업 → Haiku, 종합 판단 → Sonnet, 깊은 분석 → Opus (주 1회). 직접 모델 지정 호출 금지
- **Prompt Caching**: 시스템 프롬프트 + 룰북 + 보유 종목 메타는 캐시 가능 prefix에 배치 (1시간 TTL)
- **사전 필터링**: LLM 호출 전 코드 레벨에서 신뢰도·관련성 점수로 노이즈 제거
- **JSON 출력 강제** + `max_tokens` 명시 — 불필요 텍스트 차단
- **Batch API**: 야간 회고·일일 다이제스트는 50% 할인 적용
- **입력 압축**: 원문 전체 X → Haiku로 1차 요약 → 그 요약만 상위 모델로

### 시그널 생성
- 출력 구조: `{ fact, applied_rule, score, source, confidence }`
- 룰북(`backend/app/intel/rulebook.md`)에 없는 근거로 시그널 만들면 거부
- 다중 출처 동조(신뢰도 합 ≥ 1.5) 시에만 강시그널

## Trigger Keywords (트리거 키워드)

- `"백테스트 돌려줘"` → `backend/app/signals/backtest.py` 실행, 결과 리포트
- `"실거래 모드 켜줘"` → `TRADING_MODE=live` 전환 전 **명시 경고 + 재확인** 필수
- `"룰북 회고해줘"` → 누적 시그널 vs 실제 비교 → 룰북 v 변경안 제안 (Opus)
- `"오늘 시그널 정리해줘"` → 그날 강시그널만 한 화면 다이제스트

## Learning Mode

학습 프로젝트 — 새 개념(라이브러리·API·도구) 등장 시 한두 줄 풀이 곁들임. 전역 CLAUDE.md의 "결과 먼저, 분석은 요청 시" 원칙은 그대로 유지.
