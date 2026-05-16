# 🚀 AI Chunsik MK1.5: Dual-Track Autonomous Quant Agent

**AI 춘식 MK1.5**는 시장의 '숫자(재무)'와 '목소리(SNS)'를 동시에 분석하는 하이브리드 인공지능 투자 에이전트입니다. 단순히 차트를 읽는 것을 넘어, 거시적 섹터 순환매부터 커뮤니티의 폭발적인 모멘텀까지 포착하여 최적의 스윙 타점을 제안합니다.

![Python](https://img.shields.io/badge/Python-3.9+-blue?style=for-the-badge&logo=python)
![Framework](https://img.shields.io/badge/Framework-Asyncio-orange?style=for-the-badge)
![LLM](https://img.shields.io/badge/AI-Gemma_4-red?style=for-the-badge)
![License](https://img.shields.io/badge/License-MIT-green?style=for-the-badge)

---

## 💡 System Architecture: The Dual-Track Pipeline

본 시스템은 두 개의 독립적인 분석 트랙을 비동기(Asynchronous)로 병렬 실행하여 시장의 모든 기회를 놓치지 않습니다.

### 🌲 Track A: Fundamental Strength (The Forest)
*   **Sector Rotation**: 11대 SPDR 섹터 ETF의 자금 흐름을 추적하여 현재 시장을 주도하는 섹터를 우선 선별합니다.
*   **Quantitative Filtering**: Finviz 및 Yahoo Finance 데이터를 활용하여 시가총액, 부채비율, 기관 보유 지분, FCF(잉여현금흐름) 등 엄격한 재무 기준을 통과한 우량주만 추출합니다.

### 🚀 Track B: Social Momentum (The Crowd)
*   **3-Tier Social Scanner**: StockTwits API 및 Reddit(`r/wallstreetbets`)의 실시간 데이터를 스캔하여 대중의 관심이 집중되는 핫티커를 포착합니다.
*   **Anti-Noise Engine**: 단순 대화 단어를 티커로 오인하지 않도록 정교한 Regex 필터와 블랙리스트 엔진이 탑재되어 있습니다.
*   **Fault-Tolerant Fallback**: API 차단 시 자동으로 스크래핑 및 로컬 핵심 풀로 전환되는 무중단 아키텍처를 가집니다.

---

## ⚙️ Core Modules

1.  **Technical Engine (Wave Energy)**: 
    - 스토캐스틱 대/중/소 파동에너지 지표를 결합하여 추세의 정점과 바닥을 판별합니다.
    - 평균 거래량 대비 1.2배 이상의 거래량 동반 여부를 필수 조건으로 체크합니다.
2.  **AI Verification (Gemma 4)**: 
    - 로컬 Ollama 환경의 **Gemma 4:26b** 모델을 사용하여 기술적 분석 결과와 최신 뉴스를 결합, 최종 투자 적합성을 심층 검증합니다.
3.  **Autonomous Reporter**:
    - 매일의 분석 결과를 Markdown 리포트로 생성하고, 핵심 요약본을 텔레그램으로 즉시 전송합니다.

---

## 🛠 Installation & Setup

### Prerequisites
*   Python 3.9+
*   [Ollama](https://ollama.ai/) (Gemma 4 모델 설치 필요)
*   Telegram Bot Token (알림 수신용)

### Setup
```bash
# 1. 레파지토리 클론
git clone https://github.com/your-repo/ai-choonsik-mk1.5.git
cd ai-choonsik-mk1.5

# 2. 필수 라이브러리 설치
pip install -r requirements.txt

# 3. 환경 설정
# config.py 파일에서 TELEGRAM_BOT_TOKEN 및 API 설정
```

### Usage
```bash
# 전체 파이프라인 수동 실행
python main_agent.py

# 시장 시간에 맞춘 자동 스케줄러 가동
python auto_runner.py
```

---

## 📊 Sample Output
분석이 완료되면 다음과 같은 형태의 인사이트가 도출됩니다:

> **[Track B 포착] NVDA (NVIDIA Corporation)**
> - **SNS Mentions**: 150+ (Top 1 in Reddit)
> - **Technical**: 파동에너지 상방 정렬 (Strong Buy Signal)
> - **AI Opinion**: "반도체 주도 섹터의 수급과 소셜 모멘텀이 일치함. 단기 과열 주의하나 추세 지속 가능성 높음."

---

## ⚠️ Disclaimer
본 프로젝트는 학습 및 정보 제공을 목적으로 개발된 오픈소스 에이전트입니다. 모든 투자에 대한 최종 결정과 책임은 투자자 본인에게 있으며, AI의 분석 결과가 수익을 보장하지 않습니다.

---

### 📬 Contact & Contribution
- **Maintainer**: AI 춘식 개발팀
- 기여하고 싶은 내용이 있다면 Issue 또는 Pull Request를 남겨주세요!
