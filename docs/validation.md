# 验收记录（2026-10-16）

## 本机环境

Ubuntu 22.04；PHP 8.1（mysqli、intl、mbstring、XML、curl、GD）；MariaDB 10.6；Poppler；Python 3.13 虚拟环境；本机已登录的 Codex CLI。网页监听 `127.0.0.1:8765`，内部 PHP 监听 `127.0.0.1:8766`。`hotcrp-sim.service` 是当前用户的 systemd 服务。

## 自动测试

`RUN_HOTCRP_INTEGRATION=1 .venv/bin/python -m pytest -q`：12 项通过。

覆盖：

- 投稿快照忽略 review 输出，正文/PDF/摘要变化会改变快照。
- 草稿、撤稿不启动审稿；重复轮询不重复创建任务。
- 新版本使旧版本任务失效；回退旧版本可复用已缓存结果。
- 服务重启使中断任务可重试；部分失败不误报为全部完成。
- 评分 schema、实际 HotCRP 评分表不匹配时拒绝写入。
- 拒绝跨站 Origin、异常 Host 与无效创建输入。
- 真正创建临时 MariaDB 会议，配置六档量表，上传 PDF，跨进程读取持久 PDF 快照。
- 通过原生 ReviewValues 提交 review，验证 completed 状态、分数及重复写入不增加 review 条数。

PHP 与 JavaScript 语法检查通过。测试框架有一条上游 FastAPI/Starlette 关于 httpx TestClient 的弃用提示，不影响测试执行。

## 真实 Codex 端到端

已通过本地创建接口创建 `OSDI 2026 · Research papers` 会议（`c0ed7486d7231`），会议调查使用真实 Codex web search，保存官方来源、匿名规则、篇幅说明与未公开 rubric 的不确定性。

使用 Playwright 驱动原生 HotCRP 投稿页面填写标题、摘要、作者，通过文件选择器上传 `data/demo-paper.pdf`，勾选 ready 并提交为论文 #1。测试稿明确标注为合成材料，所有性能数值都是虚构示例。

三个独立 Codex reviewer 完成正文与页面图像审阅，并将结构化结果写入原生 HotCRP。测试期间会议配置同步改变了 PC conflict 元数据，产生了第二个投稿快照和三份新 review；两个版本均保留导出。最新快照中三位 reviewer 都给出 Reject（1/5），置信度均为 4/4，指出缺少真实实验和创新性，不把虚构数字当成证据。

已实际验证一次生成结果后的写回失败重试：重试读取缓存结果，不再次调用模型。审稿结果的 strengths、weaknesses、questions、evidence 和 limitations 均出现在 Comments for authors 中。

## 浏览器验证

`.venv/bin/python scripts/browser-smoke.py --conference c0ed7486d7231` 通过：

- 工作区会议详情与原生 reviews 链接可访问；Main 模式展示 review 分数表与正文。
- 新浏览器会话可免密码进入本地会议，直接投稿链接在登录跳转后仍进入上传表单。
- 原生 PDF 上传表单可用。
- 390 px 宽工作区无横向溢出；浏览器没有 JavaScript 错误。

截图仅保存在被忽略的 `data/portal.png`、`data/native-reviews.png`、`data/native-reviews-top.png`、`data/native-submission.png`。

## 限制

本次验证使用三页合成 PDF；不能据此保证所有复杂论文版式、扫描 PDF 或超长论文均可处理。当前支持范围和拒绝条件见 README。模型审稿不构成真实会议决定，会议调查也不能恢复未公开的私有审稿标准。该服务面向可信本地单用户，不是公网多租户部署。
