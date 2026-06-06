import sys
import os
import asyncio
from typing import Any, List, Dict

# 프로젝트 루트 경로를 sys.path에 추가
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agents.base import BaseAgent
from core.ai_verify import run_ai_verification
from learning.validator import validate_report, auto_fix_report
from plugins.social_scanner import fetch_target_stocktwits_sentiment, fetch_target_reddit_sentiment

class CriticAgent(BaseAgent):
    """
    AI 생성 보고서의 정합성 검증 및 팩트 기반 자동 교정을 담당하는 에이전트.
    """
    def __init__(self, name: str, broker: Any):
        super().__init__(name, broker)

    async def get_social_detail(self, item: dict):
        """개별 종목의 정성적 소셜 감성 수집을 비동기 스레드로 수행"""
        ticker = item.get('ticker')
        if not ticker:
            return
        try:
            st_data = await asyncio.to_thread(fetch_target_stocktwits_sentiment, ticker)
            rd_data = await asyncio.to_thread(fetch_target_reddit_sentiment, ticker)
            
            item['social_sentiment'] = {
                'stocktwits_bullish_pct': st_data.get('bullish_pct', 50.0),
                'stocktwits_total': st_data.get('total_count', 0),
                'stocktwits_samples': st_data.get('messages', []),
                'reddit_posts': rd_data
            }
            self.logger.info(f"Social sentiment fetched for {ticker}: Bullish {st_data.get('bullish_pct', 50.0)}%")
        except Exception as e:
            self.logger.error(f"Failed to fetch social sentiment for {ticker}: {e}")
            item['social_sentiment'] = None

    async def start(self):
        await super().start()
        # 기술 시그널 분석 완료 채널 구독
        await self.subscribe("technical/signals_analyzed")

    async def handle_message(self, channel: str, message: Any):
        if channel == "technical/signals_analyzed":
            signals = message.get("signals", [])
            leading_names = message.get("leading_names", [])
            sub_theme_results = message.get("sub_theme_results", {})
            self.logger.info(f"Starting AI verification and factual review for {len(signals)} items...")

            try:
                # 0. 개별 종목별 상세 소셜 감성 비동기 병렬 수집
                self.logger.info("Starting targeted social media sentiment collection...")
                await asyncio.gather(*(self.get_social_detail(item) for item in signals))

                # 1. AI 검증 수행 (LLM 연동 동기 함수이므로 스레드 풀 할당)
                ai_verified_results = await asyncio.to_thread(
                    run_ai_verification, signals, leading_sectors=leading_names
                )
                self.logger.info(f"AI verification finished. Reviewing report consistency...")

                # 2. 정량 규칙 검증 및 자동 교정 루프
                for item in ai_verified_results:
                    report_data = {
                        "ticker": item.get("ticker", "UNKNOWN"),
                        "sector": item.get("disp_sector", item.get("sector", "Unknown")),
                        "pe_ratio": item.get("pe", 0.0),
                        "peg_ratio": item.get("peg", 0.0),
                        "inst_ownership": item.get("inst_own", 0.0),
                        "close_price": item.get("close", 0.0),
                        "high_52w": item.get("high_52w", 0.0),
                        "vol_ratio": item.get("vol_ratio", 1.0),
                        "signal_label": item.get("signal", "관망"),
                        "all_candidates": signals,
                        "report_text": item.get("ai_briefing", "")
                    }
                    
                    # 6대 정량 규칙 검증
                    violations = validate_report(report_data)
                    item["violations"] = violations
                    item["auto_fixed"] = False
                    item["revised_report"] = None
                    item["raw_report"] = item.get("ai_briefing", "")

                    if violations:
                        self.logger.warning(f"Fact-check violations found in {item['ticker']} report (Count: {len(violations)}). Initiating AI correction...")
                        for v in violations:
                            self.logger.warning(f" - [{v['rule_id']}] {v['rule_name']}: {v['description']}")
                        
                        # 자동 교정 (LLM 동기 함수)
                        revised_report = await asyncio.to_thread(
                            auto_fix_report, item["raw_report"], violations
                        )
                        
                        if revised_report and revised_report != item["raw_report"]:
                            item["ai_briefing"] = revised_report
                            item["revised_report"] = revised_report
                            item["auto_fixed"] = True
                            self.logger.info(f"Report for {item['ticker']} successfully self-corrected.")
                    else:
                        self.logger.info(f"Fact-check passed for {item['ticker']}.")

                # 결과 발행
                result_msg = {
                    "ai_verified_results": ai_verified_results,
                    "signals": signals,
                    "leading_names": leading_names,
                    "sub_theme_results": sub_theme_results
                }
                await self.publish("critic/reports_verified", result_msg)

            except Exception as e:
                self.logger.error(f"Error in CriticAgent processing: {e}", exc_info=True)
