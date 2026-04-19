#!/bin/bash

# stock_scheduler 재배포 스크립트
# 빌드, 설정 반영, 컨테이너 재시작을 한 번에 처리합니다.

echo "🚀 [1/3] 컨테이너 빌드 및 업데이트 시작..."
docker-compose up -d --build

if [ $? -eq 0 ]; then
    echo "✅ [2/3] 컨테이너 실행 성공!"
else
    echo "❌ [2/3] 컨테이너 실행 실패. 로그를 확인해 주세요."
    exit 1
fi

echo "🔍 [3/3] 백엔드 상태 확인 (5초간 로그 출력)..."
echo "------------------------------------------------"
docker-compose logs --tail 20 -f backend &
LOG_PID=$!


# 5초간 로그를 보여준 뒤 종료
sleep 5
kill $LOG_PID

echo ""
echo "------------------------------------------------"
echo "✨ 재배포 완료! 이제 대시보드와 텔레그램을 확인해 보세요."
