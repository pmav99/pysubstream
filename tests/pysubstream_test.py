from __future__ import annotations

import os
import subprocess
import sys

import pytest

from pysubstream import async_run, run

MISSING_FILE_ERROR = 127


def assert_processes_equal(cp1, cp2) -> None:
    assert cp1.args == cp2.args
    assert cp1.returncode == cp2.returncode
    assert cp1.stdout == cp2.stdout
    assert cp1.stderr == cp2.stderr


@pytest.mark.parametrize(
    "cmd",
    [
        pytest.param("echo 111", id="str"),
        pytest.param(b"echo 111", id="bytes"),
        pytest.param(["echo", "111"], id="sequence of strings"),
        pytest.param([b"echo", b"111"], id="sequence of bytes"),
    ],
)
def test_run_cmd_types(cmd, capfd):
    proc = run(cmd)
    assert isinstance(proc, subprocess.CompletedProcess)
    assert isinstance(proc.stdout, str)
    assert isinstance(proc.stderr, str)
    assert proc.stdout
    assert "111\n" == proc.stdout
    assert not proc.stderr
    assert proc.returncode == 0
    sys_out, sys_err = capfd.readouterr()
    assert "111\n" == sys_out
    assert not sys_err


def test_run_silence_stdout_and_stderr(capfd):
    cmd = "echo 111; echo 222 > /dev/stderr"
    expected = subprocess.CompletedProcess(args=cmd, returncode=0, stdout="111\n", stderr="222\n")
    proc = run(cmd, on_stdout=None, on_stderr=None)
    assert_processes_equal(proc, expected)
    sys_stdout, sys_stderr = capfd.readouterr()
    assert not sys_stdout
    assert not sys_stderr


def test_run_capture_just_stderr():
    cmd = "echo 111; echo 222 > /dev/stderr"
    expected = subprocess.CompletedProcess(args=cmd, returncode=0, stdout="", stderr="222\n")
    proc = run(cmd, stdout=None)
    assert_processes_equal(proc, expected)


def test_run_capture_just_stdout():
    cmd = "echo 111; echo 222 > /dev/stderr"
    expected = subprocess.CompletedProcess(args=cmd, returncode=0, stdout="111\n", stderr="")
    proc = run(cmd, stderr=None)
    assert_processes_equal(proc, expected)


def test_run_capture_both_stdout_and_stderr(capfd):
    cmd = "echo 111; echo 222 > /dev/stderr"
    expected = subprocess.CompletedProcess(args=cmd, returncode=0, stdout="111\n", stderr="222\n")
    proc = run(cmd)
    assert_processes_equal(proc, expected)
    sys_stdout, sys_stderr = capfd.readouterr()
    assert sys_stdout == "111\n"
    assert sys_stderr == "222\n"


@pytest.mark.parametrize(
    "on_stdout_val",
    [pytest.param(sys.stdout.write, id="on_stdout=write"), pytest.param(None, id="on_stdout=None")],
)
def test_run_capture_both_stdout_and_stderr_using_file_descriptors(capfd, tmp_path, on_stdout_val):
    cmd = "echo 111; echo 222 > /dev/stderr"
    expected = subprocess.CompletedProcess(args=cmd, returncode=0, stdout="", stderr="")
    stdout_file, stderr_file = tmp_path / "stdout.txt", tmp_path / "stderr.txt"
    with stdout_file.open("w") as stdout_fd, stderr_file.open("w") as stderr_fd:
        proc = run(cmd, stdout=stdout_fd, stderr=stderr_fd, on_stdout=on_stdout_val, on_stderr=on_stdout_val)
    assert_processes_equal(proc, expected)
    assert stdout_file.read_text() == "111\n"
    assert stderr_file.read_text() == "222\n"
    # Regardless of the callback, nothing gets echoed to console
    sys_stdout, sys_stderr = capfd.readouterr()
    assert not sys_stdout
    assert not sys_stderr


def test_run_no_capture_using_devnull(capfd):
    cmd = "echo 111; echo 222 > /dev/stderr"
    expected = subprocess.CompletedProcess(args=cmd, returncode=0, stdout="", stderr="")
    proc = run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    assert_processes_equal(proc, expected)
    sys_stdout, sys_stderr = capfd.readouterr()
    assert not sys_stdout
    assert not sys_stderr


