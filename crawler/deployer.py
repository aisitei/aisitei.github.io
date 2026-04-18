"""GitHub 자동 배포 모듈 - 단일 레포 운영"""
import os
import subprocess
import logging
from datetime import datetime

import config

logger = logging.getLogger(__name__)


def run_git(args: list[str], cwd: str) -> tuple[int, str]:
    cmd = ["git"] + args
    try:
        result = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=60)
        output = (result.stdout.strip() + "\n" + result.stderr.strip()).strip()
        return result.returncode, output
    except subprocess.TimeoutExpired:
        return 1, "timeout"
    except Exception as e:
        return 1, str(e)


def setup_git_config(repo_dir: str):
    run_git(["config", "user.name", config.GIT_USER_NAME], repo_dir)
    run_git(["config", "user.email", config.GIT_USER_EMAIL], repo_dir)


def ensure_repo(repo_dir: str):
    git_dir = os.path.join(repo_dir, ".git")
    if os.path.isdir(git_dir):
        if config.GITHUB_REPO_URL:
            run_git(["remote", "set-url", "origin", config.GITHUB_REPO_URL], repo_dir)
        return
    if not config.GITHUB_REPO_URL:
        logger.warning("GITHUB_REPO_URL이 설정되지 않아 git clone을 건너뜁니다.")
        return
    parent_dir = os.path.dirname(repo_dir)
    os.makedirs(parent_dir, exist_ok=True)
    basename = os.path.basename(repo_dir)
    code, output = run_git(["clone", config.GITHUB_REPO_URL, basename], parent_dir)
    if code != 0:
        raise RuntimeError(f"git clone 실패: {output}")


def run_build(repo_dir: str) -> bool:
    """build.py를 실행하여 index.html, reports.html을 재생성합니다."""
    try:
        result = subprocess.run(
            ["python3", "build.py"],
            cwd=repo_dir,
            capture_output=True,
            text=True,
            timeout=120,
        )
        if result.returncode == 0:
            logger.info("build.py 실행 완료")
            return True
        else:
            logger.error(f"build.py 실패:\n{result.stderr}")
            return False
    except Exception as e:
        logger.error(f"build.py 실행 오류: {e}")
        return False


def commit_and_push(repo_dir: str, article_dirs: list[str], article_titles: list[str]) -> bool:
    """변경된 파일을 commit하고 push합니다."""
    setup_git_config(repo_dir)
    run_git(["pull", "--rebase", "origin", config.GIT_BRANCH], repo_dir)

    # articles/ 폴더 전체 스테이징
    run_git(["add", "articles/"], repo_dir)

    # build.py 실행 후 생성된 페이지도 스테이징
    run_build(repo_dir)
    run_git(["add", "index.html", "reports.html"], repo_dir)

    # 변경사항 확인
    code, status = run_git(["status", "--porcelain"], repo_dir)
    if not status.strip():
        logger.info("변경사항 없음, commit 건너뜀")
        return True

    today = datetime.now().strftime("%Y-%m-%d")
    count = len(article_titles)
    commit_msg = f"feat: {today} IT뉴스 {count}건 추가\n\n"
    for title in article_titles:
        commit_msg += f"- {title}\n"

    code, output = run_git(["commit", "-m", commit_msg], repo_dir)
    if code != 0:
        logger.error(f"git commit 실패: {output}")
        return False

    code, output = run_git(["push", "origin", config.GIT_BRANCH], repo_dir)
    if code != 0:
        logger.error(f"git push 실패: {output}")
        return False

    logger.info(f"GitHub push 완료: {count}건")
    return True
