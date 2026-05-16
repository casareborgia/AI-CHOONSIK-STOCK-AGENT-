import time
import datetime
import subprocess
import sys
import os
import pytz
import exchange_calendars as xcals

# [설정] 실행할 메인 에이전트 경로
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
MAIN_AGENT_PATH = os.path.join(CURRENT_DIR, "main_agent.py")

# 타임존 설정
KST = pytz.timezone('Asia/Seoul')
UTC = pytz.utc

def run_agent(label=""):
    """메인 에이전트 프로세스를 실행하고 결과를 출력합니다."""
    timestamp = datetime.datetime.now(KST).strftime("%Y-%m-%d %H:%M:%S")
    print(f"\n[{timestamp}] 🚀 AI 춘식 파이프라인 가동 시작 ({label})...")
    
    try:
        # 텔레그램 전송을 포함한 메인 에이전트 실행
        result = subprocess.run([sys.executable, MAIN_AGENT_PATH], capture_output=True, text=True)
        print(result.stdout)
        if result.stderr:
            print(f"--- [Error Output] ---\n{result.stderr}")
        print(f"[{datetime.datetime.now(KST)}] ✨ {label} 분석 및 보고 완료!")
    except Exception as e:
        print(f"❌ {label} 실행 중 오류 발생: {e}")

def get_market_schedule():
    """NYSE 달력을 기반으로 오늘의 장 운영 시간을 계산합니다."""
    nyse = xcals.get_calendar("XNYS")
    now_utc = datetime.datetime.now(UTC)
    
    # 오늘이 영업일인지 확인
    is_session = nyse.is_session(now_utc.date())
    
    if not is_session:
        return None
    
    # 오늘의 개장/마감 시간 (UTC)
    schedule = nyse.schedule.loc[now_utc.date().strftime('%Y-%m-%d')]
    market_open_utc = schedule['market_open']
    market_close_utc = schedule['market_close']
    
    # KST로 변환
    open_kst = market_open_utc.astimezone(KST)
    close_kst = market_close_utc.astimezone(KST)
    
    return {
        "open": open_kst,
        "close": close_kst,
        "is_early_close": nyse.is_early_close(now_utc.date())
    }

def main():
    print("================================================================================")
    print("🤖 [AI 춘식 지능형 매니저 V2.0] 가동 시작")
    print("   - 미국 NYSE 시장 달력 연동 완료")
    print("   - 개장/마감 자동 감지 및 서머타임 대응")
    print("================================================================================")

    while True:
        try:
            now = datetime.datetime.now(KST)
            schedule = get_market_schedule()
            
            if not schedule:
                print(f"[{now.strftime('%H:%M:%S')}] 😴 오늘은 미장 휴장일입니다. 푹 쉬세요!")
                # 다음 날 자정까지 대기하거나 1시간마다 체크
                time.sleep(3600)
                continue

            open_time = schedule['open']
            close_time = schedule['close']
            
            # 장 시작 전이면
            if now < open_time:
                wait_seconds = (open_time - now).total_seconds()
                print(f"[{now.strftime('%H:%M:%S')}] ⏳ 장 개장 대기 중... ({open_time.strftime('%H:%M')} KST 예정)")
                # 너무 오래 기다리면 1시간마다 다시 체크 (혹시 모를 오류 방지)
                time.sleep(min(wait_seconds, 3600))
            
            # 장 시작 시점 (오차 5분 이내)
            elif abs((now - open_time).total_seconds()) < 60:
                run_agent(label="장 시작(시가) 분석")
                time.sleep(61) # 중복 실행 방지
            
            # 장 마감 전이면
            elif now < close_time:
                wait_seconds = (close_time - now).total_seconds()
                print(f"[{now.strftime('%H:%M:%S')}] 📊 장 운영 중... 마감 대기 ({close_time.strftime('%H:%M')} KST 예정)")
                time.sleep(min(wait_seconds, 3600))
            
            # 장 마감 시점 (오차 5분 이내)
            elif abs((now - close_time).total_seconds()) < 60:
                run_agent(label="장 마감(종가) 분석")
                time.sleep(61)
            
            # 장이 이미 끝났으면
            else:
                print(f"[{now.strftime('%H:%M:%S')}] ✅ 오늘 장 분석이 모두 완료되었습니다. 내일을 기다립니다.")
                time.sleep(3600)
                
        except Exception as e:
            print(f"❌ 루프 실행 중 오류 발생: {e}")
            time.sleep(60)

if __name__ == "__main__":
    main()
