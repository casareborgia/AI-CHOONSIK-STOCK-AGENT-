import sys
import os
import asyncio
from typing import Any

# 프로젝트 루트 경로를 sys.path에 추가
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agents.base import BaseAgent
import reporter

class ReporterAgent(BaseAgent):
    """
    최종 보고서 파일 생성 및 텔레그램 실시간 알림 발송을 담당하는 에이전트.
    """
    def __init__(self, name: str, broker: Any):
        super().__init__(name, broker)

    async def start(self):
        await super().start()
        # DB 저장 완료 채널 구독
        await self.subscribe("db/saved")

    async def handle_message(self, channel: str, message: Any):
        if channel == "db/saved":
            ai_verified_results = message.get("ai_verified_results", [])
            leading_names = message.get("leading_names", [])
            sub_theme_results = message.get("sub_theme_results", {})
            self.logger.info("Starting reporting process (Markdown generation & Telegram dispatch)...")

            try:
                # 1. 종합 마크다운 리포트 생성 (동기 I/O이므로 스레드 풀에서 실행)
                report_path = await asyncio.to_thread(
                    reporter.generate_markdown_report, leading_names, sub_theme_results, ai_verified_results
                )
                self.logger.info(f"Markdown report generated successfully at: {report_path}")

                # 2. 텔레그램 메시지 포맷 구성 (동기 함수)
                tele_msg = await asyncio.to_thread(
                    reporter.format_telegram_message, leading_names, sub_theme_results, ai_verified_results
                )

                # 3. 텔레그램 전송 (비동기 함수)
                self.logger.info("Sending notification message via Telegram...")
                await reporter.send_telegram_message(tele_msg)
                self.logger.info("Telegram notification sent successfully.")

                # 4. 전체 파이프라인 가동 완료 신호 발행
                await self.publish("system/done", {
                    "status": "success",
                    "report_path": report_path
                })

            except Exception as e:
                self.logger.error(f"Error in ReporterAgent process: {e}", exc_info=True)
                await self.publish("system/done", {
                    "status": "failed",
                    "error": str(e)
                })