@pytest.mark.parametrize(
    "on_stdout_val",
    [pytest.param(sys.stdout.write, id="on_stdout=write"), pytest.param(None, id="on_stdout=None")],
)
def test_run_no_capture_using_none(capfd, on_stdout_val):
    cmd = "echo 111; echo 222 > /dev/stderr"
    expected = subprocess.CompletedProcess(args=cmd, returncode=0, stdout="", stderr="")
    proc = run(cmd, stdout=None, stderr=None, on_stdout=on_stdout_val, on_stderr=on_stdout_val)
    assert_processes_equal(proc, expected)
    # Regardless of the callback, the results get printed to the console (stdout=None bypasses PIPE)
    sys_stdout, sys_stderr = capfd.readouterr()
    assert sys_stdout == "111\n"
    assert sys_stderr == "222\n"


def test_run_merge_stderr_in_stdout(capfd):
    cmd = "echo 111; echo 222 > /dev/stderr"
    expected = subprocess.CompletedProcess(args=cmd, returncode=0, stdout="111\n222\n", stderr="")
    proc = run(cmd, stderr=subprocess.STDOUT)
    assert_processes_equal(proc, expected)
    sys_stdout, sys_stderr = capfd.readouterr()
    assert sys_stdout == "111\n222\n"
    assert sys_stderr == ""


def test_run_merge_stderr_in_stdout_when_stdout_is_a_file_descriptor(tmp_path, capfd):
    # cmd = "echo 111; echo 222 > /dev/stderr"
    cmd = "echo 111; echo 222 >&2"
    expected = subprocess.CompletedProcess(args=cmd, returncode=0, stdout="", stderr="")
    output_file = tmp_path / "out.txt"
    with output_file.open("w+") as fd:
        proc = run(cmd, stdout=fd, stderr=subprocess.STDOUT)
    assert_processes_equal(proc, expected)
    sys_stdout, sys_stderr = capfd.readouterr()
    assert sys_stdout == ""
    assert sys_stderr == ""
    assert output_file.read_text() == "111\n222\n"


def test_run_error_no_check():
    cmd = "missing_command"
    expected = subprocess.CompletedProcess(
        args=cmd,
        returncode=MISSING_FILE_ERROR,
        stdout="",
        stderr=f"/bin/sh: line 1: {cmd}: command not found\n",
    )
    proc = run(cmd, check=False)
    # We can't use `assess_processes_equal()` because Ubuntu, Archlinux and MacOS return a different error
    #   - /bin/sh: line 1: missing_command: command not found
    #   + /bin/sh: 1: missing_command: not found
    #   + /bin/sh: missing_command: not found
    #
    # assert_processes_equal(proc, expected)
    assert proc.args == expected.args
    assert proc.returncode == expected.returncode
    assert proc.stdout == expected.stdout
    assert "/bin/sh" in proc.stderr
    assert f"{cmd}" in proc.stderr
    assert "not found" in proc.stderr


def test_run_error_check():
    cmd = "missing_command"
    with pytest.raises(subprocess.CalledProcessError) as exc:
        run(cmd, check=True)
    main_exc = exc.value
    assert main_exc.cmd == cmd
    assert isinstance(main_exc.stdout, str)
    assert not main_exc.stdout
    assert isinstance(main_exc.stderr, str)
    assert main_exc.stderr
    assert cmd in main_exc.stderr
    assert main_exc.returncode == MISSING_FILE_ERROR


@pytest.mark.parametrize("timeout", [0, 0.01])
def test_run_timeout(timeout):
    with pytest.raises(subprocess.TimeoutExpired):
        run("sleep 1", timeout=timeout)


def test_run_env():
    variable = "variable"
    value = "111"
    proc = run("env", env={variable: value})
    assert variable not in os.environ
    assert f"{variable}={value}" in proc.stdout
    assert proc.returncode == 0


def test_run_cwd(tmp_path):
    cwd = tmp_path
    proc = run("pwd", cwd=cwd)
    assert str(cwd) in proc.stdout
    assert not proc.stderr
    assert proc.returncode == 0


@pytest.mark.anyio
async def test_async_run():
    # Test a simple command
    result = await async_run(["echo", "Hello, Async World!"])
    assert result.stdout.strip() == "Hello, Async World!"

    # Test a command that fails
    with pytest.raises(subprocess.CalledProcessError):
        await async_run(["ls", "/nonexistentdirectory"], check=True)

    # Test a command that times out
    with pytest.raises(subprocess.TimeoutExpired):
        await async_run(["sleep", "10"], timeout=0.01)


