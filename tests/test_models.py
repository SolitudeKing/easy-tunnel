from pathlib import Path

import pytest

from easytunnel.models import TunnelConfig


def make_config(**changes: object) -> TunnelConfig:
    values = {
        "name": "开发机桌面",
        "ssh_host": "gateway.example.com",
        "username": "alice",
        "local_port": 13389,
        "remote_host": "192.168.3.88",
        "remote_port": 3389,
        "identity_file": __file__,
    }
    values.update(changes)
    return TunnelConfig(**values)


def test_valid_config_passes_validation() -> None:
    assert make_config().validate(require_key_exists=True) == []


@pytest.mark.parametrize("port", [0, -1, 65536, True, 3.14])
def test_invalid_local_ports_are_rejected(port: object) -> None:
    errors = make_config(local_port=port).validate()  # type: ignore[arg-type]
    assert any("本地端口" in error for error in errors)


def test_control_characters_and_unsafe_username_are_rejected() -> None:
    errors = make_config(ssh_host="host\nname", username="a b@c").validate()
    assert any("控制字符" in error for error in errors)
    assert any("用户名不能包含" in error for error in errors)


def test_missing_key_is_only_checked_for_connection(tmp_path: Path) -> None:
    config = make_config(identity_file=str(tmp_path / "missing"))
    assert config.validate(require_key_exists=False) == []
    assert any("私钥文件不存在" in error for error in config.validate(require_key_exists=True))


def test_unknown_json_fields_are_ignored() -> None:
    source = make_config().to_dict()
    source["future_option"] = "supported later"
    restored = TunnelConfig.from_dict(source)
    assert restored.name == "开发机桌面"
    assert restored.local_port == 13389
