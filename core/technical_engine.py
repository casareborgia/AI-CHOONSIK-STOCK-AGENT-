# ==============================================================================
# [AI Trading Agent] 코어 모듈 3: 타점 분석기 (Technical Engine)
# ==============================================================================
# 재무 필터링을 통과한 종목들을 대상으로 3중 스토캐스틱(5.3.3, 10.5.5, 20.12.12)과
# 20일 평균 거래량 대비 급증 여부를 계산하여 정밀 매수/매도 시그널을 도출합니다.
#
# [P0 패치] 의사결정 근거 보존 + 테스트 용이화
#  - 파동에너지 판정의 중간 계산값(스토캐스틱 K/D, 이평 국면, 거래량 배수)을
#    result_item에 그대로 담아 decision_traces로 적재될 수 있게 한다.
#  - 순수 연산부를 evaluate_signal(df, item, track)로 분리하여 네트워크 없이
#    골든 회귀 테스트가 가능하도록 한다.

import sys
import os
import logging
import pandas as pd
import yfinance as yf

# 부모 디렉토리 경로 추가
sys.path.append(os.path.dirname(os.path.dirname(__file__)))
import config
from core.sector_monitor import compute_stochastic_tv
from core.toss_client import toss_client

logger = logging.getLogger("TechnicalEngine")


