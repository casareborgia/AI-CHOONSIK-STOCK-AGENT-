# ==============================================================================
# [AI Trading Agent] 향후 확장 플러그인 A: 매매일지 분석기 (Journal Analytics)
# ==============================================================================
# 사용자가 로컬에서 작성 중인 엑셀 매매일지(.xlsx)를 파싱하여, 과거 매매의 승률과
# 손익비를 산출하고 로컬 AI를 통해 심리적/기계적 매매 오류를 코칭합니다.

import sys
import os

# 부모 경로 추가
sys.path.append(os.path.dirname(os.path.dirname(__file__)))
import config

try:
    import pandas as pd
    import openpyxl
    PANDAS_AVAILABLE = True
except ImportError:
    PANDAS_AVAILABLE = False


class JournalAnalyzer:
    def __init__(self, excel_path="my_trading_journal.xlsx"):
        self.excel_path = excel_path
        
    def load_journal(self):
        """
        엑셀 매매일지를 로드하여 데이터프레임으로 변환합니다.
        (표준 컬럼 권장: 매수일, 티커, 매수가, 매도일, 매도가, 손익률, 매수사유)
        """
        if not PANDAS_AVAILABLE:
            print("⚠️ pandas 또는 openpyxl 라이브러리가 없어 매매일지 분석 모듈을 가동할 수 없습니다.")
            return None
            
        if not os.path.exists(self.excel_path):
            print(f"⚠️ 매매일지 파일을 찾을 수 없습니다: {self.excel_path}")
            # 테스트용 더미 데이터셋 반환
            return pd.DataFrame([
                {'buy_date': '2026-05-01', 'ticker': 'NVDA', 'profit_rate': 12.5, 'reason': '파동에너지 찐폭발 돌파'},
                {'buy_date': '2026-05-03', 'ticker': 'TSLA', 'profit_rate': -8.0, 'reason': '소파동 반등 뇌동매매 (5일선 이탈 후 손절 지연)'}
            ])
            
        try:
            df = pd.read_excel(self.excel_path)
            print(f"✅ 매매일지 로드 성공 (총 {len(df)}건 거래 내역)")
            return df
        except Exception as e:
            print(f"❌ 엑셀 파일 로드 중 오류 발생: {e}")
            return None

    def analyze_trading_habits(self):
        """
        Gemma 4를 활용하여 사용자의 매매 내역을 진단하고 피드백 리포트를 도출합니다.
        """
        print("\n🧠 [플러그인 A] AI 트레이딩 코치 진단 가동 중...")
        df = self.load_journal()
        if df is None or df.empty:
            return "매매일지 분석 데이터가 부족합니다."
            
        # 기초 통계 연산
        wins = df[df['profit_rate'] > 0]
        losses = df[df['profit_rate'] < 0]
        win_rate = len(wins) / len(df) * 100
        
        # 손실 거래 사유 문자열 취합
        loss_reasons = "\n".join(losses['reason'].astype(str).tolist())
        
        # 프롬프트 조립 (Gemma 4 호출용)
        prompt = f"""
당신은 냉철한 트레이딩 심리 분석가이자 리스크 관리 코치입니다.
아래의 매매 통계와 손실 사유를 분석하여 사용자의 매매 습관을 개선할 피드백을 작성하세요.

[매매 통계 요약]
- 전체 거래 횟수: {len(df)}회
- 승률: {win_rate:.1f}%

[주요 손실 거래 사유]
{loss_reasons}

[코칭 요구사항]
1. 원칙 매매 준수 여부 평가 (5일선 이탈 손절 등).
2. 가장 잦은 뇌동매매 또는 손실 원인 파악.
3. 기계적 손익비(Risk-Reward Ratio) 개선을 위한 1가지 핵심 행동 지침.
"""
        # 임포트 지연 보호
        from core.ai_verify import call_ollama
        feedback = call_ollama(prompt)
        
        print("==================================================")
        print("💡 [AI 매매일지 코칭 피드백 결과]")
        print("==================================================")
        print(feedback)
        return feedback


# 플러그인 단독 테스트용 코드
if __name__ == "__main__":
    analyzer = JournalAnalyzer()
    analyzer.analyze_trading_habits()
