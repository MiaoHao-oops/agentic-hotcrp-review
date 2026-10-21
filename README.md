# HotCRP Review Lab

基于 [HotCRP](https://github.com/kohler/hotcrp) 与 Codex 的本地计算机论文模拟审稿系统。创建目标会议、上传论文，由多个独立 agent 审稿，在原生 HotCRP 页面查看评分与意见。

## 功能

- **会议调研**：查询本届及最近几届公开资料，生成投稿规则和多维评分量表，标注来源与模拟补充项。
- **多视角审稿**：结合论文元数据、不同侧重点及公开 PC 研究背景生成 reviewer 档案与提示词；模拟意见不代表真实 PC 本人。
- **原生投稿体验**：使用 HotCRP 的 PDF 上传、投稿表单、评分和 reviewer comments。
- **进度与结果**：查看任务阶段、近期活动和重试状态，汇总得分与决定性审稿意见，支持按投稿版本导出 JSON。
- **本地管理**：每个会议使用独立数据库，可删除会议及关联文件。

## 快速开始

适用于 Ubuntu / Debian。需要 Python 3.10+，以及已安装、完成登录的 Codex CLI；安装脚本会配置 PHP、MariaDB、Poppler 和 Python 依赖。

```bash
# 在克隆后的项目目录中执行
git submodule update --init --recursive
./scripts/setup.sh
codex login
./scripts/start.sh
```

打开 **http://127.0.0.1:8765**：

1. 输入会议名称、年份和 track，选择 2–5 位 reviewer 及审稿语言。
2. 等待会议调研完成，进入 HotCRP 上传论文并填写投稿信息。
3. 勾选 **The submission is ready for review** 后提交；草稿不会启动审稿。
4. 在会议详情查看进度与摘要，在 HotCRP 中查看完整 reviews。

PDF 需包含可提取的文本层，不支持加密文件；当前上限为 80 页、300,000 字符正文。

## 运行配置

默认沿用本机 Codex 模型与认证，也可在启动时指定：

```bash
CODEX_MODEL=your-model AGENT_CONCURRENCY=3 AGENT_TIMEOUT=1200 ./scripts/start.sh
```

后台运行：

```bash
.venv/bin/python scripts/install-user-service.py
systemctl --user status hotcrp-sim
journalctl --user -u hotcrp-sim -f
```

默认仅允许本机访问。可信局域网可按实际地址配置，例如：

```bash
HOST=0.0.0.0 ALLOWED_HOSTS=192.168.1.100 \
ALLOWED_NETWORKS=127.0.0.0/8,::1/128,192.168.1.0/24 ./scripts/start.sh
```

工作区自动登录 Local Chair，访问者共享论文、管理权限和 Codex 配额，不适合直接暴露到公网。

## 数据与隐私

应用在本地运行；**论文正文、页面图像和任务上下文会通过 Codex 发送到配置的模型服务**，会议调研会使用网页搜索。评审结果仅供模拟参考，不代表真实会议决定。

- `data/documents/`、`data/papers/`：论文文件与副本。
- `data/jobs/`：任务输入、结果、页面图片和日志。
- `data/state.sqlite`：会议、任务和投稿快照。
- 本机 MariaDB 的 `hcsim_*` 数据库：HotCRP 投稿信息与 reviews。

`data/` 已被 Git 忽略。备份需同时保存该目录与 MariaDB 数据库；删除会议会永久清理关联数据。

## 开发

`app/` 为 FastAPI 服务与前端，`extensions/` 为本地 HotCRP 接入配置，`upstream/` 为 [HotCRP fork](https://github.com/MiaoHao-oops/hotcrp) 子模块。HotCRP 许可证见 [upstream/LICENSE](upstream/LICENSE)。

```bash
.venv/bin/pip install -r requirements-dev.txt
.venv/bin/python -m pytest -q
# 额外运行本机 PHP / MariaDB 集成测试，不调用模型
RUN_HOTCRP_INTEGRATION=1 .venv/bin/python -m pytest -q
```

更多实现说明见 [HotCRP 集成文档](docs/hotcrp-integration.md)。