def test_run_on_stdout_callback(capfd):
    collected = []
    proc = run("echo 111", on_stdout=collected.append)
    assert proc.stdout == "111\n"
    assert collected == ["111\n"]
    sys_stdout, sys_stderr = capfd.readouterr()
    assert not sys_stdout
    assert not sys_stderr


def test_run_on_stderr_callback(capfd):
    collected = []
    proc = run("echo 222 > /dev/stderr", on_stderr=collected.append)
    assert proc.stderr == "222\n"
    assert collected == ["222\n"]
    sys_stdout, sys_stderr = capfd.readouterr()
    assert not sys_stdout
    assert not sys_stderr


def test_run_on_stdout_and_on_stderr_callbacks(capfd):
    stdout_lines, stderr_lines = [], []
    cmd = "echo 111; echo 222 > /dev/stderr"
    proc = run(cmd, on_stdout=stdout_lines.append, on_stderr=stderr_lines.append)
    assert proc.stdout == "111\n"
    assert proc.stderr == "222\n"
    assert stdout_lines == ["111\n"]
    assert stderr_lines == ["222\n"]
    sys_stdout, sys_stderr = capfd.readouterr()
    assert not sys_stdout
    assert not sys_stderr


def test_run_on_stdout_callback_buffer_still_captured():
    proc = run("echo 111", on_stdout=lambda _: None)
    assert proc.stdout == "111\n"


def bad_callback(chunk: str) -> None:  # noqa: ARG001
    raise ValueError("callback error")


async def async_bad_callback(chunk: str) -> None:  # noqa: ARG001
    raise ValueError("async callback error")


def test_run_on_stdout_callback_exception_propagates():
    with pytest.raises(ExceptionGroup) as exc_info:
        run("echo 111", on_stdout=bad_callback)
    assert len(exc_info.value.exceptions) == 1
    assert isinstance(exc_info.value.exceptions[0], ValueError)
    assert str(exc_info.value.exceptions[0]) == "callback error"


def test_run_on_stderr_callback_exception_propagates():
    with pytest.raises(ExceptionGroup) as exc_info:
        run("echo 222 > /dev/stderr", on_stderr=bad_callback)
    assert len(exc_info.value.exceptions) == 1
    assert isinstance(exc_info.value.exceptions[0], ValueError)
    assert str(exc_info.value.exceptions[0]) == "callback error"


def test_run_kwargs_passed_to_open_process():
    proc = run("env", env={"FOO": "bar"}, on_stdout=None, on_stderr=None)
    assert proc.returncode == 0
    assert "FOO=bar" in proc.stdout


# ---------------------------------------------------------------------------
# stdin / input tests
# ---------------------------------------------------------------------------


def test_run_stdin_devnull():
    proc = run("cat", stdin=subprocess.DEVNULL, on_stdout=None, on_stderr=None)
    assert proc.stdout == ""
    assert proc.returncode == 0


def test_run_input_string(capfd):
    proc = run("cat", input="hello\n", on_stdout=None, on_stderr=None)
    assert proc.stdout == "hello\n"
    assert proc.returncode == 0
    sys_stdout, sys_stderr = capfd.readouterr()
    assert not sys_stdout
    assert not sys_stderr


def test_run_input_echoed_by_default(capfd):
    proc = run("cat", input="hello\n")
    assert proc.stdout == "hello\n"
    sys_stdout, _ = capfd.readouterr()
    assert sys_stdout == "hello\n"


def test_run_input_empty_string():
    proc = run("cat", input="", on_stdout=None, on_stderr=None)
    assert proc.stdout == ""
    assert proc.returncode == 0


def test_run_input_multiline():
    data = "line1\nline2\nline3\n"
    proc = run("cat", input=data, on_stdout=None, on_stderr=None)
    assert proc.stdout == data
    assert proc.returncode == 0


def test_run_input_with_check():
    proc = run("cat", input="ok\n", check=True, on_stdout=None, on_stderr=None)
    assert proc.stdout == "ok\n"
    assert proc.returncode == 0


