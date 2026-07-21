from __future__ import annotations

import ipaddress
import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from string import Template


_VARIABLE_NAME = re.compile(r"[A-Za-z_][A-Za-z0-9_]*\Z")
_DECIMAL_PORT = re.compile(r"[0-9]+\Z")
_SHELL_OPERATORS = frozenset(";&|<>")
_DISABLED_CONFIG_FILES = frozenset({"nul", "/dev/null"})

_FIXED_SAFE_OPTIONS: dict[str, tuple[str, frozenset[str]]] = {
    "batchmode": ("BatchMode", frozenset({"yes"})),
    "connectionattempts": ("ConnectionAttempts", frozenset({"1"})),
    "exitonforwardfailure": ("ExitOnForwardFailure", frozenset({"yes"})),
    "forwardagent": ("ForwardAgent", frozenset({"no"})),
    "identitiesonly": ("IdentitiesOnly", frozenset({"yes"})),
    "kbdinteractiveauthentication": (
        "KbdInteractiveAuthentication",
        frozenset({"no"}),
    ),
    "passwordauthentication": ("PasswordAuthentication", frozenset({"no"})),
    "permitlocalcommand": ("PermitLocalCommand", frozenset({"no"})),
    "preferredauthentications": (
        "PreferredAuthentications",
        frozenset({"publickey"}),
    ),
    "pubkeyauthentication": ("PubkeyAuthentication", frozenset({"yes"})),
    "stricthostkeychecking": (
        "StrictHostKeyChecking",
        frozenset({"accept-new", "yes"}),
    ),
    "serveralivecountmax": ("ServerAliveCountMax", frozenset({"3"})),
}

_INTEGER_SAFE_OPTIONS: dict[str, tuple[str, int, int]] = {
    "connecttimeout": ("ConnectTimeout", 1, 120),
    "serveraliveinterval": ("ServerAliveInterval", 1, 3600),
}


class SSHImportError(ValueError):
    """An SSH command could not be safely converted into structured data.

    Args:
        message: User-facing explanation of the invalid input.
        code: Stable category suitable for UI-specific handling.
    """

    def __init__(self, message: str, *, code: str = "invalid_command") -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True, slots=True)
class ImportedForward:
    """A validated local TCP forwarding rule from one ``-L`` argument."""

    bind_host: str
    local_port: int
    remote_host: str
    remote_port: int


@dataclass(frozen=True, slots=True)
class ImportedOption:
    """A validated, canonical OpenSSH ``-o`` option."""

    name: str
    value: str


@dataclass(frozen=True, slots=True)
class ImportedSSHCommand:
    """Structured data extracted from a local-forward-only SSH command.

    The object deliberately contains data rather than an executable command. Callers
    can map the connection fields and each item in ``forwards`` into their own config
    model, then let the normal SSH command builder reconstruct the final argv.
    """

    executable: str
    identity_file: str
    ssh_port: int
    username: str
    ssh_host: str
    forwards: tuple[ImportedForward, ...]
    options: tuple[ImportedOption, ...]
    no_remote_command: bool
    disable_tty: bool
    config_file_disabled: bool

    def option_value(self, name: str) -> str | None:
        """Return a validated option value using a case-insensitive name lookup."""

        wanted = name.casefold()
        for option in self.options:
            if option.name.casefold() == wanted:
                return option.value
        return None


