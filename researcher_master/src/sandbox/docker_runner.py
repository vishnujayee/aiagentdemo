"""Docker-backed sandbox runner.

This runs the provided Python code inside an ephemeral Docker container with
resource limits. Requires Docker to be installed and the current user to have
permissions to run `docker` locally.

Security note: Running arbitrary code in Docker is safer than running on the
host, but not a full security boundary for truly untrusted code; use proper
isolation (VMs, Firecracker) for production.
"""
import subprocess
import tempfile
import os
import uuid
from typing import Tuple


def _docker_available() -> bool:
    try:
        subprocess.run(["docker", "--version"], capture_output=True, check=True)
        return True
    except Exception:
        return False


def run_code_in_docker(code: str, timeout: int = 10, memory: str = "256m", cpus: float = 0.5) -> Tuple[int, str, str]:
    """Run code inside an ephemeral Python Docker container.

    Returns: (returncode, stdout, stderr)
    """
    if not _docker_available():
        return -127, "", "docker not available"

    tmpdir = tempfile.mkdtemp(prefix="sandbox_")
    fname = os.path.join(tmpdir, "code.py")
    with open(fname, "w", encoding="utf-8") as f:
        f.write(code)

    # build docker run command
    # - remove container after run, --network none for isolation, memory/cpu limits
    # Hardened docker flags (best-effort): read-only filesystem, pids limit, no network,
    # drop capabilities, run as non-root (1000), and limit mounts to workspace only.
    # Path to bundled seccomp profile (best-effort). Docker on some platforms
    # may ignore this option; we don't fail if it's not applied.
    repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
    seccomp_path = os.path.join(repo_root, "seccomp", "researcher_seccomp.json")

    cmd = [
        "docker", "run", "--rm",
        "--network", "none",
        "--memory", memory,
        "--cpus", str(cpus),
        "--pids-limit", "64",
        "--read-only",
        "--user", "1000:1000",
        "--cap-drop", "ALL",
        "--security-opt", "no-new-privileges",
        # mount code as read-only and provide a small writable tmpfs for runtime needs
        "-v", f"{tmpdir}:/work:ro",
        "--tmpfs", "/tmp:rw,noexec,nosuid,size=64m",
        "-w", "/work",
    ]

    # Add seccomp option when profile exists
    if os.path.exists(seccomp_path):
        cmd.extend(["--security-opt", f"seccomp={seccomp_path}"])

    cmd.extend([
        "python:3.11-slim",
        "python", "code.py"
    ])

    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return proc.returncode, proc.stdout, proc.stderr
    except subprocess.TimeoutExpired as e:
        return -1, "", f"TimeoutExpired: {e}"
    except Exception as e:
        return -2, "", f"Error running docker sandbox: {e}"
    finally:
        try:
            # remove tempdir and file
            for _f in os.listdir(tmpdir):
                try:
                    os.remove(os.path.join(tmpdir, _f))
                except Exception:
                    pass
            os.rmdir(tmpdir)
        except Exception:
            pass
