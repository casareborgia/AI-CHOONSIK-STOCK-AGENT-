# ==============================================================================
# [AI Trading Agent] 코어 모듈 2: 나무 분석기 (Fundamental Filter)
# ==============================================================================
# 1차로 Finviz 스크리너를 통해 저평가/고효율 우량주 후보군을 고속 추출하고,
# 2차로 Yahoo Finance API를 통해 기관 보유 지분, 잉여현금흐름(FCF) 등을 심층 검증합니다.
# 
# [기능 고도화] 1단계에서 도출된 주도 섹터(target_sectors) 정보와 연동하여,
# 주도 섹터에 속하지 않은 소외 종목은 결과 리스트에서 가차 없이 탈락시키는
# 직렬 섹터 필터링을 강제 적용합니다. (섹터-종목 정합성 극대화)

import sys
import os
import yfinance as yf
import functools

# 부모 디렉토리 경로 추가
sys.path.append(os.path.dirname(os.path.dirname(__file__)))
import config

try:
    from finvizfinance.screener.overview import Overview
    FINVIZ_AVAILABLE = True
except ImportError:
    FINVIZ_AVAILABLE = False


# 단순 인메모리 LRU 캐싱을 통해 당일 구동 내 중복 yfinance Ticker 조회 비용을 0으로 단축
@functools.lru_cache(maxsize=256)
def get_cached_ticker_info(ticker: str) -> dict:
    """yfinance Ticker.info 호출 결과를 캐싱합니다.
    에러 발생 시 빈 딕셔너리를 반환하여 프로그램이 중단되지 않도록 보호합니다."""
    try:
        t = yf.Ticker(ticker)
        info = t.info
        if not info:
            return {}
        return info
    except Exception:
        return {}


def run_finviz_screener(target_sectors=None):
    """
    Finviz 서버사이드 필터링을 통해 1차 우량주 후보군 티커 리스트를 추출합니다.
    """
    print("\n🔍 [2단계-A: 고속 필터링] Finviz 서버 연동 우량주 후보군 추출 중...")
    
    # finvizfinance 라이브러리가 없거나 통신 실패 시 사용할 예비 우량주 풀 (Fall-back)
    fallback_tickers = ['NVDA', 'AAPL', 'MSFT', 'GOOGL', 'AMZN', 'META', 'TSLA', 'AVGO', 'AMD', 'QCOM', 'NFLX', 'ADBE']
    
    if not FINVIZ_AVAILABLE:
        print("⚠️ finvizfinance 라이브러리가 감지되지 않아 기본 핵심 우량주 풀로 대체합니다.")
        return fallback_tickers
        
    try:
        overview = Overview()
        
        # config.py의 프리셋 필터 적용 (값 'Any'인 조건은 스크리너 파라미터에서 제외)
        filters = {k: v for k, v in config.FINVIZ_PRESETS.items() if v != 'Any'}
        
        overview.set_filter(filters_dict=filters)
        df = overview.screener_view()
        
        if df.empty:
            print("⚠️ 조건에 부합하는 종목이 없어 Fallback 풀을 사용합니다.")
            return fallback_tickers
            
        tickers = df['Ticker'].tolist()
        print(f"✅ Finviz 1차 스크리닝 통과: 총 {len(tickers)}개 티커 추출 완료.")
        return tickers[:50]  # 주도 섹터 필터링으로 많이 탈락할 수 있으므로 풀을 50개로 확대
        
    except Exception as e:
        print(f"⚠️ Finviz 스크리닝 통신 오류 발생({e}). Fallback 풀을 가동합니다.")
        return fallback_tickers


