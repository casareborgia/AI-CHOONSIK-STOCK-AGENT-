import asyncio
import logging
import sys
import time
from datetime import datetime, timedelta

from message_bus.broker import MessageBroker
from agents.market_agent import MarketAgent
from agents.screener_agent import ScreenerAgent
from agents.technical_agent import TechnicalAgent
from agents.critic_agent import CriticAgent
from agents.db_agent import DBAgent
from agents.reporter_agent import ReporterAgent
# from agents.telegram_agent import TelegramAgent
from agents.thesis_agent import ThesisAgent
from learning.reflection_engine import ReflectionEngine
from learning.outcome_tracker import track_outcomes

# 루트 로거 설정
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] (%(name)s) %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger("Orchestrator")

async def main():
    start_time = time.time()
    logger.info("================================================================================")
    logger.info("🚀 [춘식 MK3] 멀티 에이전트 기반 투자 의사결정 보조 시스템 기동")
    logger.info("================================================================================")

    # 0. 지연 성찰(Deferred Reflection) 배치 구동 (사후 성과 추적)
    skip_reflection = "--skip-reflection" in sys.argv
    if not skip_reflection:
        # [P0] 성과 추적 배선 복구: 5/10/20영업일 정밀 성과를 먼저 집계한 뒤 성찰을 수행한다.
        # (track_outcomes는 그동안 정의만 되어 있고 호출되지 않아 10/20일 성과가 누락되어 있었음)
        logger.info("Tracking outcomes for past reports (5/10/20 business days)...")
        try:
            await asyncio.to_thread(track_outcomes)
        except Exception as e:
            logger.error(f"track_outcomes failed (continuing): {e}")

        logger.info("Starting Deferred Reflection Engine...")
        reflection_engine = ReflectionEngine()
        await reflection_engine.run_reflection_batch()
    else:
        logger.info("⏭️ Deferred Reflection Engine skipped by user flag.")

    # [P1-1] 규칙 자가진화(Weekly Rule Evolution) 구동
    skip_evolution = "--skip-evolution" in sys.argv
    force_evolution = "--force-evolution" in sys.argv

    if not skip_evolution:
        from learning.db import get_system_meta, set_system_meta
        from learning.rule_evolution import run_weekly_evolution

        # 마지막 진화 일자 확인
        last_run_str = get_system_meta("last_evolution_run")
        should_run = False

        if force_evolution:
            logger.info("⚡ Force-evolution flag detected. Running rule evolution...")
            should_run = True
        elif not last_run_str:
            logger.info("No record of prior rule evolution. Initiating first run...")
            should_run = True
        else:
            try:
                last_run_dt = datetime.strptime(last_run_str, "%Y-%m-%d")
                if datetime.now() - last_run_dt >= timedelta(days=7):
                    should_run = True
            except Exception as e:
                logger.warning(f"Failed to parse last_evolution_run ({last_run_str}): {e}")
                should_run = True

        if should_run:
            logger.info("Running Weekly Rule Evolution...")
            try:
                await asyncio.to_thread(run_weekly_evolution)
                # 성공 시 마지막 진화 일자 갱신
                set_system_meta("last_evolution_run", datetime.now().strftime("%Y-%m-%d"))
            except Exception as e:
                logger.error(f"Rule evolution failed: {e}")
        else:
            logger.info("⏭️ Weekly Rule Evolution skipped (run interval < 7 days).")

    # 1. 메시지 브로커 생성
    broker = MessageBroker()

    # 2. 에이전트 인스턴스화
    market_agent = MarketAgent("MarketAgent", broker)
    screener_agent = ScreenerAgent("ScreenerAgent", broker)
    technical_agent = TechnicalAgent("TechnicalAgent", broker)
    critic_agent = CriticAgent("CriticAgent", broker)
    db_agent = DBAgent("DBAgent", broker)
    reporter_agent = ReporterAgent("ReporterAgent", broker)
    # telegram_agent = TelegramAgent("TelegramAgent", broker)
    thesis_agent = ThesisAgent("ThesisAgent", broker)
 
    agents = [
        market_agent,
        screener_agent,
        technical_agent,
        critic_agent,
        db_agent,
        reporter_agent,
        # telegram_agent,
        thesis_agent
    ]

    # 3. 모든 에이전트 백그라운드 구동 시작
    logger.info("Starting all agents in the background...")
    for agent in agents:
        await agent.start()

    # 4. 오케스트레이터 완료 감시용 큐 등록
    done_queue = asyncio.Queue()
    await broker.subscribe("system/done", done_queue)
    logger.info("Orchestrator subscribed to 'system/done' for monitoring execution completion.")

    # 5. 파이프라인 시작 트리거 신호 발행
    logger.info("Publishing 'system/trigger' to initiate execution flow.")
    await broker.publish("system/trigger", {"action": "start"})

    # 6. 완료 신호 대기
    try:
        channel, result = await done_queue.get()
        logger.info(f"Received completion signal on '{channel}': {result}")
        done_queue.task_done()
    except asyncio.CancelledError:
        logger.warning("Orchestrator execution was cancelled.")
    finally:
        # 7. 구독 해제 및 모든 에이전트 정상 정지
        logger.info("Shutting down all active agents...")
        await broker.unsubscribe("system/done", done_queue)
        
        # 에이전트들을 안전하게 정지
        await asyncio.gather(*(agent.stop() for agent in agents))

    elapsed = time.time() - start_time
    logger.info("================================================================================")
    if result.get("status") == "success":
        logger.info(f"✨ [실행 완료] 멀티 에이전트 파이프라인 구동 성공 (총 소요시간: {elapsed:.1f}초)")
        logger.info(f"📂 저장된 종합 리포트 경로: {result.get('report_path')}")
    else:
        logger.error(f"❌ [실행 실패] 파이프라인 수행 실패 (소요시간: {elapsed:.1f}초)")
        logger.error(f"⚠️ 에러 내역: {result.get('error') or result.get('status')}")
    logger.info("================================================================================")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("\nProcess terminated by user (KeyboardInterrupt).")
