# Windows 手动打包

项目提供统一的 Windows 打包脚本，产物结构与 GitHub Release 工作流保持一致。脚本会读取 `easytunnel.__version__` 作为版本号，运行测试、构建 Python 分发包、构建 Flet Windows 应用，并用 Inno Setup 生成安装程序。

Flet 会自动使用根级 `assets/icon.png` 作为构建图标；界面品牌图使用
`assets/images/easytunnel-logo.png`，运行时窗口标题栏使用
`assets/icons/easytunnel.ico`，Inno Setup 使用 `installer/EasyTunnel.ico`。
这些文件均由 `assets/icons/easytunnel.svg` 中的同一设计导出。Windows 标题栏
要求 ICO 格式，因此运行时 ICO 与安装器图标保持相同内容。

Python wheel 通过 `pyproject.toml` 的 `data-files` 将运行时资源安装到
`share/easytunnel/assets`。`python -m easytunnel` 和安装后的 `easytunnel`
命令都会显式解析该目录，因此不要求用户从项目根目录启动。

## 前置条件

- Windows 10/11。
- [uv](https://docs.astral.sh/uv/getting-started/installation/)；它会创建项目的 `.venv`，并自动选择或下载兼容的 Python 3.10 及以上版本。
- Inno Setup 6：可任选一种方式安装；脚本支持系统范围、当前用户范围和 Scoop 的默认安装位置。

  ```powershell
  winget install --id JRSoftware.InnoSetup --exact
  # 或者（首次使用 Scoop 时需先添加 extras bucket）
  scoop bucket add extras
  scoop install inno-setup
  # 或者
  choco install innosetup --yes
  ```
- Visual Studio 的“使用 C++ 的桌面开发”工作负载。Flet 首次打包还可能下载 Flutter 及其所需工具链，因此需要网络连接和足够磁盘空间。

## 执行打包

在项目根目录打开 PowerShell 后执行：

```powershell
uv sync
powershell -ExecutionPolicy Bypass -File .\scripts\package_windows.ps1
```

默认输出到 `release/manual/<版本号>/`。脚本不会覆盖已有输出目录；需要重新构建时，请先手动删除旧目录，或使用新的输出目录：

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\package_windows.ps1 `
  -OutputDir release\manual\0.1.0-rebuild
```

若已在本地单独完成测试，可传入 `-SkipTests` 跳过测试步骤：

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\package_windows.ps1 -SkipTests
```

## 产物

以版本 `0.1.0` 为例，默认目录包含：

| 路径 | 内容 |
| --- | --- |
| `python/easy_tunnel-0.1.0.tar.gz` | Python 源码分发包（sdist） |
| `python/easy_tunnel-0.1.0-py3-none-any.whl` | Python wheel 包 |
| `windows/EasyTunnel.exe` | 免安装的 Windows 应用目录入口 |
| `installer/EasyTunnel-Setup-0.1.0.exe` | Windows 安装程序 |
| `installer/EasyTunnel-Setup-0.1.0.exe.sha256` | 安装程序 SHA-256 校验文件 |

脚本会在测试、构建或安装程序生成失败时立即退出，并保留已生成的产物，便于排查。

## 与 GitHub Release 的关系

推送版本标签后，GitHub Actions 的 Release 工作流会调用同一个 `scripts/package_windows.ps1` 脚本，只是使用 `-SkipTests`，因为工作流已在打包前运行完整测试。因此，本地手动打包与自动发布使用相同的构建参数和安装程序配置。
