import asyncio
import logging
import time
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

    [ChatDev Memory Management] TTL 기반 공유 메모리 자동 만료 기능을 제공하여,
    파이프라인 완료 후 누적된 임시 페이로드가 메모리를 점유하지 않도록 합니다.
    """
    def __init__(self):
        # channel_name -> list of asyncio.Queue
        self._subscribers: Dict[str, List[asyncio.Queue]] = {}
        self._lock = asyncio.Lock()
        self._shared_memory: Dict[str, Any] = {}
        self._memory_lock = asyncio.Lock()
        self._memory_timestamps: Dict[str, float] = {}  # 페이로드별 적재 시각
        self._memory_ttl: float = 1800.0  # 기본 TTL: 30분

    async def cleanup_stale_payloads(self, max_age: float = None):
        """TTL이 만료된 공유 메모리 항목을 정리합니다.
        max_age=0 이면 모든 항목을 즉시 정리합니다."""
        ttl = max_age if max_age is not None else self._memory_ttl
        async with self._memory_lock:
            now = time.time()
            stale_keys = [
                key for key, ts in self._memory_timestamps.items()
                if (now - ts) >= ttl
            ]
            for key in stale_keys:
                self._shared_memory.pop(key, None)
                self._memory_timestamps.pop(key, None)
            if stale_keys:
                logger.info(f"[Memory Diet] 만료된 공유 메모리 {len(stale_keys)}건 정리 완료.")

    async def put_payload(self, key: str, data: Any) -> str:
        """대용량 데이터를 공유 메모리에 저장하고 참조 식별자(태그)를 반환합니다."""
        async with self._memory_lock:
            tag = f"#payload:{key}"
            self._shared_memory[tag] = data
            self._memory_timestamps[tag] = time.time()
            return tag

    async def get_payload(self, tag: str) -> Any:
        """참조 식별자(태그)를 사용해 공유 메모리에서 데이터를 조회합니다."""
        async with self._memory_lock:
            return self._shared_memory.get(tag)

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
