"""Integration checks use Docker. They make no network model requests."""
import asyncio
import shutil
import tempfile
import unittest
from pathlib import Path

from dev_session import DevSession, BudgetReached, ROOT
from editor import edit
from executor import DockerExecutor
from scripted_demo import demo_model


class EditorTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.game = self.root / "game"
        shutil.copytree(ROOT / "game", self.game)

    def session(self, profile="opening"):
        return DevSession(self.game, DockerExecutor(), profile=profile, runs=self.root / "runs")

    def test_single_use_demo_accepts_and_preserves_original(self):
        session = self.session("single-use")
        original = (self.game / "world.py").read_bytes()
        asyncio.run(edit(demo_model(session, "single-use"), session, "Make the key single-use."))
        self.assertEqual(session.executions, 2)
        self.assertEqual((self.game / "world.py").read_bytes(), original)
        result = session.verify()
        self.assertEqual(result["exit_code"], 0, result)
        self.assertEqual(session.preview()["exit_code"], 0)
        session.accept()
        self.assertNotEqual((self.game / "world.py").read_bytes(), original)
        self.assertEqual((session.run_dir / "original/world.py").read_bytes(), original)
        self.assertTrue((session.run_dir / "messages.json").is_file())

    def test_opening_demo_discards(self):
        session = self.session()
        original = (self.game / "world.py").read_bytes()
        asyncio.run(edit(demo_model(session, "opening"), session, "Change the opening."))
        self.assertEqual(session.verify()["exit_code"], 0)
        session.discard()
        self.assertEqual((self.game / "world.py").read_bytes(), original)
        with self.assertRaises(ValueError):
            session.accept()

    def test_original_fails_single_use_profile(self):
        session = self.session("single-use")
        self.assertNotEqual(session.verify()["exit_code"], 0)
        with self.assertRaises(ValueError):
            session.accept()

    def test_path_and_symlink_rejected(self):
        session = self.session()
        for path in ("../world.py", "/tmp/world.py", ".env", "manual_room.py"):
            with self.assertRaises(ValueError):
                session.write_file(path, "bad")
        target = session.workspace / "check_change.py"
        target.symlink_to(self.game / "world.py")
        with self.assertRaises(ValueError):
            session.read_file("check_change.py")

    def test_limit_and_changed_after_verification(self):
        session = self.session()
        self.assertEqual(session.verify()["exit_code"], 0)
        session.write_file("world.py", session.read_file("world.py") + "\n# changed\n")
        with self.assertRaises(ValueError):
            session.accept()
        session.executions = 3
        with self.assertRaises(BudgetReached):
            session.run_python("print('should not run')")

    def test_stale_working_game_is_not_overwritten(self):
        session = self.session()
        self.assertEqual(session.verify()["exit_code"], 0)
        (self.game / "world.py").write_text("# another edit\n")
        with self.assertRaises(ValueError):
            session.accept()
        self.assertEqual((self.game / "world.py").read_text(), "# another edit\n")

    def test_docker_timeout_output_and_isolation(self):
        session = self.session()
        result = DockerExecutor(timeout=2).run(session.workspace, "while True: pass")
        self.assertTrue(result["timed_out"], result)
        result = session.run_python("import os, socket\n"
            "assert 'LLM_API_KEY' not in os.environ\n"
            "assert not os.path.exists('/checks')\n"
            "s=socket.socket(); s.settimeout(1)\n"
            "assert s.connect_ex(('1.1.1.1', 443)) != 0\n"
            "print('x' * 100000)\n")
        self.assertEqual(result["exit_code"], 0, result)
        self.assertTrue(result["output_truncated"])
        self.assertLessEqual(len(result["stdout"]), 16000)


if __name__ == "__main__":
    unittest.main()
