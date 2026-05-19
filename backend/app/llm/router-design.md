# 모델 라우터 설계 v1.0

> 모든 LLM 호출은 이 라우터를 거친다 (CLAUDE.md 절대 규칙).
> 실제 코드는 `router.py` (예정). 이 문서는 *설계도*.

## 0. 설계 원칙

1. **작업 난이도 ≠ 한 모델** — 작업별로 적절한 모델 선택
2. **캐시 우선** — 동일 prefix는 캐시로 처리, 신규 호출 최소화
3. **사전 필터링** — LLM 호출 *전*에 코드 레벨에서 노이즈 제거
4. **비용 가시화** — 매 호출 비용 DB 기록, 일일/월 한도 모니터링

---

## 1. 작업 → 모델 매핑

| 카테고리 | 작업 예시 | 모델 | 1건 비용 추정 | 주기 |
|---|---|---|---|---|
| 추출 (Extract) | RSS 파싱, HTML 정제, 정규식 매칭 | **없음 (코드만)** | $0 | 실시간 |
| 분류 (Classify) | 카테고리·중요도·관련성 점수 | **Haiku** | ~$0.0002 | 매 수집 |
| 번역·요약 (Summarize) | 영어 → 한국어 3~5줄 요약 | **Haiku** | ~$0.001 | 매 수집 |
| 시그널 종합 (Synthesize) | 여러 요약 + 룰북 → 시그널 출력 | **Sonnet 4.6** | ~$0.005 | 시그널 후보당 |
| 깊은 분석 (Deep Analysis) | 주간/분기 회고, 룰북 개선 제안 | **Opus 4.7** | ~$0.5 | 주 1회 |
| 사용자 대화 (Chat) | 대시보드 챗·일반 질문 | **Sonnet 4.6** (캐시 적용) | ~$0.002 | 사용자 요청 |

---

## 2. 라우팅 로직 (의사코드)

```python
@dataclass
class Task:
    category: str        # extract|classify|summarize|synthesize|deep|chat
    complexity: int      # 1~10
    input_tokens: int
    cache_eligible: bool

def route(task: Task) -> str | None:
    # 1. 코드만 처리되는 작업은 LLM 호출 X
    if task.category in ("extract",):
        return None

    # 2. 단순 분류·번역은 Haiku
    if task.category in ("classify", "summarize") and task.complexity < 4:
        return "claude-haiku-4"

    # 3. 시그널 종합·일반 대화는 Sonnet
    if task.category in ("synthesize", "chat") or task.complexity < 8:
        return "claude-sonnet-4-6"

    # 4. 그 외 + 명시적 deep 요청은 Opus
    return "claude-opus-4-7"
```

## 3. 캐시 전략 (Prompt Caching)

| 콘텐츠 종류 | TTL | 캐시 위치 |
|---|---|---|
| 시스템 프롬프트 (역할 정의) | 1시간 | prefix #1 |
| 룰북 v1.x (`rulebook.md`) | 1시간 | prefix #2 |
| 사용자 보유 종목 메타 | 1시간 | prefix #3 |
| 매크로 데이터 스냅샷 (DXY, VIX 등) | 12시간 (지표는 일 단위 갱신) | prefix #4 |
| 보유 종목 가격·재무 요약 | 12시간 | prefix #5 |
| 분석 대상 단일 뉴스/공시 | 캐시 X | tail (변동) |
| 사용자 질의 | 캐시 X | tail (변동) |

→ 매 호출의 입력 중 **80~90%가 캐시에서 읽힘** (정상 비용의 1/10).

**캐시 키 설계**:
- prefix는 *결정론적*으로 구성 (같은 룰북 v + 같은 종목 메타 → 같은 prefix → 같은 캐시 적중)
- 룰북 v 올라가면 캐시 자동 무효 (prefix가 달라지므로)

---

## 4. 비용 추적

호출마다 다음 정보를 `llm_call_log` 테이블에 저장:

```
- timestamp
- model_used (haiku | sonnet-4-6 | opus-4-7)
- task_category
- input_tokens (총)
- input_tokens_cached (캐시에서 읽힌 부분)
- output_tokens
- cost_usd (계산값)
- request_id
- success (bool)
```

**대시보드 표시**:
- 일일 누적 비용 / 월 누적 비용
- 모델별 호출 비율 (Haiku %, Sonnet %, Opus %)
- 캐시 적중률 (cached / total)
- 한도 90% 도달 시 사용자 알림

---

## 5. 사전 필터링 (LLM 호출 전 단계)

LLM 호출 *직전*에 코드로 1차 필터링:

```python
def should_call_llm(item: IntelItem) -> bool:
    # 출처 신뢰도 < 0.3 → 노이즈, 호출 X
    if item.source_weight < 0.3:
        return False

    # 룰북 3축 합산 점수 < 9 → 수집 가치 없음
    if item.score_sum() < 9:
        return False

    # 중복 (24h 이내 동일 사건 처리 이력)
    if cache.exists(item.dedup_key):
        return False

    return True
```

→ LLM 호출 양 **70~80% 절감** 가능 (대부분의 RSS 항목이 여기서 걸러짐).

---

## 6. 폴백·재시도 정책

```
1차 호출 (예: Haiku)
   ↓ 실패 (rate limit / 5xx)
2차 호출 (같은 모델, 지수 백오프 1초 후)
   ↓ 실패
3차 호출 (한 단계 상위 모델로 폴백, 예: Sonnet)
   ↓ 실패
사용자에게 에러 보고 + 작업 큐에 적재 (수동 재시도)
```

**폴백 금지 케이스**:
- Opus 실패 → 추가 폴백 없음. 사용자 통보.
- 결정적 오류(잘못된 입력 형식 등) → 재시도 없이 즉시 실패 처리

---

## 7. Batch API 적용 작업

다음은 즉시 응답 불필요 → Batch (50% 할인):

- 일일 회고 (장 마감 후, 23시경 일괄 처리)
- 주간 회고 (일요일 자정 일괄)
- 과거 데이터 백필 (역사 데이터 일괄 요약)
- 룰북 정확도 회귀 분석 (분기당)

즉시 응답 필요 → 일반 API:
- 사용자 실시간 질의
- 강시그널 알림 생성
- 주문 전 마지막 검증

---

## 8. 구현 우선순위 (코드 작성 시 순서)

1. `router.py` — 작업 카테고리 → 모델 매핑 로직만
2. `cache.py` — Anthropic Prompt Caching 헤더 설정
3. `pre_filter.py` — 신뢰도·점수 기반 필터
4. `cost_tracker.py` — 호출 로깅 + DB 적재
5. `batch.py` — Batch API 래퍼 (회고용)

각 모듈은 독립적이라 *위에서 아래로* 순차 구현 가능. 1~3까지만 있어도 절감 효과 80% 확보.