def parse_variable_definitions(definitions: Iterable[str]) -> dict[str, str]:
    """Parse explicit ``NAME=value`` definitions without shell evaluation.

    Values are split at the first equals sign. Matching outer single or double quotes
    are removed using the same constrained lexer as SSH commands.

    Args:
        definitions: Individual variable definitions supplied by a trusted UI field.

    Returns:
        A validated variable mapping.

    Raises:
        SSHImportError: If a definition is malformed, duplicated, or contains control
            characters.
    """

    variables: dict[str, str] = {}
    for definition in definitions:
        if not isinstance(definition, str) or "=" not in definition:
            raise SSHImportError(
                "变量必须使用 NAME=value 格式",
                code="invalid_variable_definition",
            )
        name, raw_value = definition.split("=", 1)
        name = name.strip()
        if not _VARIABLE_NAME.fullmatch(name):
            raise SSHImportError(
                f"变量名 {name!r} 无效",
                code="invalid_variable_definition",
            )
        if name in variables:
            raise SSHImportError(
                f"变量 {name} 重复定义",
                code="duplicate_variable",
            )

        value = raw_value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            tokens = _split_command(value)
            if len(tokens) != 1:
                raise SSHImportError(
                    f"变量 {name} 的引号格式无效",
                    code="invalid_variable_definition",
                )
            value = tokens[0]
        _reject_control_characters(value, f"变量 {name}")
        variables[name] = value
    return variables


def parse_ssh_command(
    command: str,
    variables: Mapping[str, str] | Iterable[str] | None = None,
) -> ImportedSSHCommand:
    """Safely parse a restricted OpenSSH local-forward command.

    Variable expansion happens after tokenization, so a value containing whitespace or
    command punctuation stays inside its original semantic field. The function never
    invokes a shell or starts a process.

    Args:
        command: SSH command text using PowerShell-compatible basic quoting.
        variables: A mapping or iterable of explicit ``NAME=value`` definitions used by
            ``$NAME`` and ``${NAME}`` placeholders. ``$$`` produces a literal dollar.

    Returns:
        A fully expanded and validated command representation.

    Raises:
        SSHImportError: If syntax, variables, options, or forwarding rules are unsafe or
            unsupported.
    """

    variable_values = _normalize_variables(variables)
    tokens = _split_command(command)
    if not tokens:
        raise SSHImportError("SSH 命令不能为空", code="empty_command")

    executable = tokens[0]
    executable_name = executable.replace("\\", "/").rsplit("/", 1)[-1].casefold()
    if executable_name not in {"ssh", "ssh.exe"}:
        raise SSHImportError(
            "命令必须以 ssh 或 ssh.exe 开始",
            code="unsupported_executable",
        )

    identity_file: str | None = None
    ssh_port = 22
    ssh_port_was_set = False
    forwards: list[ImportedForward] = []
    options: list[ImportedOption] = []
    option_names: set[str] = set()
    destination: tuple[str, str] | None = None
    no_remote_command = False
    disable_tty = False
    config_file_disabled = False
    config_file_was_set = False

    index = 1
    while index < len(tokens):
        token = tokens[index]

        if destination is not None:
            if token == "-N":
                if no_remote_command:
                    raise SSHImportError("-N 不能重复", code="duplicate_option")
                no_remote_command = True
                index += 1
                continue
            if token == "-T":
                if disable_tty:
                    raise SSHImportError("-T 不能重复", code="duplicate_option")
                disable_tty = True
                index += 1
                continue
            raise SSHImportError(
                "SSH 目标之后不允许远程命令或其它参数",
                code="remote_command_not_allowed",
            )

        if token == "-N":
            if no_remote_command:
                raise SSHImportError("-N 不能重复", code="duplicate_option")
            no_remote_command = True
            index += 1
            continue
        if token == "-T":
            if disable_tty:
                raise SSHImportError("-T 不能重复", code="duplicate_option")
            disable_tty = True
            index += 1
            continue

        option_kind = _argument_option_kind(token)
        if option_kind:
            kind, inline_value = option_kind
            if inline_value is None:
                index += 1
                if index >= len(tokens):
                    raise SSHImportError(
                        f"{kind} 缺少参数",
                        code="missing_option_argument",
                    )
                raw_value = tokens[index]
            else:
                raw_value = inline_value
            value = _expand_template(raw_value, variable_values, kind)

            if kind == "-i":
                if identity_file is not None:
                    raise SSHImportError("-i 不能重复", code="duplicate_option")
                if not value:
                    raise SSHImportError("私钥路径不能为空", code="invalid_identity_file")
                _reject_control_characters(value, "私钥路径")
                identity_file = value
            elif kind == "-p":
                if ssh_port_was_set:
                    raise SSHImportError("-p 不能重复", code="duplicate_option")
                ssh_port = _parse_port(value, "SSH 端口")
                ssh_port_was_set = True
            elif kind == "-L":
                forward = _parse_forward(value)
                duplicate = any(
                    item.bind_host.casefold() == forward.bind_host.casefold()
                    and item.local_port == forward.local_port
                    for item in forwards
                )
                if duplicate:
                    raise SSHImportError(
                        f"本地监听 {forward.bind_host}:{forward.local_port} 重复",
                        code="duplicate_forward",
                    )
                forwards.append(forward)
            elif kind == "-o":
                option = _parse_safe_option(value)
                folded_name = option.name.casefold()
                if folded_name in option_names:
                    raise SSHImportError(
                        f"SSH 选项 {option.name} 重复",
                        code="duplicate_option",
                    )
                option_names.add(folded_name)
                options.append(option)
            else:
                if config_file_was_set:
                    raise SSHImportError("-F 不能重复", code="duplicate_option")
                if value.casefold() not in _DISABLED_CONFIG_FILES:
                    raise SSHImportError(
                        "仅允许 -F NUL 或 -F /dev/null，不能导入外部 SSH 配置",
                        code="unsafe_config_file",
                    )
                config_file_disabled = True
                config_file_was_set = True

            index += 1
            continue

        if token.startswith("-"):
            code = "unsafe_option" if _looks_dangerous(token) else "unsupported_option"
            raise SSHImportError(f"不支持 SSH 参数 {token}", code=code)

        expanded_destination = _expand_template(token, variable_values, "SSH 目标")
        destination = _parse_destination(expanded_destination)
        index += 1

    if destination is None:
        raise SSHImportError("缺少 user@host SSH 目标", code="missing_destination")
    if identity_file is None:
        raise SSHImportError("缺少 -i 私钥路径", code="missing_identity_file")
    if not forwards:
        raise SSHImportError("至少需要一条 -L 本地端口转发", code="missing_forward")
    if not no_remote_command:
        raise SSHImportError(
            "本地转发命令必须包含 -N，禁止启动远程 Shell",
            code="missing_no_command_option",
        )

    username, ssh_host = destination
    return ImportedSSHCommand(
        executable=executable,
        identity_file=identity_file,
        ssh_port=ssh_port,
        username=username,
        ssh_host=ssh_host,
        forwards=tuple(forwards),
        options=tuple(options),
        no_remote_command=no_remote_command,
        disable_tty=disable_tty,
        config_file_disabled=config_file_disabled,
    )


