import sys
import os
import asyncio
from typing import Any, List, Dict

# 프로젝트 루트 경로를 sys.path에 추가
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agents.base import BaseAgent
from core.fundamental_filter import get_fundamental_candidates, get_track_c_candidates, get_track_d_candidates
from plugins.social_scanner import get_social_candidates

class ScreenerAgent(BaseAgent):
    """
    4대 트랙(A, B, C, D)을 병렬 가동하여 투자 후보군을 스캔 및 병합하는 에이전트.
    """
    def __init__(self, name: str, broker: Any):
        super().__init__(name, broker)

    async def start(self):
        await super().start()
        # 주도 섹터 분석 완료 채널 구독
        await self.subscribe("market/sectors_identified")

    async def execute_track_a(self, leading_names: List[str]) -> List[Dict[str, Any]]:
        """[Track A] 주도 섹터 기반 펀더멘털 우량주 스윙 트랙"""
        self.logger.info("[Track A] 펀더멘털 우량주 파이프라인 가동...")
        cands = await asyncio.to_thread(get_fundamental_candidates, target_sectors=leading_names)
        for c in cands:
            c['track'] = 'Track A'
        return cands

    async def execute_track_b(self) -> List[Dict[str, Any]]:
        """[Track B] SNS 모멘텀 기반 급등주 트랙"""
        self.logger.info("[Track B] SNS 모멘텀 급등주 비동기 스캐너 가동...")
        cands = await get_social_candidates()
        for c in cands:
            c['track'] = 'Track B'
        return cands

    async def execute_track_c(self, leading_names: List[str]) -> List[Dict[str, Any]]:
        """[Track C] 대형 기관 스마트 머니 펀더멘털 트랙"""
        self.logger.info("[Track C] 기관 우량주 파이프라인 가동...")
        cands = await asyncio.to_thread(get_track_c_candidates, target_sectors=leading_names)
        for c in cands:
            c['track'] = 'Track C'
        return cands

    async def execute_track_d(self, leading_names: List[str]) -> List[Dict[str, Any]]:
        """[Track D] 실리콘밸리 VC 고성장 테크 트랙"""
        self.logger.info("[Track D] 거물 VC 주도 테크주 파이프라인 가동...")
        cands = await asyncio.to_thread(get_track_d_candidates, target_sectors=leading_names)
        for c in cands:
            c['track'] = 'Track D'
        return cands

    async def handle_message(self, channel: str, message: Any):
        if channel == "market/sectors_identified":
            leading_names = message.get("leading_names", [])
            sub_theme_results = message.get("sub_theme_results", {})
            self.logger.info(f"Starting parallel screening for sectors: {leading_names}")

            try:
                # 4대 트랙 비동기 병렬 실행
                results = await asyncio.gather(
                    self.execute_track_a(leading_names),
                    self.execute_track_b(),
                    self.execute_track_c(leading_names),
                    self.execute_track_d(leading_names)
                )
                
                track_a_cands, track_b_cands, track_c_cands, track_d_cands = results
                
                # 티커 중복 제거 및 병합
                all_cands_dict = {}
                for c in (track_a_cands + track_b_cands + track_c_cands + track_d_cands):
                    if c['ticker'] not in all_cands_dict:
                        all_cands_dict[c['ticker']] = c
                
                union_candidates = list(all_cands_dict.values())
                tickers_list = [c['ticker'] for c in union_candidates]
                self.logger.info(f"Screening complete. Total {len(union_candidates)} candidates: {tickers_list}")
                self.logger.info(f"Breakdown -> Track A: {len(track_a_cands)}, Track B: {len(track_b_cands)}, Track C: {len(track_c_cands)}, Track D: {len(track_d_cands)}")

                if not union_candidates:
                    self.logger.warning("No candidates found in any tracks. Stopping flow.")
                    await self.publish("system/done", {"status": "no_candidates"})
                    return

                # 스캔 결과 발행 (이전 데이터 캐리오버)
                result_msg = {
                    "union_candidates": union_candidates,
                    "leading_names": leading_names,
                    "sub_theme_results": sub_theme_results
                }
                await self.publish("screener/candidates_screened", result_msg)

            except Exception as e:
                self.logger.error(f"Error during parallel screening: {e}", exc_info=True)
