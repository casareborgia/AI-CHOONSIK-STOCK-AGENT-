import os
import json
import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv
import config

load_dotenv()

_raw_key = os.getenv("FMP_API_KEY", "")
# API 키가 제대로 된 영문/숫자 조합이 아니거나 더미 텍스트일 경우 빈 문자열로 처리
FMP_API_KEY = _raw_key if len(_raw_key) >= 30 and "여기에" not in _raw_key else ""

BASE_URL = "https://financialmodelingprep.com/api/v4"

def fetch_13f_fmp(cik):
    """FMP API를 이용한 13F 호출"""
    try:
        url = f"{BASE_URL}/institutional-ownership/portfolio"
        params = {"cik": cik, "limit": 15, "apikey": FMP_API_KEY}
        response = requests.get(url, params=params)
        if response.status_code == 200:
            data = response.json()
            tickers = []
            for item in data:
                symbol = item.get("symbol")
                if symbol and symbol not in tickers:
                    tickers.append(symbol)
                if len(tickers) >= 10: break
            return tickers
        else:
            print(f"⚠️ FMP API 오류 (코드 {response.status_code}): {response.text}")
    except Exception as e:
        print(f"⚠️ API 파싱 에러: {e}")
    return []

def fetch_13f_dataroma(name):
    """API 키가 없을 때 Dataroma를 스크래핑하는 폴백 로직"""
    dataroma_map = {
        "Berkshire Hathaway": "BRK",
        "Scion Asset Management": "SAM",
        "Pershing Square": "PSCM",
        "Appaloosa": "APP",
        "Bill & Melinda Gates": "GATES"
    }
    
    dr_id = dataroma_map.get(name)
    if not dr_id:
        # 맵핑이 없거나 VC인 경우 빈 리스트 반환 (기본값 폴백 유도)
        return []
        
    try:
        url = f"https://www.dataroma.com/m/holdings.php?m={dr_id}"
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
        response = requests.get(url, headers=headers)
        if response.status_code == 200:
            soup = BeautifulSoup(response.text, 'html.parser')
            tickers = []
            # Dataroma 테이블의 종목 셀 추출
            for td in soup.select('td.sym'):
                tickers.append(td.text.strip())
                if len(tickers) >= 10: break
            return tickers
    except Exception as e:
        print(f"⚠️ 스크래핑 에러: {e}")
    return []

def fetch_13f_hybrid(name, cik):
    """하이브리드 분기 로직 (API 실패 시 스크래핑으로 자동 폴백)"""
    tickers = []
    
    # 1. API 키가 있으면 먼저 시도
    if FMP_API_KEY:
        tickers = fetch_13f_fmp(cik)
        
    # 2. API 키가 없거나, API 호출이 실패/권한없음(401, 403)으로 빈 리스트가 반환되었을 경우 스크래핑 시도
    if not tickers:
        if FMP_API_KEY:
            print(f"   [폴백] FMP API 조회 실패. 무료 스크래핑(Dataroma)으로 우회합니다...")
        tickers = fetch_13f_dataroma(name)
        
    return tickers

def update_watchlists():
    print("==================================================")
    print("🚀 [AI 춘식] 스마트 머니 스캐너 (하이브리드 모드 가동)")
    print("==================================================")
    
    # 1. Track C (기관) 업데이트
    print("\n🏛️ Track C (기관) CIK 스캔 중...")
    track_c_tickers = []
    for name, cik in config.TRACK_C_PRESETS['target_ciks'].items():
        print(f" - {name} (CIK: {cik}) 조회 중...")
        holdings = fetch_13f_hybrid(name, cik)
        if holdings:
            print(f"   └ 포착: {holdings[:5]}...")
            track_c_tickers.extend(holdings)
            
    if track_c_tickers:
        final_c = list(set(track_c_tickers))
        with open(config.GURUS_WATCHLIST_PATH, 'w') as f:
            json.dump(final_c, f, indent=4)
        print(f"✅ Track C 와치리스트 업데이트 완료 (총 {len(final_c)}개)")

    # 2. Track D (VC) 업데이트
    print("\n🚀 Track D (VC) CIK 스캔 중...")
    track_d_tickers = []
    for name, cik in config.TRACK_D_PRESETS['target_ciks'].items():
        print(f" - {name} (CIK: {cik}) 조회 중...")
        holdings = fetch_13f_hybrid(name, cik)
        if holdings:
            print(f"   └ 포착: {holdings[:5]}...")
            track_d_tickers.extend(holdings)
            
    if track_d_tickers:
        final_d = list(set(track_d_tickers))
        with open(config.VC_WATCHLIST_PATH, 'w') as f:
            json.dump(final_d, f, indent=4)
        print(f"✅ Track D 와치리스트 업데이트 완료 (총 {len(final_d)}개)")
        
if __name__ == "__main__":
    update_watchlists()
