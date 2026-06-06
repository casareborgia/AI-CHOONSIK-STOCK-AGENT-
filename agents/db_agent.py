import sys
import os
import asyncio
from typing import Any, List, Dict

# 프로젝트 루트 경로를 sys.path에 추가
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agents.base import BaseAgent
from learning.db import save_report_to_db, save_validation_results

class DBAgent(BaseAgent):
    """
    분석 데이터 및 AI 보고서를 데이터베이스에 적재하는 에이전트.
    """
    def __init__(self, name: str, broker: Any):
        super().__init__(name, broker)

    async def start(self):
        await super().start()
        # AI 검증 및 교정 완료 채널 구독
        await self.subscribe("critic/reports_verified")

    async def save_result(self, item: Dict[str, Any]):
        """단일 추천 종목 분석 결과의 DB 적재 수행"""
        try:
            # 1. MTF 등급 추출
            mtf_info = item.get("mtf_analysis")
            if isinstance(mtf_info, dict):
                entry_grade = mtf_info.get("entry_grade", "C")
            else:
                entry_grade = "C"

            raw_report = item.get("raw_report", "")
            revised_report = item.get("revised_report")
            violations = item.get("violations", [])
            auto_fixed = item.get("auto_fixed", False)

            # 2. SQLite DB 저장 실행 (동기 I/O이므로 스레드 활용)
            report_id = await asyncio.to_thread(
                save_report_to_db, item, raw_report, revised_report, entry_grade
            )
            
            # 3. 정량 팩트 검증 위반 내역 저장
            if violations:
                await asyncio.to_thread(
                    save_validation_results, report_id, violations, auto_fixed
                )
                
            self.logger.info(f"Successfully saved DB record for {item.get('ticker')} (Report ID: {report_id})")
            
        except Exception as e:
            self.logger.error(f"Failed to save database entry for {item.get('ticker')}: {e}", exc_info=True)

    async def handle_message(self, channel: str, message: Any):
        if channel == "critic/reports_verified":
            ai_verified_results = message.get("ai_verified_results", [])
            self.logger.info(f"Storing {len(ai_verified_results)} analysis records to database...")

            try:
                # 모든 항목에 대해 병렬 DB 적재 시도
                await asyncio.gather(*(self.save_result(item) for item in ai_verified_results))
                
                # 저장 완료 알림 발행 (기존 메시지를 다음 ReporterAgent가 이어서 쓸 수 있도록 전달)
                await self.publish("db/saved", message)

            except Exception as e:
                self.logger.error(f"Error in DBAgent process: {e}", exc_info=True)
