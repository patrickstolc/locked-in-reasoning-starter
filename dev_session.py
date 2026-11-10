"""Workspace policy and review state live outside the agent's writable mount."""
import difflib
import hashlib
import json
import os
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
MAX_FILE = 64000


class BudgetReached(Exception):
    pass


class DevSession:
    def __init__(self, game, executor, *, profile="opening", runs=None):
        self.game = Path(game).resolve()
        self.executor, self.profile = executor, profile
        runs = Path(runs or ROOT / "runs")
        runs.mkdir(parents=True, exist_ok=True)
        self.run_dir = Path(tempfile.mkdtemp(prefix="edit-", dir=runs)).resolve()
        self.workspace = self.run_dir / "workspace"
        self.workspace.mkdir()
        self.original = {}
        for filename in ("world.py", "manual_room.py"):
            path = self.game / filename
            if path.is_symlink() or not path.is_file():
                raise ValueError(f"Expected a regular game file: {filename}")
            self.original[filename] = path.read_bytes()
            (self.workspace / filename).write_bytes(self.original[filename])
        original_dir = self.run_dir / "original"
        original_dir.mkdir()
        for name, content in self.original.items():
            (original_dir / name).write_bytes(content)
        self.executions = 0
        self.blocked = False
        self.verified_hash = None
        self.accepted = False

    def log(self, event, **fields):
        with (self.run_dir / "execution.jsonl").open("a") as file:
            file.write(json.dumps({"event": event, **fields}) + "\n")

    def path(self, name, *, writing=False):
        allowed = {"world.py", "check_change.py"} if writing else {
            "world.py", "manual_room.py", "check_change.py"}
        if name not in allowed:
            raise ValueError("Use an allowed filename, without directories.")
        path = self.workspace / name
        if path.is_symlink() or path.resolve().parent != self.workspace:
            raise ValueError("Symlinks and paths outside the workspace are not allowed.")
        if path.exists() and not path.is_file():
            raise ValueError("Expected a regular file.")
        return path

    def read_file(self, name):
        path = self.path(name)
        if path.stat().st_size > MAX_FILE:
            raise ValueError("File is too large.")
        result = path.read_text()
        self.log("read", path=name)
        return result

    def write_file(self, name, content):
        if len(content.encode()) > MAX_FILE:
            raise ValueError("File is too large.")
        path = self.path(name, writing=True)
        self.verified_hash = None
        path.write_text(content)
        self.log("write", path=name, bytes=len(content.encode()))
        return f"Saved {name}."

    def run_python(self, code):
        if self.executions >= 3:
            self.blocked = True
            raise BudgetReached("Three executions used; review or start a new run.")
        if len(code.encode()) > MAX_FILE:
            raise ValueError("Code is too large.")
        self.executions += 1
        self.verified_hash = None
        result = self.executor.run(self.workspace, code)
        self.log("execute", number=self.executions, code=code, result=result)
        print(f"\n--- Execution {self.executions}/3 ---")
        print(result["stdout"], end="")
        print(result["stderr"], end="")
        print(f"Exit: {result['exit_code']}; timed out: {result['timed_out']}")
        return result

    def diff(self):
        result = []
        for name in ("world.py", "manual_room.py", "check_change.py"):
            before = self.original.get(name, b"").decode()
            path = self.path(name)
            after = self.read_file(name) if path.exists() else ""
            result.extend(difflib.unified_diff(before.splitlines(True), after.splitlines(True),
                                              fromfile="original/" + name, tofile="proposed/" + name))
        return "".join(result)

    def digest(self):
        # Validate every mounted file after arbitrary code has run.
        files = sorted(self.workspace.iterdir())
        if any(p.name not in {"world.py", "manual_room.py", "check_change.py"} for p in files):
            raise ValueError("Unexpected workspace files; discard this run.")
        digest = hashlib.sha256()
        for path in files:
            data = self.read_file(path.name).encode()
            digest.update(path.name.encode() + b"\0" + data)
        if self.path("manual_room.py").read_bytes() != self.original["manual_room.py"]:
            raise ValueError("The preview runner must remain unchanged.")
        self.path("world.py").stat()
        return digest.hexdigest()

    def verify(self):
        self.verified_hash = None
        before = self.digest()
        code = ("import sys, unittest\n"
                "sys.path.insert(0, '/checks')\n"
                "import verify_game\n"
                f"verify_game.PROFILE = {self.profile!r}\n"
                "suite = unittest.defaultTestLoader.loadTestsFromModule(verify_game)\n"
                "result = unittest.TextTestRunner(verbosity=2).run(suite)\n"
                "raise SystemExit(0 if result.wasSuccessful() else 1)\n")
        result = self.executor.run(self.workspace, code, checks=ROOT / "checks", readonly=True)
        if result["exit_code"] == 0 and not result["timed_out"] and self.digest() == before:
            self.verified_hash = before
        self.log("verify", profile=self.profile, result=result)
        return result

    def accept(self):
        if self.blocked or not self.verified_hash or self.digest() != self.verified_hash:
            raise ValueError("This run has not passed verification, or changed afterward.")
        for name, content in self.original.items():
            path = self.game / name
            if path.is_symlink() or path.read_bytes() != content:
                raise ValueError("The working game changed during this run. Start again.")
        content = self.path("world.py").read_bytes()
        fd, name = tempfile.mkstemp(prefix=".world-", dir=self.game)
        try:
            with os.fdopen(fd, "wb") as file:
                file.write(content)
            os.replace(name, self.game / "world.py")
        finally:
            if os.path.exists(name):
                os.unlink(name)
        self.accepted = True
        self.log("accepted", sha256=hashlib.sha256(content).hexdigest())

    def discard(self):
        self.verified_hash = None
        self.blocked = True
        self.log("discarded")

    def preview(self):
        self.digest()
        # Reads and runs edited code only in Docker.
        return self.executor.run(self.workspace,
            "import sys, runpy\nsys.argv=['manual_room.py', '--demo']\n"
            "runpy.run_path('manual_room.py', run_name='__main__')\n", readonly=True)
