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
            ma60 = df['Close'].rolling(window=60).mean().iloc[-1]
            ma120 = df['Close'].rolling(window=120).mean().iloc[-1]
            
            # 이평선 배열 패턴 판별
            is_aligned = ma5 > ma20 and ma20 > ma60 and ma60 > ma120  # 정배열
            is_reversed = ma120 > ma60 and ma60 > ma20 and ma20 > ma5  # 완연한 역배열
            
            # 이평선 밀집도 계산 (수렴/혼조 여부: ma20, ma60, ma120의 편차가 4% 이내)
            ma_list = [ma20, ma60, ma120]
            ma_spread = (max(ma_list) - min(ma_list)) / (min(ma_list) + 1e-5)
            is_converged = ma_spread < 0.04
            
            vol = df['Volume'].iloc[-1]
            vol_ma20 = df['Volume'].rolling(window=config.VOL_MA_LENGTH).mean().iloc[-1]
            vol_ratio = vol / (vol_ma20 + 1e-5)
            
            # 국면별 거래량 급증 가중치 동적 적용
            base_multiplier = config.SNS_PRESETS.get('vol_multiplier', 1.5) if track == 'Track B' else config.VOL_MULTIPLIER
            if is_aligned:
                target_multiplier = base_multiplier * 0.8  # 정배열은 거래량 허들을 다소 낮춰 상승 지속을 잡아냄
            elif is_reversed:
                target_multiplier = base_multiplier * 1.8  # 역배열은 강력한 물량 소화를 위한 높은 거래량 필요
            elif is_converged:
                target_multiplier = base_multiplier * 1.2  # 수렴 구간 상방 돌파에는 확실한 유입 거래량 필요
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
                    print(f"   [역배열 돌파] {ticker}: 장기 역배열 상태에서 강한 거래량 동반 돌파 발생! (Vol:{vol_ratio:.1f}배)")
                elif s_rising and m_rising and l_rising:
                    signal = "⚠️ 역배열 거래량미달 반등 (관망)"
                    print(f"   [역배열 필터] {ticker}: 파동 상승세이나 거래량 부족으로 가짜반등 가능성 주의.")
                    
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
