from __future__ import annotations

from pathlib import Path

import pytest

from easytunnel.model.runtime import RuntimeSnapshot
from easytunnel.model.tunnel import LocalForward, TunnelConfig
from easytunnel.repository.tunnel_repository import ConfigError, TunnelRepository
from easytunnel.viewmodel.app_viewmodel import EasyTunnelViewModel, ViewModelError


class _FakeTunnelService:
    ssh_executable = "ssh"

    def __init__(self) -> None:
        self.configs: list[TunnelConfig] = []
        self.started: list[str] = []
        self.stopped: list[str] = []
        self.was_shutdown = False

    def set_configs(self, configs: list[TunnelConfig]) -> None:
        self.configs = list(configs)

    def snapshots(self) -> list[RuntimeSnapshot]:
        return []

    def snapshot(self, _tunnel_id: str) -> RuntimeSnapshot | None:
        return None

    def command_preview(self, config: TunnelConfig) -> str:
        return f"ssh {config.username}@{config.ssh_host}"

    def start(self, tunnel_id: str) -> bool:
        self.started.append(tunnel_id)
        return True

    def stop(self, tunnel_id: str) -> bool:
        self.stopped.append(tunnel_id)
        return True

    def shutdown(self) -> None:
        self.was_shutdown = True


def _config(key_path: Path, *, tunnel_id: str = "tunnel-1") -> TunnelConfig:
    return TunnelConfig(
        id=tunnel_id,
        name="数据库服务",
        ssh_host="pi.example.com",
        username="pi",
        identity_file=str(key_path),
        forwards=(
            LocalForward(
                name="MySQL",
                bind_host="127.0.0.1",
                local_port=13306,
                remote_host="127.0.0.1",
                remote_port=3369,
            ),
        ),
    )


def test_viewmodel_validates_and_persists_tunnel(tmp_path: Path) -> None:
    key_path = tmp_path / "pi-server"
    key_path.write_text("test key", encoding="utf-8")
    repository = TunnelRepository(tmp_path / "tunnels.json")
    service = _FakeTunnelService()
    view_model = EasyTunnelViewModel(
        repository=repository,
        tunnel_service=service,
    )
    view_model.configs = []
    service.set_configs([])

    view_model.save_config(_config(key_path), editing=False)

    assert repository.load() == view_model.configs
    assert service.configs == view_model.configs
    assert view_model.last_runtime_fingerprint == ()


def test_viewmodel_imports_variable_driven_multi_forward_command(
    tmp_path: Path,
) -> None:
    repository = TunnelRepository(tmp_path / "tunnels.json")
    view_model = EasyTunnelViewModel(
        repository=repository,
        tunnel_service=_FakeTunnelService(),
    )
    command = (
        "PrivateKey=.\\pi-server\n"
        "LocalMySqlPort=13306\n"
        "ssh -i $PrivateKey -o IdentitiesOnly=yes "
        "-o ExitOnForwardFailure=yes -o ServerAliveInterval=30 "
        "-o ServerAliveCountMax=3 "
        "-L 127.0.0.1:${LocalMySqlPort}:127.0.0.1:3369 "
        "-L 127.0.0.1:16379:127.0.0.1:6380 "
        "pi@pi.example.com -N -T"
    )

    config = view_model.import_ssh_command(command)

    assert config.name == "pi@pi.example.com"
    assert [item.local_port for item in config.forwards] == [13306, 16379]
    assert [item.name for item in config.forwards] == ["MySQL", "Redis"]
    assert config.keepalive_interval == 30
    assert Path(config.identity_file).is_absolute()


def test_viewmodel_routes_platform_actions_without_ui_dependencies(
    tmp_path: Path,
) -> None:
    opened: list[tuple[str, str]] = []
    view_model = EasyTunnelViewModel(
        repository=TunnelRepository(tmp_path / "tunnels.json"),
        tunnel_service=_FakeTunnelService(),
        remote_desktop_opener=lambda endpoint: opened.append(("rdp", endpoint)),
        web_service_opener=lambda endpoint: opened.append(("web", endpoint)),
    )
    rdp = LocalForward("RDP", "127.0.0.1", 13389, "host", 3389, "rdp")
    web = LocalForward("Web", "::1", 19001, "host", 9001, "web")
    tcp = LocalForward("Redis", "127.0.0.1", 16379, "host", 6380)

    assert view_model.open_forward(rdp) is None
    assert view_model.open_forward(web) is None
    assert view_model.open_forward(tcp) == "127.0.0.1:16379"
    assert opened == [("rdp", "127.0.0.1:13389"), ("web", "[::1]:19001")]


def test_viewmodel_restores_configs_when_delete_cannot_be_persisted(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repository = TunnelRepository(tmp_path / "tunnels.json")
    service = _FakeTunnelService()
    view_model = EasyTunnelViewModel(
        repository=repository,
        tunnel_service=service,
    )
    original = list(view_model.configs)

    def fail_save(_configs: list[TunnelConfig]) -> None:
        raise ConfigError("无法保存配置")

    monkeypatch.setattr(repository, "save", fail_save)

    with pytest.raises(ViewModelError, match="无法保存配置"):
        view_model.delete_config(original[0].id)

    assert view_model.configs == original
    assert service.configs == original
