# EasyTunnel

EasyTunnel 是一个使用 Python + Flet 编写的图形化 SSH 本地端口转发管理器。它把下面这类带保护参数的命令：

```powershell
ssh -i .\pi-server -o IdentitiesOnly=yes -o ExitOnForwardFailure=yes -o ServerAliveInterval=30 -o ServerAliveCountMax=3 -L 127.0.0.1:13389:192.168.3.88:3389 -N -T pi@pi.solitude.love
```

变成可保存、可观察的一键开关。一条 SSH 会话可以包含多条 `-L` 本地转发并统一启停；连接成功后，还可以直接打开 Windows 远程桌面、Web 服务，或复制通用 TCP 服务地址。

## 已实现功能

- 隧道卡片：状态、多条转发端点、SSH 跳板机、启动时间和一键连接开关
- 新建、编辑、删除和搜索隧道配置，通过动态输入框组管理一条 SSH 会话中的多条 `-L`
- 安全导入 SSH 命令，支持显式 `NAME=value` 赋值与 `$NAME`、`${NAME}` 变量引用
- RDP、Web、通用 TCP 三种服务类型
- 私钥文件选择器与实时 SSH 命令预览
- SSH 子进程启动、监听检测、断开和异常退出监控
- 常见错误中文提示：认证失败、端口占用、主机名解析失败、超时等
- 按隧道筛选的运行日志
- JSON 配置持久化和原子保存
- Windows 下隐藏 SSH 命令行窗口
- 自动识别系统 OpenSSH 客户端

首次运行会显示一条与题目命令对应的示例隧道。如果项目上级目录存在 `pi-server`，界面会自动填入它的绝对路径；程序不会复制或读取私钥内容。

## 运行

环境要求：`uv`、系统 OpenSSH Client。`uv` 会创建项目 `.venv`，并自动选择或下载兼容的 Python 3.10+。

```powershell
cd E:\XM\EasyTunnel
uv sync
uv run python main.py
```

