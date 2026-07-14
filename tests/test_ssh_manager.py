import os
import subprocess
import threading
import time
from pathlib import Path

from easytunnel.models import TunnelConfig, TunnelState
from easytunnel.ssh_manager import SSHManager


def config(key: Path, **changes: object) -> TunnelConfig:
    values = {
        "name": "RDP",
        "ssh_host": "pi.solitude.love",
        "username": "pi",
        "identity_file": str(key),
        "local_port": 13389,
        "remote_host": "192.168.3.88",
        "remote_port": 3389,
    }
    values.update(changes)
    return TunnelConfig(**values)


def option_value(args: list[str], option: str) -> str:
    return args[args.index(option) + 1]


def test_command_is_argument_list_and_matches_example(tmp_path: Path) -> None:
    key = tmp_path / "pi server"
    key.write_text("fake", encoding="utf-8")
    manager = SSHManager(ssh_executable=r"C:\Windows\System32\OpenSSH\ssh.exe")
    args = manager.build_command(config(key))

    assert isinstance(args, list)
    assert option_value(args, "-i") == str(key.resolve())
    assert option_value(args, "-L") == "127.0.0.1:13389:192.168.3.88:3389"
    assert "ExitOnForwardFailure=yes" in args
    assert "BatchMode=yes" in args
    assert option_value(args, "-F") == os.devnull
    assert "-N" in args
    assert args[-1] == "pi@pi.solitude.love"


def test_ipv6_hosts_are_bracketed_in_forward_spec(tmp_path: Path) -> None:
    manager = SSHManager(ssh_executable="ssh")
    args = manager.build_command(config(tmp_path / "key", bind_host="::1", remote_host="fd00::88"))
    assert option_value(args, "-L") == "[::1]:13389:[fd00::88]:3389"


def test_strict_host_key_mode_is_explicit(tmp_path: Path) -> None:
    manager = SSHManager(ssh_executable="ssh")
    default_args = manager.build_command(config(tmp_path / "key"))
    strict_args = manager.build_command(config(tmp_path / "key", strict_host_key=True))
    assert "StrictHostKeyChecking=accept-new" in default_args
    assert "StrictHostKeyChecking=yes" in strict_args


def test_start_failure_is_reflected_in_snapshot(tmp_path: Path) -> None:
    manager = SSHManager(ssh_executable="ssh")
    tunnel = config(tmp_path / "missing")
    manager.set_configs([tunnel])
    assert manager.start(tunnel.id) is False
    snapshot = manager.snapshot(tunnel.id)
    assert snapshot is not None
    assert snapshot.state == TunnelState.ERROR
    assert "私钥文件不存在" in snapshot.last_error


def test_duplicate_start_is_rejected_without_spawning(tmp_path: Path) -> None:
    key = tmp_path / "key"
    key.write_text("fake", encoding="utf-8")
    manager = SSHManager(ssh_executable="ssh")
    tunnel = config(key)
    manager.set_configs([tunnel])
    runtime = manager._items[tunnel.id]  # exercise the concurrency guard without network access
    runtime.state = TunnelState.CONNECTING
    assert manager.start(tunnel.id) is False


def test_friendly_openssh_errors() -> None:
    assert "公钥认证失败" in SSHManager._friendly_error("Permission denied (publickey).", 255)
    assert "端口已被占用" in SSHManager._friendly_error("bind: Address already in use", 255)
    assert "主机名" in SSHManager._friendly_error("Could not resolve hostname sample", 255)


def test_preview_quotes_key_path_with_spaces(tmp_path: Path) -> None:
    key = tmp_path / "a key"
    manager = SSHManager(ssh_executable="ssh")
    preview = manager.command_preview(config(key))
    assert str(key.resolve()) in preview
    if os.name == "nt":
        assert f'"{key.resolve()}"' in preview


class _BlockingOutput:
    def __init__(self, finished: threading.Event) -> None:
        self.finished = finished

    def __iter__(self) -> "_BlockingOutput":
        return self

    def __next__(self) -> str:
        self.finished.wait()
        raise StopIteration


