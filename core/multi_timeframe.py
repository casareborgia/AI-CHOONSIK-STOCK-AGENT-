# ==============================================================================
# [AI Trading Agent] 코어 모듈 3-2: 멀티타임프레임 분석기 (Multi-Timeframe Engine)
# ==============================================================================
# 주봉(Weekly) + 일봉(Daily) + 4시간봉(4H) 데이터를 입체적으로 스캔하여,
# 장기 추세 방향과 정밀 진입 타점을 크로스체크하고 타점 등급(A~E)을 산출합니다.
# TradingView의 "파동에너지 전략 v6" Pine Script 로직을 완벽하게 재현합니다.

import sys
import os
import pandas as pd
import numpy as np
import yfinance as yf
from datetime import datetime

# 부모 디렉토리 경로 추가
sys.path.append(os.path.dirname(os.path.dirname(__file__)))
import config
# 스토캐스틱 계산은 sector_monitor의 단일 구현을 재사용한다 (중복 구현으로 인한 로직 분기 방지).
from core.sector_monitor import compute_stochastic_tv


def pivotlow(series: pd.Series, left: int, right: int) -> pd.Series:
    """
    Pine Script의 ta.pivotlow(series, left, right) 함수를 재현합니다.
    series[i - right]가 좌측 left개 봉과 우측 right개 봉 사이의 엄격한 최솟값일 때 값을 채웁니다.
    """
    pivots = pd.Series(index=series.index, dtype=float)
    n = len(series)
    if n < (left + right + 1):
        return pivots
        
    for i in range(left + right, n):
        target_idx = i - right
        target_val = series.iloc[target_idx]
        
        left_window = series.iloc[target_idx - left : target_idx]
        right_window = series.iloc[target_idx + 1 : i + 1]
        
        # NaN이 포함된 윈도우는 패스
        if left_window.isnull().any() or right_window.isnull().any() or pd.isna(target_val):
            continue
            
        # 좌측 및 우측과 크기 비교
        if all(target_val < val for val in left_window) and all(target_val <= val for val in right_window):
            pivots.iloc[i] = target_val
            
    return pivots


def pivothigh(series: pd.Series, left: int, right: int) -> pd.Series:
    """
    Pine Script의 ta.pivothigh(series, left, right) 함수를 재현합니다.
    """
    pivots = pd.Series(index=series.index, dtype=float)
    n = len(series)
    if n < (left + right + 1):
        return pivots
        
    for i in range(left + right, n):
        target_idx = i - right
        target_val = series.iloc[target_idx]
        
        left_window = series.iloc[target_idx - left : target_idx]
        right_window = series.iloc[target_idx + 1 : i + 1]
        
        if left_window.isnull().any() or right_window.isnull().any() or pd.isna(target_val):
            continue
            
        if all(target_val > val for val in left_window) and all(target_val >= val for val in right_window):
            pivots.iloc[i] = target_val
            
    return pivots


def resample_to_4h(df_1h: pd.DataFrame) -> pd.DataFrame:
    """
    yfinance 1시간봉 데이터를 정규 4시간봉 단위로 병합 및 리샘플링합니다.
    - Open: 4시간 내 첫 번째 거래값 (first)
    - High: 4시간 내 최고 거래값 (max)
    - Low: 4시간 내 최저 거래값 (min)
    - Close: 4시간 내 마지막 거래값 (last)
    - Volume: 4시간 내 거래량 총합 (sum)
    """
    conversion = {
        'Open': 'first',
        'High': 'max',
        'Low': 'min',
        'Close': 'last',
        'Volume': 'sum'
    }
    # 미국의 정규장 거래 시간대와 일치하도록 origin='start_day' 또는 'start'를 사용해 병합
    df_4h = df_1h.resample('4h', origin='start').agg(conversion).dropna()
    return df_4h


