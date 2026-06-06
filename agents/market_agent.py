import sys
import os
import asyncio
from typing import Any

# 프로젝트 루트 경로를 sys.path에 추가
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agents.base import BaseAgent
from core.sector_monitor import get_leading_sectors, get_leading_sub_themes

class MarketAgent(BaseAgent):
    """
    주도 섹터 및 세부 테마를 탐색하는 에이전트.
    """
    def __init__(self, name: str, broker: Any):
        super().__init__(name, broker)

    async def start(self):
        await super().start()
        # 시작 트리거 채널 구독
        await self.subscribe("system/trigger")

    async def handle_message(self, channel: str, message: Any):
        if channel == "system/trigger":
            self.logger.info("Received system trigger. Starting market sector analysis...")
            
            try:
                # 1. 주도 섹터 탐색 (동기 I/O 함수이므로 스레드 풀에서 실행)
                leading_names, leading_tickers = await asyncio.to_thread(get_leading_sectors)
                self.logger.info(f"Leading sectors identified: {leading_names}")
                
                # 2. 주도 섹터 하위 테마 분석
                sub_theme_results = await asyncio.to_thread(get_leading_sub_themes, leading_names)
                self.logger.info(f"Sub-theme analysis completed for sectors: {leading_names}")
                
                # 3. 분석 결과 발행
                result = {
                    "leading_names": leading_names,
                    "leading_tickers": leading_tickers,
                    "sub_theme_results": sub_theme_results
                }
                await self.publish("market/sectors_identified", result)
                
            except Exception as e:
                self.logger.error(f"Failed to analyze market sectors: {e}", exc_info=True)