def _normalize_variables(
    variables: Mapping[str, str] | Iterable[str] | None,
) -> dict[str, str]:
    if variables is None:
        return {}
    if not isinstance(variables, Mapping):
        if isinstance(variables, str):
            variables = (variables,)
        return parse_variable_definitions(variables)

    result: dict[str, str] = {}
    for name, value in variables.items():
        if not isinstance(name, str) or not _VARIABLE_NAME.fullmatch(name):
            raise SSHImportError(
                f"变量名 {name!r} 无效",
                code="invalid_variable_definition",
            )
        if not isinstance(value, str):
            raise SSHImportError(
                f"变量 {name} 的值必须是字符串",
                code="invalid_variable_definition",
            )
        _reject_control_characters(value, f"变量 {name}")
        result[name] = value
    return result


def _split_command(command: str) -> list[str]:
    if not isinstance(command, str):
        raise SSHImportError("SSH 命令必须是字符串", code="invalid_syntax")

    tokens: list[str] = []
    buffer: list[str] = []
    quote: str | None = None
    token_started = False
    index = 0

    while index < len(command):
        char = command[index]

        if quote == "'":
            token_started = True
            if char == "'":
                if index + 1 < len(command) and command[index + 1] == "'":
                    buffer.append("'")
                    index += 2
                    continue
                quote = None
            elif char == "$":
                buffer.append("$$")
            else:
                buffer.append(char)
            index += 1
            continue

        if char == '"':
            token_started = True
            quote = None if quote == '"' else '"'
            index += 1
            continue
        if char == "'" and quote is None:
            token_started = True
            quote = "'"
            index += 1
            continue

        if char == "`":
            if index + 1 >= len(command):
                raise SSHImportError("命令末尾存在无效转义符", code="invalid_syntax")
            escaped = command[index + 1]
            if escaped == "\r" and index + 2 < len(command) and command[index + 2] == "\n":
                index += 3
                continue
            if escaped == "\n":
                index += 2
                continue
            token_started = True
            buffer.append("$$" if escaped == "$" else escaped)
            index += 2
            continue

        if quote is None and char.isspace():
            if token_started:
                tokens.append("".join(buffer))
                buffer.clear()
                token_started = False
            index += 1
            continue
        if quote is None and char in _SHELL_OPERATORS:
            raise SSHImportError(
                f"命令中不允许 Shell 运算符 {char}",
                code="shell_operator_not_allowed",
            )

        token_started = True
        buffer.append(char)
        index += 1

    if quote is not None:
        raise SSHImportError("命令包含未闭合的引号", code="invalid_syntax")
    if token_started:
        tokens.append("".join(buffer))
    return tokens


