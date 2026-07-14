import json
from pathlib import Path

import pytest

from easytunnel.config_store import ConfigError, ConfigStore
from easytunnel.models import TunnelConfig


def sample(key: Path) -> TunnelConfig:
    return TunnelConfig(
        name="中文隧道",
        note="仅保存路径，不保存密钥内容",
        ssh_host="pi.solitude.love",
        username="pi",
        identity_file=str(key),
        local_port=13389,
        remote_host="192.168.3.88",
        remote_port=3389,
    )


def test_round_trip_preserves_unicode_and_windows_style_path(tmp_path: Path) -> None:
    store = ConfigStore(tmp_path / "nested" / "tunnels.json")
    config = sample(Path(r"E:\密钥\pi-server"))
    store.save([config])
    loaded = store.load()
    assert loaded == [config]
    text = store.path.read_text(encoding="utf-8")
    assert "中文隧道" in text
    assert "BEGIN PRIVATE KEY" not in text


def test_missing_file_returns_ready_to_use_example(tmp_path: Path) -> None:
    key = tmp_path / "pi-server"
    key.write_text("fake", encoding="utf-8")
    tunnels = ConfigStore(tmp_path / "none.json", key).load()
    assert len(tunnels) == 1
    assert tunnels[0].local_port == 13389
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
    assert data["schema_version"] == 1
    assert len(data["tunnels"]) == 1


def test_future_schema_is_rejected_without_overwriting(tmp_path: Path) -> None:
    path = tmp_path / "tunnels.json"
    path.write_text('{"schema_version": 99, "tunnels": []}', encoding="utf-8")
    with pytest.raises(ConfigError, match="高于当前程序支持"):
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
    path.write_text(json.dumps({"schema_version": 1, "tunnels": [data]}), encoding="utf-8")
    with pytest.raises(ConfigError, match="无法读取配置"):
        ConfigStore(path).load()
