# ==============================================================================
# [AI Trading Agent] 코어 모듈 1: 숲 분석기 (Sector Monitor)
# ==============================================================================
# 미국 11대 SPDR 섹터 ETF 및 핵심 테마 ETF의 파동에너지와 모멘텀을 연산하여,
# 현재 시장에서 자금이 가장 강하게 유입되는 상위 주도 섹터를 추출합니다.

import sys
import os
import pandas as pd
import yfinance as yf

# 부모 디렉토리의 config 모듈 임포트를 위한 경로 추가 (단독 실행 지원)
sys.path.append(os.path.dirname(os.path.dirname(__file__)))
import config


def compute_stochastic_tv(df, length=20, k_len=12, d_len=12):
    """
    트레이딩뷰(TradingView) 방식의 파동에너지 3중 스토캐스틱을 완벽히 재현합니다.
    """
    # 1. Fast Stochastic %K 계산
    low_min = df['Low'].rolling(window=length).min()
    high_max = df['High'].rolling(window=length).max()
    
    # 분모가 0이 되는 것을 방지
    raw_k = 100 * (df['Close'] - low_min) / (high_max - low_min + 1e-8)
    
    # 2. 부드러운 %K (k_len 기간 단순이동평균)
    k = raw_k.rolling(window=k_len).mean()
    
    # 3. %D (d_len 기간 단순이동평균)
    d = k.rolling(window=d_len).mean()
    
    return k, d


def get_leading_sectors():
    """
    전체 타겟 섹터 ETF의 일봉을 분석하여 모멘텀 상위 TOP N 섹터명을 반환합니다.
    """
    print("\n🌐 [1단계: 숲 분석] 대표 섹터 ETF 자금 순환매 스캔 중...")
    
    sector_results = []
    
    for sector_name, ticker in config.SECTOR_ETFS.items():
        try:
            # 최소 6개월치 데이터 로드 (안정적인 120MA 및 대파동 계산용)
            etf = yf.Ticker(ticker)
            df = etf.history(period="6mo")
            
            if df.empty or len(df) < 60:
                continue
                
            # 대파동(20.12.12) 스토캐스틱 연산
            l_len = config.STOCH_LARGE['len']
            l_k   = config.STOCH_LARGE['k']
            l_d   = config.STOCH_LARGE['d']
            
            large_k, large_d = compute_stochastic_tv(df, length=l_len, k_len=l_k, d_len=l_d)
            
            # 최근 종가 및 지표 값 추출
            curr_k = large_k.iloc[-1]
            curr_d = large_d.iloc[-1]
            
            # 1개월(20거래일) 모멘텀 수익률 (Rate of Change)
            roc_1m = (df['Close'].iloc[-1] / df['Close'].iloc[-21] - 1) * 100
            
            # 20일 이평선 및 60일 이평선 정배열 상태 확인
            ma20 = df['Close'].rolling(window=20).mean().iloc[-1]
            ma60 = df['Close'].rolling(window=60).mean().iloc[-1]
            is_uptrend = ma20 > ma60
            
            # 스코어링 정책: 1개월 모멘텀 수익률 중심 + 파동 정배열 가점
            score = roc_1m
            if curr_k > curr_d:          # 파동 상승세 가점
                score += 2.0
            if is_uptrend:               # 이평선 정배열 가점
                score += 2.0
                
            sector_results.append({
                'sector_name': sector_name,
                'ticker': ticker,
                'roc_1m': roc_1m,
                'large_k': curr_k,
                'large_d': curr_d,
                'score': score
            })
            
        except Exception as e:
            print(f"⚠️ {sector_name}({ticker}) 데이터 수집 실패: {e}")
            continue
            
    # 스코어 기준 내림차순 정렬
    df_sectors = pd.DataFrame(sector_results).sort_values(by='score', ascending=False)
    
    # TOP N 주도 섹터 추출
    top_n = config.TOP_N_SECTORS
    leading_sectors_df = df_sectors.head(top_n)
    
    leading_names = leading_sectors_df['sector_name'].tolist()
    leading_tickers = leading_sectors_df['ticker'].tolist()
    
    print("==================================================")
    print(f"🏆 오늘의 TOP {top_n} 주도 섹터 (자금 유입 최상위)")
    print("==================================================")
    for idx, row in leading_sectors_df.iterrows():
        status = "🔥 파동상승" if row['large_k'] > row['large_d'] else "눌림/조정"
        print(f"{row['sector_name']} ({row['ticker']}) | 1M 모멘텀: {row['roc_1m']:.2f}% | 대파동: {status}")
        
    return leading_names, leading_tickers


# 모듈 단독 테스트용 코드
if __name__ == "__main__":
    get_leading_sectors()
