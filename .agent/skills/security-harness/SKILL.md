---
name: security-harness
description: >
  범용 보안 취약점 자동 스캔 하네스. 프로젝트 타입(Python, Node.js, Go, Java, 웹앱, LLM 에이전트 등)을
  자동 감지하고 OWASP Top 10 2025 기준으로 보안 점검을 수행합니다.
  "보안 점검", "security audit", "취약점 스캔", "시크릿 검사", "OWASP 점검",
  "코드 리뷰 보안", "pre-commit 보안", "배포 전 점검" 등의 요청 시 활성화됩니다.
version: 2.0.0
---

# 범용 보안 하네스 (Universal Security Harness)

## Use this skill when

- 코드 변경 후 보안 취약점을 점검하고 싶을 때
- 커밋, PR, 배포 전에 보안 게이트를 실행하고 싶을 때
- OWASP Top 10 기준 보안 감사를 수행할 때
- 새 프로젝트를 시작하면서 보안 기반을 잡고 싶을 때
- "보안 점검", "security scan", "OWASP audit" 등으로 요청할 때

## Do not use this skill when

- 보안과 무관한 기능 개발이나 버그 수정만 요청할 때
- 보안 개념 설명이나 교육만 원할 때 (스캔 실행 불필요)

## Safety

- 모든 파일을 **읽기 전용**으로 접근 (수정/삭제 없음)
- `.env`, 키 파일 등의 **내용을 출력하지 않음** — 존재 여부와 권한만 확인
- 탐지된 비밀값은 자동 **마스킹** 처리

## Instructions

### 1단계: 자동 스캔 실행

프로젝트 루트에서 실행:

- Command: `python .agent/skills/security-harness/scripts/security_scan.py`

옵션:
- `--json` : CI/CD 파이프라인용 JSON 출력
- `--md`   : Markdown 리포트 파일 생성
- `--fix`  : 자동 수정 가능한 항목 제안 (dry-run)
- `--severity HIGH` : 특정 심각도 이상만 필터링

### 2단계: 프로젝트 자동 감지

스크립트가 프로젝트 루트의 파일 구성을 분석해서 타입을 자동 결정합니다:

| 감지 기준 | 프로젝트 타입 | 활성화 스캐너 |
|-----------|-------------|-------------|
| `requirements.txt` / `pyproject.toml` / `.py` | Python | 전체 + Python 특화 |
| `package.json` / `.js` / `.ts` | Node.js | 전체 + JS/TS 특화 |
| `go.mod` / `.go` | Go | 전체 + Go 특화 |
| `pom.xml` / `build.gradle` / `.java` | Java | 전체 + Java 특화 |
| `index.html` / React/Vue/Svelte | 웹 프론트엔드 | 전체 + XSS/CORS 특화 |
| Ollama/OpenAI/Gemini API 호출 | LLM 에이전트 | 전체 + 프롬프트 인젝션 |

### 3단계: OWASP Top 10 2025 기반 12개 카테고리 스캔

모든 프로젝트에 공통 적용되는 항목(●)과 조건부 활성화 항목(○):

| ID | 카테고리 | OWASP | 적용 |
|----|---------|-------|------|
| S01 | 하드코딩 비밀값 | — | ● 전체 |
| S02 | 개인정보/경로 노출 | — | ● 전체 |
| S03 | Git 위생 | — | ● 전체 |
| S04 | 의존성 관리 | A06, A08 | ● 전체 |
| S05 | 코드/커맨드 인젝션 | A03 | ● 전체 |
| S06 | SQL / NoSQL 인젝션 | A03 | ○ DB 사용 시 |
| S07 | XSS (Cross-Site Scripting) | A03 | ○ 웹앱 |
| S08 | 보안 설정 오류 | A05 | ● 전체 |
| S09 | 인증/접근 제어 | A01, A07 | ○ 웹앱/API |
| S10 | SSRF | A10 | ○ 서버앱 |
| S11 | 프롬프트 인젝션 | LLM Top10 | ○ LLM 에이전트 |
| S12 | 암호화 취약점 | A02 | ○ 인증/암호 사용 시 |

### 4단계: 결과 보고

```
🛡️ Security Harness Scan Report (YYYY-MM-DD)
📁 Project: my-project | Type: Python + LLM Agent
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

 ID  │ Category          │ Status │ Findings
─────┼───────────────────┼────────┼─────────
 S01 │ Hardcoded Secrets  │ ✅ PASS │ 0
 S02 │ PII Disclosure     │ ❌ FAIL │ 2
 ...
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Result: 2 categories failed, 5 findings total
```

## Constraints

- 비밀값은 마스킹 처리하여 보고합니다. 원본을 절대 노출하지 마세요.
- `.env` 파일은 존재/권한만 확인하고 내용을 읽지 마세요.
- 스캔 범위는 프로젝트 디렉토리 내부로 한정합니다.
- 자동 수정(`--fix`)은 제안만 하고 실행 전 반드시 사용자 확인을 받으세요.
