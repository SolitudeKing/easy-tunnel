# Windows 手动打包

项目提供统一的 Windows 打包脚本，产物结构与 GitHub Release 工作流保持一致。脚本会读取 `easytunnel.__version__` 作为版本号，运行测试、构建 Python 分发包、构建 Flet Windows 应用，并用 Inno Setup 生成安装程序。

## 前置条件

- Windows 10/11。
- Python 3.10 及以上，并已在项目根目录安装开发和构建依赖：`pip install -e ".[dev]" build`。
- Inno Setup 6：可通过 `choco install innosetup --yes` 安装。
- Visual Studio 的“使用 C++ 的桌面开发”工作负载。Flet 首次打包还可能下载 Flutter 及其所需工具链，因此需要网络连接和足够磁盘空间。

## 执行打包

在项目根目录打开 PowerShell 后执行：

```powershell
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
