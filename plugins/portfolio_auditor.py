# ==============================================================================
# [AI Trading Agent] 향후 확장 플러그인 B: 포트폴리오 감사관 (Portfolio Auditor)
# ==============================================================================
# 실제 증권사 API(한국투자증권, 키움증권 등)를 통해 현재 계좌 보유 종목을 실시간
# 조회하고, 파동에너지 코어 엔진과 교차 검증하여 리스크(쌍봉, 투매)를 경고합니다.

import sys
import os

# 부모 디렉토리 추가
sys.path.append(os.path.dirname(os.path.dirname(__file__)))
import config
from core.technical_engine import analyze_technical_signals


class BrokerageAdapter:
    """
    다양한 증권사 API를 규격화하여 동일한 구조로 계좌 잔고를 반환하는 추상 어댑터입니다.
    """
    def __init__(self, broker_name="KIS"):
        self.broker_name = broker_name
        
    def fetch_live_holdings(self):
        """
        증권사 서버와 통신하여 실시간 보유 종목 리스트를 반환합니다.
        (향후 실제 API 키 연동 로직 구현 영역)
        """
        print(f"\n🔐 [{self.broker_name} API 어댑터] 증권사 실계좌 연동 잔고 조회 중...")
        
        # 실제 연결 전 테스트를 위한 하드코딩된 모의 잔고 반환
        return [
            {'ticker': 'TSLA', 'qty': 50, 'avg_price': 175.0, 'name': 'Tesla Inc.'},
            {'ticker': 'NVDA', 'qty': 30, 'avg_price': 110.0, 'name': 'NVIDIA Corp.'}
        ]


def audit_portfolio_safety():
    """
    내 계좌의 보유 종목을 로드하고, 차트 상태를 정밀 감사하여 위험 시그널을 출력합니다.
    """
    print("\n🛡️ [플러그인 B] 실계좌 포트폴리오 적정성 및 리스크 감사 가동 중...")
    
    # 1. 계좌 보유 종목 로드
    adapter = BrokerageAdapter()
    holdings = adapter.fetch_live_holdings()
    
    if not holdings:
        print("보유 중인 주식 잔고가 없습니다.")
        return
        
    # 2. 분석용 입력 데이터 포맷팅 (기술적 분석 모듈 호환)
    candidates_input = []
    for h in holdings:
        candidates_input.append({
            'ticker': h['ticker'],
            'name': h['name'],
            'qty': h['qty'],
            'avg_price': h['avg_price'],
            'sector': 'Portfolio Holding'
        })
        
    # 3. 코어 엔진 호출 (보유 종목에 대한 실시간 파동 시그널 스캔)
    audited_results = analyze_technical_signals(candidates_input)
    
    print("\n==================================================")
    print("🚨 [보유 계좌 리스크 정밀 감사 결과]")
    print("==================================================")
    
    risk_found = False
    for r in audited_results:
        ticker = r['ticker']
        sig = r.get('signal', '')
        
        # 위험 신호(쌍봉, 투매폭발, 데드크로스) 필터링
        if "주의" in sig or "하락" in sig or "관망" in sig:
            risk_found = True
            print(f"⚠️ [비중 축소 권장] {ticker} ({r['name']})")
            print(f"   - 현재 상태: {sig} (종가: ${r.get('close',0):.2f})")
            print(f"   - 감사관 의견: 파동에너지 약세 및 주요 지지선 이탈 리스크가 감지되었습니다. 리밸런싱을 검토하십시오.")
            print("-" * 50)
            
    if not risk_found:
        print("✅ 현재 보유하신 포트폴리오의 모든 종목이 견고한 상승 파동을 유지하고 있습니다.")
        
    return audited_results


# 플러그인 단독 테스트용 코드
if __name__ == "__main__":
    audit_portfolio_safety()
