import json
from pathlib import Path

import pytest

from easytunnel.model.tunnel import LocalForward, TunnelConfig
from easytunnel.repository.tunnel_repository import (
    ConfigError,
    TunnelRepository as ConfigStore,
)


def sample(key: Path, *, extra_forward: bool = False) -> TunnelConfig:
    forwards = [
        LocalForward(
            name="远程桌面",
            service_type="rdp",
            bind_host="127.0.0.1",
            local_port=13389,
            remote_host="192.168.3.88",
            remote_port=3389,
        )
    ]
    if extra_forward:
        forwards.append(
            LocalForward(
                name="Redis",
                bind_host="127.0.0.1",
                local_port=16380,
                remote_host="127.0.0.1",
                remote_port=6380,
            )
        )
    return TunnelConfig(
        name="中文隧道",
        note="仅保存路径，不保存密钥内容",
        ssh_host="pi.solitude.love",
        username="pi",
        identity_file=str(key),
        forwards=tuple(forwards),
    )


def legacy_document(key: str = "") -> dict[str, object]:
    return {
        "schema_version": 1,
        "tunnels": [
            {
                "id": "legacy-tunnel",
                "name": "旧版远程桌面",
                "note": "v1",
                "service_type": "rdp",
                "ssh_host": "pi.solitude.love",
                "username": "pi",
                "identity_file": key,
                "bind_host": "127.0.0.1",
                "local_port": 13389,
                "remote_host": "192.168.3.88",
                "remote_port": 3389,
                "keepalive_interval": 15,
            }
        ],
    }


def test_round_trip_preserves_unicode_and_multiple_forwards(tmp_path: Path) -> None:
    store = ConfigStore(tmp_path / "nested" / "tunnels.json")
    config = sample(Path(r"E:\密钥\pi-server"), extra_forward=True)
    store.save([config])
    loaded = store.load()
    assert loaded == [config]
    text = store.path.read_text(encoding="utf-8")
    assert "中文隧道" in text
    assert "Redis" in text
    assert "BEGIN PRIVATE KEY" not in text


def test_missing_file_returns_ready_to_use_example(tmp_path: Path) -> None:
    key = tmp_path / "pi-server"
    key.write_text("fake", encoding="utf-8")
    tunnels = ConfigStore(tmp_path / "none.json", key).load()
    assert len(tunnels) == 1
    assert tunnels[0].forwards[0].local_port == 13389
    assert tunnels[0].identity_file == str(key.resolve())


def test_corrupt_file_has_recoverable_error(tmp_path: Path) -> None:
    path = tmp_path / "tunnels.json"
    path.write_text("{broken", encoding="utf-8")
    with pytest.raises(ConfigError, match="无法读取配置"):
        ConfigStore(path).load()


def test_saved_document_has_schema_version(tmp_path: Path) -> None:
    store = ConfigStore(tmp_path / "tunnels.json")
    store.save([sample(tmp_path / "key")])
    data = json.loads(store.path.read_text(encoding="utf-8"))
    assert data["schema_version"] == 2
    assert len(data["tunnels"]) == 1


def test_v1_document_migrates_to_stable_forward_and_new_keepalive(
    tmp_path: Path,
) -> None:
    path = tmp_path / "tunnels.json"
    path.write_text(json.dumps(legacy_document()), encoding="utf-8")
    store = ConfigStore(path)
    first = store.load()[0]
    second = store.load()[0]
    assert first.forwards[0].id == "legacy-tunnel-forward-1"
    assert second.forwards[0].id == first.forwards[0].id
    assert first.forwards[0].service_type == "rdp"
    assert first.keepalive_interval == 30


def test_v1_disabled_keepalive_is_upgraded_to_protected_default(tmp_path: Path) -> None:
    path = tmp_path / "tunnels.json"
    data = legacy_document()
    data["tunnels"][0]["keepalive_interval"] = 0  # type: ignore[index]
    path.write_text(json.dumps(data), encoding="utf-8")

    assert ConfigStore(path).load()[0].keepalive_interval == 30


def test_document_without_schema_is_treated_as_v1(tmp_path: Path) -> None:
    path = tmp_path / "tunnels.json"
    data = legacy_document()
    data.pop("schema_version")
    path.write_text(json.dumps(data), encoding="utf-8")
    assert ConfigStore(path).load()[0].forwards[0].local_port == 13389


def test_future_schema_is_rejected_without_overwriting(tmp_path: Path) -> None:
    path = tmp_path / "tunnels.json"
    path.write_text('{"schema_version": 99, "tunnels": []}', encoding="utf-8")
    with pytest.raises(ConfigError, match="高于当前程序支持"):
        ConfigStore(path).load()


@pytest.mark.parametrize("version", [0, -1, True, "2"])
def test_invalid_schema_version_is_rejected(tmp_path: Path, version: object) -> None:
    path = tmp_path / "tunnels.json"
    path.write_text(
        json.dumps({"schema_version": version, "tunnels": []}), encoding="utf-8"
    )
    with pytest.raises(ConfigError, match="版本.*无效"):
        ConfigStore(path).load()


def test_duplicate_ids_are_repaired_on_load(tmp_path: Path) -> None:
    store = ConfigStore(tmp_path / "tunnels.json")
    first = sample(tmp_path / "key")
    second = sample(tmp_path / "other")
    second.id = first.id
    store.save([first, second])
    loaded = store.load()
    assert loaded[0].id != loaded[1].id


def test_string_boolean_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "tunnels.json"
    data = sample(tmp_path / "key").to_dict()
    data["auto_connect"] = "false"
    path.write_text(
        json.dumps({"schema_version": 2, "tunnels": [data]}), encoding="utf-8"
    )
    with pytest.raises(ConfigError, match="无法读取配置"):
        ConfigStore(path).load()


def test_invalid_v2_forward_structure_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "tunnels.json"
    data = sample(tmp_path / "key").to_dict()
    data["forwards"] = ["not-an-object"]
    path.write_text(
        json.dumps({"schema_version": 2, "tunnels": [data]}), encoding="utf-8"
    )
    with pytest.raises(ConfigError, match="无法读取配置"):
        ConfigStore(path).load()