def test_run_input_and_stdin_mutually_exclusive():
    with pytest.raises(ValueError, match="stdin and input arguments may not both be used"):
        run("cat", stdin=subprocess.DEVNULL, input="hello")


def test_run_stdin_from_file(tmp_path):
    f = tmp_path / "in.txt"
    f.write_text("from file\n")
    with f.open() as fd:
        proc = run("cat", stdin=fd, on_stdout=None, on_stderr=None)
    assert proc.stdout == "from file\n"
    assert proc.returncode == 0


@pytest.mark.anyio
async def test_async_run_input():
    result = await async_run("cat", input="async hello\n", on_stdout=None, on_stderr=None)
    assert result.stdout == "async hello\n"
    assert result.returncode == 0


@pytest.mark.anyio
async def test_async_run_input_and_stdin_mutually_exclusive():
    with pytest.raises(ValueError, match="stdin and input arguments may not both be used"):
        await async_run("cat", stdin=subprocess.DEVNULL, input="hello")


@pytest.mark.anyio
async def test_async_run_on_stdout_callback(capfd):
    collected = []
    result = await async_run(["echo", "Hello!"], on_stdout=collected.append)
    assert result.stdout.strip() == "Hello!"
    assert collected == ["Hello!\n"]
    sys_stdout, _ = capfd.readouterr()
    assert not sys_stdout


# ---------------------------------------------------------------------------
# Async callback tests
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_async_run_async_on_stdout_callback(capfd):
    """async_run with an async on_stdout callback awaits it correctly."""
    collected: list[str] = []

    async def async_cb(chunk: str) -> None:
        collected.append(chunk)

    result = await async_run(["echo", "hello"], on_stdout=async_cb)
    assert result.stdout == "hello\n"
    assert collected == ["hello\n"]
    sys_stdout, sys_stderr = capfd.readouterr()
    assert not sys_stdout
    assert not sys_stderr


@pytest.mark.anyio
async def test_async_run_async_on_stderr_callback(capfd):
    """async_run with an async on_stderr callback awaits it correctly."""
    collected: list[str] = []

    async def async_cb(chunk: str) -> None:
        collected.append(chunk)

    result = await async_run("echo err >&2", on_stderr=async_cb)
    assert result.stderr == "err\n"
    assert collected == ["err\n"]
    sys_stdout, sys_stderr = capfd.readouterr()
    assert not sys_stdout
    assert not sys_stderr


@pytest.mark.anyio
async def test_async_run_async_on_stdout_and_on_stderr_callbacks(capfd):
    """Both on_stdout and on_stderr can be async simultaneously."""
    stdout_chunks: list[str] = []
    stderr_chunks: list[str] = []

    async def async_stdout_cb(chunk: str) -> None:
        stdout_chunks.append(chunk)

    async def async_stderr_cb(chunk: str) -> None:
        stderr_chunks.append(chunk)

    cmd = "echo out; echo err >&2"
    result = await async_run(cmd, on_stdout=async_stdout_cb, on_stderr=async_stderr_cb)
    assert result.stdout == "out\n"
    assert result.stderr == "err\n"
    assert stdout_chunks == ["out\n"]
    assert stderr_chunks == ["err\n"]
    sys_stdout, sys_stderr = capfd.readouterr()
    assert not sys_stdout
    assert not sys_stderr


@pytest.mark.anyio
async def test_async_run_mixed_sync_stdout_async_stderr(capfd):
    """Sync on_stdout + async on_stderr work together."""
    sync_collected: list[str] = []
    async_collected: list[str] = []

    async def async_cb(chunk: str) -> None:
        async_collected.append(chunk)

    cmd = "echo out; echo err >&2"
    result = await async_run(cmd, on_stdout=sync_collected.append, on_stderr=async_cb)
    assert result.stdout == "out\n"
    assert result.stderr == "err\n"
    assert sync_collected == ["out\n"]
    assert async_collected == ["err\n"]
    sys_stdout, sys_stderr = capfd.readouterr()
    assert not sys_stdout
    assert not sys_stderr


