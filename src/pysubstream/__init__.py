from __future__ import annotations

import functools
import importlib.metadata
import inspect
import io
import subprocess
import sys
import typing as T
from collections.abc import Callable, Coroutine, Sequence

if T.TYPE_CHECKING:
    from anyio.abc import ByteSendStream
    from anyio.streams.text import TextReceiveStream

__version__ = importlib.metadata.version("pysubstream")

#: A callback that receives a chunk of text. May be sync or async.
StreamCallback = Callable[[str], T.Any] | Callable[[str], Coroutine[T.Any, T.Any, T.Any]]

__all__: list[str] = [
    "StreamCallback",
    "__version__",
    "async_run",
    "run",
]


async def _handle_stream(
    input_stream: TextReceiveStream,
    buffer: io.StringIO,
    callback: StreamCallback | None = None,
) -> None:
    """Read from *input_stream*, buffering every chunk.

    Args:
        input_stream: The text stream to read from.
        buffer: StringIO buffer that accumulates all chunks unconditionally.
        callback: Optional callable invoked with each chunk of text as it arrives.
            May be a regular function or an async function.
            When ``None``, chunks are only buffered.
    """
    async for line in input_stream:
        _ = buffer.write(line)
        if callback is not None:
            result = callback(line)
            if inspect.isawaitable(result):
                await result


async def _feed_stdin(stream: ByteSendStream, data: bytes) -> None:
    """Write *data* to the subprocess's stdin, then close the stream."""
    try:
        await stream.send(data)
    finally:
        await stream.aclose()


# Sentinel meaning "use the default echo callback (sys.stdout.write / sys.stderr.write)".
# A sentinel (rather than None or sys.stdout.write directly) because:
#   1. None already means "suppress output", so we need a third value for "use default".
#   2. Deferring the sys.stdout/sys.stderr lookup to call time is correct when stdout
#      has been redirected (e.g. pytest capsys, rich console, contextlib.redirect_stdout).
_ECHO: T.Any = object()


async def async_run(
    cmd: str | bytes | Sequence[str | bytes],
    *,
    input: str | None = None,
    stdin: int | T.IO[str] | None = None,
    stdout: int | T.IO[str] | None = subprocess.PIPE,
    stderr: int | T.IO[str] | None = subprocess.PIPE,
    check: bool = False,
    timeout: float = 60,
    on_stdout: StreamCallback | None = _ECHO,
    on_stderr: StreamCallback | None = _ECHO,
    **kwargs: T.Any,  # pyright: ignore[reportAny]
) -> subprocess.CompletedProcess[str]:
    """
    Run a command asynchronously and return a `subprocess.CompletedProcess`.

    The `stdout` and `stderr` parameters are used to specify where the standard output and
    standard error of the command should be directed. By default, both `stdout` and `stderr`
    are set to [PIPE][subprocess.PIPE], which means that the output and error are captured
    and available to you in the object returned by the function ([CompletedProcess][subprocess.CompletedProcess]).
    This allows for programmatic access and manipulation of the command's output and error streams.
    Documentation of all the supported values is provided in the
    [StdLib docs](https://docs.python.org/3/library/subprocess.html#subprocess.Popen).

    `on_stdout` and `on_stderr` control what happens with each chunk of text as it arrives.
    By default they write to `sys.stdout` / `sys.stderr`. Pass a custom callable (sync or async)
    to process chunks yourself, or ``None`` to suppress output. In certain cases, depending on the
    values you pass to `stdout` and `stderr`, these arguments might have no effect (for example if
    you pass an open file then the process writes directly to that file and there are no chunks to
    forward).

    Args:
        cmd: The command to run.
        input: A string to feed to the process's standard input. The stdin stream is
            closed after the data is written. May not be used together with *stdin*.
        stdin: The standard input option. Defaults to ``None`` (inherit from parent).
            Accepts the same values as [subprocess.Popen](https://docs.python.org/3/library/subprocess.html#subprocess.Popen).
            May not be used together with *input*.
        stdout: The standard output option. Defaults to subprocess.PIPE.
        stderr: The standard error option. Defaults to subprocess.PIPE.
        check: If True, checks the return code. Defaults to False.
        timeout: The timeout for the command. Defaults to 60.
        on_stdout: Callback invoked with each chunk of stdout text as it arrives.
            May be a regular function or an async function.
            Defaults to ``sys.stdout.write``. Pass ``None`` to suppress output.
        on_stderr: Callback invoked with each chunk of stderr text as it arrives.
            May be a regular function or an async function.
            Defaults to ``sys.stderr.write``. Pass ``None`` to suppress output.
        **kwargs: Additional keyword arguments to be passed to `anyio.open_process()`.
            Common options include `cwd` and `env`.

    Returns:
        subprocess.CompletedProcess: The completed process.

    Raises:
        ValueError: If both *stdin* and *input* are provided.
        subprocess.TimeoutExpired: If the command times out.
        subprocess.CalledProcessError: If the command returns a non-zero exit code and `check` is True.
    """
    import anyio.streams.text

    if input is not None and stdin is not None:
        raise ValueError("stdin and input arguments may not both be used.")
    if input is not None:
        stdin = subprocess.PIPE

    if on_stdout is _ECHO:
        on_stdout = sys.stdout.write
    if on_stderr is _ECHO:
        on_stderr = sys.stderr.write

    stdout_buffer = io.StringIO() if stdout == subprocess.PIPE else None
    stderr_buffer = io.StringIO() if stderr == subprocess.PIPE else None
    proc = await anyio.open_process(
        command=cmd,
        stdin=stdin,
        stdout=stdout,
        stderr=stderr,
        **kwargs,  # pyright: ignore[reportAny]
    )

    try:
        with anyio.fail_after(timeout):
            async with proc:
                async with anyio.create_task_group() as tg:
                    if input is not None and proc.stdin is not None:
                        tg.start_soon(_feed_stdin, proc.stdin, input.encode())

                    if proc.stdout is not None and stdout_buffer is not None:
                        proc_stdout = anyio.streams.text.TextReceiveStream(transport_stream=proc.stdout)
                        tg.start_soon(_handle_stream, proc_stdout, stdout_buffer, on_stdout)

                    if proc.stderr is not None and stderr_buffer is not None:
                        proc_stderr = anyio.streams.text.TextReceiveStream(transport_stream=proc.stderr)
                        tg.start_soon(_handle_stream, proc_stderr, stderr_buffer, on_stderr)

                if proc.returncode is None:
                    _ = await proc.wait()

    except TimeoutError as exc:
        raise subprocess.TimeoutExpired(
            cmd=cmd,
            timeout=timeout,
            output=stdout_buffer.getvalue() if stdout_buffer is not None else "",
            stderr=stderr_buffer.getvalue() if stderr_buffer is not None else "",
        ) from exc

    stdout_result = stdout_buffer.getvalue() if stdout_buffer is not None else ""
    stderr_result = stderr_buffer.getvalue() if stderr_buffer is not None else ""

    if check and proc.returncode:
        raise subprocess.CalledProcessError(
            cmd=cmd,
            returncode=proc.returncode,
            output=stdout_result,
            stderr=stderr_result,
        )

    return subprocess.CompletedProcess(
        args=cmd,
        returncode=T.cast(int, proc.returncode),
        stdout=stdout_result,
        stderr=stderr_result,
    )


