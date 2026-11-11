"""Sandbox runner for small experiments.

This is a lightweight, local-only sandbox for running untrusted Python snippets during
development. It uses subprocess to run the snippet in a separate process with a timeout.

WARNING: This is NOT secure for running truly untrusted code. It is intended for
local development only. Use proper containerization/VMs for stronger isolation.
"""
import subprocess
import sys
import tempfile
import os
import uuid
from typing import Tuple

try:
    from .docker_runner import run_code_in_docker
except Exception:
    run_code_in_docker = None

from src.storage.db import save_sandbox_run


def _local_run(code: str, timeout: int = 10) -> Tuple[int, str, str]:
    # write to a temporary file
    fname = os.path.join(tempfile.gettempdir(), f"sandbox_{uuid.uuid4().hex}.py")
    with open(fname, "w", encoding="utf-8") as f:
        f.write(code)

    try:
        python_exe = sys.executable
        proc = subprocess.run([python_exe, fname], capture_output=True, text=True, timeout=timeout)
        return proc.returncode, proc.stdout, proc.stderr
    except subprocess.TimeoutExpired as e:
        return -1, "", f"TimeoutExpired: {e}"
    except Exception as e:
        return -2, "", f"Error running sandbox: {e}"
    finally:
        try:
            os.remove(fname)
        except Exception:
            pass


def run_code(code: str, timeout: int = 10) -> Tuple[int, str, str]:
    """Run code using Docker runner when available, falling back to local subprocess.

    Also record run metadata into the sandbox_runs DB table (best-effort).
    """
    run_id = uuid.uuid4().hex
    rc = out = err = None
    # prefer docker runner when available, but gracefully fall back to local run
    if run_code_in_docker:
        try:
            rc, out, err = run_code_in_docker(code, timeout=timeout)
        except Exception as e:
            rc, out, err = -2, "", f"docker runner exception: {e}"

    # If docker wasn't available or returned a docker-specific error, fall back to local
    docker_failure = False
    if rc is None:
        docker_failure = True
    else:
        # docker runner uses negative return codes for availability/errors
        if isinstance(rc, int) and rc < 0:
            docker_failure = True
        # also detect common docker connect error strings
        if isinstance(err, str) and ("docker not available" in err or "error during connect" in err.lower() or "cannot connect" in err.lower()):
            docker_failure = True

    if docker_failure:
        rc, out, err = _local_run(code, timeout=timeout)

    # best-effort save run record
    try:
        record = {"run_id": run_id, "returncode": rc, "stdout": out, "stderr": err}
        save_sandbox_run(run_id, record)
    except Exception:
        pass

    return rc, out, err
