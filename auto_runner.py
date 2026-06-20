import time
import datetime
import subprocess
import sys
import os
import pytz
import json
import exchange_calendars as xcals

# [설정] 실행할 메인 오케스트레이터 경로
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
MAIN_ORCHESTRATOR_PATH = os.path.join(CURRENT_DIR, "main_orchestrator.py")
STATE_FILE = os.path.join(CURRENT_DIR, "run_state.json")

# 타임존 설정
KST = pytz.timezone('Asia/Seoul')
UTC = pytz.utc

def load_state():
    """상태 파일(run_state.json)을 로드합니다."""
    if not os.path.exists(STATE_FILE):
        return {}
    try:
        with open(STATE_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        print(f"⚠️ 상태 파일 로드 실패: {e}")
        return {}

def save_state(state):
    """상태 파일(run_state.json)을 저장합니다. 30일 지난 항목은 자동 정리합니다."""
    try:
        # 30일 이전 항목은 관리 항목에서 제외하여 파일 크기 유지
        cutoff_date = (datetime.date.today() - datetime.timedelta(days=30)).strftime('%Y-%m-%d')
        pruned_state = {k: v for k, v in state.items() if k >= cutoff_date}
        
        with open(STATE_FILE, 'w', encoding='utf-8') as f:
            json.dump(pruned_state, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"⚠️ 상태 파일 저장 실패: {e}")

def is_run_completed(session_str, run_type):
    """특정 영업일의 분석 완료 여부를 확인합니다."""
    state = load_state()
    return state.get(session_str, {}).get(run_type, False)

def mark_run_completed(session_str, run_type):
    """특정 영업일의 분석을 완료 처리합니다."""
    state = load_state()
    state.setdefault(session_str, {})[run_type] = True
    save_state(state)

def run_orchestrator(label=""):
    """메인 오케스트레이터 프로세스를 실행하고 결과를 출력합니다."""
    timestamp = datetime.datetime.now(KST).strftime("%Y-%m-%d %H:%M:%S")
    print(f"\n[{timestamp}] 🚀 AI 춘식 MK4 파이프라인 가동 시작 ({label})...")
    
    try:
        # 텔레그램 전송을 포함한 메인 오케스트레이터 실행 (python3로 실행)
        # 오케스트레이터가 멈춰도 스케줄러 루프가 영구 정지하지 않도록 타임아웃(기본 30분) 적용
        result = subprocess.run(
            [sys.executable, MAIN_ORCHESTRATOR_PATH],
            capture_output=True, text=True, timeout=1800
        )
        print(result.stdout)
        if result.stderr:
            print(f"--- [Error Output] ---\n{result.stderr}")
        print(f"[{datetime.datetime.now(KST)}] ✨ {label} 분석 및 보고 완료!")
    except subprocess.TimeoutExpired:
        print(f"⏱️ {label} 실행이 30분 타임아웃을 초과하여 강제 종료되었습니다. (다음 세션에서 재시도)")
    except Exception as e:
        print(f"❌ {label} 실행 중 오류 발생: {e}")

def check_and_run_sessions(nyse, now_kst):
    """최근 및 당일 세션을 검사하여 누락된 분석을 실행합니다."""
    now_utc = now_kst.astimezone(UTC)
    
    # 검사할 세션 목록 정의 (이전 영업일과 당일 영업일)
    sessions_to_check = []
    
    # [정합성/예외 방지] 주말이나 공휴일처럼 현재 날짜가 영업일이 아닐 때 exchange_calendars 예외가 나는 문제를 방지
    # nyse.schedule.index(영업일 리스트)에서 현재 날짜보다 같거나 작은 최근 2개 세션을 안전하게 추출합니다.
    past_sessions = nyse.schedule.index[nyse.schedule.index.date <= now_utc.date()]
    recent_sessions = past_sessions[-2:]
    
    for s in recent_sessions:
        sessions_to_check.append(s.date())
        
    # 중복 제거 및 정렬
    sessions_to_check = sorted(list(set(sessions_to_check)))
    
    for session_date in sessions_to_check:
        session_str = session_date.strftime('%Y-%m-%d')
        
        # 영업일 일정 획득
        schedule = nyse.schedule.loc[session_str]
        open_time = schedule['open'].astimezone(KST)
        close_time = schedule['close'].astimezone(KST)
        
        # 1. 아직 개장 전인 경우 -> 대기
        if now_kst < open_time:
            continue
            
        # 2. 개장 후 ~ 장 마감 전인 경우 -> 시가 분석 실행 여부 체크
        elif open_time <= now_kst < close_time:
            if not is_run_completed(session_str, 'open_run'):
                run_orchestrator(label=f"장 시작(시가) 분석 [{session_str}]")
                mark_run_completed(session_str, 'open_run')
                
        # 3. 장 마감 이후인 경우 -> 종가 분석 실행 여부 체크
        else: # now_kst >= close_time
            if not is_run_completed(session_str, 'close_run'):
                run_orchestrator(label=f"장 마감(종가) 분석 [{session_str}]")
                mark_run_completed(session_str, 'close_run')

def main():
    print("================================================================================")
    print("🤖 [AI 춘식 MK4 지능형 매니저 - 상태 기반/절전 대응 버전] 가동 시작")
    print("   - 미국 NYSE 시장 달력 연동 및 캐싱 완료")
    print("   - 상태 파일(run_state.json) 기반 누락 방지 가동")
    print("================================================================================")

    # 캘린더 인스턴스 싱글톤 로드
    nyse = xcals.get_calendar("XNYS")
    
    # ------------------------------------------------------------------------------
    # [챗봇 데몬 기동] 24시간 실시간 텔레그램 명령어 대기를 위해 데몬 프로세스 동시 기동
    # ------------------------------------------------------------------------------
    chatbot_proc = None
    chatbot_path = os.path.join(CURRENT_DIR, "chatbot_daemon.py")
    try:
        print(f"📡 [챗봇 서비스] 백그라운드 챗봇 리스너 데몬 구동 중... ({chatbot_path})")
        chatbot_proc = subprocess.Popen([sys.executable, "-u", chatbot_path])
    except Exception as e:
        print(f"❌ [챗봇 서비스] 챗봇 데몬 구동 실패: {e}")

    last_heartbeat_time = 0

    try:
        while True:
            try:
                now = datetime.datetime.now(KST)
                
                # 누락된 세션 확인 및 실행
                check_and_run_sessions(nyse, now)
                
                # 1시간에 한 번 작동 중 하트비트 로그 출력
                if time.time() - last_heartbeat_time >= 3600:
                    print(f"[{now.strftime('%Y-%m-%d %H:%M:%S')}] 📡 스케줄러 정상 가동 중... (이상 없음)")
                    # 챗봇 데몬 프로세스 생존 검사 및 자동 복구
                    if chatbot_proc and chatbot_proc.poll() is not None:
                        print("⚠️ [챗봇 서비스] 챗봇 데몬이 예기치 않게 종료되었습니다. 재기동을 시도합니다.")
                        chatbot_proc = subprocess.Popen([sys.executable, "-u", chatbot_path])
                    last_heartbeat_time = time.time()
                    
                # 60초 간격으로 상태 체크 (Lightweight)
                time.sleep(60)
                
            except Exception as e:
                print(f"❌ 루프 실행 중 오류 발생: {e}")
                time.sleep(60)
    finally:
        # 종료 시 서브프로세스인 챗봇 데몬도 함께 안전하게 종료
        if chatbot_proc:
            print("📡 [챗봇 서비스] 챗봇 데몬 프로세스 종료 처리 중...")
            chatbot_proc.terminate()
            try:
                chatbot_proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                chatbot_proc.kill()

if __name__ == "__main__":
    main()
