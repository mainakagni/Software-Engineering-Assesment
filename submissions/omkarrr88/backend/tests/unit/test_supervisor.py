"""Running the API and the worker side by side in one container."""

import signal
import subprocess
import sys
import time

from app.supervisor import api_command, supervise, worker_command

SLEEPER = [sys.executable, "-c", "import time; time.sleep(60)"]
# Prints once it runs, which means the supervisor has installed its signal handlers.
ANNOUNCED_SLEEPER = [sys.executable, "-c", "import time; print('up', flush=True); time.sleep(60)"]


def test_a_failing_child_stops_the_other_and_its_exit_code_is_returned() -> None:
    started = time.monotonic()
    assert supervise([SLEEPER, [sys.executable, "-c", "raise SystemExit(3)"]], stop_timeout=5) == 3
    assert time.monotonic() - started < 10  # the sleeper was stopped, not waited for


def test_a_child_that_exits_cleanly_still_counts_as_a_failure() -> None:
    # Neither the API nor the worker should ever finish on their own.
    assert supervise([SLEEPER, [sys.executable, "-c", "pass"]], stop_timeout=5) == 1


def test_a_child_killed_by_a_signal_gives_the_shell_exit_code() -> None:
    killed = [sys.executable, "-c", "import os, signal; os.kill(os.getpid(), signal.SIGKILL)"]
    assert supervise([SLEEPER, killed], stop_timeout=5) == 128 + signal.SIGKILL


def test_a_stop_signal_is_passed_on_and_ends_cleanly() -> None:
    script = (
        "import sys\n"
        "from app.supervisor import supervise\n"
        f"sys.exit(supervise([{ANNOUNCED_SLEEPER!r}, {SLEEPER!r}], stop_timeout=5))\n"
    )
    command = [sys.executable, "-c", script]
    process = subprocess.Popen(command, stdout=subprocess.PIPE, text=True)  # noqa: S603
    try:
        assert process.stdout is not None
        assert process.stdout.readline().strip() == "up"
        process.send_signal(signal.SIGTERM)
        assert process.wait(timeout=15) == 0
    finally:
        process.kill()
        process.wait()


def test_the_previous_signal_handlers_are_restored() -> None:
    before = signal.getsignal(signal.SIGTERM)
    supervise([[sys.executable, "-c", "pass"]], stop_timeout=5)
    assert signal.getsignal(signal.SIGTERM) is before


def test_the_api_listens_on_the_platform_port() -> None:
    assert api_command("10000")[-4:] == ["--host", "0.0.0.0", "--port", "10000"]  # noqa: S104
    assert worker_command()[-2:] == ["-m", "app.worker"]
