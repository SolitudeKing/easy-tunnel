from pathlib import Path

import pytest

from easytunnel.models import LocalForward, TunnelConfig


def make_forward(**changes: object) -> LocalForward:
    values = {
        "name": "远程桌面",
        "service_type": "rdp",
        "bind_host": "127.0.0.1",
        "local_port": 13389,
        "remote_host": "192.168.3.88",
        "remote_port": 3389,
    }
    values.update(changes)
    return LocalForward(**values)


def make_config(**changes: object) -> TunnelConfig:
    values = {
        "name": "开发机桌面",
        "ssh_host": "gateway.example.com",
        "username": "alice",
        "forwards": (make_forward(),),
        "identity_file": __file__,
    }
    values.update(changes)
    return TunnelConfig(**values)


def test_valid_config_passes_validation() -> None:
    assert make_config().validate(require_key_exists=True) == []
    assert make_config().keepalive_interval == 30


@pytest.mark.parametrize("port", [0, -1, 65536, True, 3.14])
def test_invalid_local_ports_are_rejected(port: object) -> None:
    config = make_config(forwards=(make_forward(local_port=port),))
    errors = config.validate()  # type: ignore[arg-type]
    assert any("本地端口" in error for error in errors)


def test_control_characters_and_unsafe_username_are_rejected() -> None:
    config = make_config(
        ssh_host="host\nname",
        username="a b@c",
        forwards=(make_forward(remote_host="bad host"),),
    )
    errors = config.validate()
    assert any("控制字符" in error for error in errors)
    assert any("用户名不能包含" in error for error in errors)
    assert any("目标主机不能包含空格" in error for error in errors)


def test_missing_key_is_only_checked_for_connection(tmp_path: Path) -> None:
    config = make_config(identity_file=str(tmp_path / "missing"))
    assert config.validate(require_key_exists=False) == []
    assert any("私钥文件不存在" in error for error in config.validate(require_key_exists=True))


def test_unknown_json_fields_are_ignored() -> None:
    source = make_config().to_dict()
    source["future_option"] = "supported later"
    source["forwards"][0]["future_forward_option"] = True
    restored = TunnelConfig.from_dict(source)
    assert restored.name == "开发机桌面"
    assert restored.forwards[0].local_port == 13389


def test_empty_and_duplicate_forwards_are_rejected() -> None:
    assert any("至少需要" in error for error in make_config(forwards=()).validate())
    duplicate = make_forward(bind_host="localhost")
    errors = make_config(forwards=(make_forward(), duplicate)).validate()
    assert any("监听地址与同组规则重复" in error for error in errors)


def test_forward_spec_supports_short_form_and_ipv6() -> None:
    short = LocalForward.from_spec("13389:192.168.3.88:3389", name="RDP")
    ipv6 = LocalForward.from_spec("[::1]:13390:[fd00::88]:3389", name="IPv6")
    assert short.to_ssh_spec() == "127.0.0.1:13389:192.168.3.88:3389"
    assert ipv6.to_ssh_spec() == "[::1]:13390:[fd00::88]:3389"
