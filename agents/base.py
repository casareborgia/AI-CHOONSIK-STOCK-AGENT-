import asyncio
import logging
from abc import ABC, abstractmethod
from typing import Any, Set
from message_bus.broker import MessageBroker

class BaseAgent(ABC):
    """
    모든 에이전트의 기반이 되는 추상 클래스.
    메시지 큐 수신 루프 및 브로커 구독/발행 연동 기능을 제공합니다.
    """
    def __init__(self, name: str, broker: MessageBroker):
        self.name = name
        self.broker = broker
        self.queue = asyncio.Queue()
        self.is_running = False
        self.subscriptions: Set[str] = set()
        self._main_task = None
        self.logger = logging.getLogger(self.name)

    async def subscribe(self, channel: str):
        """
        특정 채널을 구독합니다.
        """
        await self.broker.subscribe(channel, self.queue)
        self.subscriptions.add(channel)
        self.logger.info(f"Subscribed to channel: '{channel}'")

    async def unsubscribe(self, channel: str):
        """
        특정 채널 구독을 해제합니다.
        """
        await self.broker.unsubscribe(channel, self.queue)
        if channel in self.subscriptions:
            self.subscriptions.remove(channel)
        self.logger.info(f"Unsubscribed from channel: '{channel}'")

    async def publish(self, channel: str, message: Any):
        """
        특정 채널로 메시지를 발행합니다.
        """
        await self.broker.publish(channel, message)

    async def start(self):
        """
        에이전트 백그라운드 태스크를 시작합니다.
        """
        if self.is_running:
            return
        self.is_running = True
        self._main_task = asyncio.create_task(self._loop())
        self.logger.info(f"Agent '{self.name}' started.")

    async def stop(self):
        """
        에이전트 백그라운드 태스크를 정지하고 구독을 모두 해제합니다.
        """
        if not self.is_running:
            return
        self.is_running = False
        
        # 모든 채널 구독 해제
        channels_to_unsubscribe = list(self.subscriptions)
        for channel in channels_to_unsubscribe:
            await self.unsubscribe(channel)

        if self._main_task:
            self._main_task.cancel()
            try:
                await self._main_task
            except asyncio.CancelledError:
                pass
        self.logger.info(f"Agent '{self.name}' stopped.")

    async def _loop(self):
        """
        메시지 수신 백그라운드 루프.
        """
        while self.is_running:
            try:
                # 큐에서 메시지 대기
                channel, message = await self.queue.get()
                
                # 메시지 처리 수행 (최대 3회 자동 재시도 및 Exponential Backoff 적용)
                retries = 3
                backoff = 2.0
                for attempt in range(1, retries + 1):
                    try:
                        await self.handle_message(channel, message)
                        break  # 성공 시 재시도 루프 탈출
                    except asyncio.CancelledError:
                        raise
                    except Exception as e:
                        if attempt < retries:
                            self.logger.warning(
                                f"[{attempt}/{retries}] Error handling message on '{channel}'. "
                                f"Retrying in {backoff}s... Error: {e}"
                            )
                            await asyncio.sleep(backoff)
                            backoff *= 2.0
                        else:
                            self.logger.error(
                                f"Failed to handle message on channel '{channel}' after {retries} attempts. Error: {e}", 
                                exc_info=True
                            )
                self.queue.task_done()
                    
            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.error(f"Unexpected error in agent loop: {e}", exc_info=True)
                await asyncio.sleep(1) # 오류 시 잠시 대기 후 루프 재개

    @abstractmethod
    async def handle_message(self, channel: str, message: Any):
        """
        수신된 메시지를 처리하는 추상 메서드.
        하위 클래스에서 반드시 구현해야 합니다.
        """
        pass
