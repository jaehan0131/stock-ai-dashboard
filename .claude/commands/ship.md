---
description: /safe-commit + git push까지 자동. 원격 저장소(GitHub 등)가 연결되어 있어야 동작.
---

# /ship — 안전 배포 자동화

`/safe-commit` 흐름 + `git push`까지 자동.

## 1. 사전 안전 검증
- `.git/` 존재 확인. 없으면 **즉시 중단**, `/setup-git` 안내
- 원격 저장소 연결 확인 (`git remote -v`). 없으면 **즉시 중단**, "원격 저장소 미연결 — `/safe-commit` 사용 권장" 안내
- 현재 브랜치 확인 → `main`/`master`면 **즉시 중단**, "PR을 통해 머지하세요" 안내
- `git status`로 변경 파일 목록 확인. 변경 없으면 중단

## 2. 시크릿 차단
`/safe-commit` 단계 2와 동일.

## 3. 테스트 실행
`/safe-commit` 단계 3과 동일. 어느 쪽이든 실패 시 **즉시 중단**, 커밋·푸시 진행 금지.

## 4. 변경 분석 + 커밋 메시지 작성
`/safe-commit` 단계 4와 동일 (`<type>: <한국어 설명>` 컨벤션).

## 5. 사용자 승인 (2단계)
첫 번째: 커밋 메시지 확인
```
제안 커밋 메시지: "feat: 코스피200 시세 수집기 추가"
변경 파일: 3개
진행할까요? (yes/no/edit)
```

두 번째: push 진행 확인
```
원격: origin (https://github.com/...)
브랜치: <현재 브랜치> → origin/<현재 브랜치>
push 진행할까요? (yes/no)
```

어느 단계든 `no`면 중단. 커밋만 됐고 push 안 됐을 수도 있으므로 상태를 명확히 출력.

## 6. 커밋
- `git add -A`
- 시크릿 더블체크
- `git commit -m "<승인된 메시지>"`

## 7. Push
- `git push origin <현재 브랜치>`
- 첫 push면 `--set-upstream` 자동 추가 (`git push -u origin <브랜치>`)

## 8. 결과 요약
- 커밋 해시 (짧은 형식)
- 커밋 메시지
- 변경 파일 수
- push된 원격 URL + 브랜치
- 한 줄 다음 단계 안내 (예: "PR 생성하려면 GitHub 페이지 확인")
