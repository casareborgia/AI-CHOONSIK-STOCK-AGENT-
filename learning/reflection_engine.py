# ==============================================================================
# [AI Trading Agent] 지연 성찰 엔진 (learning/reflection_engine.py)
# ==============================================================================
# 과거에 생성된 보고서 중 성과 평가가 누락된 건들에 대해 yfinance로 사후 주가를 
# 추적하고, LLM을 통해 성과 복기(Deferred Reflection)를 작성하여 DB에 적재합니다.

import sqlite3
import yfinance as yf
from datetime import datetime, timedelta
import asyncio
import logging

from learning.db import get_connection
from core.ai_verify import call_ollama

logger = logging.getLogger("ReflectionEngine")

class ReflectionEngine:
    def __init__(self):
        pass

    def get_pending_reports(self):
        """성과 평가가 누락되었거나 pending 상태인 보고서 목록을 가져옵니다."""
        conn = get_connection()
        cursor = conn.cursor()
        try:
            # 5/10/20 영업일 추적을 위해 DB 내 outcomes 매칭이 없거나 pending 상태인 최신 30일 이내 보고서 조회
            cursor.execute("""
                SELECT r.id, r.date, r.ticker, r.close_price, r.revised_text, r.report_text
                FROM reports r
                LEFT JOIN outcomes o ON r.id = o.report_id
                WHERE o.id IS NULL OR o.outcome = 'pending'
                ORDER BY r.date DESC
                LIMIT 2
            """)
            rows = cursor.fetchall()
            return rows
        except Exception as e:
            logger.error(f"Failed to query pending reports: {e}")
            return []
        finally:
            conn.close()

    async def process_single_reflection(self, r_id, r_date_str, ticker, entry_price, revised_text, report_text):
        """개별 종목의 성찰을 처리하는 단일 비동기 태스크"""
        logger.info(f"Processing outcome reflection for {ticker} (Report ID: {r_id}, Date: {r_date_str})")
        try:
            # 1. yfinance를 통한 사후 주가 정보 획득 (스레드 풀 할당)
            hist = await asyncio.to_thread(self._fetch_history, ticker, r_date_str)
            hist_spy = await asyncio.to_thread(self._fetch_history, "SPY", r_date_str)
            
            if hist is None or len(hist) < 2:
                logger.warning(f" -> Insufficient trading days for {ticker} since {r_date_str}. Skipping.")
                return

            # 5영업일 경과 시점의 종가 획득
            target_idx = min(5, len(hist) - 1)
            check_date = hist.index[target_idx].strftime('%Y-%m-%d')
            check_price = float(hist['Close'].iloc[target_idx])
            
            return_pct = round(((check_price - entry_price) / entry_price) * 100, 2)
            
            # SPY 벤치마크 수익률 연산
            spy_return_pct = 0.0
            if hist_spy is not None and len(hist_spy) > target_idx:
                spy_entry = float(hist_spy['Close'].iloc[0])
                spy_check = float(hist_spy['Close'].iloc[target_idx])
                spy_return_pct = round(((spy_check - spy_entry) / spy_entry) * 100, 2)
                
            alpha_return_pct = round(return_pct - spy_return_pct, 2)
            
            # 초과수익률(Alpha) 기반의 성과 등급 정의 (지수 대비 2%p 이상 아웃퍼폼 시 WIN)
            if alpha_return_pct >= 2.0:
                outcome_label = "win"
            elif alpha_return_pct <= -2.0:
                outcome_label = "loss"
            else:
                outcome_label = "hold"

            # 2. LLM 호출하여 자가 복기 성찰(Reflection) 생성
            analysis_text = revised_text if revised_text else report_text
            prompt = f"""[미국 주식 투자 자가학습 복기 성찰 지침]
당신은 과거의 투자 판단을 냉정하게 사후 분석하여 교훈을 이끌어내는 리스크 관리 및 성찰 AI 에이전트입니다.

[과거 분석 정보]
- 추천 일자: {r_date_str}
- 대상 종목: {ticker}
- 진입 종가: ${entry_price:.2f}
- 당시 작성된 분석 내용 일부:
{analysis_text[:600]}

[실제 시장 결과 (5영업일 경과)]
- 평가 기준일: {check_date}
- 평가 시점 종가: ${check_price:.2f}
- 실제 달성 수익률: {return_pct:+.2f}%
- 벤치마크 지수(SPY) 수익률: {spy_return_pct:+.2f}%
- 지수 대비 초과수익률 (Alpha): {alpha_return_pct:+.2f}%p (최종 결과 분류: {outcome_label.upper()})

[요구사항]
1. 위 '실제 시장 결과'와 '당시 분석 내용'을 대조하여, 나의 기술적/기본적 예측 중 무엇이 들어맞았거나 빗나갔는지 팩트 기반으로 냉정하게 짚어내십시오. 특히 단순히 종목이 올랐는지가 아니라 지수(SPY) 상승 대비 초과수익(Alpha)을 냈는지에 입각하여 판단하십시오.
2. 향후 동일 종목 및 섹터를 분석할 때 반복하지 말아야 할 실수나 주의점(Actionable Lesson)을 2문장 내외로 명확하고 짧게 요약해 기술하십시오.

한국어로 차분하고 전문적인 애널리스트 톤으로 작성하십시오.
"""
            logger.info(f" -> Invoking LLM for reflecting on {ticker}...")
            # 듀얼 LLM: 성찰은 고도의 추론이 필요하므로 heavy 모델 호출
            reflection_text = await asyncio.to_thread(call_ollama, prompt, model_type="heavy")
            
            # 3. DB Outcomes 및 Learned Rules 저장 (스레드 풀 할당)
            await asyncio.to_thread(
                self.save_reflection, r_id, ticker, entry_price, check_date, check_price, return_pct, spy_return_pct, alpha_return_pct, outcome_label, reflection_text
            )
            logger.info(f" -> Successfully reflected on {ticker}. Alpha: {alpha_return_pct:+.2f}%p | Outcome: {outcome_label}")

        except Exception as e:
            logger.error(f"Error processing reflection for {ticker}: {e}", exc_info=True)

    async def run_reflection_batch(self):
        """성과가 나지 않은 종목들에 대해 사후 성과 매칭 및 성찰문 생성을 병렬로 비동기 배치 실행합니다."""
        logger.info("🔍 Scanning for pending report outcomes to perform reflection...")
        pending = self.get_pending_reports()
        if not pending:
            logger.info("✨ No pending reports found for reflection.")
            return

        # 병렬 비동기 태스크 목록 생성
        tasks = [
            self.process_single_reflection(r_id, r_date_str, ticker, entry_price, revised_text, report_text)
            for r_id, r_date_str, ticker, entry_price, revised_text, report_text in pending
        ]
        
        # gather를 활용해 한 번에 동시 실행
        await asyncio.gather(*tasks)

    def _fetch_history(self, ticker, start_date_str):
        try:
            # 시작일 기준 14일 정도 버퍼를 두어 주가 가져옴
            start_date = datetime.strptime(start_date_str, "%Y-%m-%d")
            end_date = start_date + timedelta(days=20)
            ticker_obj = yf.Ticker(ticker)
            hist = ticker_obj.history(start=start_date.strftime("%Y-%m-%d"), end=end_date.strftime("%Y-%m-%d"))
            return hist
        except Exception as e:
            logger.error(f"yfinance fetch failed for {ticker}: {e}")
            return None

    def save_reflection(self, report_id, ticker, entry_price, check_date, check_price, return_pct, benchmark_return_pct, alpha_return_pct, outcome, reflection):
        conn = get_connection()
        cursor = conn.cursor()
        try:
            # 1. outcomes 테이블 적재 (또는 갱신)
            cursor.execute("""
                INSERT OR REPLACE INTO outcomes (
                    report_id, ticker, entry_price, check_date, check_price, days_elapsed, return_pct, outcome, benchmark_return_pct, alpha_return_pct
                ) VALUES (?, ?, ?, ?, ?, 5, ?, ?, ?, ?)
            """, (report_id, ticker, entry_price, check_date, check_price, return_pct, outcome, benchmark_return_pct, alpha_return_pct))

            # 2. learned_rules 테이블에 피드백 누적
            rule_id = f"REF_{ticker}_{check_date.replace('-', '')}"
            rule_text = f"[{ticker} 성과 복기 ({check_date})] 결과: {outcome.upper()}({return_pct}%, Alpha: {alpha_return_pct}%p). 성찰 교훈: {reflection}"
            
            cursor.execute("""
                INSERT INTO learned_rules (rule_id, rule_text, source, trigger_count, is_active)
                VALUES (?, ?, 'outcome_analysis', 1, 1)
                ON CONFLICT(rule_id) DO UPDATE SET 
                    rule_text = rule_text || '\n' || excluded.rule_text,
                    trigger_count = trigger_count + 1
            """, (rule_id, rule_text))
            
            conn.commit()
        except Exception as e:
            logger.error(f"Failed to save reflection to database for {ticker}: {e}")
            conn.rollback()
        finally:
            conn.close()


if __name__ == "__main__":
    # 독립 테스트 코드
    logging.basicConfig(level=logging.INFO)
    engine = ReflectionEngine()
    
    # 강제 모의 테스트를 위해 비동기 루프 기동
    async def test():
        await engine.run_reflection_batch()
        
    asyncio.run(test())
