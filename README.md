# 주식 AI 대시보드 — 학습 프로젝트

> 한국 KRX 시장 대상 통합 AI 대시보드 학습 프로젝트.
> **글로벌 매크로 모니터링 → AI 시그널 생성 → (모의) 실거래**까지 풀스택 구현.
> Python · TypeScript · Anthropic Claude · 한국투자증권 OpenAPI.

---

## 프로젝트 개요

게임 업계 사업PM 8년차의 **개발 학습 + 실사용 겸용** 프로젝트.

- **목적**: 영어 원문 글로벌 매크로 정보를 AI가 자동 수집·요약하고, 룰북 기반으로 한국 주식 시그널을 생성. 사용자 승인 후 모의·실거래.
- **차별점**: 단순 시각화가 아닌 *실거래 워크플로우*까지 가는 풀스택.
- **개발 방법**: Claude Code (바이브 코딩)로 2~3일에 풀스택 구축.

---

## 아키텍처

```
[데이터 수집]                [AI 처리]               [사용자 UI]
RSS / DART / FRED  →   Haiku 요약 → Sonnet 종합  →   Next.js 대시보드
       ↓                     ↓                            ↓
사전 필터 (코드)      LLMCallLog (비용 추적)    승인/거부 클릭
       ↓                     ↓                            ↓
       └──── 룰북 기반 그룹화 ────┘                 KIS OpenAPI (모의)
                  ↓                                       ↓
              Signal DB                           매수/매도 주문
```

핵심 절대 규칙:
- 기본 모드 **모의투자** (`TRADING_MODE=paper`)
- AI 시그널은 **추천만**, 자동 주문 영구 금지
- 모든 시크릿은 `.env`만 (git 추적 X)
- Decimal 강제 (float 금지) — 금융 코드 안전성

---

## 기술 스택

### 백엔드 (Python)
- **FastAPI** + **SQLAlchemy 2.x** + **Alembic** (DB 마이그레이션)
- **pydantic-settings** — `.env` 환경변수 + `SecretStr` 마스킹
- **Anthropic SDK** (Haiku / Sonnet / Opus 라우팅)
- **feedparser** (RSS 수집)
- **pykrx** (한국 KRX 시세 — 예정)

### 프론트엔드 (TypeScript)
- **Next.js 16** + **App Router**
- **Server Component** (page.tsx — 데이터 페치)
- **Client Component** (SignalActions.tsx — 인터랙션)
- **Tailwind CSS 4** + **Turbopack**

### 외부 서비스
- **Anthropic API** — LLM 호출 (선불 충전 종량제)
- **한국투자증권 KIS OpenAPI** — 모의/실전 매매
- **Yahoo Finance · Reuters RSS** — 글로벌 매크로 정보 (확장 예정: DART, FRED, EDGAR)

---

## Phase별 학습 진행 회고

### Phase A — 기초 인프라 (config + storage)
- **`core/config.py`**: `pydantic-settings` + `SecretStr` 마스킹. 모의/실전 KIS 키 분리 (`active_kis_credentials` 동적 선택)
- **`storage/`**: SQLAlchemy 2.x `DeclarativeBase` + `Mapped[T]` 패턴. UTC tz-aware `UtcDateTime` 커스텀 타입으로 SQLite timezone 한계 보강
- **마일스톤**: `Decimal(str(1.4))` 패턴 — 부동소수점 사고 차단의 첫 안전망

### Phase B — LLM 인프라 (router · cache · pre_filter · cost_tracker)
- **`router.py`**: Task 카테고리·복잡도로 Haiku/Sonnet/Opus 자동 라우팅. lazy Anthropic client
- **`cost_tracker.py`**: 모델별 단가 상수 + Decimal 비용 계산 + `LLMCallLog` 자동 적재
- **`cache.py`**: Prompt Caching의 `cache_control` 헤더. 룰북 1110 토큰 → Sonnet 캐시 자격 통과
- **`pre_filter.py`**: 룰북 기준 신뢰도 가중치·점수 게이트. **노이즈 70~90% 코드 레벨 차단**
- **마일스톤**: 사전 필터 + 캐시 + 모델 라우팅의 **3중 비용 절감**. 게이트 미적용 대비 25배 절감