def _argument_option_kind(token: str) -> tuple[str, str | None] | None:
    for option in ("-i", "-p", "-L", "-o", "-F"):
        if token == option:
            return option, None
        if token.startswith(option) and len(token) > len(option):
            return option, token[len(option) :]
    return None


def _expand_template(value: str, variables: Mapping[str, str], label: str) -> str:
    try:
        return Template(value).substitute(variables)
    except KeyError as exc:
        missing = str(exc.args[0])
        raise SSHImportError(
            f"{label} 引用了未定义变量 {missing}",
            code="undefined_variable",
        ) from exc
    except ValueError as exc:
        raise SSHImportError(
            f"{label} 包含无效变量表达式",
            code="invalid_variable_expression",
        ) from exc


def _parse_destination(value: str) -> tuple[str, str]:
    if value.count("@") != 1:
        raise SSHImportError(
            "SSH 目标必须使用 user@host 格式",
            code="invalid_destination",
        )
    username, host = value.split("@", 1)
    _validate_endpoint_text(username, "SSH 用户名")
    if username.startswith("-"):
        raise SSHImportError("SSH 用户名不能以 - 开头", code="invalid_destination")
    host = _normalize_host(host, "SSH 主机")
    return username, host


def _parse_forward(value: str) -> ImportedForward:
    parts = _split_forward_parts(value)
    if len(parts) == 3:
        bind_host = "127.0.0.1"
        local_port_text, remote_host, remote_port_text = parts
    elif len(parts) == 4:
        bind_host, local_port_text, remote_host, remote_port_text = parts
        bind_host = bind_host or "127.0.0.1"
    else:
        raise SSHImportError(
            "-L 必须使用 [bind_host:]local_port:remote_host:remote_port 格式",
            code="invalid_forward",
        )

    bind_host = _normalize_host(bind_host, "本地绑定地址")
    if not _is_loopback(bind_host):
        raise SSHImportError(
            f"本地绑定地址 {bind_host!r} 不是回环地址",
            code="non_loopback_bind",
        )
    remote_host = _normalize_host(remote_host, "目标主机")
    return ImportedForward(
        bind_host=bind_host,
        local_port=_parse_port(local_port_text, "本地端口"),
        remote_host=remote_host,
        remote_port=_parse_port(remote_port_text, "目标端口"),
    )