def evaluate_signal(df: pd.DataFrame, item: dict, track: str = "Track A") -> dict:
    """
    [순수 함수] 단일 종목의 가격 DataFrame과 메타정보를 받아 파동에너지 시그널과
    그 '근거가 되는 모든 중간 계산값'을 담은 result_item을 반환합니다.
    네트워크 호출이 없어 고정 픽스처로 결정성(골든) 테스트가 가능합니다.
    df 길이가 부족하면 None을 반환합니다.
    """
    # MA60/MA120 정배열·수렴 국면 판정에 120개 봉이 필요하다.
    # 40~119개 구간에서는 MA60/MA120이 NaN이 되어 비교가 조용히 모두 False("mixed")로
    # 묻히므로, 데이터가 부족하면 분석 대상에서 제외한다.
    if df is None or df.empty or len(df) < 120:
        return None

    # 1. 3중 스토캐스틱 파동 연산 (소 5.3.3 / 중 10.5.5 / 대 20.12.12)
    s_k, s_d = compute_stochastic_tv(df, length=config.STOCH_SMALL['len'], k_len=config.STOCH_SMALL['k'], d_len=config.STOCH_SMALL['d'])
    m_k, m_d = compute_stochastic_tv(df, length=config.STOCH_MID['len'], k_len=config.STOCH_MID['k'], d_len=config.STOCH_MID['d'])
    l_k, l_d = compute_stochastic_tv(df, length=config.STOCH_LARGE['len'], k_len=config.STOCH_LARGE['k'], d_len=config.STOCH_LARGE['d'])

    # 2. 이동평균선 및 거래량 급증 연산
    close = df['Close'].iloc[-1]
    high = df['High'].iloc[-1]
    low = df['Low'].iloc[-1]
    ma5 = df['Close'].rolling(window=5).mean().iloc[-1]
    ma20 = df['Close'].rolling(window=20).mean().iloc[-1]
    ma60 = df['Close'].rolling(window=60).mean().iloc[-1]
    ma120 = df['Close'].rolling(window=120).mean().iloc[-1]

    # 이평선 배열 패턴 판별
    is_aligned = ma5 > ma20 and ma20 > ma60 and ma60 > ma120   # 정배열
    is_reversed = ma120 > ma60 and ma60 > ma20 and ma20 > ma5   # 완연한 역배열

    # 이평선 밀집도 계산 (수렴/혼조 여부: ma20, ma60, ma120의 편차가 4% 이내)
    ma_list = [ma20, ma60, ma120]
    ma_spread = (max(ma_list) - min(ma_list)) / (min(ma_list) + 1e-5)
    is_converged = ma_spread < 0.04

    # 국면 라벨 (decision_traces 적재용)
    if is_aligned:
        regime = "aligned"
    elif is_reversed:
        regime = "reversed"
    elif is_converged:
        regime = "converged"
    else:
        regime = "mixed"

    vol = df['Volume'].iloc[-1]
    vol_ma20 = df['Volume'].rolling(window=config.VOL_MA_LENGTH).mean().iloc[-1]
    vol_ratio = vol / (vol_ma20 + 1e-5)

    # 국면별 거래량 급증 가중치 동적 적용
    base_multiplier = config.SNS_PRESETS.get('vol_multiplier', 1.5) if track == 'Track B' else config.VOL_MULTIPLIER
    if is_aligned:
        target_multiplier = base_multiplier * 0.8   # 정배열은 거래량 허들을 다소 낮춰 상승 지속을 잡아냄
    elif is_reversed:
        target_multiplier = base_multiplier * 1.8   # 역배열은 강력한 물량 소화를 위한 높은 거래량 필요
    elif is_converged:
        target_multiplier = base_multiplier * 1.2   # 수렴 구간 상방 돌파에는 확실한 유입 거래량 필요
    else:
        target_multiplier = base_multiplier

    is_vol_surge = vol_ratio >= target_multiplier

    # 3. 파동 상승세 판별 (현재 %K > %D)
    s_rising = s_k.iloc[-1] > s_d.iloc[-1]
    m_rising = m_k.iloc[-1] > m_d.iloc[-1]
    l_rising = l_k.iloc[-1] > l_d.iloc[-1]

    # 4. 시그널 판별 로직 (이평선 배열 국면별 차등화)
    signal = "관망 (대기)"

    if is_aligned:
        # [정배열 국면]
        if s_rising and m_rising and l_rising and is_vol_surge:
            signal = "🔥 정배열 추세지속 (강력매수)"
        elif s_rising and m_rising and l_rising:
            signal = "📈 정배열 파동정배열 (분할매수)"
        elif (not s_rising) and m_rising and l_rising:
            # 대/중 파동은 살아있는데 소파동만 눌렸을 때의 타점
            signal = "📈 정배열 눌림목 구간 (매수대기)"

    elif is_reversed:
        # [역배열 국면]
        if s_rising and m_rising and l_rising and is_vol_surge:
            signal = "⚡ 역배열 거래량돌파 (단기대응)"
            logger.info(f"   [역배열 돌파] {item.get('ticker')}: 장기 역배열 상태에서 강한 거래량 동반 돌파 발생! (Vol:{vol_ratio:.1f}배)")
        elif s_rising and m_rising and l_rising:
            signal = "⚠️ 역배열 거래량미달 반등 (관망)"
            logger.info(f"   [역배열 필터] {item.get('ticker')}: 파동 상승세이나 거래량 부족으로 가짜반등 가능성 주의.")

    elif is_converged:
        # [수렴/혼조 국면]
        if close > max(ma20, ma60) and is_vol_surge:
            signal = "🌀 수렴 상방발산 (매수진입)"
        elif s_rising and m_rising and l_rising:
            signal = "🌀 수렴 에너집결 (매수준비)"

    else:
        # [일반 혼조 국면]
        if s_rising and m_rising and l_rising and (close > ma5) and is_vol_surge:
            signal = "🔥 찐폭발 (강력매수)"
        elif s_rising and m_rising and l_rising:
            signal = "📈 파동정배열 (분할매수)"
        elif m_rising and l_rising and is_vol_surge:
            signal = "📈 파동상승 (분할매수)"
        elif (l_k.iloc[-1] < l_d.iloc[-1]) and (close < ma20) and is_vol_surge:
            signal = "⚠️ 투매폭발 (리스크주의)"

    # 결과 병합 (기존 재무 정보 복사 + 시그널 + 의사결정 근거 raw 값 보존)
    result_item = dict(item)
    result_item.update({
        'close': close,
        'high': high,
        'low': low,
        'vol_ratio': vol_ratio,
        'signal': signal,
        'stoch_summary': f"S:{'▲' if s_rising else '▼'} M:{'▲' if m_rising else '▼'} L:{'▲' if l_rising else '▼'}",
        # --- [P0] decision_traces 적재용 근거값 ---
        'regime': regime,
        'ma5': float(ma5), 'ma20': float(ma20), 'ma60': float(ma60), 'ma120': float(ma120),
        'stoch_s_k': float(s_k.iloc[-1]), 'stoch_s_d': float(s_d.iloc[-1]),
        'stoch_m_k': float(m_k.iloc[-1]), 'stoch_m_d': float(m_d.iloc[-1]),
        'stoch_l_k': float(l_k.iloc[-1]), 'stoch_l_d': float(l_d.iloc[-1]),
        's_rising': bool(s_rising), 'm_rising': bool(m_rising), 'l_rising': bool(l_rising),
        'vol_multiplier': float(target_multiplier),
        'is_vol_surge': bool(is_vol_surge),
    })
    return result_item