Windows 也可以直接双击 `start.bat`；它会使用 `uv` 自动创建并同步项目的 `.venv` 后启动。请先按 [uv 安装说明](https://docs.astral.sh/uv/getting-started/installation/) 安装 `uv`。

## 使用方法

1. 检查示例卡片，或点击“新建隧道”。也可以粘贴已有 SSH 命令进行安全导入。
2. 填写 SSH 主机、用户名和私钥路径，再添加一条或多条本地转发；每条转发分别填写本地入口、内网目标和服务类型。
3. 保存后打开卡片右侧开关。
4. 状态变为绿色“运行中”后，打开所需转发对应的服务。
   - 远程桌面：启动 `mstsc /v:127.0.0.1:<本地端口>`
   - Web：打开 `http://127.0.0.1:<本地端口>`
   - TCP：复制 `127.0.0.1:<本地端口>`
5. 断开时关闭同一个开关。

题目示例在项目中的私钥实际位于上级目录，因此从 `EasyTunnel` 目录手工执行时相对路径是 `..\pi-server`。EasyTunnel 使用绝对路径保存配置，不受启动目录变化影响。

### 多转发与变量导入

导入文本可以先用独立的 `NAME=value` 行声明变量，再在 SSH 命令中使用 `$NAME` 或 `${NAME}`。下面的内容会创建一个 SSH 会话和四条统一启停的本地转发：

```text
PrivateKey=E:\keys\pi-server
LocalMySqlPort=13306
LocalRedisPort=16380
LocalMinioApiPort=19000
LocalMinioConsolePort=19001

ssh -i $PrivateKey
  -o IdentitiesOnly=yes
  -o ExitOnForwardFailure=yes
  -o ServerAliveInterval=30
  -o ServerAliveCountMax=3
  -L "127.0.0.1:${LocalMySqlPort}:127.0.0.1:3369"
  -L "127.0.0.1:${LocalRedisPort}:127.0.0.1:6380"
  -L "127.0.0.1:${LocalMinioApiPort}:127.0.0.1:9000"
  -L "127.0.0.1:${LocalMinioConsolePort}:127.0.0.1:9001"
  -N -T pi@pi.solitude.love
```

这是 EasyTunnel 的导入格式，不是交给 PowerShell 执行的脚本。普通 PowerShell 会话变量（例如先在终端执行 `$PrivateKey = ...`）不会跨进程传给从桌面启动的 EasyTunnel；需要把变量以 `NAME=value` 一并粘贴。导入器只解析受支持的 SSH 连接、保护选项和 `-L` 参数，不调用 PowerShell，也不执行输入文本。未定义变量、无效端口、命令替换、管道、重定向及其它 Shell 片段会被拒绝。相对私钥路径会按导入界面显示的当前目录转换为绝对路径；Windows 网络共享和设备路径会被拒绝。

## 安全策略

- 使用参数列表调用 `ssh`，始终设置 `shell=False`；粘贴的命令只解析为结构化配置，从不作为脚本执行。
- 默认设置 `IdentitiesOnly=yes`、`ExitOnForwardFailure=yes`、`BatchMode=yes`、`-N` 和 `-T`，限制身份来源，并在认证或任一转发建立失败时立即反馈。
- 默认设置 `ServerAliveInterval=30` 和 `ServerAliveCountMax=3`，定期探测失去响应的 SSH 连接。
- 使用 `-F NUL`（Linux/macOS 为 `/dev/null`）忽略用户 SSH config，确保实际连接参数与界面预览一致。
- 默认只绑定 `127.0.0.1`；界面拒绝 `0.0.0.0` 和 `::`，避免意外暴露给局域网。
- 默认使用 `StrictHostKeyChecking=accept-new`：首次接受新主机，已记录的密钥发生变化时拒绝连接。也可启用严格模式。
- 仅保存私钥路径，不保存密码、私钥内容或密钥口令。
- 加密私钥请先加入 `ssh-agent`：

```powershell
Get-Service ssh-agent | Set-Service -StartupType Manual
Start-Service ssh-agent
ssh-add E:\XM\pi-server
```

配置文件默认位于 `%APPDATA%\EasyTunnel\tunnels.json`。也可以通过环境变量 `EASYTUNNEL_CONFIG` 指定其它位置。

## 测试

```powershell
uv run pytest -q
```

测试不连接真实 SSH 服务器，按 Model、Repository、Service、ViewModel 与 View
分层覆盖配置校验与迁移、多转发和变量解析、持久化、IPv6 转发格式、安全命令
构造、监听就绪、错误状态和 Flet 控件树序列化。

## 版本与发布

应用版本以 `easytunnel.__version__` 为唯一来源。推送与版本匹配的 `v*` Git 标签会触发 GitHub Actions：校验版本、运行测试、构建 wheel/源码包和 Windows 安装程序，并创建 GitHub Release。

Windows 安装版会在启动时后台检查最新稳定版本。发现更新后，用户确认下载，程序会校验 GitHub Release 提供的 SHA-256 摘要，再启动安装程序；源码运行模式不会自动改动本地文件。详细的版本号规则与发布步骤见[版本与发布指南](docs/VERSIONING.md)，本地生成 Windows 安装程序请参阅 [Windows 手动打包](docs/PACKAGING.md)。

## 项目结构

项目采用 MVVM 架构，主业务依赖方向为
`View / Component → ViewModel → Service / Repository → Model`；View 仅为表单和
资源显示只读依赖 Model/Config。完整职责与兼容策略见
[MVVM 架构文档](docs/ARCHITECTURE.md)，其它规划和发布指南统一放在
[docs/](docs/README.md)。

```text
EasyTunnel/
├─ easytunnel/
│  ├─ component/
│  │  ├─ dialog/                 # 对话框公共组件
│  │  └─ widget/                 # 主题与通用控件
│  ├─ view/                      # Flet 视图层
│  ├─ viewmodel/                 # 页面状态与用例编排
│  ├─ model/                     # 配置、状态和 DTO
│  ├─ repository/                # 配置与更新数据仓库
│  ├─ service/                   # SSH、导入、更新和平台服务
│  ├─ utils/                     # 纯工具函数
│  ├─ config/                    # 路径与资源配置
│  ├─ app.py                     # 组合根与兼容入口
│  ├─ __main__.py                # 模块/安装后命令入口
│  └─ __init__.py
├─ assets/
│  ├─ images/                    # 界面图片
│  ├─ icons/                     # SVG/ICO 图标
│  └─ icon.png                   # Flet 构建兼容入口
├─ tests/                        # 分层自动化测试
├─ docs/                         # 架构、规格与发布文档
├─ main.py                       # Flet 入口
├─ start.bat                     # Windows 双击启动入口
├─ pyproject.toml
└─ uv.lock                       # 受版本控制的依赖锁定文件
```

关闭 EasyTunnel 时会停止由本次应用启动的 SSH 子进程。若应用被强制结束，操作系统仍可能留下孤立的 `ssh.exe`，此时可在任务管理器中确认命令行后手动结束。

常见故障可先在“运行日志”中查看：端口占用时更换本地端口；`Permission denied (publickey)` 时核对用户名和私钥，或把加密私钥加入 `ssh-agent`；`Host key verification failed` 时应先确认服务器密钥确实发生了合法变化，再处理用户目录中的 `known_hosts`，不要直接关闭校验。