### Phase C — 글로벌 매크로 수집 + 요약 (intel)
- **`collectors/rss.py`**: Yahoo Finance + Reuters RSS. 정적 기본값 + 키워드 부스트 점수 산정. dedup_key SHA256 16자
- **`summarizer/summarize.py`**: Haiku로 영문 → 한국어 JSON 요약. `is_relevant` 플래그로 false positive 컷
- **마일스톤**: "Navy Federal" 같은 false positive를 *코드는 통과 / LLM이 컷* 하는 **역할 분담** 원리 체험

### Phase D — 시그널 종합 (signals)
- **`aggregate.py`**: Sonnet으로 여러 SummarizedItem을 룰북 §1-N 인과 사슬별 그룹화 → 시그널 생성
- **`Signal` ORM**: `user_status` default `pending` → **DB 스키마가 "자동 주문 금지" 절대 룰 강제**
- **`save_signal()`**: dataclass → ORM 변환 + JSON 직렬화 + 자동 timestamp
- **마일스톤**: `supporting_log_ids` 역추적 패턴 — 시그널 → 요약 → 원본 RSS까지 *감사 가능한 시그널*

### Phase F — API + 풀스택 UI (api + frontend)
- **`main.py` + `api/signals.py`**: FastAPI 5개 엔드포인트 (`/healthz`, `/signals/pending`, `/signals/{id}`, `approve`, `reject`, `/intel/run`)
- **`page.tsx` (Server Component)**: 백엔드 fetch → 표 렌더. UTC ISO → KST 변환
- **`SignalActions.tsx` (Client Component)**: `useTransition` + `router.refresh()`로 승인/거부 → Server Component 재페치
- **마일스톤**: **클릭 한 번이 4개 시스템(브라우저·Next.js·FastAPI·SQLite)을 한 바퀴 순환**

---

## 검증된 마일스톤

| # | 마일스톤 | 검증 |
|---|---|---|
| 1 | 첫 백엔드 모듈 (`config.py`) | SecretStr 마스킹 출력 확인 |
| 2 | DB 마이그레이션 + tz-aware UTC | Alembic upgrade + INSERT/SELECT 통합 |
| 3 | 첫 LLM 호출 (Haiku) | `text: 2` + `cost: $0.000037` + DB 적재 |
| 4 | 풀 파이프라인 (`/intel/run`) | RSS 20건 → 게이트 2건 → 요약 2건 (8.95초) |
| 5 | 풀스택 UI (시그널 표 + 승인 클릭) | 클릭 → 행 사라짐 |
| 6 | KIS 모의 키 발급 + .env 안전 저장 | `account: 50188808` 인식 |
| 7 | 사전 필터 비용 절감 정량 | 90% 차단 = 게이트 미적용 대비 25배 절감 |

---

## 어려움 + 해결

### 1. 시크릿 노출 사고 (보안 학습)
- **상황**: 실전투자 + 모의투자 APP_KEY/SECRET을 채팅에 평문 입력
- **위험**: 실전 키 노출은 자동매매 봇이 발견할 위험 高
- **해결**: 실전 키 *즉시 폐기·재발급* (사용자 직접). 모의는 별도 결정으로 메모리 저장
- **교훈**: 시크릿은 *오직 `.env` 또는 password manager*. 채팅·README·메모리 *전부 X*.

### 2. KIS 결제 마찰 (한국 사용자 + Stripe)
- **상황**: Anthropic 콘솔 결제 버튼 비활성화
- **원인**: 카드사 청구지 주소와 입력 주소의 *문자열 불일치* (호수 누락·표기 차이)
- **해결**: 카드사 등록 주소를 글자 단위 정확히 복사
- **교훈**: Stripe fraud check는 *문자열 매칭*. 한글·영문·띄어쓰기·구두점까지 동일해야

### 3. pnpm 11 빌드 차단
- **상황**: `pnpm dev` 시 `ERR_PNPM_IGNORED_BUILDS`
- **원인**: pnpm 11이 *네이티브 빌드 스크립트(sharp, unrs-resolver) 기본 차단*
- **해결**: `pnpm-workspace.yaml`에서 `true` 승인 + `pnpm install`
- **교훈**: 공급망 공격 방어 — 모든 install 스크립트는 *명시 승인*

