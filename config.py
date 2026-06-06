# ==============================================================================
# [AI Trading Agent] 중앙 설정 파일 (Configuration Hub)
# ==============================================================================
# 전체 파이프라인의 임계치, API 설정, 타겟 ETF 목록을 통합 관리합니다.
# 전략 수정 시 소스 코드가 아닌 본 파일의 수치만 조정하십시오.

import os
import json

# ------------------------------------------------------------------------------
# [공통 데이터 관리] 동적 와치리스트 로더 세팅
# ------------------------------------------------------------------------------
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
GURUS_WATCHLIST_PATH = os.path.join(BASE_DIR, "watchlist_gurus.json")
VC_WATCHLIST_PATH = os.path.join(BASE_DIR, "watchlist_vc.json")

def load_json_watchlist(file_path, default_list):
    """지정된 경로에서 와치리스트를 로드하며, 파일이 없을 경우 기본값으로 자동 생성합니다."""
    if not os.path.exists(file_path):
        try:
            with open(file_path, 'w') as f:
                json.dump(default_list, f, indent=4)
            return default_list
        except Exception:
            return default_list
    try:
        with open(file_path, 'r') as f:
            return json.load(f)
    except Exception:
        return default_list

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

# ------------------------------------------------------------------------------
# 1-B. 대분류 섹터별 하위 세부 테마 ETF 및 특징 매핑
# ------------------------------------------------------------------------------
SUB_SECTOR_CONFIG = {
    'Technology': {
        'Semiconductors': {'etfs': ['SOXX', 'SMH'], 'desc': '사이클 가장 강함'},
        'AI Infra': {'etfs': ['BOTZ', 'ROBT'], 'desc': 'NVDA 중심'},
        'Cybersecurity': {'etfs': ['CIBR', 'HACK'], 'desc': '방어적 성격'},
        'Cloud/SaaS': {'etfs': ['WCLD', 'SKYY'], 'desc': '금리 민감'},
        'Fintech': {'etfs': ['FINX'], 'desc': 'XLF와 중첩 주의'}
    },
    'Communication Services': {
        'Social/Ads': {'etfs': ['SOCL'], 'desc': 'META·GOOGL 중심'},
        'Streaming': {'etfs': ['SUBZ'], 'desc': 'NFLX 비중 높음'},
        'Telecom Infra': {'etfs': ['FCOM'], 'desc': '배당 성격'}
    },
    'Consumer Discretionary': {
        'E-Commerce': {'etfs': ['IBUY', 'ONLN'], 'desc': 'AMZN 중복 주의'},
        'EV': {'etfs': ['DRIV', 'KARS'], 'desc': 'TSLA 비중 지배적'},
        'Travel/Leisure': {'etfs': ['AWAY', 'JETS'], 'desc': '경기 후행'}
    },
    'Financials': {
        'Large Banks': {'etfs': ['KBE', 'KRE'], 'desc': '금리 직결'},
        'Payments/Fintech': {'etfs': ['IPAY', 'PYPL'], 'desc': '성장주 성격'},
        'Asset Management': {'etfs': ['IAI'], 'desc': '시장 변동성 연동'},
        'Insurance': {'etfs': ['IAK'], 'desc': '방어적'}
    },
    'Healthcare': {
        'Biotech': {'etfs': ['XBI', 'IBB'], 'desc': '고변동'},
        'Pharma': {'etfs': ['PJP'], 'desc': '방어적 배당'},
        'Medical Devices': {'etfs': ['IHI'], 'desc': '경기 중립'},
        'Healthcare IT': {'etfs': ['HTEC'], 'desc': 'SaaS와 유사 특성'}
    },
    'Energy': {
        'Traditional Energy': {'etfs': ['OIH', 'XOP'], 'desc': '유가 직결'},
        'Renewable Energy': {'etfs': ['ICLN', 'TAN'], 'desc': '금리·정책 민감'},
        'Midstream': {'etfs': ['AMLP'], 'desc': '배당 인프라'}
    },
    'Industrials': {
        'Defense': {'etfs': ['ITA', 'XAR'], 'desc': '지정학 민감'},
        'Transportation/Logistics': {'etfs': ['IYT'], 'desc': '경기선행'},
        'Automation/Robotics': {'etfs': ['ROBO'], 'desc': '제조업 사이클'},
        'Infrastructure': {'etfs': ['PAVE'], 'desc': '정책 수혜'}
    },
    'Materials': {
        'Precious Metals': {'etfs': ['GDX', 'SIL'], 'desc': '달러 역상관'},
        'Copper/Minerals': {'etfs': ['COPX'], 'desc': '중국 수요 연동'},
        'Chemicals': {'etfs': ['XLB'], 'desc': 'XLB 내 필터'}
    },
    'Real Estate': {
        'Data Center REITs': {'etfs': ['SRVR'], 'desc': 'AI 인프라 테마'},
        'Residential REITs': {'etfs': ['REZ'], 'desc': '금리 민감'},
        'Commercial REITs': {'etfs': ['STOR'], 'desc': '경기 소비 연동'},
        'Healthcare REITs': {'etfs': ['HLTH'], 'desc': '방어적'}
    },
    'Utilities': {
        'Nuclear/Power': {'etfs': ['URE', 'NLR'], 'desc': 'AI 전력 수요 테마'},
        'Renewable Utilities': {'etfs': ['UTES'], 'desc': 'ICLN과 중첩 주의'}
    },
    'Consumer Staples': {
        'Food/Beverages': {'etfs': ['PBJ'], 'desc': '인플레 방어'},
        'Large Retail': {'etfs': ['WMT', 'COST'], 'desc': 'ETF 한계'}
    }
}

