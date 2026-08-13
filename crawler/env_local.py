"""
env_local.py — crawler/.env.local 파일을 읽어 프로세스 환경변수로 주입합니다.

배경:
  launchd가 매일 07:00에 main.py를 실행할 때는 로그인 셸(zsh)을 거치지 않으므로
  ~/.zshrc의 export(GEMINI_API_KEY 등)가 전혀 보이지 않는다. 그래서 비밀값은
  crawler/.env.local(git에 커밋 안 됨)에 KEY=VALUE 형식으로 저장해두고,
  main.py 시작 시 이 모듈로 직접 읽어 os.environ에 주입한다.

형식 (crawler/.env.local):
  # 주석은 무시됨
  GEMINI_API_KEY=xxxxx
  GMAIL_ADDRESS=someone@gmail.com
  GMAIL_APP_PASSWORD=xxxx xxxx xxxx xxxx
  DIGEST_RECIPIENT=someone@company.com

이미 os.environ에 값이 있는 키는 덮어쓰지 않는다(터미널에서 수동으로 다른 값을
export해서 돌리고 싶을 때 우선권을 준다).
"""
import os
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

ENV_LOCAL_PATH = Path(__file__).parent / ".env.local"


def load_env_local(path: Path = ENV_LOCAL_PATH) -> int:
    """.env.local을 읽어 os.environ에 주입. 로딩한 키 개수를 반환."""
    if not path.exists():
        logger.info(f".env.local 없음 ({path}) — 클라우드 API/이메일 기능 비활성 상태로 진행")
        return 0

    loaded = 0
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if not key:
            continue
        if key in os.environ:
            continue  # 이미 셸에서 export된 값이 있으면 그걸 우선
        os.environ[key] = value
        loaded += 1

    logger.info(f".env.local에서 {loaded}개 값 로딩")
    return loaded
