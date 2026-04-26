"""Sandboxed Python execution with timeout. Disable in shared production without isolation (gVisor/Firecracker)."""
import subprocess
import tempfile
import os


def run_python(code: str, timeout: int = 5) -> dict:
    with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False) as f:
        f.write(code)
        path = f.name
    try:
        proc = subprocess.run(
            ["python", "-I", path],
            capture_output=True, text=True, timeout=timeout,
            env={"PYTHONDONTWRITEBYTECODE": "1", "PATH": os.environ.get("PATH", "")},
        )
        return {"stdout": proc.stdout[-4000:], "stderr": proc.stderr[-2000:], "returncode": proc.returncode}
    except subprocess.TimeoutExpired:
        return {"stdout": "", "stderr": f"Timeout after {timeout}s", "returncode": -1}
    finally:
        try:
            os.unlink(path)
        except OSError:
            pass