def analyze_technical_signals(candidates):
    """
    기본적 분석을 통과한 후보군 딕셔너리 리스트를 받아 기술적 타점을 분석합니다.
    입력 예시: [{'ticker': 'NVDA', 'name': 'NVIDIA', ...}]
    """
    print(f"\n📈 [3단계: 기술적 타점 분석] 3중 파동에너지 및 거래량 급증 스캔 중 (대상: {len(candidates)}개)...")

    signal_results = []

    for item in candidates:
        ticker = item['ticker']
        track = item.get('track', 'Track A')
        df = None
        
        # 1차 시도: 토스증권 API로 데이터 로드 (120일선 연산을 위해 150개 봉 로드)
        try:
            df = toss_client.get_candles(ticker, interval="1d", count=150)
            logger.info(f"📊 [Toss API] {ticker} 일봉 {len(df)}개 로드 완료.")
        except Exception as toss_err:
            logger.warning(f"⚠️ [Toss API] {ticker} 로드 실패 ({toss_err}). yfinance 폴백 작동...")
            
        # 2차 시도 (폴백): 기존 yfinance 로드
        if df is None or df.empty:
            try:
                stock = yf.Ticker(ticker)
                df = stock.history(period="6mo")
                logger.info(f"📈 [yfinance] {ticker} 일봉 {len(df)}개 로드 완료.")
            except Exception as yf_err:
                logger.error(f"❌ [yfinance] {ticker} 로드 최종 실패: {yf_err}")
                continue

        try:
            result_item = evaluate_signal(df, item, track)
            if result_item is None:
                # [P0] 데이터 부족으로 스킵된 종목을 조용히 버리지 않고 명시적으로 로깅
                logger.warning(f"[Skip] {ticker}: 데이터 부족(len<120) 또는 빈 데이터프레임으로 분석 제외.")
                continue

            signal_results.append(result_item)

        except Exception as e:
            # [P0] 종목별 예외를 침묵으로 삼키지 않고 사유를 로깅 (관측 가능성 확보)
            logger.error(f"[Error] {ticker} 기술적 분석 실패: {e}")
            continue

    # 시그널이 뜬 종목 위주로 정렬 (매수 신호 우선)
    strong_candidates = [r for r in signal_results if "매수" in r['signal'] or "폭발" in r['signal']]
    others = [r for r in signal_results if r not in strong_candidates]
    
    final_sorted = strong_candidates + others
    
    print("\n==================================================")
    print(f"🎯 기술적 파동 시그널 스캔 결과 (총 {len(final_sorted)}개)")
    print("==================================================")
    for r in final_sorted:
        track_str = r.get('track', 'Track A')
        print(f"[{track_str}] [{r['ticker']}] {r['signal']} | 종가: ${r['close']:.2f} | 거래량: {r['vol_ratio']:.1f}배 | 파동: {r['stoch_summary']}")
        
    return final_sorted


# 모듈 단독 테스트용 코드
if __name__ == "__main__":
    # 임의의 샘플 데이터 주입
    sample = [
        {'ticker': 'TSLA', 'name': 'Tesla Inc.', 'inst_own': 60.5, 'fcf': 1200000, 'sector': 'Consumer Discretionary'},
        {'ticker': 'NVDA', 'name': 'NVIDIA Corp.', 'inst_own': 75.0, 'fcf': 5000000, 'sector': 'Technology'}
    ]
    analyze_technical_signals(sample)
