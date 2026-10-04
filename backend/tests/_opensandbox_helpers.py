"""Shared fake-SDK family for the OpenSandbox provider tests.

One coherent test-double family (message/execution shapes, file and command
fakes, the fake sandbox class, config stubs, and the install/box helpers) so
both ``tests/test_opensandbox_provider.py`` and
``tests/blocking_io/test_opensandbox_acquire.py`` import it from here instead
of one test module importing another — a collected test module must never be
someone else's fixture library.
"""

from __future__ import annotations

import re
import shlex
import types
from dataclasses import dataclass, field
from datetime import timedelta
from typing import Any

import pytest

from deerflow.community.opensandbox.provider import OpenSandboxProvider
from deerflow.community.opensandbox.sandbox import OpenSandboxSandbox


@dataclass
class _Message:
    text: str


@dataclass
class _Result:
    text: str | None


@dataclass
class _Logs:
    stdout: list[_Message] = field(default_factory=list)
    stderr: list[_Message] = field(default_factory=list)


@dataclass
class _Execution:
    exit_code: int | None = 0
    logs: _Logs = field(default_factory=_Logs)
    result: list[_Result] = field(default_factory=list)


def _execution(*, stdout: tuple[str, ...] = (), stderr: tuple[str, ...] = (), result: tuple[str, ...] = (), exit_code: int | None = 0) -> _Execution:
    return _Execution(
        exit_code=exit_code,
        logs=_Logs(
            stdout=[_Message(text) for text in stdout],
            stderr=[_Message(text) for text in stderr],
        ),
        result=[_Result(text) for text in result],
    )


@dataclass
class _FakeRunCommandOpts:
    background: bool = False
    working_directory: str | None = None
    timeout: timedelta | None = None
    uid: int | None = None
    gid: int | None = None
    envs: dict[str, str] | None = None


class _FakeFiles:
    def __init__(self, owner: _FakeRemote) -> None:
        self._owner = owner
        self.calls: list[tuple[str, str]] = []

    def _guard(self) -> None:
        if self._owner.file_error is not None:
            raise self._owner.file_error

    def read_file(self, path: str, *, encoding: str = "utf-8") -> str:
        self._guard()
        self.calls.append(("read_file", path))
        if path not in self._owner.file_data:
            raise FileNotFoundError(path)
        return self._owner.file_data[path].decode(encoding, errors="replace")

    def read_bytes(self, path: str) -> bytes:
        self._guard()
        self.calls.append(("read_bytes", path))
        if path not in self._owner.file_data:
            raise FileNotFoundError(path)
        return self._owner.file_data[path]

    def read_bytes_stream(self, path: str):
        self._guard()
        self.calls.append(("read_bytes_stream", path))
        if path not in self._owner.file_data:
            raise FileNotFoundError(path)
        data = self._owner.file_data[path]
        try:
            yield from (data[index : index + 3] for index in range(0, len(data), 3))
        finally:
            self._owner.stream_closed = True

    def write_file(self, path: str, data: str | bytes, *, mode: int = 755) -> None:
        self._guard()
        self.calls.append(("write_file", path))
        self._owner.file_data[path] = data.encode() if isinstance(data, str) else bytes(data)
        parent = path.rsplit("/", 1)[0]
        while parent:
            self._owner.directories.add(parent)
            parent = parent.rsplit("/", 1)[0]


