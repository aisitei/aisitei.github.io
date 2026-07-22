#!/bin/bash
# priority_watcher.sh — 일일 크롤러(main.py --run)가 실행 중일 때
# 백그라운드 복구/재번역 작업(recover_corrupted_multilang.py, retranslate_broken.py)을
# 일시정지(SIGSTOP)시켜 LM Studio를 독점하게 하고, 크롤러가 끝나면 재개(SIGCONT)한다.
#
# 사용법: nohup bash priority_watcher.sh > logs/priority_watcher.log 2>&1 &

RECOVERY_PATTERN="recover_corrupted_multilang.py|retranslate_broken.py"
CRAWLER_PATTERN="main.py --run"

echo "$(date '+%Y-%m-%d %H:%M:%S') priority_watcher 시작"

while true; do
  crawler_running=$(pgrep -f "$CRAWLER_PATTERN")
  recovery_pids=$(pgrep -f "$RECOVERY_PATTERN")

  if [ -n "$crawler_running" ]; then
    if [ -n "$recovery_pids" ]; then
      for pid in $recovery_pids; do
        state=$(ps -o state= -p "$pid" 2>/dev/null | tr -d ' ')
        # state는 "T", "TN" 등 접미사가 붙을 수 있으므로 접두사로 판별 (정확히 일치 비교 금지)
        case "$state" in
          T*) ;;  # 이미 정지 상태 → 아무 것도 안 함
          *)
            kill -STOP "$pid" 2>/dev/null
            echo "$(date '+%Y-%m-%d %H:%M:%S') 크롤러 실행 중 → 복구 프로세스 일시정지 (PID $pid)"
            ;;
        esac
      done
    fi
  else
    if [ -n "$recovery_pids" ]; then
      for pid in $recovery_pids; do
        state=$(ps -o state= -p "$pid" 2>/dev/null | tr -d ' ')
        case "$state" in
          T*)
            kill -CONT "$pid" 2>/dev/null
            echo "$(date '+%Y-%m-%d %H:%M:%S') 크롤러 종료 → 복구 프로세스 재개 (PID $pid)"
            ;;
          *) ;;  # 이미 실행 중 → 아무 것도 안 함
        esac
      done
    fi
  fi

  sleep 30
done
