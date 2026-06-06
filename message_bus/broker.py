import asyncio
import logging
from typing import Dict, List, Any

# 로깅 설정
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] (%(name)s) %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger("MessageBroker")

class MessageBroker:
    """
    asyncio.Queue를 활용한 인메모리 Pub/Sub 메시지 브로커.
    에이전트 간의 비동기 메시지 교환을 중재합니다.
    """
    def __init__(self):
        # channel_name -> list of asyncio.Queue
        self._subscribers: Dict[str, List[asyncio.Queue]] = {}
        self._lock = asyncio.Lock()

    async def subscribe(self, channel: str, queue: asyncio.Queue):
        """
        특정 채널에 구독용 Queue를 등록합니다.
        """
        async with self._lock:
            if channel not in self._subscribers:
                self._subscribers[channel] = []
            if queue not in self._subscribers[channel]:
                self._subscribers[channel].append(queue)
                logger.debug(f"Queue registered to channel: '{channel}'")

    async def unsubscribe(self, channel: str, queue: asyncio.Queue):
        """
        특정 채널에서 구독용 Queue를 제거합니다.
        """
        async with self._lock:
            if channel in self._subscribers:
                if queue in self._subscribers[channel]:
                    self._subscribers[channel].remove(queue)
                    logger.debug(f"Queue removed from channel: '{channel}'")
                if not self._subscribers[channel]:
                    del self._subscribers[channel]

    async def publish(self, channel: str, message: Any):
        """
        특정 채널을 구독하는 모든 Queue에 메시지를 전송(Broadcasting)합니다.
        메시지는 (channel, message) 형태로 전송됩니다.
        """
        async with self._lock:
            queues = self._subscribers.get(channel, [])
            if not queues:
                logger.debug(f"No subscribers for channel: '{channel}'")
                return

            logger.info(f"Publishing to '{channel}': {str(message)[:100]}...")
            for queue in queues:
                await queue.put((channel, message))