### 4. Windows + Git Bash 환경 함정
- **CP949 인코딩**: 콘솔 한글 깨짐 → `PYTHONIOENCODING=utf-8` 환경변수 강제
- **backslash vs forward slash**: Git Bash에선 `\`가 escape → `./.venv/Scripts/python.exe` 사용
- **OneDrive 한글 경로**: 일부 도구가 한글 경로 파싱 실패 → 절대 경로 명시
- **교훈**: 셸 단일 기준 유지. 사용자 셸(Git Bash)에 맞춘 명령만 안내

### 5. 두 트랙 협업 방식 정착
- **상황**: 같은 세션에서 코드 작성 + 학습 가이드 동시 진행 시 컨텍스트 부담
- **해결**: **두 트랙 분리** — 코드 트랙(별도 Claude 세션, Plan Mode), 가이드 트랙(이 세션)
- **흐름**: 가이드 트랙이 *프롬프트 작성 + Plan 검토 + 학습 안내*, 코드 트랙이 *실제 코드 생성 + 검증*
- **교훈**: 페어 프로그래밍의 LLM 버전 — 각자 역할 분리가 효율적

---

## 실행 방법

### 사전 조건
- Python 3.11+ (venv는 `backend/.venv/`)
- Node.js 18+ + pnpm 11+ (corepack 또는 `npm install -g pnpm`)
- Anthropic API 키 (선불 충전)
- 한국투자증권 모의투자 계좌 + KIS Developers 앱키

### 설치
```bash
# 백엔드
cd backend
python -m venv .venv
./.venv/Scripts/python.exe -m pip install -r requirements.txt
./.venv/Scripts/python.exe -m alembic upgrade head

# 프론트엔드
cd ../frontend
pnpm install
```

### `.env` 설정 (backend/.env 신규 생성)
```
KIS_PAPER_APP_KEY=...
KIS_PAPER_APP_SECRET=...
KIS_PAPER_ACCOUNT=...
TRADING_MODE=paper
ANTHROPIC_API_KEY=...
DART_API_KEY=          # 선택, DART 사용 시
```

### 실행 (3개 터미널 동시)
```bash
# 터미널 1 — 백엔드
cd backend
./.venv/Scripts/python.exe -m uvicorn app.main:app --reload --port 8000

# 터미널 2 — 프론트엔드
cd frontend
pnpm dev

# 터미널 3 — Claude Code (선택, 추가 작업 시)
cd "주식 AI 대시보드"
claude -c
```

### 브라우저
- 대시보드: http://localhost:3000
- API 문서 (Swagger): http://localhost:8000/docs
- 헬스체크: http://localhost:8000/healthz

---

## 다음 단계 로드맵

학습 단계 코드는 완성. 이제 *진짜 자산 운용*까지의 길:

| 단계 | 작업 | 가치 | 학습 부담 |
|---|---|---|---|
| 1 | **KIS 시세 조회** (Phase E 시작) | 한국 종목 가격 실시간 확인 | 중 |
| 2 | **APScheduler 자동화** | RSS 30분 폴링, 시세 5분 폴링 | 낮음 |
| 3 | **UI 보강** (자동 새로고침·toast) | 사용자 경험 ↑ | 낮음 |
| 4 | **시그널 × 종목 매칭** | "반도체 강매수" → 삼전·하이닉스 추천 | 중 |
| 5 | **KIS 모의 주문 실행** (dry_run 패턴) | 진짜 매매 워크플로우 완성 | 중-높음 |
| 6 | **회고 잡 + 룰북 갱신** | 시그널 정확도 추적·룰북 v 진화 | 낮음 |
| 7 | **운영 인프라** (로깅·비용 대시보드) | 모니터링 | 낮음 |
| 8 | **실전 모드 전환** (먼 미래) | 모의 검증 충분히 쌓인 후 | **매우 신중** |

> **권장 순서**: 1 → 2 → 3 → 4 → 5 → 6 → 7. 실전 전환(8)은 *별도 결정*.

---

## 면책 (Disclaimer)

이 프로젝트는 **학습용**입니다. AI 시그널은 **투자 권유가 아닙니다**. 모든 매매 결정과 그에 따른 손익은 **사용자 본인의 책임**입니다.

실거래(LIVE) 모드 전환은 모의투자에서 *충분한 검증 기간*(최소 수 개월)을 거친 후에만 권장됩니다.

---

## 라이센스

개인 학습 프로젝트. 외부 배포·상업 사용 X.