def verify_with_yahoo(tickers, target_sectors=None, config_preset=None):
    """
    추출된 티커를 대상으로 Yahoo Finance 정밀 재무제표 및 주도 섹터 부합 여부를 교차 검증합니다.
    """
    print(f"\n📊 [2단계-B: 심층 검증] Yahoo 상세 검증 및 주도 섹터 부합 필터링 중 (대상: {len(tickers)}개)...")
    if target_sectors:
        print(f"🎯 타겟 주도 섹터 필터: {', '.join(target_sectors)}")
        
    passed_tickers = []
    
    for t in tickers:
        try:
            info = get_cached_ticker_info(t)
            
            # 정보가 누락된 티커 제외
            if not info or 'shortName' not in info:
                continue
                
            # [섹터 정합성 검증] 야후 파이낸스 섹터명 정규화 및 타겟 포함 여부 판단
            yahoo_sector = info.get('sector', 'Unknown')
            normalized_sec = yahoo_sector
            
            # 야후 고유 명칭을 SPDR/일반 명칭으로 호환 매핑
            if yahoo_sector == 'Consumer Defensive':
                normalized_sec = 'Consumer Staples'
            elif yahoo_sector == 'Consumer Cyclical':
                normalized_sec = 'Consumer Discretionary'
            elif yahoo_sector == 'Financial Services':
                normalized_sec = 'Financials'
            elif yahoo_sector == 'Basic Materials':
                normalized_sec = 'Materials'
                
            if target_sectors:
                is_matching = False
                for t_sec in target_sectors:
                    # 서브스트링 검사 (예: 'Technology' in 'Technology (기술)')
                    if normalized_sec.lower() in t_sec.lower():
                        is_matching = True
                        break
                    # 반도체 테마 처리: 야후는 보통 'Technology' 섹터, 'Semiconductors' 산업군으로 분류함
                    if 'semiconductor' in t_sec.lower() and 'semiconductor' in info.get('industry', '').lower():
                        is_matching = True
                        break
                        
                if not is_matching:
                    # 주도 섹터와 불일치하는 종목은 탈락 (Drop)
                    continue
                    
            # 동적 필터 셋업 (preset이 있으면 우선 적용, 없으면 기본 config 적용)
            min_inst_own = config.MIN_INST_OWNERSHIP
            require_fcf = config.REQUIRE_FCF_POSITIVE
            max_debt = config.MAX_DEBT_RATIO
            
            if config_preset and 'filters' in config_preset:
                min_inst_own = config_preset['filters'].get('Institutional Ownership', min_inst_own)
                require_fcf = config_preset['filters'].get('REQUIRE_FCF_POSITIVE', require_fcf)
                max_debt = config_preset['filters'].get('MAX_DEBT_RATIO', max_debt)

            # 1. 기관 보유 지분율 검증 (heldPercentInstitutions)
            inst_own = info.get('heldPercentInstitutions', 0)
            if inst_own is None:
                inst_own = 0.0
                
            if inst_own < min_inst_own:
                continue
                
            # 2. 잉여현금흐름 (Free Cash Flow) 흑자 검증
            fcf = info.get('freeCashflow', 0)
            if fcf is None:
                fcf = 0
                
            if require_fcf and fcf <= 0:
                continue
                
            # 3. 부채비율 교차 검증 (debtToEquity)
            de_ratio = info.get('debtToEquity', 0)
            if de_ratio is not None and max_debt is not None:
                normalized_de = de_ratio / 100.0 if de_ratio > 10 else de_ratio
                if normalized_de > max_debt:
                    continue
                    
            # 4. 부가 정보 및 밸류에이션 지표 추출 (클로드 지적사항 완벽 반영)
            op_margin = info.get('operatingMargins', 0.0)
            
            pe_ratio = info.get('trailingPE', info.get('forwardPE', 0.0))
            if pe_ratio is None:
                pe_ratio = 0.0
                
            peg_ratio = info.get('pegRatio', 0.0)
            if peg_ratio is None:
                peg_ratio = 0.0
                
            ev_ebitda = info.get('enterpriseToEbitda', 0.0)
            if ev_ebitda is None:
                ev_ebitda = 0.0
                
            high_52w = info.get('fiftyTwoWeekHigh', 0.0)
            if high_52w is None:
                high_52w = 0.0
                
            low_52w = info.get('fiftyTwoWeekLow', 0.0)
            if low_52w is None:
                low_52w = 0.0
                
            beta_val = info.get('beta', 1.0)
            if beta_val is None:
                beta_val = 1.0
                
            # 표기용 섹터명 동적 생성 (내적 모순 해소)
            disp_sector = yahoo_sector
            if yahoo_sector != normalized_sec:
                disp_sector = f"{yahoo_sector} ({normalized_sec} 호환)"
            
            # 세부 테마(Sub-Sector) 매핑
            industry = info.get('industry', 'Unknown')
            sub_sector = 'General'
            sub_sector_desc = ''
            
            # 1. 완전 매칭 검사
            if industry in config.INDUSTRY_TO_SUB_SECTOR:
                sub_sector = config.INDUSTRY_TO_SUB_SECTOR[industry]
            else:
                # 2. 부분 문자열 매칭 검사 (대소문자 무시)
                for ind_key, sub_val in config.INDUSTRY_TO_SUB_SECTOR.items():
                    if ind_key.lower() in industry.lower():
                        sub_sector = sub_val
                        break
            
            # 세부 테마 설명 추출
            if normalized_sec in config.SUB_SECTOR_CONFIG:
                sec_cfg = config.SUB_SECTOR_CONFIG[normalized_sec]
                if sub_sector in sec_cfg:
                    sub_sector_desc = sec_cfg[sub_sector].get('desc', '')
            
            passed_tickers.append({
                'ticker': t,
                'name': info.get('shortName', t),
                'inst_own': inst_own * 100,
                'fcf': fcf,
                'op_margin': (op_margin or 0.0) * 100,
                'sector': yahoo_sector,
                'disp_sector': disp_sector,
                'sub_sector': sub_sector,
                'sub_sector_desc': sub_sector_desc,
                'pe': pe_ratio,
                'peg': peg_ratio,
                'ev_ebitda': ev_ebitda,
                'high_52w': high_52w,
                'low_52w': low_52w,
                'beta': beta_val
            })
            
        except Exception as e:
            continue
            
    print(f"🎯 최종 섹터/재무 검증 통과: 총 {len(passed_tickers)}개 알짜 주도주 선별 완료.")
    return passed_tickers


