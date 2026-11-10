"""Run generated Python in a disposable Docker container, never in the host interpreter."""
import subprocess
import threading
import uuid
from pathlib import Path


class DockerExecutor:
    def __init__(self, image="locked-in-executor", timeout=30):
        self.image, self.timeout = image, timeout

    def run(self, workspace: Path, code: str, *, checks=None, readonly=False):
        name = "locked-in-" + uuid.uuid4().hex
        mount = f"type=bind,source={workspace.resolve()},target=/workspace"
        if readonly:
            mount += ",readonly"
        args = ["docker", "run", "--rm", "--name", name, "-i",
                "--network", "none", "--read-only", "--cap-drop", "ALL",
                "--security-opt", "no-new-privileges", "--pids-limit", "64",
                "--memory", "256m", "--cpus", "1", "--tmpfs", "/tmp:rw,size=16m",
                "--env", "PYTHONDONTWRITEBYTECODE=1", "--mount", mount,
                "--workdir", "/workspace"]
        if checks:
            args += ["--mount", f"type=bind,source={Path(checks).resolve()},target=/checks,readonly"]
        args += [self.image, "python", "-B", "-u", "-"]
        # Drain output while keeping only a bounded prefix in memory.
        buffers = {"stdout": bytearray(), "stderr": bytearray()}
        truncated = {key: False for key in buffers}

        def drain(stream, key):
            while chunk := stream.read(4096):
                remaining = 16000 - len(buffers[key])
                buffers[key].extend(chunk[:max(remaining, 0)])
                if len(chunk) > remaining:
                    truncated[key] = True

        process = subprocess.Popen(args, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                   stderr=subprocess.PIPE)
        readers = [threading.Thread(target=drain, args=(getattr(process, key), key), daemon=True)
                   for key in buffers]
        for reader in readers:
            reader.start()

        def feed():
            try:
                process.stdin.write(code.encode())
                process.stdin.close()
            except (BrokenPipeError, OSError):
                pass

        writer = threading.Thread(target=feed, daemon=True)
        writer.start()
        timed_out = False
        try:
            try:
                process.wait(timeout=self.timeout)
            except subprocess.TimeoutExpired:
                timed_out = True
        finally:
            # Killing the client alone does not stop its container.
            subprocess.run(["docker", "rm", "-f", name], stdout=subprocess.DEVNULL,
                           stderr=subprocess.DEVNULL, timeout=15)
            if process.poll() is None:
                process.kill()
            process.wait()
            for reader in readers:
                reader.join(timeout=5)
            writer.join(timeout=5)
            process.stdin.close()
            process.stdout.close()
            process.stderr.close()
        return {key: value.decode(errors="replace") for key, value in buffers.items()} | {
            "exit_code": None if timed_out else process.returncode,
            "timed_out": timed_out, "output_truncated": any(truncated.values())}
