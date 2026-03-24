## pysubstream

<!-- pysubstream: simultaneously stream and capture subprocess stdout/stderr in Python. -->
<!-- Exports: pysubstream.run() (sync) and pysubstream.async_run() (async). -->
<!-- Returns subprocess.CompletedProcess[str]. Requires Python >= 3.11. -->

`pysubstream` is a Python library that provides a `subprocess`-like API which simultaneously **streams** and **captures** stdout/stderr. It uses [anyio](https://anyio.readthedocs.io/) internally for async I/O, but exposes a simple synchronous `run()` function alongside the async `async_run()`.

## The problem

Python's [`subprocess`][subprocess] module forces you to choose:

- **Capture** output (set `stdout=PIPE`) -- you can inspect it after the process finishes, but you see nothing in real-time.
- **Stream** output (leave `stdout=None` or pass a file descriptor) -- you see it in real-time, but can't easily access it programmatically afterward.

Doing both at once -- especially while keeping stdout and stderr as **separate streams** -- is surprisingly difficult with the standard library.

### How pysubstream solves this

By leveraging async I/O, `pysubstream` reads from both stdout and stderr concurrently. Each chunk of text is:

1. **Buffered** into a `StringIO` for later access (always).
2. **Forwarded** to a callback for real-time processing (configurable).

This means you always get a `subprocess.CompletedProcess` with captured output, and you can simultaneously echo, log, parse, or transform the output as it arrives.

## Quick start

```python
import pysubstream

# Runs the command, streams output to console, and captures it
proc = pysubstream.run("echo hello; echo error >&2")

print(proc.stdout)  # "hello\n"
print(proc.stderr)  # "error\n"
print(proc.returncode)  # 0
```

## API overview

`pysubstream` exports two functions:

| Function | Description |
|---|---|
| [`run()`][pysubstream.run] | Synchronous. Runs a command and returns `subprocess.CompletedProcess`. |
| [`async_run()`][pysubstream.async_run] | Async. Same behavior, for use in async code. |

Both accept the same parameters and return `subprocess.CompletedProcess[str]`.

### Parameters

All parameters are keyword-only except `cmd`.

| Parameter | Type | Default | Description |
|---|---|---|---|
| `cmd` | `str \| bytes \| Sequence[str \| bytes]` | *(required)* | The command to run. Strings are executed via the shell; sequences are executed directly. |
| `stdout` | `int \| IO[str] \| None` | `subprocess.PIPE` | Where to direct stdout. Accepts `PIPE`, `DEVNULL`, `None`, or an open file object. |
| `stderr` | `int \| IO[str] \| None` | `subprocess.PIPE` | Where to direct stderr. Also accepts `subprocess.STDOUT` to merge into stdout. |
| `check` | `bool` | `False` | If `True`, raise `subprocess.CalledProcessError` on non-zero exit. |
| `timeout` | `float` | `60` | Seconds to wait before raising `subprocess.TimeoutExpired`. |
| `cwd` | `str \| bytes \| PathLike \| None` | `None` | Working directory for the subprocess. |
| `env` | `Mapping[str, str] \| None` | `None` | Environment variables. **Replaces** (does not extend) the current environment. |
| `on_stdout` | `Callable[[str], Any] \| None` | `sys.stdout.write` | Callback invoked with each stdout chunk. Pass `None` to suppress console output. |
| `on_stderr` | `Callable[[str], Any] \| None` | `sys.stderr.write` | Callback invoked with each stderr chunk. Pass `None` to suppress console output. |
| `start_new_session` | `bool` | `False` | If `True`, run the subprocess in a new session. |
| `**kwargs` | | | Additional keyword arguments passed to `anyio.open_process()`. |

### Return value

Both functions return [`subprocess.CompletedProcess[str]`](https://docs.python.org/3/library/subprocess.html#subprocess.CompletedProcess) with:

- `args` -- the command as passed.
- `returncode` -- the process exit code.
- `stdout` -- captured stdout as a string (empty string if stdout was not piped).
- `stderr` -- captured stderr as a string (empty string if stderr was not piped).

### Exceptions

| Exception | When raised |
|---|---|
| `subprocess.CalledProcessError` | Non-zero exit code **and** `check=True`. The exception's `.stdout` and `.stderr` contain the captured output. |
| `subprocess.TimeoutExpired` | The process exceeds `timeout` seconds. The exception's `.output` and `.stderr` contain any output captured before the timeout. |

## Differences from `subprocess.run()`

| Behavior | `subprocess.run()` | `pysubstream.run()` |
|---|---|---|
| Default stdout/stderr | Not captured (`None`) | Captured (`PIPE`) |
| Real-time streaming | Not possible when capturing | Enabled by default |
| Separate stdout/stderr while streaming | Very difficult | Built-in |
| Default timeout | `None` (waits forever) | `60` seconds |
| Return type | `CompletedProcess` | `CompletedProcess` (identical) |
| Exception types | `CalledProcessError`, `TimeoutExpired` | Same (identical) |

## Usage examples

### Capture without echoing to console

Pass `on_stdout=None` and/or `on_stderr=None` to suppress real-time output while still capturing:

```python
proc = pysubstream.run(
    "echo hello; echo error >&2",
    on_stdout=None,
    on_stderr=None,
)
assert proc.stdout == "hello\n"  # captured
assert proc.stderr == "error\n"  # captured
# Nothing was printed to the console
```

### Custom callbacks for real-time processing

Pass any callable to `on_stdout` / `on_stderr`. Output is still captured in the returned `CompletedProcess` regardless of the callback:

```python
stdout_lines = []
stderr_lines = []

proc = pysubstream.run(
    "echo out1; echo err1 >&2",
    on_stdout=stdout_lines.append,
    on_stderr=stderr_lines.append,
)

assert stdout_lines == ["out1\n"]
assert stderr_lines == ["err1\n"]
assert proc.stdout == "out1\n"  # always captured
assert proc.stderr == "err1\n"  # always captured
```

### Error handling

```python
import subprocess
import pysubstream

# Non-zero exit with check=True raises CalledProcessError
try:
    pysubstream.run("exit 1", check=True)
except subprocess.CalledProcessError as exc:
    print(exc.returncode)  # 1
    print(exc.stdout)  # ""
    print(exc.stderr)  # ""

# Timeout raises TimeoutExpired
try:
    pysubstream.run("sleep 60", timeout=2)
except subprocess.TimeoutExpired as exc:
    print(exc.timeout)  # 2
```

### Redirect to files

When stdout/stderr are redirected to file objects, the process writes directly to those files. The callbacks have no effect and the returned `CompletedProcess` has empty strings for the redirected streams:

```python
with open("out.txt", "w") as f:
    proc = pysubstream.run("echo hello", stdout=f)

assert proc.stdout == ""  # not captured when redirected to file
assert open("out.txt").read() == "hello\n"
```

### Merge stderr into stdout

```python
import subprocess
import pysubstream

proc = pysubstream.run(
    "echo out; echo err >&2",
    stderr=subprocess.STDOUT,
)
assert proc.stdout == "out\nerr\n"  # both streams merged
assert proc.stderr == ""
```

### Discard output

```python
import subprocess
import pysubstream

proc = pysubstream.run(
    "echo hello",
    stdout=subprocess.DEVNULL,
    stderr=subprocess.DEVNULL,
)
assert proc.stdout == ""
assert proc.stderr == ""
```

### Set working directory and environment

```python
proc = pysubstream.run("pwd", cwd="/tmp")
assert "/tmp" in proc.stdout

proc = pysubstream.run("env", env={"MY_VAR": "hello"})
assert "MY_VAR=hello" in proc.stdout
```

### Command types

Commands can be strings (executed via shell) or sequences (executed directly):

```python
# String -- executed via /bin/sh
proc = pysubstream.run("echo hello && echo world")

# List of strings -- executed directly (no shell)
proc = pysubstream.run(["echo", "hello"])

# Bytes also work
proc = pysubstream.run(b"echo hello")
proc = pysubstream.run([b"echo", b"hello"])
```

### Async usage

Use `async_run()` in async code. It has the same parameters and return type as `run()`:

```python
import pysubstream


async def main():
    result = await pysubstream.async_run(["echo", "hello"])
    assert result.stdout.strip() == "hello"

    # With custom callback
    lines = []
    result = await pysubstream.async_run(
        ["echo", "hello"],
        on_stdout=lines.append,
    )
    assert lines == ["hello\n"]
```

## Gotchas and caveats

A few things to watch out for when using `pysubstream`:

- **`env` replaces the environment** -- it does *not* extend `os.environ`. To add a variable while preserving the rest: `env={**os.environ, "MY_VAR": "value"}`.
- **File redirects disable callbacks** -- when `stdout` or `stderr` is set to an open file object, `on_stdout`/`on_stderr` have no effect and `CompletedProcess` returns empty strings for those streams.
- **Default timeout is 60 seconds** -- unlike `subprocess.run()` which waits forever, `pysubstream` defaults to 60 seconds.
- **Always text mode** -- output is always `str`, never `bytes`. There is no binary mode.
- **Don't call `run()` from async code** -- `run()` calls `anyio.run()` internally, which fails inside an existing event loop. Use `async_run()` in async contexts.
- **String commands use the shell** -- `"echo hello"` runs via `/bin/sh`. Use `["echo", "hello"]` for direct execution without shell interpretation.

[subprocess]: https://docs.python.org/3/library/subprocess.html