def analyze_timeframe(ticker: str, timeframe: str, vol_multiplier: float = 1.5) -> dict:
    """
    지정된 종목 티커와 타임프레임("1wk" | "1d" | "4h")의 모든 기술적 파동 및 이평 지표를 분석합니다.
    """
    stock = yf.Ticker(ticker)
    
    # 1. 데이터 로드 및 4H 리샘플링 분기
    if timeframe == "1wk":
        # MA120 연산을 위해 3년치(충분히 120주 이상) 데이터 안전 로드
        df = stock.history(interval="1wk", period="3y")
    elif timeframe == "1d":
        df = stock.history(interval="1d", period="1y")
    elif timeframe == "4h":
        df_1h = stock.history(interval="1h", period="60d")
        if df_1h.empty:
            raise ValueError(f"{ticker} 1시간봉 데이터가 비어 있습니다.")
        df = resample_to_4h(df_1h)
    else:
        raise ValueError(f"지원하지 않는 타임프레임입니다: {timeframe}")
        
    if df.empty or len(df) < 40:
        raise ValueError(f"{ticker} ({timeframe}) 분석에 충분한 데이터가 확보되지 않았습니다. (현재 데이터 수: {len(df)})")
        
    # 2. 이동평균선(SMA) 연산
    df['MA5'] = df['Close'].rolling(window=5).mean()
    df['MA20'] = df['Close'].rolling(window=20).mean()
    df['MA60'] = df['Close'].rolling(window=60).mean()
    df['MA120'] = df['Close'].rolling(window=120).mean()
    
    # 3. 3중 스토캐스틱 파동 연산
    s_k, s_d = compute_stochastic_tv(df, length=5, k_len=3, d_len=3)
    m_k, m_d = compute_stochastic_tv(df, length=10, k_len=5, d_len=5)
    l_k, l_d = compute_stochastic_tv(df, length=20, k_len=12, d_len=12)
    
    # 최신 및 직전 인덱스
    curr_idx = -1
    prev_idx = -2
    
    # 지표 값 추출
    close_curr = df['Close'].iloc[curr_idx]
    close_prev = df['Close'].iloc[prev_idx]
    
    ma5_curr = df['MA5'].iloc[curr_idx]
    ma5_prev = df['MA5'].iloc[prev_idx]
    
    ma20_curr = df['MA20'].iloc[curr_idx]
    ma60_curr = df['MA60'].iloc[curr_idx]
    # MA120은 데이터가 충분하지 않으면 NaN. MA20으로 대체하면 정배열 판정이 왜곡되므로
    # 가용 여부를 별도로 보관하여 추세 판정 시 조건을 분기한다.
    ma120_raw = df['MA120'].iloc[curr_idx]
    has_ma120 = not pd.isna(ma120_raw)
    ma120_curr = ma120_raw if has_ma120 else ma60_curr
    
    # 스토캐스틱 K/D 최신 및 직전 값
    sk_curr, sk_prev = s_k.iloc[curr_idx], s_k.iloc[prev_idx]
    mk_curr, mk_prev = m_k.iloc[curr_idx], m_k.iloc[prev_idx]
    lk_curr, lk_prev = l_k.iloc[curr_idx], l_k.iloc[prev_idx]
    
    sd_curr = s_d.iloc[curr_idx]
    md_curr = m_d.iloc[curr_idx]
    ld_curr = l_d.iloc[curr_idx]
    
    # 4. 파동 및 거래량 판별
    # 스토캐스틱 상승 중 판정 (K가 전봉 대비 상승)
    s_rising = sk_curr > sk_prev
    m_rising = mk_curr > mk_prev
    l_rising = lk_curr > lk_prev
    
    # 스토캐스틱 하락 중 판정 (K가 전봉 대비 하락)
    s_falling = sk_curr < sk_prev
    m_falling = mk_curr < mk_prev
    l_falling = lk_curr < lk_prev
    
    all_rising = s_rising and m_rising and l_rising
    all_falling = s_falling and m_falling and l_falling
    
    # MA5 돌파 판정
    ma5_crossover = (close_prev < ma5_prev) and (close_curr > ma5_curr)
    ma5_crossunder = (close_prev > ma5_prev) and (close_curr < ma5_curr)
    
    # 거래량 급증 판정 (20일 평균 대비 1.5배 이상)
    df['VolMA20'] = df['Volume'].rolling(window=20).mean()
    vol_ma20 = df['VolMA20'].iloc[curr_idx]
    vol_curr = df['Volume'].iloc[curr_idx]
    vol_ratio = vol_curr / (vol_ma20 + 1e-8)
    is_vol_surge = vol_curr > (vol_ma20 * vol_multiplier)
    
    # 5. 시그널 조합
    signals = []
    if all_rising and ma5_crossover:
        if is_vol_surge:
            signals.append("bull_surge")   # 찐폭발
        else:
            signals.append("bull_normal")  # 폭발
            
    if all_falling and ma5_crossunder:
        if is_vol_surge:
            signals.append("bear_surge")   # 투매폭발
        else:
            signals.append("bear_normal")  # 주의
            
    # 6. 쌍바닥 & 쌍봉 감지 (대파동 largeK 피봇 기준, 좌우 3봉)
    p_lows = pivotlow(l_k, 3, 3)
    valid_lows = p_lows.dropna()
    twin_bottom_detected = False
    if len(valid_lows) >= 2:
        valley_curr = valid_lows.iloc[-1]
        valley_prev = valid_lows.iloc[-2]
        # 최신 피봇 로우가 이전보다 높고, 현재 대파동(largeK)이 40 이하일 때
        if (valley_curr > valley_prev) and (lk_curr < 40):
            twin_bottom_detected = True
            signals.append("twin_bottom")
            
    p_highs = pivothigh(l_k, 3, 3)
    valid_highs = p_highs.dropna()
    twin_top_detected = False
    if len(valid_highs) >= 2:
        peak_curr = valid_highs.iloc[-1]
        peak_prev = valid_highs.iloc[-2]
        # 최신 피봇 하이가 이전보다 낮고, 현재 대파동이 60 이상일 때
        if (peak_curr < peak_prev) and (lk_curr > 60):
            twin_top_detected = True
            signals.append("twin_top")
            
    # 7. 추세 배경 판정 (MA 정배열/역배열)
    # 120일 선이 데이터 부족으로 NaN인 경우, MA120 조건은 제외하고 MA20/MA60만으로 판정한다.
    if has_ma120:
        if (ma20_curr > ma60_curr) and (ma60_curr > ma120_curr):
            ma_trend = "bull"
        elif (ma20_curr < ma60_curr) and (ma60_curr < ma120_curr):
            ma_trend = "bear"
        else:
            ma_trend = "neutral"
    else:
        if ma20_curr > ma60_curr:
            ma_trend = "bull"
        elif ma20_curr < ma60_curr:
            ma_trend = "bear"
        else:
            ma_trend = "neutral"
        
    return {
        "ticker": ticker,
        "timeframe": timeframe,
        "close": close_curr,
        "ma_trend": ma_trend,
        "stoch": {
            "small": {"k": sk_curr, "d": sd_curr, "rising": s_rising},
            "mid":   {"k": mk_curr, "d": md_curr, "rising": m_rising},
            "large": {"k": lk_curr, "d": ld_curr, "rising": l_rising}
        },
        "all_rising": all_rising,
        "all_falling": all_falling,
        "ma5_crossover": ma5_crossover,
        "ma5_crossunder": ma5_crossunder,
        "vol_surge": is_vol_surge,
        "vol_ratio": vol_ratio,
        "signals": signals,
        "twin_bottom_detected": twin_bottom_detected,
        "twin_top_detected": twin_top_detected
    }