class _FakeCommands:
    def __init__(self, owner: _FakeRemote) -> None:
        self._owner = owner
        self.calls: list[tuple[str, _FakeRunCommandOpts | None]] = []

    def run(self, command: str, *, opts: _FakeRunCommandOpts | None = None) -> _Execution:
        self.calls.append((command, opts))
        if self._owner.command_error is not None:
            raise self._owner.command_error
        if command.startswith("mkdir -p /mnt/user-data/"):
            return _execution(stderr=("bootstrap failed",), exit_code=self._owner.bootstrap_exit_code)
        if command == "true":
            return _execution(exit_code=self._owner.health_exit_code)
        if command == "mixed-output":
            return _execution(stdout=("out-1", "out-2"), stderr=("err-1",), exit_code=7)
        if command == "result-output":
            return _execution(stdout=("stdout",), result=("result",), stderr=("stderr",))
        if command == "silent-failure":
            return _execution(exit_code=9)
        if command == "missing-complete":
            return _execution(stderr=("stream ended",), exit_code=None)
        if "__DF_SEARCH_STATUS__:" in command:
            return self._search(command)
        if command.startswith("find ") or "find -H " in command:
            return self._find(command)
        if command.startswith(("grep ", "{ grep ")):
            return self._grep(command)
        return _execution()

    def _find(self, command: str) -> _Execution:
        match = re.search(r"(?:^|[\s;{])find(?:\s+-[HLP])*\s+(\S+)", command)
        root = (match.group(1).strip("'\"") if match else "").rstrip("/") or "/"
        include_dirs = "-type d" in command
        paths = list(self._owner.file_data)
        if include_dirs:
            paths.extend(self._owner.directories)
        matches = sorted(path for path in set(paths) if path == root or path.startswith(f"{root}/"))
        if "__DF_FIND_STATUS__:" in command:
            status = 0 if matches else 1
            marker = "__DF_FIND_STATUS__:0" if matches else "__DF_FIND_STATUS__:missing"
            stdout = (*matches, "", marker) if matches else ("", marker)
            return _execution(stdout=stdout, exit_code=status)
        return _execution(stdout=tuple(matches))

    def _grep(self, command: str) -> _Execution:
        tokens = shlex.split(command)
        pattern = tokens[tokens.index("-e") + 1]
        root = tokens[tokens.index("-e") + 2].rstrip("/")
        flags = 0 if "-i" not in tokens else re.IGNORECASE
        literal = "-F" in tokens
        rows: list[str] = []
        for path, data in sorted(self._owner.file_data.items()):
            if path != root and not path.startswith(f"{root}/"):
                continue
            for line_number, line in enumerate(data.decode(errors="replace").splitlines(), start=1):
                matched = pattern.lower() in line.lower() if literal and flags else pattern in line if literal else re.search(pattern, line, flags) is not None
                if matched:
                    rows.append(f"{path}:{line_number}:{line}")
        if self._owner.grep_duplicate_rows:
            rows.extend(rows)
        return _execution(stdout=tuple(rows))

    def _search(self, command: str) -> _Execution:
        # remote_search_command: a root-existence check, then the wrapped search and its status marker.
        root = shlex.split(re.search(r"\[ ! -e (.+?) \]; then", command).group(1))[0].rstrip("/") or "/"
        paths = set(self._owner.file_data) | set(self._owner.directories)
        if not any(path == root or path.startswith(f"{root}/") for path in paths):
            return _execution(stdout=("__DF_SEARCH_STATUS__:missing",))
        inner = command[command.index("{ ") + 2 : command.index('; echo $? > "$_st"; }')]
        if inner.startswith("find "):
            rows, status = [message.text for message in self._find(inner).logs.stdout], 0
        else:
            rows = [message.text for message in self._grep(inner).logs.stdout]
            status = 0 if rows else 1
        return _execution(stdout=(*rows, "", f"__DF_SEARCH_STATUS__:{status}"))


class _FakeRemote:
    def __init__(self, remote_id: str, *, bootstrap_exit_code: int | None = 0) -> None:
        self.id = remote_id
        self.bootstrap_exit_code = bootstrap_exit_code
        self.health_exit_code: int | None = 0
        self.command_error: Exception | None = None
        self.file_error: Exception | None = None
        self.renew_error: Exception | None = None
        self.renew_calls: list[timedelta] = []
        self.destroy_calls = 0
        self.file_data: dict[str, bytes] = {}
        self.directories: set[str] = set()
        self.stream_closed = False
        self.grep_duplicate_rows = False
        self.commands = _FakeCommands(self)
        self.files = _FakeFiles(self)

    def renew(self, timeout: timedelta) -> None:
        self.renew_calls.append(timeout)
        if self.renew_error is not None:
            raise self.renew_error

    def destroy(self) -> None:
        self.destroy_calls += 1


class _FakeSandboxClass:
    def __init__(self, remote_factory=None) -> None:
        self.remote_factory = remote_factory
        self.create_calls: list[dict[str, Any]] = []
        self.remotes: list[_FakeRemote] = []

    def create(self, image: str, **kwargs: Any) -> _FakeRemote:
        self.create_calls.append({"image": image, **kwargs})
        index = len(self.remotes) + 1
        remote = self.remote_factory(index) if self.remote_factory is not None else _FakeRemote(f"remote-{index}")
        self.remotes.append(remote)
        return remote


class _FakeConnectionConfig:
    def __init__(self, **kwargs: Any) -> None:
        self.kwargs = kwargs


class _TerminalApiError(RuntimeError):
    def __init__(self, message: str, status_code: int = 404) -> None:
        super().__init__(message)
        self.status_code = status_code


def _stub_config(attrs: dict[str, Any] | None = None) -> types.SimpleNamespace:
    values = {"idle_timeout": 0, **(attrs or {})}
    return types.SimpleNamespace(sandbox=types.SimpleNamespace(**values))


def _install(monkeypatch: pytest.MonkeyPatch, *, sdk: _FakeSandboxClass | None = None, config: dict[str, Any] | None = None) -> tuple[OpenSandboxProvider, _FakeSandboxClass]:
    fake_sdk = sdk or _FakeSandboxClass()
    monkeypatch.setattr("deerflow.community.opensandbox.provider.get_app_config", lambda: _stub_config(config))
    monkeypatch.setattr(
        "deerflow.community.opensandbox.provider._import_sdk",
        lambda: (fake_sdk, _FakeConnectionConfig, _FakeRunCommandOpts),
    )
    return OpenSandboxProvider(), fake_sdk


def _box(
    remote: _FakeRemote,
    *,
    on_terminal_failure=None,
    default_env=None,
    sandbox_timeout: timedelta | None = None,
    default_command_timeout: float = 600,
) -> OpenSandboxSandbox:
    return OpenSandboxSandbox(
        "sandbox-id",
        remote,
        run_command_opts_cls=_FakeRunCommandOpts,
        default_env=default_env,
        sandbox_timeout=sandbox_timeout,
        default_command_timeout=default_command_timeout,
        on_terminal_failure=on_terminal_failure,
    )
