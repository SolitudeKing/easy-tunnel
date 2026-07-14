# EasyTunnel

EasyTunnel 是一个使用 Python + Flet 编写的图形化 SSH 本地端口转发管理器。它把下面这类命令：

```powershell
ssh -i .\pi-server -L 13389:192.168.3.88:3389 pi@pi.solitude.love -N
```

变成可保存、可观察的一键开关。连接成功后，还可以直接打开 Windows 远程桌面、Web 服务，或复制通用 TCP 服务地址。

## 已实现功能

- 隧道卡片：状态、端点、SSH 跳板机、启动时间和一键连接开关
- 新建、编辑、删除和搜索隧道配置
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

环境要求：Python 3.10+、系统 OpenSSH Client。

```powershell
cd E:\XM\EasyTunnel
python -m pip install -r requirements.txt
python main.py
```

Windows 也可以直接双击 `start.bat`；若缺少依赖，它会先安装依赖再启动。

## 使用方法

1. 检查示例卡片，或点击“新建隧道”。
2. 填写 SSH 主机、用户名、私钥路径，以及本地和内网目标端口。
3. 保存后打开卡片右侧开关。
4. 状态变为绿色“运行中”后，点击“打开服务”。
   - 远程桌面：启动 `mstsc /v:127.0.0.1:<本地端口>`
   - Web：打开 `http://127.0.0.1:<本地端口>`
   - TCP：复制 `127.0.0.1:<本地端口>`
5. 断开时关闭同一个开关。

题目示例在项目中的私钥实际位于上级目录，因此从 `EasyTunnel` 目录手工执行时相对路径是 `..\pi-server`。EasyTunnel 使用绝对路径保存配置，不受启动目录变化影响。

## 安全策略

- 使用参数列表调用 `ssh`，始终设置 `shell=False`，不执行用户拼接的命令文本。
- 设置 `ExitOnForwardFailure=yes` 和 `BatchMode=yes`，绑定或认证失败时立即反馈。
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
python -m pip install "pytest>=8.0"
python -m pytest -q
```

测试不连接真实 SSH 服务器，覆盖配置校验、持久化、IPv6 转发格式、安全命令构造和错误状态。

## 项目结构

下一阶段的功能规划、详细规格、架构演进和发布指南统一放在 [docs/](docs/README.md)。

```text
EasyTunnel/
├─ main.py                       # Flet 入口
├─ start.bat                     # Windows 双击启动入口
├─ easytunnel/
│  ├─ __main__.py                # 模块/安装后命令入口
│  ├─ app.py                     # 界面与交互
│  ├─ models.py                  # 配置、状态和日志模型
│  ├─ config_store.py            # JSON 配置持久化
│  └─ ssh_manager.py             # OpenSSH 进程生命周期
├─ tests/                        # 核心层自动化测试
├─ requirements.txt
└─ pyproject.toml
```

关闭 EasyTunnel 时会停止由本次应用启动的 SSH 子进程。若应用被强制结束，操作系统仍可能留下孤立的 `ssh.exe`，此时可在任务管理器中确认命令行后手动结束。

常见故障可先在“运行日志”中查看：端口占用时更换本地端口；`Permission denied (publickey)` 时核对用户名和私钥，或把加密私钥加入 `ssh-agent`；`Host key verification failed` 时应先确认服务器密钥确实发生了合法变化，再处理用户目录中的 `known_hosts`，不要直接关闭校验。
