import asyncio
import sys
import os
import httpx
import logging
from typing import Any
import yfinance as yf

# 프로젝트 루트 디렉토리 추가
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config
from agents.base import BaseAgent
from learning.db import add_or_update_thesis, get_thesis_map, get_all_thesis_maps, delete_thesis_map
from core.thesis_evaluator import generate_initial_thesis_map, evaluate_thesis_change
from plugins.news_monitor import fetch_recent_news

class TelegramAgent(BaseAgent):
    """
    텔레그램 사용자 입력을 실시간으로 수신하고 처리하는 리스너 에이전트.
    """
    def __init__(self, name: str, broker: Any):
        super().__init__(name, broker)
        self.bot_token = config.TELEGRAM_BOT_TOKEN
        self.chat_id = config.TELEGRAM_CHAT_ID
        self.offset = 0
        self.client = httpx.AsyncClient(timeout=30.0)
        self._tg_poll_task = None
        self.logger = logging.getLogger("TelegramAgent")

    async def start(self):
        await super().start()
        if not self.bot_token or not self.chat_id:
            self.logger.warning("텔레그램 설정이 비어있어 수신 리스너를 실행하지 않습니다.")
            return
        self._tg_poll_task = asyncio.create_task(self._tg_polling_loop())
        self.logger.info("텔레그램 수신 리스너 폴링 루프 가동 완료.")

    async def stop(self):
        await super().stop()
        if self._tg_poll_task:
            self._tg_poll_task.cancel()
            try:
                await self._tg_poll_task
            except asyncio.CancelledError:
                pass
        await self.client.aclose()
        self.logger.info("텔레그램 수신 리스너 폴링 루프 종료 완료.")

    async def handle_message(self, channel: str, message: Any):
        pass

    async def send_response(self, text: str):
        """답장 메시지 전송"""
        url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"
        payload = {
            "chat_id": self.chat_id,
            "text": text,
            "parse_mode": "Markdown"
        }
        try:
            resp = await self.client.post(url, json=payload)
            if resp.status_code != 200:
                self.logger.error(f"텔레그램 응답 발송 실패: {resp.text}")
        except Exception as e:
            self.logger.error(f"텔레그램 응답 발송 예외: {e}")

    async def _tg_polling_loop(self):
        """텔레그램 updates를 획득하기 위한 폴링 루프"""
        while self.is_running:
            try:
                url = f"https://api.telegram.org/bot{self.bot_token}/getUpdates"
                params = {"offset": self.offset, "timeout": 20}
                resp = await self.client.get(url, params=params)
                
                if resp.status_code == 200:
                    data = resp.json()
                    if data.get("ok"):
                        updates = data.get("result", [])
                        for update in updates:
                            self.offset = update.get("update_id", 0) + 1
                            message = update.get("message")
                            if not message:
                                continue
                            
                            sender_chat_id = message.get("chat", {}).get("id")
                            if str(sender_chat_id) != str(self.chat_id):
                                continue
                                
                            text = message.get("text", "").strip()
                            if text:
                                await self.process_command(text)
                else:
                    self.logger.warning(f"getUpdates API 오류 (상태 코드: {resp.status_code})")
                    
            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.error(f"텔레그램 폴링 에러: {e}")
                
            await asyncio.sleep(2)

    async def process_command(self, text: str):
        """명령어 파싱 및 처리"""
        self.logger.info(f"수신된 명령어: {text}")
        
        if text.startswith("/help"):
            help_msg = """💡 *아이춘식 Thesis 감시 명령어 안내*

📌 *종목 추가 및 자동 생성*
`/add [티커]`
👉 예: `/add AAPL`
(yfinance 정보 기반으로 Gemma 4가 Thesis Map 초안을 작성하여 자동 등록합니다.)

📌 *Thesis Map 수동 저장 및 편집*
`/save [티커] | [투자 thesis] | [핵심 지표] | [촉매] | [리스크] | [kill condition] | [잡뉴스 기준] | [실적 체크포인트] | [valuation] | [한줄결론]`
👉 파이프(|) 문자로 각 항목을 나누어 입력합니다.
👉 예: `/save AAPL | 애플 해자 강함 | 아이폰 판매량 | AI 폰 출시 | 반독점 소송 | FCF 마이너스 | 소셜 소문 | 서비스 매출 | P/E 30배 이하 | 장기 홀딩`

📌 *감시 목록 확인*
`/list` ➡️ 현재 감시 중인 모든 종목을 조회합니다.

📌 *감시 종목 삭제*
`/del [티커]` ➡️ 해당 종목을 감시 목록에서 삭제합니다.

📌 *즉시 뉴스/Thesis 감시*
`/check [티커]` ➡️ 최근 24시간 내 뉴스를 즉시 긁어와 Thesis 변화 평가를 실행합니다."""
            await self.send_response(help_msg)
            
        elif text.startswith("/add"):
            parts = text.split()
            if len(parts) < 2:
                await self.send_response("⚠️ 티커를 입력해주세요. 예: `/add AAPL`")
                return
                
            ticker = parts[1].upper()
            import re
            if not re.match(r"^[A-Z]{1,5}$", ticker):
                await self.send_response("⚠️ 유효하지 않은 티커 형식입니다. 영문 1~5자리로 입력해주세요. (예: AAPL)")
                return
            await self.send_response(f"🤖 [{ticker}] 기업 정보를 분석하여 최초 Thesis Map 초안을 빌드하고 있습니다. 잠시만 기다려주세요...")
            
            try:
                def get_yf_info(t):
                    tick = yf.Ticker(t)
                    return tick.info, tick.info.get("longName", t)
                
                info, company_name = await asyncio.to_thread(get_yf_info, ticker)
                thesis_data = await asyncio.to_thread(generate_initial_thesis_map, ticker, company_name, info)
                success = add_or_update_thesis(ticker, company_name, thesis_data)
                
                if success:
                    res_text = f"✨ *[{ticker} / {company_name}] Thesis Map 빌드 및 감시 등록 완료!*\n\n"
                    res_text += f"▪️ *투자 thesis*: {thesis_data['investment_thesis']}\n"
                    res_text += f"▪️ *핵심 지표*: {thesis_data['key_indicators']}\n"
                    res_text += f"▪️ *주요 촉매*: {thesis_data['catalysts']}\n"
                    res_text += f"▪️ *주요 리스크*: {thesis_data['risks']}\n"
                    res_text += f"▪️ *kill condition*: {thesis_data['kill_condition']}\n"
                    res_text += f"▪️ *무시해도 되는 잡뉴스*: {thesis_data['noise_rules']}\n"
                    res_text += f"▪️ *실적 체크포인트*: {thesis_data['earnings_checkpoints']}\n"
                    res_text += f"▪️ *valuation 기준*: {thesis_data['valuation_criteria']}\n"
                    res_text += f"▪️ *한 줄 결론*: {thesis_data['one_line_conclusion']}"
                    await self.send_response(res_text)
                else:
                    await self.send_response(f"❌ [{ticker}] DB 저장에 실패했습니다.")
            except Exception as e:
                self.logger.error(f"add 명령어 수행 에러: {e}")
                await self.send_response(f"❌ [{ticker}] Thesis Map 생성 중 에러 발생: {e}")
                
        elif text.startswith("/save"):
            body = text[5:].strip()
            parts = [p.strip() for p in body.split("|")]
            if len(parts) < 10:
                await self.send_response("⚠️ 형식에 맞춰 10개 파트를 파이프(|)로 구분하여 입력해주세요.\n형식: `/save [티커] | [투자 thesis] | [핵심 지표] | [촉매] | [리스크] | [kill condition] | [잡뉴스 기준] | [실적 체크포인트] | [valuation] | [한줄결론]`")
                return
                
            ticker = parts[0].upper()
            import re
            if not re.match(r"^[A-Z]{1,5}$", ticker):
                await self.send_response("⚠️ 유효하지 않은 티커 형식입니다. 첫 번째 항목은 영문 1~5자리 티커여야 합니다. (예: AAPL)")
                return
            thesis_data = {
                "investment_thesis": parts[1],
                "key_indicators": parts[2],
                "catalysts": parts[3],
                "risks": parts[4],
                "kill_condition": parts[5],
                "noise_rules": parts[6],
                "earnings_checkpoints": parts[7],
                "valuation_criteria": parts[8],
                "one_line_conclusion": parts[9]
            }
            
            try:
                def get_company_name(t):
                    return yf.Ticker(t).info.get("longName", t)
                company_name = await asyncio.to_thread(get_company_name, ticker)
                
                success = add_or_update_thesis(ticker, company_name, thesis_data)
                if success:
                    await self.send_response(f"💾 *[{ticker}] 수동 Thesis Map을 성공적으로 저장 및 갱신하였습니다.*")
                else:
                    await self.send_response(f"❌ [{ticker}] 수동 Thesis Map 저장 실패.")
            except Exception as e:
                await self.send_response(f"❌ [{ticker}] Thesis 저장 중 에러 발생: {e}")
                
        elif text.startswith("/list"):
            try:
                maps = get_all_thesis_maps()
                if not maps:
                    await self.send_response("📭 현재 감시 중인 종목이 없습니다. `/add [티커]`로 등록해 보세요.")
                    return
                    
                msg = "📋 *현재 밀착 감시 중인 보유 종목 목록*\n\n"
                for idx, item in enumerate(maps, 1):
                    msg += f"{idx}. *{item['ticker']}* ({item['name']})\n"
                    msg += f"   └ *결론*: {item['one_line_conclusion']}\n\n"
                await self.send_response(msg)
            except Exception as e:
                await self.send_response(f"❌ 목록 조회 중 오류 발생: {e}")
                
        elif text.startswith("/del"):
            parts = text.split()
            if len(parts) < 2:
                await self.send_response("⚠️ 삭제할 티커를 입력해주세요. 예: `/del AAPL`")
                return
            ticker = parts[1].upper()
            import re
            if not re.match(r"^[A-Z]{1,5}$", ticker):
                await self.send_response("⚠️ 유효하지 않은 티커 형식입니다. 영문 1~5자리로 입력해주세요. (예: AAPL)")
                return
            try:
                success = delete_thesis_map(ticker)
                if success:
                    await self.send_response(f"🗑️ *[{ticker}] 감시 목록에서 삭제되었습니다.*")
                else:
                    await self.send_response(f"⚠️ [{ticker}] 감시 목록에 등록되어 있지 않거나 삭제에 실패했습니다.")
            except Exception as e:
                await self.send_response(f"❌ 삭제 중 오류 발생: {e}")
                
        elif text.startswith("/check"):
            parts = text.split()
            if len(parts) < 2:
                await self.send_response("⚠️ 검사할 티커를 입력해주세요. 예: `/check AAPL`")
                return
            ticker = parts[1].upper()
            import re
            if not re.match(r"^[A-Z]{1,5}$", ticker):
                await self.send_response("⚠️ 유효하지 않은 티커 형식입니다. 영문 1~5자리로 입력해주세요. (예: AAPL)")
                return
            await self.send_response(f"🔍 [{ticker}]의 최근 뉴스/공시 및 기존 Thesis Map 비교 분석을 즉시 가동합니다...")
            
            try:
                thesis_map = get_thesis_map(ticker)
                if not thesis_map:
                    await self.send_response(f"⚠️ [{ticker}]는 감시 목록에 등록되어 있지 않습니다. `/add {ticker}`를 먼저 실행해주세요.")
                    return
                    
                news_list = fetch_recent_news(ticker, hours=24)
                if not news_list:
                    news_list = fetch_recent_news(ticker, hours=168)
                    if not news_list:
                        await self.send_response(f"📭 [{ticker}] 최근 7일 내에 수집된 새로운 뉴스가 없습니다.")
                        return
                    else:
                        await self.send_response(f"💡 최근 24시간 내 뉴스가 없어 최근 7일 내의 뉴스를 토대로 분석합니다. (수집 뉴스: {len(news_list)}개)")
                
                eval_res = await asyncio.to_thread(evaluate_thesis_change, ticker, thesis_map, news_list)
                
                if eval_res.get("has_change"):
                    await self.send_response(f"🚨 *[{ticker}] Thesis 변화 감시 브리핑*\n\n{eval_res['evaluation_text']}")
                else:
                    await self.send_response(f"✅ *[{ticker}] 분석 결과*: 기존 투자 Thesis에 영향을 미칠 만한 유의미한 변화가 발견되지 않았습니다.")
            except Exception as e:
                self.logger.error(f"check 명령어 수행 에러: {e}")
                await self.send_response(f"❌ [{ticker}] 검사 수행 중 에러 발생: {e}")
