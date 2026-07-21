from easytunnel.app import EasyTunnelApp as LegacyEasyTunnelApp
from easytunnel.config_store import ConfigError as LegacyConfigError
from easytunnel.config_store import ConfigStore
from easytunnel.model.runtime import RuntimeSnapshot
from easytunnel.model.ssh_import import (
    ImportedForward,
    ImportedOption,
    ImportedSSHCommand,
)
from easytunnel.model.tunnel import LocalForward, TunnelConfig
from easytunnel.model.update import UpdateError, UpdateInfo
from easytunnel.models import (
    LocalForward as LegacyLocalForward,
    RuntimeSnapshot as LegacyRuntimeSnapshot,
    TunnelConfig as LegacyTunnelConfig,
)
from easytunnel.repository.tunnel_repository import ConfigError, TunnelRepository
from easytunnel.repository.update_repository import (
    download_installer,
    fetch_latest_update,
    parse_latest_release,
)
from easytunnel.service.ssh_import_service import (
    SSHImportError,
    parse_ssh_command,
    parse_variable_definitions,
)
from easytunnel.service.ssh_tunnel_service import SSHTunnelService
from easytunnel.ssh_import import (
    ImportedForward as LegacyImportedForward,
    ImportedOption as LegacyImportedOption,
    ImportedSSHCommand as LegacyImportedSSHCommand,
    SSHImportError as LegacySSHImportError,
    parse_ssh_command as legacy_parse_ssh_command,
    parse_variable_definitions as legacy_parse_variable_definitions,
)
from easytunnel.ssh_manager import SSHManager, _powershell_join
from easytunnel.updater import (
    UpdateError as LegacyUpdateError,
    UpdateInfo as LegacyUpdateInfo,
    download_installer as legacy_download_installer,
    fetch_latest_update as legacy_fetch_latest_update,
    parse_latest_release as legacy_parse_latest_release,
)
from easytunnel.utils.shell import powershell_join
from easytunnel.view.app_view import EasyTunnelApp


def test_flat_module_compatibility_exports_share_canonical_objects() -> None:
    assert LegacyEasyTunnelApp is EasyTunnelApp
    assert LegacyLocalForward is LocalForward
    assert LegacyRuntimeSnapshot is RuntimeSnapshot
    assert LegacyTunnelConfig is TunnelConfig
    assert LegacyImportedForward is ImportedForward
    assert LegacyImportedOption is ImportedOption
    assert LegacyImportedSSHCommand is ImportedSSHCommand
    assert LegacySSHImportError is SSHImportError
    assert LegacyConfigError is ConfigError
    assert LegacyUpdateError is UpdateError
    assert LegacyUpdateInfo is UpdateInfo
    assert ConfigStore is TunnelRepository
    assert SSHManager is SSHTunnelService
    assert _powershell_join is powershell_join
    assert legacy_parse_ssh_command is parse_ssh_command
    assert legacy_parse_variable_definitions is parse_variable_definitions
    assert legacy_download_installer is download_installer
    assert legacy_fetch_latest_update is fetch_latest_update
    assert legacy_parse_latest_release is parse_latest_release
