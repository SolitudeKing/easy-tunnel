from __future__ import annotations

import pytest

from easytunnel.ssh_import import (
    ImportedForward,
    SSHImportError,
    parse_ssh_command,
    parse_variable_definitions,
)


def test_imports_multiple_forwards_and_explicit_variables() -> None:
    command = r"""
        ssh -i $PrivateKey
        -o IdentitiesOnly=yes
        -o ExitOnForwardFailure=yes
        -o ServerAliveInterval=30
        -o ServerAliveCountMax=3
        -L "127.0.0.1:${LocalMySqlPort}:127.0.0.1:3369"
        -L "127.0.0.1:${LocalRedisPort}:127.0.0.1:6380"
        -L "127.0.0.1:${LocalMinioApiPort}:127.0.0.1:9000"
        -L "127.0.0.1:${LocalMinioConsolePort}:127.0.0.1:9001"
        pi@pi.solitude.love -N -T
    """
    variables = [
        r"PrivateKey=E:\keys\pi server",
        "LocalMySqlPort=13306",
        "LocalRedisPort=16379",
        "LocalMinioApiPort=19000",
        "LocalMinioConsolePort=19001",
    ]

    imported = parse_ssh_command(command, variables)

    assert imported.identity_file == r"E:\keys\pi server"
    assert imported.username == "pi"
    assert imported.ssh_host == "pi.solitude.love"
    assert imported.ssh_port == 22
    assert imported.no_remote_command is True
    assert imported.disable_tty is True
    assert imported.forwards == (
        ImportedForward("127.0.0.1", 13306, "127.0.0.1", 3369),
        ImportedForward("127.0.0.1", 16379, "127.0.0.1", 6380),
        ImportedForward("127.0.0.1", 19000, "127.0.0.1", 9000),
        ImportedForward("127.0.0.1", 19001, "127.0.0.1", 9001),
    )
    assert imported.option_value("IdentitiesOnly") == "yes"
    assert imported.option_value("serveraliveinterval") == "30"
    assert imported.option_value("ServerAliveCountMax") == "3"


def test_three_part_forward_defaults_to_ipv4_loopback() -> None:
    imported = parse_ssh_command(
        r"ssh -i .\pi-server -L 13389:192.168.3.88:3389 pi@example.test -N"
    )

    assert imported.identity_file == r".\pi-server"
    assert imported.forwards == (
        ImportedForward("127.0.0.1", 13389, "192.168.3.88", 3389),
    )
    assert imported.disable_tty is False


def test_ipv6_forward_and_destination_are_unbracketed_in_result() -> None:
    imported = parse_ssh_command(
        "ssh -i key -L '[::1]:13389:[fd00::88]:3389' "
        "alice@[2001:db8::10] -N -T"
    )

    assert imported.ssh_host == "2001:db8::10"
    assert imported.forwards == (
        ImportedForward("::1", 13389, "fd00::88", 3389),
    )


def test_current_safe_builder_options_and_disabled_config_are_accepted() -> None:
    command = (
        "ssh -F NUL -ikey -p2222 -L127.0.0.1:18080:service.test:8080 "
        "-N -T -oExitOnForwardFailure=yes -oBatchMode=yes "
        "-oPasswordAuthentication=no -oKbdInteractiveAuthentication=no "
        "-oIdentitiesOnly=yes -oPreferredAuthentications=publickey "
        "-oForwardAgent=no -oPermitLocalCommand=no "
        "-oStrictHostKeyChecking=accept-new -o 'ConnectTimeout 10' "
        "-oConnectionAttempts=1 app@gateway.test"
    )

    imported = parse_ssh_command(command)

    assert imported.config_file_disabled is True
    assert imported.identity_file == "key"
    assert imported.ssh_port == 2222
    assert imported.option_value("StrictHostKeyChecking") == "accept-new"
    assert imported.option_value("ConnectTimeout") == "10"


def test_variable_expansion_occurs_after_tokenization() -> None:
    identity_file = r"C:\keys\a key; $not-a-command"
    imported = parse_ssh_command(
        "ssh -i $PrivateKey -L 127.0.0.1:$LocalPort:db.test:3306 "
        "alice@gateway.test -N",
        {"PrivateKey": identity_file, "LocalPort": "13306"},
    )

    assert imported.identity_file == identity_file
    assert imported.forwards[0].local_port == 13306


def test_single_quotes_keep_a_dollar_literal() -> None:
    imported = parse_ssh_command(
        "ssh -i '$$literal-key' -L 13389:host.test:3389 alice@gateway.test -N"
    )

    assert imported.identity_file == "$$literal-key"


def test_parse_variable_definitions_supports_quotes_and_rejects_duplicates() -> None:
    variables = parse_variable_definitions(
        [r'PrivateKey="E:\keys\pi server"', "LocalPort=13306"]
    )

    assert variables == {
        "PrivateKey": r"E:\keys\pi server",
        "LocalPort": "13306",
    }
    with pytest.raises(SSHImportError, match="重复定义") as caught:
        parse_variable_definitions(["Port=1000", "Port=2000"])
    assert caught.value.code == "duplicate_variable"