# 1-C. Yahoo Finance industry 영문명 -> 세부 테마 매핑 테이블
# ------------------------------------------------------------------------------
INDUSTRY_TO_SUB_SECTOR = {
    # Technology
    'Semiconductors': 'Semiconductors',
    'Semiconductor Equipment & Materials': 'Semiconductors',
    'Software—Infrastructure': 'Cloud/SaaS',
    'Software—Application': 'Cloud/SaaS',
    'Information Technology Services': 'Cloud/SaaS',
    'Computer Hardware': 'AI Infra',
    'Consumer Electronics': 'AI Infra',
    'Electronic Components': 'AI Infra',
    
    # Communication Services
    'Internet Content & Information': 'Social/Ads',
    'Entertainment': 'Streaming',
    'Telecom Services': 'Telecom Infra',
    'Advertising Agencies': 'Social/Ads',
    
    # Consumer Discretionary
    'Internet Retail': 'E-Commerce',
    'Auto Manufacturers': 'EV',
    'Travel Services': 'Travel/Leisure',
    'Lodging': 'Travel/Leisure',
    'Airlines': 'Travel/Leisure',
    'Leisure': 'Travel/Leisure',
    'Resorts & Casinos': 'Travel/Leisure',
    
    # Financials
    'Banks—Diversified': 'Large Banks',
    'Banks—Regional': 'Large Banks',
    'Credit Services': 'Payments/Fintech',
    'Asset Management': 'Asset Management',
    'Financial Data & Stock Exchanges': 'Payments/Fintech',
    'Insurance—Diversified': 'Insurance',
    'Insurance—Life': 'Insurance',
    'Insurance—Property & Casualty': 'Insurance',
    'Insurance Brokers': 'Insurance',
    
    # Healthcare
    'Biotechnology': 'Biotech',
    'Drug Manufacturers—General': 'Pharma',
    'Drug Manufacturers—Specialty & Generic': 'Pharma',
    'Medical Devices': 'Medical Devices',
    'Medical Instruments & Supplies': 'Medical Devices',
    'Health Information Services': 'Healthcare IT',
    
    # Energy
    'Oil & Gas E&P': 'Traditional Energy',
    'Oil & Gas Refining & Marketing': 'Traditional Energy',
    'Oil & Gas Equipment & Services': 'Traditional Energy',
    'Oil & Gas Integrated': 'Traditional Energy',
    'Thermal Coal': 'Traditional Energy',
    'Solar': 'Renewable Energy',
    'Clean Energy': 'Renewable Energy',
    'Oil & Gas Midstream': 'Midstream',
    
    # Industrials
    'Aerospace & Defense': 'Defense',
    'Integrated Freight & Logistics': 'Transportation/Logistics',
    'Railroads': 'Transportation/Logistics',
    'Trucking': 'Transportation/Logistics',
    'Specialty Industrial Machinery': 'Automation/Robotics',
    'Engineering & Construction': 'Infrastructure',
    'Rental & Leasing Services': 'Transportation/Logistics',
    'Industrial Distribution': 'Infrastructure',
    
    # Materials
    'Gold': 'Precious Metals',
    'Silver': 'Precious Metals',
    'Copper': 'Precious Metals',
    'Other Industrial Metals & Mining': 'Copper/Minerals',
    'Agricultural Inputs': 'Chemicals',
    'Specialty Chemicals': 'Chemicals',
    'Chemicals': 'Chemicals',
    
    # Real Estate
    'REIT—Specialty': 'Data Center REITs',
    'REIT—Residential': 'Residential REITs',
    'REIT—Retail': 'Commercial REITs',
    'REIT—Office': 'Commercial REITs',
    'REIT—Healthcare': 'Healthcare REITs',
    'REIT—Diversified': 'Commercial REITs',
    
    # Utilities
    'Utilities—Regulated Electric': 'Nuclear/Power',
    'Utilities—Regulated Gas': 'Nuclear/Power',
    'Utilities—Independent Power Producers': 'Nuclear/Power',
    'Utilities—Regulated Water': 'Nuclear/Power',
    'Utilities—Renewable': 'Renewable Utilities',
    
    # Consumer Staples
    'Packaged Foods': 'Food/Beverages',
    'Beverages—Non-Alcoholic': 'Food/Beverages',
    'Beverages—Brewers': 'Food/Beverages',
    'Beverages—Wineries & Distilleries': 'Food/Beverages',
    'Discount Stores': 'Large Retail',
    'Grocery Stores': 'Large Retail',
    'Household & Personal Products': 'Food/Beverages',
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
# 2-C. 트랙 C: 대형 기관 및 헤지펀드 스마트 머니 (Track C - Institutional Gurus)
# ------------------------------------------------------------------------------
GURUS_DEFAULT = ['AAPL', 'MSFT', 'GOOGL', 'AMZN', 'NVDA'] # 초기 폴백 리스트

TRACK_C_PRESETS = {
    'watchlist': load_json_watchlist(GURUS_WATCHLIST_PATH, GURUS_DEFAULT),
    'target_ciks': {
        'Berkshire Hathaway': '0001067983',
        'Scion Asset Management': '0001649339',
        'Pershing Square': '0001336528',
        'Citadel Advisors': '0001423053'
    },
    'filters': {
        'Market Cap.': '+Mid (over $2bln)',
        'Institutional Ownership': 0.30,         # 30% 이상
        'REQUIRE_FCF_POSITIVE': True,            # FCF 흑자 필수
        'MAX_DEBT_RATIO': 1.5,                   # 부채비율 150% 제한
        'vol_multiplier': 1.5
    },
    'max_candidates': 5
}


# ------------------------------------------------------------------------------
# 2-D. 트랙 D: 실리콘밸리 거물 VC 주도주 (Track D - Venture Capital Whales)
# ------------------------------------------------------------------------------
VC_DEFAULT = ['PLTR', 'ABNB', 'ASAN', 'AFRM', 'SNOW', 'COIN', 'ROKU', 'ANET', 'U', 'APP']

TRACK_D_PRESETS = {
    'watchlist': load_json_watchlist(VC_WATCHLIST_PATH, VC_DEFAULT),
    'target_ciks': {
        'Founders Fund': '0001438722',
        'Sequoia Capital': '0001393649',
        'Andreesen Horowitz': '0001475283'
    },
    'filters': {
        'Market Cap.': '+Mid (over $2bln)',
        'Institutional Ownership': 0.15,          # 15% 이상 완화
        'REQUIRE_FCF_POSITIVE': False,            # 적자 허용
        'MAX_DEBT_RATIO': 2.5,                    # 부채비율 250% 허용
        'vol_multiplier_boost': 1.8               # 1.8배 거래량 요구
    },
    'max_candidates': 3
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

# .env 파일 로드 (시스템 환경변수를 무시하고 .env 설정을 강제 덮어쓰기 위해 override=True 지정 및 절대 경로 명시)
load_dotenv(dotenv_path=os.path.join(BASE_DIR, ".env"), override=True)

OUTPUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "reports")

# 환경변수에서 가져오되, 없을 경우 기본값(또는 빈 문자열) 설정
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")

# [주의] 아래 직접 입력 방식은 지양하시고 .env 파일을 사용하십시오.
if not TELEGRAM_BOT_TOKEN:
    # 여기에 직접 입력 시 깃허브 공유에 각별히 유의하십시오.
    pass 

# ------------------------------------------------------------------------------
# 6. 리스크 관리 설정 (Risk Management & Guardrails)
# ------------------------------------------------------------------------------
# 리스크 프로파일 설정: 'CONSERVATIVE' | 'BALANCED' | 'AGGRESSIVE'
USER_RISK_PROFILE = os.getenv("USER_RISK_PROFILE", "BALANCED")

RISK_LIMITS = {
    'CONSERVATIVE': {
        'traditional_pe_limit': 25.0,
        'growth_pe_limit': 60.0,
        'peg_limit': 1.8
    },
    'BALANCED': {
        'traditional_pe_limit': 40.0,
        'growth_pe_limit': 100.0,
        'peg_limit': 2.5
    },
    'AGGRESSIVE': {
        'traditional_pe_limit': 60.0,
        'growth_pe_limit': 150.0,
        'peg_limit': 3.5
    }
}

# ------------------------------------------------------------------------------
# 7. 장기 투자 종목 Thesis 감시 설정
# ------------------------------------------------------------------------------
# Thesis 감시 주기 (기본: 4시간 - 14400초)
THESIS_CHECK_INTERVAL = 14400

# ------------------------------------------------------------------------------
# 8. 듀얼 LLM 아키텍처 및 벤치마크 설정
# ------------------------------------------------------------------------------
# 듀얼 LLM 모델명
LIGHT_LLM_MODEL = "gemma4"         # 가벼운 판단, 교정, 1차 분류용
HEAVY_LLM_MODEL = "gemma4:26b"     # 심층 추론, 리포트 작성, Thesis 평가용

# 성과 분석 벤치마크 지수 (S&P 500 ETF)
BENCHMARK_INDEX = "SPY"



