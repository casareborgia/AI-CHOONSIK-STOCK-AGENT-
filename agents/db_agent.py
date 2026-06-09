import sys
import os
import asyncio
from typing import Any, List, Dict

# 프로젝트 루트 경로를 sys.path에 추가
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agents.base import BaseAgent
from learning.db import save_report_to_db, save_validation_results, save_decision_traces, save_run

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
                save_report_to_db, item, raw_report, revised_report, entry_grade, getattr(self, "_run_id", None)
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
            from datetime import datetime
            import time as _time

            ai_verified_results = message.get("ai_verified_results", [])
            signals = message.get("signals", [])
            leading_names = message.get("leading_names", [])

            # [P0] 실행 세션 ID 생성 (리포트/트레이스를 한 run으로 묶는 식별자)
            started_at = datetime.now()
            self._run_id = started_at.strftime("%Y%m%d_%H%M%S")
            _t0 = _time.time()

            self.logger.info(f"Storing {len(ai_verified_results)} analysis records to database... (run_id={self._run_id})")

            try:
                # 모든 항목에 대해 병렬 DB 적재 시도
                await asyncio.gather(*(self.save_result(item) for item in ai_verified_results))

                # [P0] 의사결정 추적 로그 적재: 기술분석을 통과한 '전체' 후보(생존+탈락)의 근거 보존
                verified_tickers = {it.get("ticker") for it in ai_verified_results}
                trace_source = signals if signals else ai_verified_results
                await asyncio.to_thread(
                    save_decision_traces, self._run_id, trace_source, verified_tickers
                )

                # [P0] 실행 세션 퍼널 요약 적재
                await asyncio.to_thread(
                    save_run,
                    self._run_id,
                    started_at.isoformat(timespec="seconds"),
                    datetime.now().isoformat(timespec="seconds"),
                    "auto",
                    leading_names,
                    len(trace_source),
                    len(ai_verified_results),
                    "success",
                    round(_time.time() - _t0, 2),
                )

                # 저장 완료 알림 발행 (기존 메시지를 다음 ReporterAgent가 이어서 쓸 수 있도록 전달)
                await self.publish("db/saved", message)

            except Exception as e:
                self.logger.error(f"Error in DBAgent process: {e}", exc_info=True)
