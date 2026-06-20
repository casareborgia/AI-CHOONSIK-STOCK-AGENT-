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
from core.thesis_evaluator import generate_criticism
from core.toss_client import toss_client
from core.technical_engine import evaluate_signal

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
        # 기술 시그널 분석 완료 채널 및 디베이트 요청 채널 구독
        await self.subscribe("technical/signals_analyzed")
        await self.subscribe("thesis/debate_request")

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
        elif channel == "thesis/debate_request":
            await self.handle_debate_request(message)

    async def handle_debate_request(self, message: dict):
        """ThesisAgent의 1차 투자 Thesis 평가 결과와 기술 지표를 검증하여 비판(Criticism) 피드백 회신"""
        ticker = message.get("ticker")
        payload_tag = message.get("payload_tag")
        turn = message.get("turn", 0)

        if turn != 1:
            return

        self.logger.info(f"📥 [{ticker}] ThesisAgent로부터 디베이트 요청 수신 (Turn 1). 비판적 검증 수행 중...")

        try:
            # 1. Shared Memory에서 1차 평가 결과 조회
            payload_data = await self.broker.get_payload(payload_tag)
            if not payload_data:
                self.logger.error(f"공유 메모리에서 페이로드를 찾을 수 없습니다: {payload_tag}")
                return

            initial_eval = payload_data["initial_evaluation"]

            # 2. 실시간 기술 지표 조회 (토스 API 캔들 조회 -> evaluate_signal 연산)
            self.logger.info(f"📊 [{ticker}] 디베이트 검증용 실시간 기술 지표 수집 및 분석 시작...")
            tech_info = {}
            try:
                # 150봉 로드
                df = await asyncio.to_thread(toss_client.get_candles, ticker, interval="1d", count=150)
                eval_res = await asyncio.to_thread(evaluate_signal, df, {"ticker": ticker})
                if eval_res:
                    tech_info = eval_res
            except Exception as toss_err:
                self.logger.warning(f"⚠️ [{ticker}] 디베이트용 실시간 기술 지표 획득 실패 ({toss_err}). 기본 피드백 적용.")
                tech_info = {
                    "regime": "mixed",
                    "signal": "관망 (지표 수집 누락)",
                    "vol_ratio": 1.0,
                    "stoch_summary": "N/A"
                }

            # ── [ChatDev Conditional Pass] 1차 평가와 기술 지표 간 모순 사전 검증 ──
            import config as _cfg
            enable_early_pass = getattr(_cfg, "ENABLE_DEBATE_EARLY_PASS", True)
            if enable_early_pass and self._is_debate_concordant(initial_eval, tech_info):
                self.logger.info(f"✅ [{ticker}] [Conditional Pass] 1차 평가와 기술 지표가 일치합니다. 디베이트 조기 종료.")
                payload_data["criticism"] = "특이 모순 발견되지 않음 (정량 사전 검증 패스)"
                await self.broker.put_payload(f"debate:{ticker}", payload_data)
                debate_response = {"ticker": ticker, "payload_tag": payload_tag, "turn": 2}
                await self.publish("critic/debate_response", debate_response)
                return

            # 3. 비판 보고서 작성 (LLM 호출) - 모순이 감지된 경우에만 도달
            self.logger.info(f"⚠️ [{ticker}] 1차 평가와 기술 지표 간 모순 감지. LLM 비판 보고서 생성 중...")
            criticism_text = await asyncio.to_thread(
                generate_criticism, ticker, initial_eval, tech_info
            )

            # 4. 결과 업데이트 및 Shared Memory 갱신
            payload_data["criticism"] = criticism_text
            await self.broker.put_payload(f"debate:{ticker}", payload_data)

            # 5. 디베이트 응답 전송 (Turn 2)
            debate_response = {
                "ticker": ticker,
                "payload_tag": payload_tag,
                "turn": 2
            }
            self.logger.info(f"📤 [{ticker}] 디베이트 비판 피드백 작성 완료. 응답 발행 중 (Turn 2)...")
            await self.publish("critic/debate_response", debate_response)

        except Exception as e:
            self.logger.error(f"디베이트 검증 처리 중 오류 발생: {e}", exc_info=True)

    def _is_debate_concordant(self, initial_eval: str, tech_info: dict) -> bool:
        """
        [ChatDev Dual-Agent Shortcut]
        1차 평가와 기술 지표가 동일한 방향(Bullish/Bearish/Neutral)을 가리키는지 판단합니다.
        모순이 없으면 True를 반환하여 LLM 비판 생성을 생략합니다.
        """
        eval_lower = (initial_eval or "").lower()
        signal = (tech_info.get("signal", "") or "").lower()
        regime = (tech_info.get("regime", "") or "").lower()

        # Bullish 평가 + 정배열/수렴 + 매수 시그널 → 모순 없음
        if "bullish" in eval_lower and regime in ("aligned", "converged") and "매수" in signal:
            return True
        # Neutral 평가 + 관망 시그널 → 모순 없음
        if "neutral" in eval_lower and "관망" in signal:
            return True
        # Bearish 평가 + 역배열/하락 시그널 → 모순 없음
        if "bearish" in eval_lower and regime == "reversed":
            return True
        # 변화 없음(중립) 평가 + 혼조 시그널 → 모순 없음
        if "중요한 변화 없음" in eval_lower and regime in ("mixed", "converged"):
            return True
        # 그 외 → 모순 가능성 있으므로 LLM 비판 수행
        return False

