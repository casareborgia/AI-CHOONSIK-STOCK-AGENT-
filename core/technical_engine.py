# ==============================================================================
# [AI Trading Agent] 코어 모듈 3: 타점 분석기 (Technical Engine)
# ==============================================================================
# 재무 필터링을 통과한 종목들을 대상으로 3중 스토캐스틱(5.3.3, 10.5.5, 20.12.12)과
# 20일 평균 거래량 대비 급증 여부를 계산하여 정밀 매수/매도 시그널을 도출합니다.

import sys
import os
import pandas as pd
import yfinance as yf

# 부모 디렉토리 경로 추가
sys.path.append(os.path.dirname(os.path.dirname(__file__)))
import config
from core.sector_monitor import compute_stochastic_tv


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
        try:
            stock = yf.Ticker(ticker)
            # 120일 이평선 및 대파동 계산을 위해 6개월치 데이터 로드
            df = stock.history(period="6mo")
            
            if df.empty or len(df) < 40:
                continue
                
            # 1. 3중 스토캐스틱 파동 연산
            # 소파동 (5.3.3)
            s_k, s_d = compute_stochastic_tv(df, length=config.STOCH_SMALL['len'], k_len=config.STOCH_SMALL['k'], d_len=config.STOCH_SMALL['d'])
            # 중파동 (10.5.5)
            m_k, m_d = compute_stochastic_tv(df, length=config.STOCH_MID['len'], k_len=config.STOCH_MID['k'], d_len=config.STOCH_MID['d'])
            # 대파동 (20.12.12)
            l_k, l_d = compute_stochastic_tv(df, length=config.STOCH_LARGE['len'], k_len=config.STOCH_LARGE['k'], d_len=config.STOCH_LARGE['d'])
            
            # 2. 이동평균선 및 거래량 급증 연산
            close = df['Close'].iloc[-1]
            high = df['High'].iloc[-1]
            low = df['Low'].iloc[-1]
            ma5 = df['Close'].rolling(window=5).mean().iloc[-1]
            ma20 = df['Close'].rolling(window=20).mean().iloc[-1]
            
            vol = df['Volume'].iloc[-1]
            vol_ma20 = df['Volume'].rolling(window=config.VOL_MA_LENGTH).mean().iloc[-1]
            
            # 거래량 급증 비율 (평균 대비 몇 배 터졌는지)
            vol_ratio = vol / (vol_ma20 + 1e-5)
            target_multiplier = config.SNS_PRESETS.get('vol_multiplier', 1.5) if track == 'Track B' else config.VOL_MULTIPLIER
            is_vol_surge = vol_ratio >= target_multiplier
            
            # 3. 파동 상승세 판별 (현재 %K > %D)
            s_rising = s_k.iloc[-1] > s_d.iloc[-1]
            m_rising = m_k.iloc[-1] > m_d.iloc[-1]
            l_rising = l_k.iloc[-1] > l_d.iloc[-1]
            
            # 4. 시그널 판별 로직 (TradingView 전략 완벽 이식)
            signal = "관망 (대기)"
            
            # [매수 타점 1: 🔥 찐폭발] 3중 파동 모두 상승 + 종가가 5일선 위 + 거래량 급증
            if s_rising and m_rising and l_rising and (close > ma5) and is_vol_surge:
                signal = "🔥 찐폭발 (강력매수)"
                
            # [매수 타점 2: 📈 파동정배열 선점] 3중 파동 모두 상승 (장중 거래량 도달 전 선점 타점)
            elif s_rising and m_rising and l_rising:
                signal = "📈 파동정배열 (분할매수)"
                
            # [매수 타점 3: 📈 파동상승 초기] 대/중 파동 상승 + 거래량 수반
            elif m_rising and l_rising and is_vol_surge:
                signal = "📈 파동상승 (분할매수)"
                
            # [위험 타점: ⚠️ 투매폭발 / 하락전환] 대파동 데드크로스 + 거래량 급증 하락
            elif (l_k.iloc[-1] < l_d.iloc[-1]) and (close < ma20) and is_vol_surge:
                signal = "⚠️ 투매폭발 (리스크주의)"
                
            # 결과 병합
            result_item = dict(item)  # 기존 재무 정보 복사
            result_item.update({
                'close': close,
                'high': high,
                'low': low,
                'vol_ratio': vol_ratio,
                'signal': signal,
                'stoch_summary': f"S:{'▲' if s_rising else '▼'} M:{'▲' if m_rising else '▼'} L:{'▲' if l_rising else '▼'}"
            })
            
            signal_results.append(result_item)
            
        except Exception as e:
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