@pytest.mark.anyio
async def test_async_run_async_stdout_sync_stderr(capfd):
    """Async on_stdout + sync on_stderr work together."""
    async_collected: list[str] = []
    sync_collected: list[str] = []

    async def async_cb(chunk: str) -> None:
        async_collected.append(chunk)

    cmd = "echo out; echo err >&2"
    result = await async_run(cmd, on_stdout=async_cb, on_stderr=sync_collected.append)
    assert result.stdout == "out\n"
    assert result.stderr == "err\n"
    assert async_collected == ["out\n"]
    assert sync_collected == ["err\n"]
    sys_stdout, sys_stderr = capfd.readouterr()
    assert not sys_stdout
    assert not sys_stderr


@pytest.mark.anyio
async def test_async_run_async_callback_buffer_still_captured():
    """The output buffer is populated even when an async callback is used."""

    async def noop(chunk: str) -> None:
        pass

    result = await async_run("echo 111", on_stdout=noop)
    assert result.stdout == "111\n"


@pytest.mark.anyio
async def test_async_run_async_callback_exception_propagates():
    """Exceptions raised inside an async callback propagate as ExceptionGroup."""
    with pytest.raises(ExceptionGroup) as exc_info:
        await async_run("echo 111", on_stdout=async_bad_callback)
    assert len(exc_info.value.exceptions) == 1
    assert isinstance(exc_info.value.exceptions[0], ValueError)
    assert str(exc_info.value.exceptions[0]) == "async callback error"


@pytest.mark.anyio
async def test_async_run_async_stderr_callback_exception_propagates():
    """Exceptions from an async on_stderr callback propagate."""
    with pytest.raises(ExceptionGroup) as exc_info:
        await async_run("echo err >&2", on_stderr=async_bad_callback)
    assert len(exc_info.value.exceptions) == 1
    assert isinstance(exc_info.value.exceptions[0], ValueError)
    assert str(exc_info.value.exceptions[0]) == "async callback error"


@pytest.mark.anyio
async def test_async_run_async_callable_object(capfd):
    """An object with an async __call__ method is detected and awaited."""
    collected: list[str] = []

    class AsyncCallable:
        async def __call__(self, chunk: str) -> None:
            collected.append(chunk)

    result = await async_run("echo hello", on_stdout=AsyncCallable())
    assert result.stdout == "hello\n"
    assert collected == ["hello\n"]
    sys_stdout, _ = capfd.readouterr()
    assert not sys_stdout


def test_run_async_on_stdout_callback(capfd):
    """run() (sync wrapper) also supports async on_stdout callbacks."""
    collected: list[str] = []

    async def async_cb(chunk: str) -> None:
        collected.append(chunk)

    proc = run("echo 111", on_stdout=async_cb)
    assert proc.stdout == "111\n"
    assert collected == ["111\n"]
    sys_stdout, sys_stderr = capfd.readouterr()
    assert not sys_stdout
    assert not sys_stderr


def test_run_async_on_stderr_callback(capfd):
    """run() (sync wrapper) also supports async on_stderr callbacks."""
    collected: list[str] = []

    async def async_cb(chunk: str) -> None:
        collected.append(chunk)

    proc = run("echo err >&2", on_stderr=async_cb)
    assert proc.stderr == "err\n"
    assert collected == ["err\n"]
    sys_stdout, sys_stderr = capfd.readouterr()
    assert not sys_stdout
    assert not sys_stderr


def test_run_async_on_stdout_and_on_stderr_callbacks(capfd):
    """run() with both async callbacks."""
    stdout_chunks: list[str] = []
    stderr_chunks: list[str] = []

    async def async_stdout_cb(chunk: str) -> None:
        stdout_chunks.append(chunk)

    async def async_stderr_cb(chunk: str) -> None:
        stderr_chunks.append(chunk)

    cmd = "echo out; echo err >&2"
    proc = run(cmd, on_stdout=async_stdout_cb, on_stderr=async_stderr_cb)
    assert proc.stdout == "out\n"
    assert proc.stderr == "err\n"
    assert stdout_chunks == ["out\n"]
    assert stderr_chunks == ["err\n"]
    sys_stdout, sys_stderr = capfd.readouterr()
    assert not sys_stdout
    assert not sys_stderr


def test_run_async_callback_exception_propagates():
    """Exceptions from an async callback propagate through run() too."""
    with pytest.raises(ExceptionGroup) as exc_info:
        run("echo 111", on_stdout=async_bad_callback)
    assert len(exc_info.value.exceptions) == 1
    assert isinstance(exc_info.value.exceptions[0], ValueError)
    assert str(exc_info.value.exceptions[0]) == "async callback error"
