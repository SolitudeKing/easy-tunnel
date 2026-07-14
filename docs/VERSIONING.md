# Versioning and Release

EasyTunnel uses Git tags and GitHub Releases for publishing. `git release` is
not a Git command: Git creates the immutable version tag, while GitHub Actions
builds the package and creates the GitHub Release.

## Single version source

The only application version is `easytunnel.__version__` in
`easytunnel/__init__.py`. `pyproject.toml` reads that value when building the
package, so the runtime version and package metadata cannot drift apart.

Use Semantic Versioning:

- `MAJOR`: incompatible configuration, CLI, or user-facing behavior changes.
- `MINOR`: backward-compatible functionality.
- `PATCH`: backward-compatible bug fixes.

Pre-release versions use PEP 440 syntax, such as `0.2.0rc1`, and their tags
must be `v0.2.0rc1`.

## Publishing a release

1. Update `__version__` and move the relevant entries from `Unreleased` into a
   dated version section in `CHANGELOG.md`.
2. Run the full test suite locally: `python -m pytest -q`.
3. Commit and push the release preparation to `master`.
4. Create and push an annotated tag whose name exactly matches the version:

   ```powershell
   git tag -a v0.2.0 -m "release: 发布 v0.2.0"
   git push origin v0.2.0
   ```

The `Publish release` workflow validates that the tag equals
`v{easytunnel.__version__}`, runs the tests, builds a wheel and source archive,
and creates a GitHub Release with auto-generated notes. `a`, `b`, `rc`, and
`.dev` versions are marked as pre-releases. A mismatched tag stops before any
release is created.

The current workflow publishes Python distribution packages only. Attach a
Windows installer after a reproducible Flet or installer build has been added
to the workflow.
