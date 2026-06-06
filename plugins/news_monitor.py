import yfinance as yf
from datetime import datetime, timedelta
import logging

logger = logging.getLogger("NewsMonitor")

# 최근 처리된 뉴스 uuid를 임시 보관하는 인메모리 캐시 (중복 알림 방지)
_processed_news_uuids = set()

# Thesis 변동과 무관한 단순 노이즈성 뉴스 제목 키워드 (소문자 기준 매칭)
NOISE_KEYWORDS = [
    'dividend', 'ex-dividend', 'ex-date', 'share repurchase', 'buyback', 'webcast',
    'presents at', 'presenting at', 'conference participation', 'investor conference',
    'annual meeting', 'shareholder meeting', 'stock rating', 'price target',
    'stock option', 'insider transaction', 'form 4', 'filing', 'earnings call webcast'
]

def fetch_recent_news(ticker: str, hours: int = 24) -> list:
    """
    yfinance를 활용해 지정된 티커의 최근 뉴스들을 수집합니다.
    hours 범위 이내에 발행된 뉴스만 필터링하고 중복 뉴스는 제외합니다.
    """
    global _processed_news_uuids
    ticker = ticker.upper()
    try:
        yf_ticker = yf.Ticker(ticker)
        raw_news = yf_ticker.news
        if not raw_news:
            logger.info(f"[{ticker}] 최근 뉴스가 없습니다.")
            return []
        
        filtered_news = []
        now = datetime.now()
        threshold_time = now - timedelta(hours=hours)
        
        for item in raw_news:
            uuid = item.get("uuid")
            title = item.get("title")
            link = item.get("link")
            publisher = item.get("publisher")
            publish_time_epoch = item.get("providerPublishTime")
            
            if not uuid or not title:
                continue
                
            # 중복 체크
            if uuid in _processed_news_uuids:
                continue
                
            # 노이즈 키워드 1차 필터링
            title_lower = title.lower()
            if any(kw in title_lower for kw in NOISE_KEYWORDS):
                logger.info(f"[{ticker}] 노이즈 기사로 분류되어 사전 드롭 처리: '{title}'")
                continue
                
            # 발행 시간 필터링
            if publish_time_epoch:
                try:
                    publish_dt = datetime.fromtimestamp(publish_time_epoch)
                except Exception:
                    publish_dt = now # 파싱 에러 시 현재 시간으로 폴백
            else:
                publish_dt = now
                
            if publish_dt >= threshold_time:
                news_data = {
                    "uuid": uuid,
                    "title": title,
                    "link": link,
                    "publisher": publisher,
                    "publish_time": publish_dt.strftime("%Y-%m-%d %H:%M:%S"),
                    "epoch_time": publish_time_epoch
                }
                filtered_news.append(news_data)
                
        logger.info(f"[{ticker}] {hours}시간 내 신규 뉴스 {len(filtered_news)}개 수집 완료.")
        return filtered_news
        
    except Exception as e:
        logger.error(f"[{ticker}] 뉴스 수집 실패: {e}", exc_info=True)
        return []

def mark_news_as_processed(uuid: str):
    """뉴스가 성공적으로 알림 처리되었을 때 중복 방지 캐시에 등록합니다."""
    global _processed_news_uuids
    _processed_news_uuids.add(uuid)
