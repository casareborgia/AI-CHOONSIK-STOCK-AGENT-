import asyncio
import sys
import os
import httpx
import logging
from typing import Any

# 프로젝트 루트 경로 추가
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config
from agents.base import BaseAgent
from learning.db import get_all_thesis_maps
from plugins.news_monitor import fetch_recent_news, mark_news_as_processed
from core.thesis_evaluator import evaluate_thesis_change, reconcile_thesis_debate

class ThesisAgent(BaseAgent):
    """
    보유 관심 종목의 뉴스/공시 변화를 백그라운드에서 주기적으로 감시하는 에이전트.
    """
    def __init__(self, name: str, broker: Any):
        super().__init__(name, broker)
        # 기본 감시 주기: 4시간 (14400초). 테스트 편의를 위해 환경설정에서 읽어올 수 있도록 처리
        self.check_interval = getattr(config, "THESIS_CHECK_INTERVAL", 14400)
        self.bot_token = config.TELEGRAM_BOT_TOKEN
        self.chat_id = config.TELEGRAM_CHAT_ID
        self.client = httpx.AsyncClient(timeout=30.0)
        self._monitor_task = None
        self.logger = logging.getLogger("ThesisAgent")

    async def start(self):
        await super().start()
        # 시작 트리거 채널 및 디베이트 응답 채널 구독
        await self.subscribe("system/trigger")
        await self.subscribe("critic/debate_response")
        self._monitor_task = asyncio.create_task(self._periodic_monitor_loop())
        self.logger.info("Thesis 감시 백그라운드 루프 기동 완료 (디베이트 구독 포함).")

    async def stop(self):
        await super().stop()
        if self._monitor_task:
            self._monitor_task.cancel()
            try:
                await self._monitor_task
            except asyncio.CancelledError:
                pass
        await self.client.aclose()
        self.logger.info("Thesis 감시 백그라운드 루프 종료 완료.")

    async def handle_message(self, channel: str, message: Any):
        if channel == "system/trigger":
            self.logger.info("System trigger received. Running instant thesis check...")
            await self.run_monitoring_cycle()
        elif channel == "critic/debate_response":
            await self.handle_debate_response(message)

    async def _periodic_monitor_loop(self):
        """주기적인 모니터링 수행 루프"""
        await asyncio.sleep(60) # 부팅 직후 바로 스캔하지 않고 기동 완료 1분 대기
        while self.is_running:
            try:
                self.logger.info("Starting periodic thesis monitoring cycle...")
                await self.run_monitoring_cycle()
            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.error(f"주기적 Thesis 감시 수행 중 예외 발생: {e}")
                
            await asyncio.sleep(self.check_interval)

    async def run_monitoring_cycle(self):
        """모든 감시 종목에 대해 뉴스를 긁어오고 1차 분석을 수행하여 Critic에게 검증(토론) 요청"""
        if not self.bot_token or not self.chat_id:
            self.logger.warning("텔레그램 토큰 또는 챗 ID가 설정되지 않아 알림을 보낼 수 없습니다.")
            return

        thesis_maps = await asyncio.to_thread(get_all_thesis_maps)
        if not thesis_maps:
            self.logger.info("감시 대상 종목이 없습니다.")
            return

        self.logger.info(f"총 {len(thesis_maps)}개 종목에 대한 Thesis 변화 스캔 시작.")

        for item in thesis_maps:
            ticker = item["ticker"]
            
            # 최근 뉴스 24시간치 가져오기
            news_list = await asyncio.to_thread(fetch_recent_news, ticker, hours=24)
            if not news_list:
                self.logger.info(f"[{ticker}] 최근 24시간 내 새 뉴스가 없습니다.")
                continue

            self.logger.info(f"[{ticker}] 신규 뉴스 {len(news_list)}건 1차 분석 요청...")
            eval_res = await asyncio.to_thread(evaluate_thesis_change, ticker, item, news_list)
            
            if eval_res.get("has_change"):
                self.logger.info(f"🚨 [{ticker}] 1차 변화 감지! CriticAgent에게 디베이트(검증) 요청 중...")
                
                # 대용량 데이터를 Shared Memory에 페이로드 참조 형식으로 저장
                payload_data = {
                    "ticker": ticker,
                    "thesis_map": item,
                    "news_list": news_list,
                    "initial_evaluation": eval_res["evaluation_text"],
                    "criticism": None,
                    "final_reconciliation": None
                }
                
                payload_tag = await self.broker.put_payload(f"debate:{ticker}", payload_data)
                
                # CriticAgent에게 순차적 디베이트 메시지 전송 (Turn 1)
                debate_msg = {
                    "ticker": ticker,
                    "payload_tag": payload_tag,
                    "turn": 1
                }
                await self.publish("thesis/debate_request", debate_msg)
            else:
                self.logger.info(f"✅ [{ticker}] 기존 Thesis 내 범위 혹은 잡뉴스로 판정되어 패스합니다.")

    async def handle_debate_response(self, message: dict):
        """CriticAgent의 피드백을 수신하여 최종 합의(Reconciliation) 수행 및 텔레그램 발송"""
        ticker = message.get("ticker")
        payload_tag = message.get("payload_tag")
        turn = message.get("turn", 0)

        if turn != 2:
            return

        self.logger.info(f"📥 [{ticker}] CriticAgent로부터 반론 피드백 수신 (Turn 2). 최종 합의안 도출 중...")

        try:
            # Shared Memory에서 데이터 복구
            payload_data = await self.broker.get_payload(payload_tag)
            if not payload_data:
                self.logger.error(f"공유 메모리에서 페이로드를 찾을 수 없습니다: {payload_tag}")
                return

            initial_eval = payload_data["initial_evaluation"]
            criticism = payload_data.get("criticism", "특이 모순 발견되지 않음")

            # ── [ChatDev Conditional Pass] CriticAgent 조기 패스 감지 ──
            is_neutral_pass = "특이 모순 발견되지 않음" in criticism
            if is_neutral_pass:
                self.logger.info(f"✅ [{ticker}] [Conditional Pass] CriticAgent 조기 패스 확인. LLM 합의 과정 생략.")
                reconciled_text = initial_eval  # 1차 평가를 최종 결과로 사용
            else:
                # 최종 합의 연산 (LLM 호출) - 모순이 감지된 경우에만 실행
                self.logger.info(f"⚠️ [{ticker}] 모순 감지됨. LLM 합의 리포트 생성 중...")
                reconciled_text = await asyncio.to_thread(
                    reconcile_thesis_debate, ticker, initial_eval, criticism
                )

            # 결과 업데이트 및 공유 메모리 갱신
            payload_data["final_reconciliation"] = reconciled_text
            await self.broker.put_payload(f"debate:{ticker}", payload_data)

            self.logger.info(f"✅ [{ticker}] 최종 디베이트 합의 리포트 발행 성공. 텔레그램 발송 중...")
            alert_text = f"🚨 *[{ticker}] 최종 투자 Thesis 변화 분석 보고서*\n\n{reconciled_text}"
            await self.send_alert(alert_text)

            # 중복 방지를 위해 뉴스 처리 상태 마킹
            news_list = payload_data.get("news_list", [])
            await asyncio.to_thread(self._mark_news_processed, news_list)

        except Exception as e:
            self.logger.error(f"디베이트 합의 처리 중 오류 발생: {e}", exc_info=True)

    def _mark_news_processed(self, news_list):
        for news in news_list:
            mark_news_as_processed(news["uuid"])

    async def send_alert(self, text: str):
        """텔레그램 알림 발송"""
        url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"
        payload = {
            "chat_id": self.chat_id,
            "text": text,
            "parse_mode": "Markdown"
        }
        try:
            resp = await self.client.post(url, json=payload)
            if resp.status_code != 200:
                self.logger.error(f"감시 알림 발송 실패: {resp.text}")
        except Exception as e:
            self.logger.error(f"감시 알림 발송 예외: {e}")
