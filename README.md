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

已有前台服务运行时先停止，避免端口冲突。默认网页端口 `8765`，内部 PHP 端口 `8766`；内部 PHP 需要随机代理凭据，仅监听 loopback。局域网访问需配置下述子网限制；这套免登录工作区不用于公网访问。

前台启动的可选环境变量：

```bash
CODEX_MODEL=your-model AGENT_CONCURRENCY=3 AGENT_TIMEOUT=1200 ./scripts/start.sh
```

未设置 `CODEX_MODEL` 时沿用本机 Codex 配置与认证；不会把模型名写死。`CODEX_BIN` 可指定 CLI 绝对路径。`PORT`、`HOTCRP_PHP_PORT` 可改变两个本地端口。服务安装脚本记录当前 PATH 和 Codex 路径，修改后重新运行脚本或编辑 systemd override。

## 同子网访问

当前机器已启用局域网入口：**http://10.156.120.40:8765**，允许 `10.156.120.0/24` 及本机访问。访问者共享 Local Chair 身份、论文和 Codex 配额；并非独立用户账户。

配置位于 `~/.config/systemd/user/hotcrp-sim.service.d/lan.conf`：

```ini
[Service]
Environment="HOST=0.0.0.0"
Environment="ALLOWED_HOSTS=10.156.120.40"
Environment="ALLOWED_NETWORKS=127.0.0.0/8,::1/128,10.156.120.0/24"
```

更改后执行 `systemctl --user daemon-reload && systemctl --user restart hotcrp-sim`。当前 IP 来自 DHCP，变更后需同步更新允许的主机地址与访问 URL。PHP 的 8766 端口仍只监听本机，不能从局域网直接访问。启动脚本关闭转发头信任，子网判断使用真实连接来源。

恢复仅本机访问：删除该 `lan.conf`，然后 daemon-reload 并重启服务。默认不配置上述环境变量时仅允许 loopback。

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

HotCRP 扩展维护在 fork 的 `local-agent-simulation` 分支，根仓库固定对应 submodule 提交。开发提交分两层：先在 `upstream/` 提交 HotCRP 修改，再在根仓库提交子模块指针和服务修改。不要将认证信息、论文、数据库或 agent 日志提交到 Git。

### 删除会议与多维评分

会议列表和详情页提供“删除会议”。确认后停止该会议的 agent，清理 MariaDB 数据库、投稿文件、审稿结果和任务目录；不可恢复。删除失败会保留状态供重试，服务重启会继续未完成的删除。

新建会议调研本届及最近三届公开材料，包括官网 reviewer instructions、公开评分表、OpenReview、程序主席报告和官方存档。详情页展示逐届对比、维度定义、评分档位及来源，区分本届公开量表、历史量表和模拟补充。资料不可获得时明确记录缺口。各 reviewer 对每个维度评分并提供论文证据，写入 HotCRP 原生评分字段并包含在 JSON 导出中。旧会议保持原评分配置；使用新版调研需新建会议，避免更换已有 review 的分数含义。

新审稿任务从机制理论、实证测量、工程部署、跨领域方法、复现工具、稳健安全和领域综合等模拟背景中不重复抽取 reviewer，搭配不同的证据判断偏好。每轮采用可复现的抽样，实际档案保存到任务中；重试保持原档案。详情页和 JSON 导出可查看档案。提示词要求结合论文确定具体子领域和知识边界，说明关键分歧与改变结论所需证据，不预设分数或强制反对意见。同一模型的独立调用仍有相关性，不等于真实专家群体。已有完成的 reviews 保持原样。

会议调研同时验证公开 PC 名单与成员学术主页中的研究方向，并记录来源和届次。新任务结合论文标题、摘要、关键词和议题作启发式背景匹配，混合相近和相邻方向，生成论文专属检查简报。作者身份不参与匹配。仅公开且有来源的研究方向用作模拟背景，不推断真人性格、投票倾向或私人观点，也不冒充真人。资料不足时回退到通用模拟背景；旧会议没有这份资料时同样回退。

Codex 日志明确报告上游过载、暂时不可用或连接中断时，应用会分别等待 30、60 秒，最多额外重试两次。页面显示等待原因；持续失败后仍可手动重试。格式配置错误不自动重试。每次重新执行前，旧 events/stderr/result 保存在该任务目录的 `attempts/` 中，便于排查。重试是新一次执行，可能重新检索资料。

### Agent 进度

会议详情中的调研与 reviewer 卡片每 4 秒更新阶段进度、运行时长、最近活动和日志更新时间。调研阶段为准备、检索、校验、配置 HotCRP；审稿阶段为检查投稿、提取 PDF、阅读评审、校验、写入 reviews。自动重试显示倒计时，会议列表显示活动任务概况。活动仅从近期日志提取工具类型，不公开原始命令、工具输出或模型推理；没有新日志不一定代表任务卡住。Codex 不提供可靠百分比，因此界面只显示实际阶段。

每轮 reviewer 卡片下方显示得分与审稿意见摘要：各 reviewer 总分及档位、均分与范围，以及逐位 reviewer 的最终判断与理由。摘要直接摘录已完成 review，不额外调用模型；部分完成时标明数量，未完成或失败结果不计入均分。可展开完整意见，历史投稿按轮次分别显示。均分不代表录用决定。