def get_fundamental_candidates(target_sectors=None):
    """
    외부에서 호출하는 모듈의 통합 엔트리 포인트.
    """
    raw_tickers = run_finviz_screener(target_sectors)
    # 2차 검증 단계로 주도 섹터 목록을 전달하여 직렬 필터링 적용
    verified_candidates = verify_with_yahoo(raw_tickers, target_sectors=target_sectors)
    
    print("\n==================================================")
    print(f"🌲 타겟 섹터 및 재무 통과 핵심 후보군 목록")
    print("==================================================")
    for c in verified_candidates:
        print(f"[{c['ticker']}] {c['name']} | 기관지분: {c['inst_own']:.1f}% | FCF: ${c['fcf']:,} | 섹터: {c['sector']}")
        
    return verified_candidates


def get_track_c_candidates(target_sectors=None):
    """
    [Track C] 기관 스마트 머니 와치리스트 기반 필터링
    """
    preset = config.TRACK_C_PRESETS
    raw_tickers = preset.get('watchlist', [])
    print(f"\n🏛️ [Track C 가동] 대형 기관 우량주 와치리스트 스캔 ({len(raw_tickers)}개)")
    
    verified = verify_with_yahoo(raw_tickers, target_sectors=target_sectors, config_preset=preset)
    
    for c in verified:
        c['track'] = 'Track C'
        # 기술적 엔진에서 사용할 볼륨 멀티플라이어 오버라이드
        c['vol_multiplier'] = preset['filters'].get('vol_multiplier', config.VOL_MULTIPLIER)
        
    return verified[:preset.get('max_candidates', 5)]


def get_track_d_candidates(target_sectors=None):
    """
    [Track D] 실리콘밸리 VC 와치리스트 기반 필터링
    """
    preset = config.TRACK_D_PRESETS
    raw_tickers = preset.get('watchlist', [])
    print(f"\n🚀 [Track D 가동] 거물 VC 주도 테크주 와치리스트 스캔 ({len(raw_tickers)}개)")
    
    verified = verify_with_yahoo(raw_tickers, target_sectors=target_sectors, config_preset=preset)
    
    for c in verified:
        c['track'] = 'Track D'
        c['vol_multiplier'] = preset['filters'].get('vol_multiplier_boost', config.VOL_MULTIPLIER)
        
    return verified[:preset.get('max_candidates', 3)]


# 모듈 단독 테스트용 코드
if __name__ == "__main__":
    # 임의의 주도 섹터 주입 테스트
    get_fundamental_candidates(['Technology (기술)', 'Semiconductors (반도체 테마)'])
