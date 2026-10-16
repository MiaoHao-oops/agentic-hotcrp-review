# Local HotCRP + Codex review lab

基于原版 HotCRP 的本地计算机论文模拟评审系统。HotCRP 子模块来自 [MiaoHao-oops/hotcrp](https://github.com/MiaoHao-oops/hotcrp)，界面、PDF 上传、投稿表单、评分和 reviewer comments 均使用原版功能。

## 使用

打开 **http://127.0.0.1:8765**。

1. 输入会议名称、年份和 track，选择 2–5 位 reviewer 与 review 语言。
2. Codex 检索会议公开信息，显示来源和不确定项，创建独立的本地 HotCRP 会议。未公开的评分规则标为模拟量表。
3. 点击“进入 HotCRP”或“上传论文”。本地工作区自动登录 Local Chair，无需密码。
4. 填写标题、摘要、作者，上传 PDF，勾选 “The submission is ready for review” 并提交。仅保存草稿不会调用审稿 agent。
5. 后台自动启动独立 Codex reviewer。任务进度和重试在工作区展示，评分和意见写回原生 HotCRP 页面。每份 review 附论文快照标记，可导出各版本完整 JSON。

这是单用户、仅本机使用的模拟环境，没有真实会议投稿或邮件发送功能。论文、数据库、运行日志都留在 `data/` 或本机 MariaDB；**正文、页面图像和任务上下文会通过 Codex 发送到其配置的模型服务**。调查会议会使用 Codex 网页搜索。

## 安装与启动

```bash
git submodule update --init --recursive
./scripts/setup.sh        # Ubuntu/Debian；sudo 仅用于安装包和初始化 MariaDB 用户
codex login              # 已登录可跳过
./scripts/start.sh
```

需要 Python 3.10+、PHP 8.1+（mysqli/intl/mbstring 等）、MariaDB、Poppler、已登录的 Codex CLI。Python 依赖安装在 `.venv`。应用数据库账户仅拥有 `hcsim_` 前缀数据库的权限；无需给应用 sudo 权限。上游许可证保留于 `upstream/LICENSE`。

作为用户服务运行：

```bash
.venv/bin/python scripts/install-user-service.py
systemctl --user status hotcrp-sim
systemctl --user restart hotcrp-sim
systemctl --user stop hotcrp-sim
journalctl --user -u hotcrp-sim -f
```

已有前台服务运行时先停止，避免端口冲突。默认网页端口 `8765`，内部 PHP 端口 `8766`；内部 PHP 需要随机代理凭据，仅监听 loopback。不要把这套免登录工作区通过端口转发暴露到网络。

前台启动的可选环境变量：

```bash
CODEX_MODEL=your-model AGENT_CONCURRENCY=3 AGENT_TIMEOUT=1200 ./scripts/start.sh
```

未设置 `CODEX_MODEL` 时沿用本机 Codex 配置与认证；不会把模型名写死。`CODEX_BIN` 可指定 CLI 绝对路径。`PORT`、`HOTCRP_PHP_PORT` 可改变两个本地端口。服务安装脚本记录当前 PATH 和 Codex 路径，修改后重新运行脚本或编辑 systemd override。

## 实现与数据

- `app/`：本地入口、SQLite 持久队列、Codex 调度、PHP 反向代理。
- `extensions/`：会议数据库配置、仅供本地代理使用的 PHP router。
- `upstream/`：真正的 Git submodule。`batch/simbridge.php` 使用 HotCRP `SettingValues`、`PaperExport`、`ReviewValues` 校验和存储配置/评审，不直接写 review 表。`src/pages/p_simulation.php` 提供本地登录与状态入口。
- `data/state.sqlite`：会议、任务、投稿快照；`data/jobs/`：输入、结构化结果与私有日志；`data/documents/`、`data/papers/`：上传文件与不可变 PDF 快照。
- MariaDB 中每个会议一个独立 `hcsim_c...` 数据库。备份时需同时备份 `data/` 与这些数据库。

正文逐页提取，页面同时渲染为 PNG 供 reviewer 检查。当前拒绝加密 PDF、超过 80 页、提取正文不足或超过 300,000 字符的论文，不静默截断。没有 OCR；扫描论文需先添加文本层。PDF 页面视觉理解取决于所配置 Codex 模型/工具，review 必须披露无法检查的内容。

论文内容或投稿元数据变化会产生新快照，草稿/撤稿不会新建任务。正在审的版本若已变化，结果不再写入。旧结果保留在导出中；原生页面保留各 reviewer 最近写入的 review，更新期间需核对每条 review 的 snapshot。重试复用已验证的模型结果，避免重复消耗；同一 reviewer 重复写入更新已有 review。服务重启后进行中的任务标记为失败供手动重试，排队任务继续运行。

## 验证

```bash
.venv/bin/pip install -r requirements-dev.txt
.venv/bin/python -m pytest -q
RUN_HOTCRP_INTEGRATION=1 .venv/bin/python -m pytest -q  # 额外验证本机 PHP/MariaDB
.venv/bin/python scripts/make_demo_paper.py
```

`data/demo-paper.pdf` 是明确标注为合成、缺少真实实验的测试稿，仅用于验收。单元测试不调用模型；真实端到端验证会消耗 Codex 配额。详细验收记录见 `docs/validation.md`。

开发提交分两层：先在 `upstream/` 提交 HotCRP 修改，再在根仓库提交子模块指针和服务修改。不要将认证信息、论文、数据库或 agent 日志提交到 Git。
