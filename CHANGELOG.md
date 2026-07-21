# Changelog

All notable changes are recorded in this file. Versions follow [Semantic
Versioning](https://semver.org/).

## [Unreleased]

## [0.1.1] - 2026-07-21

### Added

- Windows manual packaging script that produces Python distributions, a desktop application, installer, and SHA-256 checksum.
- Automatic stable-release checks and SHA-256-verified Windows installer updates.
- Windows installer build and publication in the release workflow.
- Multiple local `-L` forwarding rules in one SSH session, managed by a single connection switch.
- Safe SSH command import with explicit `NAME=value` assignments and `$NAME`/`${NAME}` references; imported text is parsed but never executed.

### Changed

- Use uv to manage the project virtual environment and locked dependencies.
- Detect Inno Setup installations in both system and current-user locations when creating Windows installers.
- Harden managed SSH sessions with `IdentitiesOnly=yes`, `ExitOnForwardFailure=yes`, `ServerAliveInterval=30`, `ServerAliveCountMax=3`, `-N`, and `-T` defaults.
- Migrate schema v1 single-forward configurations to schema v2 multi-forward sessions; legacy disabled or 15-second keepalive values adopt the protected 30-second default.

## [0.1.0] - Initial development baseline

### Added

- Graphical management of OpenSSH local port forwarding.
- Persistent tunnel configuration, connection monitoring, and test coverage.
