import asyncio
import logging
import sys

from message_bus.broker import MessageBroker
from agents.telegram_agent import TelegramAgent
from agents.thesis_agent import ThesisAgent
from agents.db_agent import DBAgent

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] (%(name)s) %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger("ChatbotDaemon")

async def main():
    logger.info("================================================================================")
    logger.info("🤖 [춘식 MK3] 텔레그램 대화형 챗봇 데몬 구동 (상시 대기 모드)")
    logger.info("================================================================================")

    broker = MessageBroker()
    
    # 챗봇 응답과 Thesis 관련 에이전트만 구동
    telegram_agent = TelegramAgent("TelegramAgent", broker)
    thesis_agent = ThesisAgent("ThesisAgent", broker)
    db_agent = DBAgent("DBAgent", broker)
    
    agents = [telegram_agent, thesis_agent, db_agent]
    
    logger.info("Starting Chatbot Agent, Thesis Agent, and DB Agent...")
    for agent in agents:
        await agent.start()
        
    logger.info("Chatbot is now ONLINE. Polling for telegram messages...")
    
    # 프로세스가 꺼지지 않고 상시 폴링을 유지하도록 무한 대기
    try:
        while True:
            await asyncio.sleep(3600)
    except asyncio.CancelledError:
        logger.info("Chatbot Daemon cancellation requested.")
    finally:
        logger.info("Shutting down chatbot agents...")
        await asyncio.gather(*(agent.stop() for agent in agents))
        logger.info("Chatbot Daemon offline.")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("\nTerminated by user.")
