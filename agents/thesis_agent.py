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
from core.thesis_evaluator import evaluate_thesis_change

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
        # 시작 트리거 채널 구독 (Orchestrator 기동 시 작동 유도)
        await self.subscribe("system/trigger")
        self._monitor_task = asyncio.create_task(self._periodic_monitor_loop())
        self.logger.info("Thesis 감시 백그라운드 루프 기동 완료.")

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
            # 시스템 기동 시 즉시 1회 검사 수행
            self.logger.info("System trigger received. Running instant thesis check...")
            await self.run_monitoring_cycle()

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
        """모든 감시 종목에 대해 뉴스를 긁어오고 Thesis 변화를 분석하여 알림 전송"""
        if not self.bot_token or not self.chat_id:
            self.logger.warning("텔레그램 토큰 또는 챗 ID가 설정되지 않아 알림을 보낼 수 없습니다.")
            return

        # 1. DB에서 모든 감시 대상 로드
        thesis_maps = await asyncio.to_thread(get_all_thesis_maps)
        if not thesis_maps:
            self.logger.info("감시 대상 종목이 없습니다.")
            return

        self.logger.info(f"총 {len(thesis_maps)}개 종목에 대한 Thesis 변화 스캔 시작.")

        for item in thesis_maps:
            ticker = item["ticker"]
            
            # 2. 최근 뉴스 24시간치 가져오기
            news_list = await asyncio.to_thread(fetch_recent_news, ticker, hours=24)
            if not news_list:
                self.logger.info(f"[{ticker}] 최근 24시간 내 새 뉴스가 없습니다.")
                continue

            # 3. LLM 분석
            self.logger.info(f"[{ticker}] 신규 뉴스 {len(news_list)}건 분석 요청...")
            eval_res = await asyncio.to_thread(evaluate_thesis_change, ticker, item, news_list)
            
            # 4. 중요한 변화가 있을 때만 텔레그램 발송
            if eval_res.get("has_change"):
                self.logger.info(f"🚨 [{ticker}] 유의미한 Thesis 변화 감지! 텔레그램 알림 발송 중...")
                alert_text = f"🚨 *[{ticker}] Thesis 변화 감시 브리핑*\n\n{eval_res['evaluation_text']}"
                
                await self.send_alert(alert_text)
                
                # 중복 알림 방지를 위해 수집된 뉴스들을 처리된 것으로 마크
                for news in news_list:
                    mark_news_as_processed(news["uuid"])
            else:
                self.logger.info(f"✅ [{ticker}] 기존 Thesis 내 범위 혹은 잡뉴스로 판정되어 패스합니다.")

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