def _split_forward_parts(value: str) -> list[str]:
    parts: list[str] = []
    buffer: list[str] = []
    in_brackets = False
    for char in value:
        if char == "[":
            if in_brackets:
                raise SSHImportError("-L 地址括号格式无效", code="invalid_forward")
            in_brackets = True
            buffer.append(char)
        elif char == "]":
            if not in_brackets:
                raise SSHImportError("-L 地址括号格式无效", code="invalid_forward")
            in_brackets = False
            buffer.append(char)
        elif char == ":" and not in_brackets:
            parts.append("".join(buffer))
            buffer.clear()
        else:
            buffer.append(char)
    if in_brackets:
        raise SSHImportError("-L 地址括号格式无效", code="invalid_forward")
    parts.append("".join(buffer))
    return parts


def _parse_safe_option(value: str) -> ImportedOption:
    if "=" in value:
        name, raw_option_value = value.split("=", 1)
    else:
        pieces = value.split(None, 1)
        if len(pieces) != 2:
            raise SSHImportError(
                "-o 必须使用 Name=value 格式",
                code="invalid_ssh_option",
            )
        name, raw_option_value = pieces

    folded_name = name.strip().casefold()
    option_value = raw_option_value.strip().casefold()
    fixed_rule = _FIXED_SAFE_OPTIONS.get(folded_name)
    if fixed_rule:
        canonical_name, allowed_values = fixed_rule
        if option_value not in allowed_values:
            raise SSHImportError(
                f"SSH 选项 {canonical_name} 不允许值 {raw_option_value!r}",
                code="unsafe_option_value",
            )
        return ImportedOption(canonical_name, option_value)

    integer_rule = _INTEGER_SAFE_OPTIONS.get(folded_name)
    if integer_rule:
        canonical_name, minimum, maximum = integer_rule
        number = _parse_bounded_integer(
            raw_option_value.strip(),
            canonical_name,
            minimum,
            maximum,
            code="unsafe_option_value",
        )
        return ImportedOption(canonical_name, str(number))

    raise SSHImportError(
        f"不支持 SSH -o 选项 {name.strip() or value!r}",
        code="unsupported_ssh_option",
    )


def _parse_port(value: str, label: str) -> int:
    return _parse_bounded_integer(value, label, 1, 65535, code="invalid_port")


def _parse_bounded_integer(
    value: str,
    label: str,
    minimum: int,
    maximum: int,
    *,
    code: str,
) -> int:
    if not _DECIMAL_PORT.fullmatch(value) or len(value) > len(str(maximum)):
        raise SSHImportError(f"{label} 必须是整数", code=code)
    number = int(value)
    if not minimum <= number <= maximum:
        raise SSHImportError(
            f"{label} 必须在 {minimum} 到 {maximum} 之间",
            code=code,
        )
    return number


def _normalize_host(value: str, label: str) -> str:
    _validate_endpoint_text(value, label)
    if value.startswith("[") or value.endswith("]"):
        if not (value.startswith("[") and value.endswith("]")):
            raise SSHImportError(f"{label} 的 IPv6 括号格式无效", code="invalid_host")
        value = value[1:-1]
        _validate_endpoint_text(value, label)
    if "[" in value or "]" in value:
        raise SSHImportError(f"{label} 的 IPv6 括号格式无效", code="invalid_host")
    if value.startswith("-"):
        raise SSHImportError(f"{label} 不能以 - 开头", code="invalid_host")
    return value


def _validate_endpoint_text(value: str, label: str) -> None:
    if not value:
        raise SSHImportError(f"{label}不能为空", code="invalid_endpoint")
    _reject_control_characters(value, label)
    if any(char.isspace() for char in value):
        raise SSHImportError(f"{label}不能包含空白字符", code="invalid_endpoint")


def _reject_control_characters(value: str, label: str) -> None:
    if any(ord(char) < 32 or ord(char) == 127 for char in value):
        raise SSHImportError(f"{label}包含控制字符", code="control_character")


def _is_loopback(host: str) -> bool:
    if host.casefold() == "localhost":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def _looks_dangerous(option: str) -> bool:
    dangerous_prefixes = (
        "-A",
        "-D",
        "-J",
        "-R",
        "-W",
        "-X",
        "-Y",
        "-t",
    )
    return option.startswith(dangerous_prefixes)
