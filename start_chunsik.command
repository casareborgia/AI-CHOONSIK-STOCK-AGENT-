#!/bin/bash
# 현재 스크립트가 실행되는 터미널 창의 작업 디렉토리를 이 프로젝트 폴더로 강제 이동합니다.
cd "$(dirname "$0")"

echo "=================================================="
echo "🤖 [AI 춘식 MK3] 자동화 스케줄러(LaunchAgent) 기동 중..."
echo "=================================================="

# 혹시 기존에 nohup 등으로 직접 띄운 프로세스가 남아있다면 완전히 정리
pkill -f "caffeinate.*auto_runner.py" 2>/dev/null
pkill -f auto_runner.py 2>/dev/null

PLIST_PATH="$HOME/Library/LaunchAgents/com.chunsik.autorun.mk3.plist"

# plist가 LaunchAgents 폴더에 없거나 다르면 최신화 및 로드
if [ ! -f "$PLIST_PATH" ] || ! cmp -s "com.chunsik.autorun.mk3.plist" "$PLIST_PATH"; then
    echo "📡 LaunchAgent 등록을 최신화합니다..."
    mkdir -p "$HOME/Library/LaunchAgents"
    cp com.chunsik.autorun.mk3.plist "$PLIST_PATH"
    launchctl unload "$PLIST_PATH" 2>/dev/null
    launchctl load "$PLIST_PATH"
    echo "✅ LaunchAgent 서비스 등록 완료"
fi

# launchd 서비스 시작 및 재부팅
echo "📡 launchd 스케줄러 서비스를 재부팅(Restart)합니다..."
launchctl stop com.chunsik.autorun.mk3 2>/dev/null
launchctl start com.chunsik.autorun.mk3 2>/dev/null

echo "=================================================="
echo "✅ 스케줄러가 launchd(LaunchAgent)를 통해 백그라운드에서 구동되었습니다!"
echo "👉 시스템 잠자기(Sleep)가 강제 방지되며, 재부팅 시에도 자동 시작됩니다."
echo "📡 로그 기록 경로: ./auto_runner.log"
echo "=================================================="

# 3초간 확인 메시지를 보여준 뒤 터미널 창을 닫습니다.
sleep 3
exit 0
