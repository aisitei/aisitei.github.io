import sys
import unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'crawler'))
import deployer

class PublishingTests(unittest.TestCase):
    def test_failed_build_cannot_commit_or_push_stale_pages(self):
        with patch.object(deployer, 'setup_git_config'), patch.object(deployer, 'run_build', return_value=False), patch.object(deployer, 'run_git', return_value=(0, 'M articles/example/index.html')) as git:
            result = deployer.commit_and_push('/test-repo', [], ['title'])
            self.assertFalse(result)
            self.assertFalse(any(call.args[0][0] in ('commit', 'push') for call in git.call_args_list))

    def test_generated_index_and_pages_are_staged_after_build(self):
        events=[]
        def git(args, cwd):
            events.append(args)
            return (0, 'M index.html')
        def build(repo):
            events.append(['build'])
            return True
        with patch.object(deployer, 'setup_git_config'), patch.object(deployer, 'run_build', side_effect=build), patch.object(deployer, 'run_git', side_effect=git):
            self.assertTrue(deployer.commit_and_push('/test-repo', [], ['title']))
        stage=next(args for args in events if args[0]=='add' and 'assets/data/' in args)
        self.assertIn('news/', stage)
        self.assertIn('articles/', stage)
        self.assertGreater(events.index(stage),events.index(['build']))
