#!/bin/bash

# 프로젝트 디렉토리로 이동
cd "$(dirname "$0")"
PROJECT_DIR="$(pwd)"

echo "=================================================="
echo "⚙️ [AI 춘식 MK4] LaunchAgent 서비스 등록을 시작합니다."
echo "=================================================="

# 1. start_chunsik.command 실행 권한 부여
chmod +x start_chunsik.command 2>/dev/null
echo "✅ start_chunsik.command 실행 권한 설정"

# 2. LaunchAgents 디렉토리 존재 확인
LAUNCH_AGENTS_DIR="$HOME/Library/LaunchAgents"
mkdir -p "$LAUNCH_AGENTS_DIR"

# 3. plist 동적 생성 및 복사
TARGET_PLIST="$LAUNCH_AGENTS_DIR/com.chunsik.autorun.mk4.plist"
if [ ! -f "com.chunsik.autorun.mk4.plist.example" ]; then
    echo "❌ com.chunsik.autorun.mk4.plist.example 파일을 찾을 수 없습니다."
    exit 1
fi
sed "s|__PROJECT_DIR__|$PROJECT_DIR|g" com.chunsik.autorun.mk4.plist.example > "$TARGET_PLIST"
echo "✅ $TARGET_PLIST 동적 생성 및 복사 완료"

# 4. 기존 서비스 언로드 및 신규 로드
echo "📡 기존 서비스 등록 해제 및 재등록 실행..."
launchctl unload "$TARGET_PLIST" 2>/dev/null
launchctl load "$TARGET_PLIST"

echo "=================================================="
echo "🎉 LaunchAgent 서비스 등록 및 가동 성공!"
echo "👉 이제 맥이 재부팅되거나 로그인될 때 스케줄러가 자동 시작됩니다."
echo "👉 수동으로 켜거나 끄고 싶을 때는 언제든지 start_chunsik.command를 실행해 주세요."
echo "=================================================="