class _FakeProcess:
    def __init__(self) -> None:
        self.pid = 4321
        self.returncode: int | None = None
        self.finished = threading.Event()
        self.stdout = _BlockingOutput(self.finished)
        self.terminated = False
        self.killed = False

    def poll(self) -> int | None:
        return self.returncode

    def wait(self, timeout: float | None = None) -> int:
        if not self.finished.wait(timeout):
            raise subprocess.TimeoutExpired("fake-ssh", timeout)
        return self.returncode or 0

    def terminate(self) -> None:
        self.terminated = True
        self.returncode = 0
        self.finished.set()

    def kill(self) -> None:
        self.killed = True
        self.returncode = -9
        self.finished.set()


def _wait_until(predicate: object, timeout: float = 1.5) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():  # type: ignore[operator]
            return True
        time.sleep(0.01)
    return False


def test_successful_lifecycle_reaches_connected_then_stops(tmp_path: Path, monkeypatch: object) -> None:
    key = tmp_path / "key"
    key.write_text("fake", encoding="utf-8")
    manager = SSHManager(ssh_executable="ssh", startup_timeout=0.2)
    tunnel = config(key)
    manager.set_configs([tunnel])
    fake = _FakeProcess()
    captured: dict[str, object] = {}

    def fake_popen(args: list[str], **kwargs: object) -> _FakeProcess:
        captured["args"] = args
        captured["kwargs"] = kwargs
        return fake

    monkeypatch.setattr(subprocess, "Popen", fake_popen)  # type: ignore[attr-defined]
    monkeypatch.setattr(manager, "_port_is_available", lambda *_: True)  # type: ignore[attr-defined]
    monkeypatch.setattr(manager, "_port_is_listening", lambda *_: True)  # type: ignore[attr-defined]

    assert manager.start(tunnel.id) is True
    assert _wait_until(lambda: manager.snapshot(tunnel.id).state == TunnelState.CONNECTED)  # type: ignore[union-attr]
    assert captured["kwargs"]["shell"] is False  # type: ignore[index]
    assert manager.stop(tunnel.id) is True
    assert _wait_until(lambda: manager.snapshot(tunnel.id).state == TunnelState.DISCONNECTED)  # type: ignore[union-attr]
    assert fake.terminated is True


def test_shutdown_cancels_process_created_during_start(tmp_path: Path, monkeypatch: object) -> None:
    key = tmp_path / "key"
    key.write_text("fake", encoding="utf-8")
    manager = SSHManager(ssh_executable="ssh")
    tunnel = config(key)
    manager.set_configs([tunnel])
    entered = threading.Event()
    release = threading.Event()
    fake = _FakeProcess()

    def delayed_popen(*_: object, **__: object) -> _FakeProcess:
        entered.set()
        release.wait(1)
        return fake

    monkeypatch.setattr(subprocess, "Popen", delayed_popen)  # type: ignore[attr-defined]
    monkeypatch.setattr(manager, "_port_is_available", lambda *_: True)  # type: ignore[attr-defined]
    result: list[bool] = []
    worker = threading.Thread(target=lambda: result.append(manager.start(tunnel.id)))
    worker.start()
    assert entered.wait(1)
    manager.shutdown()
    release.set()
    worker.join(1)

    assert result == [False]
    assert fake.terminated is True
    assert manager.start(tunnel.id) is False


def test_non_loopback_bind_is_rejected_before_spawn(tmp_path: Path) -> None:
    key = tmp_path / "key"
    key.write_text("fake", encoding="utf-8")
    manager = SSHManager(ssh_executable="ssh")
    tunnel = config(key, bind_host="192.168.1.20")
    manager.set_configs([tunnel])
    assert manager.start(tunnel.id) is False
    snapshot = manager.snapshot(tunnel.id)
    assert snapshot is not None
    assert "回环地址" in snapshot.last_error
