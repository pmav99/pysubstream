## Cookbook

Intent-based recipes for common tasks. Each recipe is self-contained and copy-pasteable.

---

### How do I run a command and capture its output?

By default, `pysubstream.run()` captures both stdout and stderr while also streaming them to the console:

```python
import pysubstream

proc = pysubstream.run("ls -la")
print(proc.stdout)  # captured stdout
print(proc.stderr)  # captured stderr
print(proc.returncode)  # exit code
```

---

### How do I capture output without printing to the console?

Pass `on_stdout=None` and `on_stderr=None`:

```python
proc = pysubstream.run(
    "echo hello; echo error >&2",
    on_stdout=None,
    on_stderr=None,
)
assert proc.stdout == "hello\n"
assert proc.stderr == "error\n"
# Nothing printed to console
```

---

### How do I process output in real-time?

Pass a callback to `on_stdout` or `on_stderr`. Output is still captured in the returned `CompletedProcess` regardless:

```python
import pysubstream

lines = []
proc = pysubstream.run("echo line1; echo line2", on_stdout=lines.append)
assert lines == ["line1\n", "line2\n"]
assert proc.stdout == "line1\nline2\n"  # always captured
```

---

### How do I log output to a file while also capturing it?

Use a callback that writes to a file:

```python
import pysubstream

with open("build.log", "w") as log:
    proc = pysubstream.run(
        "make build",
        on_stdout=lambda chunk: log.write(chunk),
        on_stderr=lambda chunk: log.write(chunk),
    )
# proc.stdout and proc.stderr have the captured output
# build.log has the same output written to disk
```

---

### How do I raise an exception on command failure?

Set `check=True`:

```python
import subprocess
import pysubstream

try:
    pysubstream.run("exit 1", check=True)
except subprocess.CalledProcessError as exc:
    print(exc.returncode)  # 1
    print(exc.stdout)  # captured stdout
    print(exc.stderr)  # captured stderr
```

---

### How do I set a timeout?

Pass `timeout` in seconds. Default is 60:

```python
import subprocess
import pysubstream

try:
    pysubstream.run("sleep 300", timeout=10)
except subprocess.TimeoutExpired as exc:
    print(f"Timed out after {exc.timeout}s")
```

---

### How do I run a command in a specific directory?

Use the `cwd` parameter:

```python
proc = pysubstream.run("ls", cwd="/tmp")
```

---

### How do I pass environment variables?

Use the `env` parameter. **Important**: this replaces the entire environment, it does not extend it.

```python
import os
import pysubstream

# Replace the entire environment (only MY_VAR will be set):
proc = pysubstream.run("env", env={"MY_VAR": "hello"})

# Extend the current environment with additional variables:
proc = pysubstream.run("env", env={**os.environ, "MY_VAR": "hello"})
```

---

### How do I merge stderr into stdout?

Pass `stderr=subprocess.STDOUT`:

```python
import subprocess
import pysubstream

proc = pysubstream.run(
    "echo out; echo err >&2",
    stderr=subprocess.STDOUT,
)
assert "out" in proc.stdout
assert "err" in proc.stdout
assert proc.stderr == ""
```

---

### How do I redirect output to a file?

Pass an open file object to `stdout` or `stderr`:

```python
with open("output.txt", "w") as f:
    proc = pysubstream.run("echo hello", stdout=f)

assert proc.stdout == ""  # not captured when redirected to file
```

!!! note
    When redirecting to a file, `on_stdout`/`on_stderr` callbacks have no effect and `CompletedProcess` returns empty strings for the redirected streams.

---

### How do I discard output entirely?

Use `subprocess.DEVNULL`:

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

---

### How do I run a command without shell interpretation?

Pass a list instead of a string:

```python
# With shell (string) — shell features like pipes and redirects work
proc = pysubstream.run("echo $HOME | tr '/' '-'")

# Without shell (list) — safer, no injection risk
proc = pysubstream.run(["echo", "hello world"])
```

---

### How do I use pysubstream in async code?

Use `async_run()` instead of `run()`. Same parameters and return type:

```python
import pysubstream


async def main():
    proc = await pysubstream.async_run(["echo", "hello"])
    assert proc.stdout.strip() == "hello"
```

!!! warning
    Do not call `pysubstream.run()` from within an async event loop. Use `async_run()` instead.

---

### How do I migrate from subprocess.run()?

```python
# Before (subprocess)
import subprocess

result = subprocess.run(["ls", "-la"], capture_output=True, text=True, timeout=30)
print(result.stdout)

# After (pysubstream) — capture is the default, text mode is always on
import pysubstream

result = pysubstream.run(["ls", "-la"], timeout=30, on_stdout=None)
print(result.stdout)
```

Key differences to watch for:

| subprocess.run() | pysubstream.run() |
|---|---|
| `capture_output=True` | Default behavior (always captured) |
| `text=True` | Always text mode (no binary) |
| `timeout=None` (infinite) | `timeout=60` (60 seconds) |
| No real-time streaming with capture | Streams by default (use `on_stdout=None` to silence) |