def run(
    cmd: str | bytes | Sequence[str | bytes],
    *,
    input: str | None = None,
    stdin: int | T.IO[str] | None = None,
    stdout: int | T.IO[str] | None = subprocess.PIPE,
    stderr: int | T.IO[str] | None = subprocess.PIPE,
    check: bool = False,
    timeout: float = 60,
    on_stdout: StreamCallback | None = _ECHO,
    on_stderr: StreamCallback | None = _ECHO,
    **kwargs: T.Any,  # pyright: ignore[reportAny]
) -> subprocess.CompletedProcess[str]:
    """
    Run a command and return a `subprocess.CompletedProcess`.

    The `stdout` and `stderr` parameters are used to specify where the standard output and
    standard error of the command should be directed. Documentation of the supported values
    is provided in the [StdLib docs](https://docs.python.org/3/library/subprocess.html#subprocess.Popen).

    By default, both `stdout` and `stderr` are set to `subprocess.PIPE`, which means that the output
    and error are captured and available to you in the `CompletedProcess` object returned by the function.
    This allows you to programmatically access and manipulate the command's output and error.

    `on_stdout` and `on_stderr` control what happens with each chunk of text as it arrives.
    By default they write to `sys.stdout` / `sys.stderr`. Pass a custom callable (sync or async)
    to process chunks yourself, or ``None`` to suppress output. In certain cases, depending on the
    values you pass to `stdout` and `stderr`, these arguments might have no effect (for example if
    you pass an open file then the process writes directly to that file and there are no chunks to
    forward).

    Args:
        cmd: The command to run.
        input: A string to feed to the process's standard input. The stdin stream is
            closed after the data is written. May not be used together with *stdin*.
        stdin: The standard input option. Defaults to ``None`` (inherit from parent).
            May not be used together with *input*.
        stdout: The standard output option. Defaults to subprocess.PIPE.
        stderr: The standard error option. Defaults to subprocess.PIPE.
        check: If True, checks the return code. Defaults to False.
        timeout: The timeout for the command. Defaults to 60.
        on_stdout: Callback invoked with each chunk of stdout text as it arrives.
            May be a regular function or an async function.
            Defaults to ``sys.stdout.write``. Pass ``None`` to suppress output.
        on_stderr: Callback invoked with each chunk of stderr text as it arrives.
            May be a regular function or an async function.
            Defaults to ``sys.stderr.write``. Pass ``None`` to suppress output.
        **kwargs: Additional keyword arguments to be passed to `anyio.open_process()`.
            Common options include `cwd` and `env`.

    Returns:
        subprocess.CompletedProcess: The completed process.

    Raises:
        ValueError: If both *stdin* and *input* are provided.
        subprocess.TimeoutExpired: If the command times out.
        subprocess.CalledProcessError: If the command returns a non-zero exit code and `check` is True.

    """
    import anyio

    return anyio.run(
        functools.partial(
            async_run,
            cmd=cmd,
            input=input,
            stdin=stdin,
            on_stdout=on_stdout,
            on_stderr=on_stderr,
            stdout=stdout,
            stderr=stderr,
            check=check,
            timeout=timeout,
            **kwargs,
        ),
    )