def multi_timeframe_analysis(ticker: str) -> dict:
    """
    주봉(1wk) + 일봉(1d) + 4시간봉(4h) 분석을 수행하여 
    최종 타점 등급(entry_grade)과 전문적인 한 줄 요약(summary)을 반환합니다.
    """
    print(f"📡 [{ticker}] 3단 시차(Weekly-Daily-4H) 파동에너지 통합 스캔 중...")
    
    # 3개 타임프레임 독립 분석 수행
    weekly = analyze_timeframe(ticker, "1wk")
    daily = analyze_timeframe(ticker, "1d")
    four_h = analyze_timeframe(ticker, "4h")
    
    # 타점 등급(entry_grade) 판정
    # "A": 주봉 상승추세(bull) + 일봉 시그널 발생(bull_surge/bull_normal/twin_bottom) + 4시간봉 시그널 발생(bull_surge/bull_normal)
    # "B": 주봉 상승추세(bull) + 일봉 시그널 발생 + 4시간봉 미확인
    # "C": 주봉 상승추세(bull) + 일봉 시그널 없음 (대기)
    # "D": 주봉 하락추세(bear) — 진입 금지
    # "E": 주봉 전환구간(neutral) + 쌍바닥 감지 — 상승 1파 초기 후보
    
    w_trend = weekly["ma_trend"]
    d_signals = daily["signals"]
    f_signals = four_h["signals"]
    
    # 일봉 상승 시그널 발생 여부
    has_d_bull_signal = any(sig in d_signals for sig in ["bull_surge", "bull_normal", "twin_bottom"])
    # 4시간봉 상승 시그널 발생 여부
    has_f_bull_signal = any(sig in f_signals for sig in ["bull_surge", "bull_normal"])
    
    if w_trend == "bear":
        entry_grade = "D"
        summary = "주봉이 중장기 하락추세(Bear)에 머물러 있어 리스크 관리 차원의 진입 전면 금지 구간입니다."
    elif w_trend == "bull":
        if has_d_bull_signal and has_f_bull_signal:
            entry_grade = "A"
            summary = "주봉 정배열 상승추세 위에 일봉/4시간봉 매수 타점이 동시 포착된 특급 퀀트 매수 타점(A등급)입니다!"
        elif has_d_bull_signal:
            entry_grade = "B"
            summary = "주봉 상승추세 하에 일봉 타점은 발생했으나 4시간 정밀 타점이 아직 무르익지 않은 분할진입(B등급) 대기선입니다."
        else:
            entry_grade = "C"
            summary = "주봉은 우상향 추세이나 일봉상 매수 타점이 포착되지 않아 눌림목 반등 시그널을 관망하는 대기(C등급) 구간입니다."
    else:  # w_trend == "neutral" (전환 구간)
        # 주봉 전환 구간에서 주봉 또는 일봉/4시간봉에서 쌍바닥이 감지되었는지 확인
        has_w_twin_bottom = "twin_bottom" in weekly["signals"] or weekly["twin_bottom_detected"]
        has_d_twin_bottom = "twin_bottom" in daily["signals"] or daily["twin_bottom_detected"]
        
        if has_w_twin_bottom or has_d_twin_bottom:
            entry_grade = "E"
            summary = "주봉 전환구간 내에서 강력한 파동 쌍바닥이 형성된 추세전환 상승 1파 초기 고배당 진입 후보(E등급)입니다."
        else:
            # 주봉 중립인데 쌍바닥도 없으면 보수적으로 C등급 처리 (또는 안전하게 관망)
            entry_grade = "C"
            summary = "주봉 추세 수렴 및 전환 구간으로 확실한 파동 쌍바닥 등 방향성 확인 전까지는 적극 진입 보류 권장 구간입니다."
            
    return {
        "ticker": ticker,
        "weekly": weekly,
        "daily": daily,
        "four_h": four_h,
        "entry_grade": entry_grade,
        "summary": summary
    }


# 단독 테스트용
if __name__ == "__main__":
    ticker = "AAPL"
    try:
        result = multi_timeframe_analysis(ticker)
        print("\n==================================================")
        print(f"📊 {ticker} 멀티타임프레임 분석 최종 결과")
        print("==================================================")
        print(f"주봉 추세: {result['weekly']['ma_trend']} | 시그널: {result['weekly']['signals']}")
        print(f"일봉 추세: {result['daily']['ma_trend']} | 시그널: {result['daily']['signals']}")
        print(f"4시간 추세: {result['four_h']['ma_trend']} | 시그널: {result['four_h']['signals']}")
        print(f"최종 타점 등급: {result['entry_grade']}")
        print(f"한 줄 요약: {result['summary']}")
    except Exception as e:
        print(f"❌ 분석 오류: {e}")
