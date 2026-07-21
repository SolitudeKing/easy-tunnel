from __future__ import annotations

import ipaddress
import os
import signal
import shlex
import shutil
import socket
import subprocess
import threading
import time
from collections import deque
from dataclasses import dataclass, field, replace
from datetime import datetime
from pathlib import Path

from .models import LogEntry, RuntimeSnapshot, TunnelConfig, TunnelState


@dataclass(slots=True)
class _Runtime:
    config: TunnelConfig
    state: TunnelState = TunnelState.DISCONNECTED
    process: subprocess.Popen[str] | None = None
    started_at: datetime | None = None
    last_error: str = ""
    logs: deque[LogEntry] = field(default_factory=lambda: deque(maxlen=300))
    current_errors: deque[str] = field(default_factory=lambda: deque(maxlen=30))


def _forward_host(host: str) -> str:
    value = host.strip()
    if ":" in value and not (value.startswith("[") and value.endswith("]")):
        return f"[{value}]"
    return value


def _powershell_join(args: list[str]) -> str:
    def quote(argument: str) -> str:
        return "'" + argument.replace("'", "''") + "'"

    return "& " + " ".join(quote(argument) for argument in args)


class SSHManager:
    def __init__(self, ssh_executable: str | None = None, startup_timeout: float = 12.0) -> None:
        self.ssh_executable = ssh_executable or self.find_ssh()
        self.startup_timeout = startup_timeout
        self._items: dict[str, _Runtime] = {}
        self._order: list[str] = []
        self._lock = threading.RLock()
        self._closing = False

    @staticmethod
    def find_ssh() -> str:
        found = shutil.which("ssh")
        if found:
            return found
        if os.name == "nt":
            fallback = Path(os.environ.get("WINDIR", r"C:\Windows")) / "System32" / "OpenSSH" / "ssh.exe"
            if fallback.is_file():
                return str(fallback)
        return ""

    def set_configs(self, configs: list[TunnelConfig]) -> None:
        ids = [config.id for config in configs]
        if any(not item for item in ids) or len(ids) != len(set(ids)):
            raise ValueError("隧道配置 ID 不能为空或重复")
        with self._lock:
            existing = set(self._items)
            incoming = {config.id for config in configs}
            replacements = {config.id: config for config in configs}
            active_changed = [
                item
                for item in existing
                if (
                    item not in incoming
                    or self._items[item].config != replacements[item]
                )
                and (
                    self._items[item].process is not None
                    or self._items[item].state == TunnelState.CONNECTING
                )
            ]
        for tunnel_id in active_changed:
            self.stop(tunnel_id)
        with self._lock:
            new_items: dict[str, _Runtime] = {}
            for config in configs:
                runtime = self._items.get(config.id)
                if runtime:
                    runtime.config = config
                    new_items[config.id] = runtime
                else:
                    new_items[config.id] = _Runtime(config=config)
            self._items = new_items
            self._order = [config.id for config in configs]

    def snapshots(self) -> list[RuntimeSnapshot]:
        with self._lock:
            return [self._snapshot(self._items[item]) for item in self._order if item in self._items]

    def snapshot(self, tunnel_id: str) -> RuntimeSnapshot | None:
        with self._lock:
            runtime = self._items.get(tunnel_id)
            return self._snapshot(runtime) if runtime else None

    @staticmethod
    def _snapshot(runtime: _Runtime) -> RuntimeSnapshot:
        return RuntimeSnapshot(
            config=replace(runtime.config),
            state=runtime.state,
            pid=runtime.process.pid if runtime.process and runtime.process.poll() is None else None,
            started_at=runtime.started_at,
            last_error=runtime.last_error,
            logs=tuple(runtime.logs),
        )

    def build_command(self, config: TunnelConfig) -> list[str]:
        if not self.ssh_executable:
            raise RuntimeError("未找到 OpenSSH 客户端，请先安装或启用系统 OpenSSH Client")
        args = [self.ssh_executable, "-F", os.devnull]
        if config.identity_file:
            args.extend(["-i", str(Path(config.identity_file).expanduser().resolve())])
        args.extend(
            [
                "-p",
                str(config.ssh_port),
                "-o",
                "ExitOnForwardFailure=yes",
                "-o",
                "BatchMode=yes",
                "-o",
                "PasswordAuthentication=no",
                "-o",
                "KbdInteractiveAuthentication=no",
                "-o",
                "IdentitiesOnly=yes",
                "-o",
                "PreferredAuthentications=publickey",
                "-o",
                "ForwardAgent=no",
                "-o",
                "PermitLocalCommand=no",
                "-o",
                f"StrictHostKeyChecking={'yes' if config.strict_host_key else 'accept-new'}",
                "-o",
                f"ConnectTimeout={config.connect_timeout}",
                "-o",
                "ConnectionAttempts=1",
            ]
        )
        args.extend(
            [
                "-o",
                f"ServerAliveInterval={config.keepalive_interval}",
                "-o",
                "ServerAliveCountMax=3",
            ]
        )
        for forward in config.forwards:
            args.extend(["-L", forward.to_ssh_spec()])
        args.extend(["-N", "-T"])
        args.append(f"{config.username}@{_forward_host(config.ssh_host)}")
        return args

    def command_preview(self, config: TunnelConfig) -> str:
        args = self.build_command(config)
        return _powershell_join(args) if os.name == "nt" else shlex.join(args)

    def start(self, tunnel_id: str) -> bool:
        with self._lock:
            if self._closing:
                return False
            runtime = self._items.get(tunnel_id)
            if runtime is None:
                return False
            if runtime.state in {TunnelState.CONNECTING, TunnelState.CONNECTED, TunnelState.STOPPING}:
                return False
            if runtime.process and runtime.process.poll() is None:
                return False
            errors = runtime.config.validate(require_key_exists=True)
            if errors:
                self._set_error(runtime, errors[0])
                return False
            if not self.ssh_executable:
                self._set_error(runtime, "未找到 OpenSSH 客户端，请在 Windows 可选功能中安装 OpenSSH Client")
                return False
            for forward in runtime.config.forwards:
                if not self._is_loopback(forward.bind_host):
                    self._set_error(
                        runtime,
                        f"转发“{forward.name}”不是本机回环地址，已拒绝启动",
                    )
                    return False
                if not self._port_is_available(forward.bind_host, forward.local_port):
                    self._set_error(
                        runtime,
                        f"转发“{forward.name}”的本地端口 {forward.local_port} 已被占用",
                    )
                    return False
            runtime.state = TunnelState.CONNECTING
            runtime.last_error = ""
            runtime.started_at = None
            runtime.current_errors.clear()
            self._log(runtime, "info", "正在启动 SSH 隧道…")
            config = replace(runtime.config)

        try:
            command = self.build_command(config)
            kwargs: dict[str, object] = {
                "stdin": subprocess.DEVNULL,
                "stdout": subprocess.PIPE,
                "stderr": subprocess.STDOUT,
                "text": True,
                "encoding": "utf-8",
                "errors": "replace",
                "bufsize": 1,
                "shell": False,
            }
            if os.name == "nt":
                startupinfo = subprocess.STARTUPINFO()
                startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                startupinfo.wShowWindow = subprocess.SW_HIDE
                kwargs["startupinfo"] = startupinfo
                kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
            else:
                kwargs["start_new_session"] = True
            process = subprocess.Popen(command, **kwargs)  # type: ignore[arg-type]
        except (OSError, ValueError) as exc:
            with self._lock:
                current = self._items.get(tunnel_id)
                if current:
                    self._set_error(current, f"无法启动 SSH：{exc}")
            return False

        with self._lock:
            current = self._items.get(tunnel_id)
            if current is None or current.state != TunnelState.CONNECTING:
                self._terminate(process)
                return False
            current.process = process
            self._log(current, "info", f"SSH 进程已启动（PID {process.pid}）")

        threading.Thread(target=self._read_output, args=(tunnel_id, process), daemon=True).start()
        threading.Thread(target=self._await_ready, args=(tunnel_id, process, config), daemon=True).start()
        return True

    def _read_output(self, tunnel_id: str, process: subprocess.Popen[str]) -> None:
        try:
            if process.stdout:
                for line in process.stdout:
                    message = line.strip()
                    if message:
                        with self._lock:
                            runtime = self._items.get(tunnel_id)
                            if runtime and runtime.process is process:
                                is_notice = "permanently added" in message.lower()
                                if not is_notice:
                                    runtime.current_errors.append(message)
                                self._log(runtime, "info" if is_notice else "error", message)
            code = process.wait()
        except (OSError, ValueError) as exc:
            if process.poll() is None and not self._terminate(process):
                with self._lock:
                    runtime = self._items.get(tunnel_id)
                    if runtime and runtime.process is process:
                        self._set_error(runtime, f"SSH 输出监控失败，且无法停止进程：{exc}")
                return
            code = process.poll() if process.poll() is not None else -1

        with self._lock:
            runtime = self._items.get(tunnel_id)
            if not runtime or runtime.process is not process:
                return
            runtime.process = None
            runtime.started_at = None
            if runtime.state == TunnelState.STOPPING:
                runtime.state = TunnelState.DISCONNECTED
                runtime.last_error = ""
                self._log(runtime, "info", "隧道已断开")
            elif runtime.state != TunnelState.ERROR:
                recent = "\n".join(runtime.current_errors)
                self._set_error(runtime, self._friendly_error(recent, code))

    def _await_ready(
        self,
        tunnel_id: str,
        process: subprocess.Popen[str],
        config: TunnelConfig,
    ) -> None:
        deadline = time.monotonic() + max(self.startup_timeout, config.connect_timeout + 2)
        while time.monotonic() < deadline:
            if process.poll() is not None:
                return
            with self._lock:
                runtime = self._items.get(tunnel_id)
                if not runtime or runtime.process is not process or runtime.state != TunnelState.CONNECTING:
                    return
                forwards = config.forwards
            if all(
                self._port_is_listening(forward.bind_host, forward.local_port)
                for forward in forwards
            ):
                with self._lock:
                    runtime = self._items.get(tunnel_id)
                    if runtime and runtime.process is process and runtime.state == TunnelState.CONNECTING:
                        runtime.state = TunnelState.CONNECTED
                        runtime.started_at = datetime.now()
                        ports = "、".join(str(forward.local_port) for forward in forwards)
                        self._log(runtime, "success", f"隧道已连接，本地端口 {ports} 正在监听")
                return
            time.sleep(0.12)

        with self._lock:
            runtime = self._items.get(tunnel_id)
            if runtime and runtime.process is process and runtime.state == TunnelState.CONNECTING:
                pending = [
                    str(forward.local_port)
                    for forward in config.forwards
                    if not self._port_is_listening(forward.bind_host, forward.local_port)
                ]
                detail = "、".join(pending) or "未知"
                self._set_error(runtime, f"连接超时：本地端口 {detail} 未能开始监听")
        self._terminate(process)

    def stop(self, tunnel_id: str) -> bool:
        with self._lock:
            runtime = self._items.get(tunnel_id)
            if not runtime:
                return False
            process = runtime.process
            if not process or process.poll() is not None:
                runtime.process = None
                runtime.started_at = None
                runtime.state = TunnelState.DISCONNECTED
                runtime.last_error = ""
                return True
            if runtime.state == TunnelState.STOPPING:
                return False
            runtime.state = TunnelState.STOPPING
            self._log(runtime, "info", "正在断开隧道…")
        stopped = self._terminate(process)
        if not stopped:
            with self._lock:
                runtime = self._items.get(tunnel_id)
                if runtime and runtime.process is process:
                    self._set_error(runtime, "无法停止 SSH 进程，请在任务管理器中检查该进程")
        return stopped

    def stop_all(self) -> None:
        with self._lock:
            ids = [
                key
                for key, runtime in self._items.items()
                if runtime.process or runtime.state == TunnelState.CONNECTING
            ]
        for tunnel_id in ids:
            self.stop(tunnel_id)

    def shutdown(self) -> None:
        with self._lock:
            self._closing = True
        self.stop_all()

    @staticmethod
    def _terminate(process: subprocess.Popen[str]) -> bool:
        if process.poll() is not None:
            return True
        try:
            if os.name == "nt":
                process.terminate()
            else:
                os.killpg(process.pid, signal.SIGTERM)
        except OSError:
            if process.poll() is not None:
                return True
        try:
            process.wait(timeout=3)
            return True
        except subprocess.TimeoutExpired:
            pass
        except OSError:
            if process.poll() is not None:
                return True
        try:
            if os.name == "nt":
                process.kill()
            else:
                os.killpg(process.pid, signal.SIGKILL)
        except OSError:
            if process.poll() is not None:
                return True
        try:
            process.wait(timeout=2)
        except (subprocess.TimeoutExpired, OSError):
            return process.poll() is not None
        return True

    @staticmethod
    def _is_loopback(host: str) -> bool:
        value = host.strip().strip("[]")
        if value.lower() == "localhost":
            return True
        try:
            return ipaddress.ip_address(value).is_loopback
        except ValueError:
            return False

    @staticmethod
    def _port_is_available(host: str, port: int) -> bool:
        family = socket.AF_INET6 if ":" in host else socket.AF_INET
        address = host.strip("[]")
        try:
            with socket.socket(family, socket.SOCK_STREAM) as sock:
                sock.bind((address, port))
            return True
        except OSError:
            return False

    @staticmethod
    def _port_is_listening(host: str, port: int) -> bool:
        address = host.strip("[]")
        if address in {"0.0.0.0", ""}:
            address = "127.0.0.1"
        elif address == "::":
            address = "::1"
        family = socket.AF_INET6 if ":" in address else socket.AF_INET
        try:
            with socket.socket(family, socket.SOCK_STREAM) as sock:
                sock.settimeout(0.15)
                return sock.connect_ex((address, port)) == 0
        except OSError:
            return False

    @staticmethod
    def _friendly_error(message: str, code: int) -> str:
        mappings = (
            (("address already in use", "cannot listen to port"), "本地端口已被占用"),
            (("identity file", "not accessible"), "无法读取私钥文件"),
            (("host key verification failed",), "SSH 主机密钥校验失败"),
            (("could not resolve hostname", "name or service not known"), "无法解析 SSH 主机名"),
            (("connection timed out", "operation timed out"), "连接 SSH 服务器超时"),
            (("connection refused",), "SSH 服务器拒绝连接"),
            (("timeout, server", "connection reset by peer"), "SSH 连接已中断，请检查网络或保活设置"),
        )
        lines = [line.strip() for line in message.splitlines() if line.strip()]
        for line in reversed(lines):
            lowered = line.lower()
            if "permission denied" in lowered and "publickey" in lowered:
                return "SSH 公钥认证失败，请检查用户名、私钥或 ssh-agent"
            for needles, friendly in mappings:
                if any(needle in lowered for needle in needles):
                    return friendly
        return lines[-1] if lines else f"SSH 进程意外退出（代码 {code}）"

    @staticmethod
    def _log(runtime: _Runtime, level: str, message: str) -> None:
        runtime.logs.append(LogEntry(datetime.now(), level, message))

    def _set_error(self, runtime: _Runtime, message: str) -> None:
        runtime.state = TunnelState.ERROR
        runtime.last_error = message
        runtime.started_at = None
        self._log(runtime, "error", message)
