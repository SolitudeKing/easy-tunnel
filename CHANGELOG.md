# Changelog

All notable changes are recorded in this file. Versions follow [Semantic
Versioning](https://semver.org/).

## [Unreleased]

### Added

- Windows manual packaging script that produces Python distributions, a desktop application, installer, and SHA-256 checksum.
- Automatic stable-release checks and SHA-256-verified Windows installer updates.
- Windows installer build and publication in the release workflow.

### Changed

- Use uv to manage the project virtual environment and locked dependencies.
- Detect Inno Setup installations in both system and current-user locations when creating Windows installers.

## [0.1.0] - Initial development baseline

### Added

- Graphical management of OpenSSH local port forwarding.
- Persistent tunnel configuration, connection monitoring, and test coverage.
