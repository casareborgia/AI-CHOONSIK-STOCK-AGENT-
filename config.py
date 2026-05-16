# ==============================================================================
# [AI Trading Agent] 중앙 설정 파일 (Configuration Hub)
# ==============================================================================
# 전체 파이프라인의 임계치, API 설정, 타겟 ETF 목록을 통합 관리합니다.
# 전략 수정 시 소스 코드가 아닌 본 파일의 수치만 조정하십시오.

import os

# ------------------------------------------------------------------------------
# 1. 시장 지수 및 탑다운 섹터 순환매 설정 (Market Indices & Sector Rotation)
# ------------------------------------------------------------------------------
# 주요 4대 시장 지수 ETF (다우, 나스닥, S&P500, 러셀2000)
MARKET_INDICES = {
    'Dow Jones (다우지수)': 'DIA',
    'Nasdaq 100 (나스닥)': 'QQQ',
    'S&P 500 (에센피)': 'SPY',
    'Russell 2000 (러셀)': 'IWM'
}

# 자금 흐름 추적을 위한 11대 SPDR 섹터 ETF + 핵심 테마 ETF
SECTOR_ETFS = {
    'Technology (기술)': 'XLK',
    'Healthcare (헬스케어)': 'XLV',
    'Financials (금융)': 'XLF',
    'Energy (에너지)': 'XLE',
    'Consumer Discretionary (임의소비재)': 'XLY',
    'Consumer Staples (필수소비재)': 'XLP',
    'Industrials (산업재)': 'XLI',
    'Materials (소재)': 'XLB',
    'Utilities (유틸리티)': 'XLU',
    'Real Estate (부동산)': 'XLRE',
    'Communication Services (통신)': 'XLC',
    'Semiconductors (반도체 테마)': 'SMH'
}

# 스캔 시 자금 유입 최상위로 판별할 주도 섹터 개수
TOP_N_SECTORS = 3


# ------------------------------------------------------------------------------
# 2. 기본적 분석 필터 프리셋 (Finviz + Yahoo)
# ------------------------------------------------------------------------------
# Finviz 고속 필터링 파라미터 (서버사이드 연산용)
FINVIZ_PRESETS = {
    'Market Cap.': '+Mid (over $2bln)', # 시총 $2B 이상 (정확한 내부 상수 옵션 매칭)
    'P/E': 'Any',                       # PER 제한 해제 (성장주 포함)
    'Return on Equity': 'Positive (>0%)', # 흑자 기업만 선별 (정확한 내부 키 매칭)
    '20-Day Simple Moving Average': 'Price above SMA20', # 20일선 위 추세 확인
    'Current Volume': 'Over 500K'       # 유동성 확보 (매수/매도 원활)
}

# Yahoo Finance 교차 검증 임계치
MAX_DEBT_RATIO = 1.5                    # 부채비율 150%까지 허용
MIN_INST_OWNERSHIP = 0.20               # 최소 기관 보유 지분 완화 (20%)
REQUIRE_FCF_POSITIVE = True             # 잉여현금흐름(FCF) 흑자 필수 여부


# ------------------------------------------------------------------------------
# 2-B. 트랙 B: SNS 모멘텀 기반 급등주 설정 (Track B - Social Momentum)
# ------------------------------------------------------------------------------
# 재무 건전성을 배제하고 커뮤니티 언급량과 거래량 폭발을 중심으로 스캔합니다.
SNS_PRESETS = {
    'min_mentions': 20,                 # 24시간 내 최소 언급 횟수 기준
    'vol_multiplier': 1.5,              # 스팸 펌핑 차단을 위해 평균 대비 1.5배 이상 거래량 요구
    'target_subreddits': ['wallstreetbets', 'stocks', 'shortsqueeze'],
    'max_candidates': 5                 # 최종 검증을 수행할 상위 종목 개수
}


# ------------------------------------------------------------------------------
# 3. 기술적 분석 엔진 설정 (Wave Energy & Volume)
# ------------------------------------------------------------------------------
# 파동에너지 지표 파라미터 (스토캐스틱 대/중/소)
STOCH_SMALL = {'len': 5,  'k': 3,  'd': 3}
STOCH_MID   = {'len': 10, 'k': 5,  'd': 5}
STOCH_LARGE = {'len': 20, 'k': 12, 'd': 12}

# 보조 지표 (RSI 및 볼린저 밴드 스윙 셋업 추가 준비)
RSI_PERIOD = 14
RSI_OVERSOLD = 30
RSI_OVERBOUGHT = 70

BB_PERIOD = 20
BB_STD = 2

# 거래량 급증 판별 기준
VOL_MA_LENGTH = 20                      # 평균 거래량 산출 기간
VOL_MULTIPLIER = 1.2                    # 1.5배에서 1.2배로 완화하여 스윙 타점 포착 확대


# ------------------------------------------------------------------------------
# 4. 로컬 AI 심층검증 설정 (Ollama - Gemma 4)
# ------------------------------------------------------------------------------
OLLAMA_ENDPOINT = "http://localhost:11434/api/generate"
TARGET_LLM_MODEL = "gemma4:26b"           # 로컬에 설치된 젬마 모델명 입력

# 뉴스 크롤링 개수
MAX_NEWS_COUNT = 3


# 5. 리포팅 및 출력 설정 (보안 강화)
# ------------------------------------------------------------------------------
# [보안] 토큰 및 ID는 .env 파일에서 관리하는 것이 권장됩니다.
# python-dotenv 설치 권장: pip install python-dotenv

import os
from dotenv import load_dotenv

# .env 파일 로드 (파일이 없을 경우 시스템 환경변수 사용)
load_dotenv()

OUTPUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "reports")

# 환경변수에서 가져오되, 없을 경우 기본값(또는 빈 문자열) 설정
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")

# [주의] 아래 직접 입력 방식은 지양하시고 .env 파일을 사용하십시오.
if not TELEGRAM_BOT_TOKEN:
    # 여기에 직접 입력 시 깃허브 공유에 각별히 유의하십시오.
    pass 
