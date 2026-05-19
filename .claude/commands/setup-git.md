---
description: Git 저장소 초기화 + .gitignore + .env.example 생성 + 첫 커밋. 프로젝트에 1회만 실행.
---

# /setup-git — Git 초기 세팅 (1회 실행)

이 프로젝트에 **처음 한 번만** 실행한다.

## 1. 사전 확인
- `.git/` 폴더 존재 여부 확인 → **이미 있으면 즉시 중단** ("이미 git 저장소입니다" 출력)
- 현재 작업 디렉터리에 `CLAUDE.md`가 있는지 확인 (잘못된 폴더 실행 방지)

## 2. .gitignore 생성
프로젝트 루트에 `.gitignore` 파일을 다음 내용으로 생성. 이미 있으면 누락된 항목만 추가.

```
# === 시크릿 (절대 커밋 금지) ===
.env
.env.*
!.env.example
*.key
*.pem
secrets/

# === Python ===
__pycache__/
*.py[cod]
.venv/
venv/
.pytest_cache/
.mypy_cache/
.ruff_cache/
*.egg-info/

# === Node / Next.js ===
node_modules/
.next/
out/
dist/
*.log
.DS_Store

# === DB / 로컬 데이터 ===
*.sqlite
*.sqlite3
*.db
data/

# === IDE ===
.vscode/
.idea/
*.swp
```

## 3. .env.example 생성 (없으면만)
KIS OpenAPI·DART·Anthropic 키 스켈레톤. 실제 값은 비워둔다.

```
# === KIS OpenAPI 모의투자 ===
KIS_PAPER_APP_KEY=
KIS_PAPER_APP_SECRET=
KIS_PAPER_ACCOUNT=

# === KIS OpenAPI 실거래 (주의) ===
KIS_LIVE_APP_KEY=
KIS_LIVE_APP_SECRET=
KIS_LIVE_ACCOUNT=

# === 거래 모드 ===
TRADING_MODE=paper

# === DART OpenAPI ===
DART_API_KEY=

# === Anthropic API ===
ANTHROPIC_API_KEY=
```

## 4. git init + 첫 커밋
- `git init`
- 다음 파일만 명시적으로 스테이징: `.gitignore`, `.env.example`, `CLAUDE.md`
- `git diff --staged`로 시크릿 노출 없는지 더블체크
- `git commit -m "chore: 프로젝트 초기 세팅 (CLAUDE.md, gitignore, env example)"`

## 5. 결과 요약
- 생성된 파일 목록
- 첫 커밋 해시
- 다음 단계 안내: "GitHub 등 원격 저장소 연결 시 `git remote add origin <URL>` 후 `git push -u origin main`"
