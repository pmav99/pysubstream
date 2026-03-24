# pysubstream

[![PyPI - Version](https://img.shields.io/pypi/v/pysubstream.svg)](https://pypi.org/project/pysubstream)
[![PyPI - Python Version](https://img.shields.io/pypi/pyversions/pysubstream.svg)](https://pypi.org/project/pysubstream)
[![ci](https://github.com/pmav99/pysubstream/workflows/test/badge.svg)](https://github.com/pmav99/pysubstream/actions?query=workflow%3Atest)

`subprocess.run()` that streams and captures at the same time.

> [!TIP]
> An [`llms.txt`](llms.txt) file is included for AI coding assistants.

## The problem

Python's `subprocess.run()` forces a tradeoff: you can **capture** output (for inspection) or **stream** it (for real-time display), but not both at once. And if you want stdout and stderr kept separate while streaming, the standard library makes it very difficult.

`pysubstream` solves this by using async I/O internally. You get a familiar synchronous API that returns `subprocess.CompletedProcess`, but both streams are captured **and** echoed in real-time by default.

## Installation

```
pip install pysubstream
```

## Quick start

```python
import pysubstream

# Streams to console in real-time AND captures output
proc = pysubstream.run("echo hello; echo error >&2")
print(proc.stdout)  # "hello\n"
print(proc.stderr)  # "error\n"
```

## Key features

- **Simultaneous streaming and capture** -- stdout and stderr are echoed to the console in real-time while also being captured in the returned `CompletedProcess` object.
- **Separate stdout/stderr** -- unlike workarounds that merge streams, pysubstream keeps them separate.
- **Custom callbacks** -- pass any callable to `on_stdout`/`on_stderr` to process output chunks as they arrive (e.g., log parsing, progress tracking).
- **Silent capture** -- pass `on_stdout=None` / `on_stderr=None` to capture without echoing.
- **Drop-in compatibility** -- returns standard `subprocess.CompletedProcess` objects; raises standard `subprocess.CalledProcessError` and `subprocess.TimeoutExpired` exceptions.
- **Async support** -- use `async_run()` directly in async code.

## Usage

### Capture without echoing to console

```python
proc = pysubstream.run("echo hello", on_stdout=None, on_stderr=None)
assert proc.stdout == "hello\n"  # captured, but nothing printed
```

### Custom callbacks

```python
lines = []
proc = pysubstream.run("echo hello", on_stdout=lines.append)
assert lines == ["hello\n"]
assert proc.stdout == "hello\n"  # always captured regardless of callback
```

### Error handling

```python
import subprocess

# Raises CalledProcessError on non-zero exit
try:
    pysubstream.run("exit 1", check=True)
except subprocess.CalledProcessError as e:
    print(e.returncode)  # 1

# Raises TimeoutExpired
try:
    pysubstream.run("sleep 60", timeout=2)
except subprocess.TimeoutExpired:
    print("timed out")
```

### Async usage

```python
import pysubstream

result = await pysubstream.async_run(["echo", "hello"])
assert result.stdout.strip() == "hello"
```

## Differences from `subprocess.run()`

| Behavior | `subprocess.run()` | `pysubstream.run()` |
|---|---|---|
| Default stdout/stderr | Not captured (`None`) | Captured (`PIPE`) |
| Real-time streaming | Not supported with capture | Enabled by default |
| Separate stdout/stderr while streaming | Very difficult | Built-in |
| Default timeout | None (waits forever) | 60 seconds |

## Alternatives

- **[subprocess-tee](https://github.com/pycontribs/subprocess-tee)** -- solves the same core problem (tee-style stream + capture) using asyncio internally. Key differences: no public async API (cannot be called from a running event loop), no per-stream callbacks, line-buffered only, and `input`/`timeout` parameters are accepted but not functional. `pysubstream` uses anyio for structured concurrency, exposes both sync and async APIs, supports independent `on_stdout`/`on_stderr` callbacks, and enforces timeouts.

## License

`pysubstream` is distributed under the terms of the [MIT](https://spdx.org/licenses/MIT.html) license.
