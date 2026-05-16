# 📈 AI Chunsik (AI 춘식) MK1.5
> **Wave Energy Theory 기반 미국 주식 자동 분석 및 텔레그램 리포팅 에이전트**

AI 춘식이는 **파동에너지 이론(Wave Energy Theory)**을 바탕으로 미국 주식 시장을 탑다운(Top-down) 방식으로 분석하고, 로컬 LLM(Ollama)을 활용하여 투자 전략 리포트를 생성한 뒤 텔레그램으로 자동 전송해주는 퀀트 투자 보조 에이전트입니다.

## 🚀 주요 기능
- **시장 지수 스캔**: NYSE(뉴욕증권거래소) 운영 달력을 연동하여 개장/마감 시점 자동 감지.
- **탑다운 섹터 분석**: 자금 유입이 강한 주도 섹터 및 종목 자동 스크리닝.
- **파동에너지 분석**: 스토캐스틱 기반의 단/중/장기 파동 정배열 및 폭발 타점 포착.
- **AI 내러티브 생성**: 로컬 AI(Ollama)를 활용하여 정교한 투자 내러티브 리포트 작성.
- **텔레그램 알림**: 분석 결과를 실시간으로 모바일 텔레그램으로 전송.
- **지능형 스케줄러**: 서머타임 및 미국 시장 휴장일(Early Close 포함) 자동 대응.

## 🛠 설치 및 설정

### 1. 필수 요구사항
- Python 3.9+
- [Ollama](https://ollama.ai/) (로컬 LLM 실행용)
- Telegram Bot Token & Chat ID

### 2. 라이브러리 설치
```bash
pip install -r requirements.txt
```

### 3. 환경 설정
`config.py` 파일 또는 환경 변수(.env)를 통해 다음 정보를 설정하십시오.
- `TELEGRAM_BOT_TOKEN`: 본인의 텔레그램 봇 토큰
- `TELEGRAM_CHAT_ID`: 리포트를 받을 본인의 텔레그램 채팅 ID

## 📂 프로젝트 구조
- `main_agent.py`: 분석 파이프라인 총괄 엔진
- `auto_runner.py`: 시장 시간 기반 지능형 스케줄러
- `reporter.py`: 리포트 생성 및 텔레그램 전송 모듈
- `config.py`: 시스템 설정 관리
- `reports/`: 생성된 마크다운 리포트 저장 폴더

## ⚠️ 주의사항
본 프로그램은 알고리즘에 기반한 참고용 분석 자료를 제공하며, 모든 투자의 책임은 투자자 본인에게 있습니다.

---
**Author**: [Your Name/GitHub ID]  
**License**: MIT
