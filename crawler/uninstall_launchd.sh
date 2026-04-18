#!/usr/bin/env bash
# uninstall_launchd.sh — launchd 스케줄러 제거 스크립트

set -euo pipefail

PLIST_LABEL="com.aisitei.crawler"
PLIST_PATH="$HOME/Library/LaunchAgents/${PLIST_LABEL}.plist"

echo "==> launchd 항목 제거 중: ${PLIST_LABEL}"

if launchctl list | grep -q "${PLIST_LABEL}" 2>/dev/null; then
    launchctl unload "${PLIST_PATH}" 2>/dev/null || true
    echo "    unload 완료"
else
    echo "    (등록된 항목 없음, 건너뜀)"
fi

if [ -f "${PLIST_PATH}" ]; then
    rm "${PLIST_PATH}"
    echo "    plist 파일 삭제: ${PLIST_PATH}"
else
    echo "    (plist 파일 없음, 건너뜀)"
fi

echo ""
echo "=========================================="
echo "  제거 완료: ${PLIST_LABEL}"
echo "=========================================="