@pytest.mark.parametrize(
    ("command", "code"),
    [
        (
            "ssh -i $Missing -L 13389:host.test:3389 alice@gateway.test -N",
            "undefined_variable",
        ),
        (
            "ssh -i 'key' -L 127.0.0.1:${Broken:host.test:3389 "
            "alice@gateway.test -N",
            "invalid_variable_expression",
        ),
        (
            "ssh -i $(Get-Key) -L 13389:host.test:3389 alice@gateway.test -N",
            "invalid_variable_expression",
        ),
    ],
)
def test_missing_or_malformed_variables_are_rejected(command: str, code: str) -> None:
    with pytest.raises(SSHImportError) as caught:
        parse_ssh_command(command)
    assert caught.value.code == code


def test_variable_cannot_inject_another_forward_through_a_port() -> None:
    command = (
        "ssh -i key -L 127.0.0.1:$Port:host.test:3389 "
        "alice@gateway.test -N"
    )

    with pytest.raises(SSHImportError) as caught:
        parse_ssh_command(command, {"Port": "13389 -R 9000:host:9000"})
    assert caught.value.code in {"invalid_forward", "invalid_port"}


def test_extremely_long_numeric_port_is_reported_as_import_error() -> None:
    command = (
        "ssh -i key -L 127.0.0.1:$Port:host.test:3389 "
        "alice@gateway.test -N"
    )

    with pytest.raises(SSHImportError) as caught:
        parse_ssh_command(command, {"Port": "9" * 5000})
    assert caught.value.code == "invalid_port"


@pytest.mark.parametrize(
    "option",
    [
        "StrictHostKeyChecking=no",
        "ForwardAgent=yes",
        "PermitLocalCommand=yes",
        "PasswordAuthentication=yes",
        "ServerAliveInterval=0",
        "ServerAliveCountMax=4",
        "ConnectionAttempts=2",
    ],
)
def test_unsafe_values_for_known_options_are_rejected(option: str) -> None:
    command = (
        f"ssh -i key -L 13389:host.test:3389 -o {option} "
        "alice@gateway.test -N"
    )

    with pytest.raises(SSHImportError) as caught:
        parse_ssh_command(command)
    assert caught.value.code == "unsafe_option_value"


@pytest.mark.parametrize(
    "argument",
    [
        "-o ProxyCommand=calc.exe",
        "-o LocalCommand=whoami",
        "-R 13389:host.test:3389",
        "-D 1080",
        "-J jump.test",
        "-A",
    ],
)
def test_unknown_or_dangerous_options_are_rejected(argument: str) -> None:
    command = (
        f"ssh -i key -L 13389:host.test:3389 {argument} "
        "alice@gateway.test -N"
    )

    with pytest.raises(SSHImportError) as caught:
        parse_ssh_command(command)
    assert caught.value.code in {"unsafe_option", "unsupported_ssh_option"}


def test_external_ssh_config_is_rejected() -> None:
    command = (
        "ssh -F custom-config -i key -L 13389:host.test:3389 "
        "alice@gateway.test -N"
    )

    with pytest.raises(SSHImportError) as caught:
        parse_ssh_command(command)
    assert caught.value.code == "unsafe_config_file"


def test_non_loopback_bind_and_duplicate_forwards_are_rejected() -> None:
    with pytest.raises(SSHImportError) as non_loopback:
        parse_ssh_command(
            "ssh -i key -L 0.0.0.0:13389:host.test:3389 "
            "alice@gateway.test -N"
        )
    assert non_loopback.value.code == "non_loopback_bind"

    with pytest.raises(SSHImportError) as duplicate:
        parse_ssh_command(
            "ssh -i key -L 13389:a.test:3389 -L 13389:b.test:3389 "
            "alice@gateway.test -N"
        )
    assert duplicate.value.code == "duplicate_forward"


def test_remote_commands_and_shell_operators_are_rejected() -> None:
    with pytest.raises(SSHImportError) as remote_command:
        parse_ssh_command(
            "ssh -i key -L 13389:host.test:3389 alice@gateway.test whoami -N"
        )
    assert remote_command.value.code == "remote_command_not_allowed"

    with pytest.raises(SSHImportError) as shell_operator:
        parse_ssh_command(
            "ssh -i key -L 13389:host.test:3389 alice@gateway.test -N; calc"
        )
    assert shell_operator.value.code == "shell_operator_not_allowed"


@pytest.mark.parametrize(
    ("command", "code"),
    [
        (
            "ssh -i key -L 13389:host.test:3389 alice@gateway.test",
            "missing_no_command_option",
        ),
        (
            "ssh -L 13389:host.test:3389 alice@gateway.test -N",
            "missing_identity_file",
        ),
        ("ssh -i key alice@gateway.test -N", "missing_forward"),
        ("ssh -i key -L 13389:host.test:3389 -N", "missing_destination"),
        (
            "plink -i key -L 13389:host.test:3389 alice@gateway.test -N",
            "unsupported_executable",
        ),
    ],
)
def test_required_local_forward_shape_is_enforced(command: str, code: str) -> None:
    with pytest.raises(SSHImportError) as caught:
        parse_ssh_command(command)
    assert caught.value.code == code
