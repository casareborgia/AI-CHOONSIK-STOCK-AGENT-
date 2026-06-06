import sys
import os
import asyncio
from typing import Any, List, Dict

# 프로젝트 루트 경로를 sys.path에 추가
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config

from agents.base import BaseAgent
from core.technical_engine import analyze_technical_signals
from core.multi_timeframe import multi_timeframe_analysis

class TechnicalAgent(BaseAgent):
    """
    기술적 지표 및 멀티타임프레임을 분석하고 시그널을 보정하는 에이전트.
    """
    def __init__(self, name: str, broker: Any):
        super().__init__(name, broker)

    async def start(self):
        await super().start()
        # 후보 종목 스캔 완료 채널 구독
        await self.subscribe("screener/candidates_screened")

    async def fetch_mtf(self, item: Dict[str, Any]):
        """개별 종목의 멀티타임프레임 분석을 스레드 풀에서 비동기로 실행"""
        try:
            res = await asyncio.to_thread(multi_timeframe_analysis, item['ticker'])
            item['mtf_analysis'] = res
        except Exception as e:
            self.logger.error(f"Error fetching MTF for {item.get('ticker')}: {e}")
            item['mtf_analysis'] = {"entry_grade": "C", "error": str(e)}

    async def handle_message(self, channel: str, message: Any):
        if channel == "screener/candidates_screened":
            candidates = message.get("union_candidates", [])
            leading_names = message.get("leading_names", [])
            sub_theme_results = message.get("sub_theme_results", {})
            self.logger.info(f"Analyzing technical signals for {len(candidates)} candidates...")

            try:
                # 1. 3중 파동에너지 및 거래량 분석 (동기 함수)
                signals = await asyncio.to_thread(analyze_technical_signals, candidates)
                self.logger.info(f"Technical signals generated: {len(signals)} items")

                if not signals:
                    self.logger.warning("No technical signals detected. Stopping flow.")
                    await self.publish("system/done", {"status": "no_signals"})
                    return

                # 2. 멀티타임프레임 분석 비동기 병렬 실행
                self.logger.info("Executing multi-timeframe analysis...")
                await asyncio.gather(*(self.fetch_mtf(item) for item in signals))

                # 3. 정합성 조율 (재무 밸류에이션 리스크 검증 및 시그널 조정)
                self.logger.info("Adjusting signals based on valuation constraints...")
                for item in signals:
                    if "매수" in item.get('signal', '') or "폭발" in item.get('signal', ''):
                        pe_val = item.get('pe', 0.0)
                        peg_val = item.get('peg', 0.0)
                        disp_sec = item.get('disp_sector', item.get('sector', 'Unknown'))
                        
                        limits = config.RISK_LIMITS.get(config.USER_RISK_PROFILE, config.RISK_LIMITS['BALANCED'])
                        is_traditional = any(kw in disp_sec.lower() for kw in ['energy', 'industrial', 'material', 'consumer', 'utility'])
                        pe_limit = limits['traditional_pe_limit'] if is_traditional else limits['growth_pe_limit']
                        peg_limit = limits['peg_limit']
                        
                        # 리스크 프로파일 기반 초고평가 경고 보정
                        if pe_val > pe_limit or peg_val > peg_limit:
                            original_sig = item['signal']
                            item['signal'] = f"⚠️ 기술적 돌파이나 재무적 고평가 주의 ({original_sig})"
                            self.logger.info(f"[Signal Adjusted] {item['ticker']}: {original_sig} -> {item['signal']} (P/E: {pe_val}/{pe_limit}, PEG: {peg_val}/{peg_limit})")
                    
                    # 개별 종목 분석 최종 시그널 로깅
                    self.logger.info(f" -> [{item['ticker']}] Signal: {item['signal']} | Close: ${item['close']:.2f} | Vol Ratio: {item['vol_ratio']:.1f}x | Waves: {item['stoch_summary']}")

                # 결과 발행
                result_msg = {
                    "signals": signals,
                    "leading_names": leading_names,
                    "sub_theme_results": sub_theme_results
                }
                await self.publish("technical/signals_analyzed", result_msg)

            except Exception as e:
                self.logger.error(f"Error analyzing technical aspects: {e}", exc_info=True)
