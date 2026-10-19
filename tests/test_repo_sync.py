import os
import time
from server import check_repo_sync_weekly, check_repo_sync


def test_check_repo_sync_weekly_non_git(tmp_path):
    # Directory without .git should gracefully return None
    notice = check_repo_sync_weekly(str(tmp_path))
    assert notice is None


def test_check_repo_sync_weekly_respects_interval(tmp_path):
    git_dir = tmp_path / ".git"
    git_dir.mkdir()
    stamp_file = git_dir / "grafeando_sync_check"
    # Write a fresh timestamp (now)
    stamp_file.write_text(str(time.time()), encoding="utf-8")

    # Should immediately return None without invoking git
    notice = check_repo_sync_weekly(str(tmp_path), interval_days=7)
    assert notice is None


def test_check_repo_sync_tool_non_git(tmp_path):
    res = check_repo_sync(path=str(tmp_path))
    assert res["is_git_repo"] is False
    assert res["is_up_to_date"] is True


def test_check_repo_sync_tool_current_repo():
    # In this current git repo
    res = check_repo_sync(path=".")
    assert res["is_git_repo"] is True
    assert "upstream" in res
    assert "behind_commits" in res
