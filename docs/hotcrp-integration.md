# 基于原版 HotCRP 的本地模拟审稿系统

## 调研结论

可以直接扩展原版 HotCRP，复用实际的投稿、PDF 存储、review form、评分汇总与评论界面。无需再独立仿制这些页面。本目录 `upstream/` 已保存上游源码快照，未修改核心文件；当前源码以 Git submodule 固定在用户 fork 的开发提交。

本文件保留初始设计。系统现已实现；实际实现与运行说明见根目录 README，验收结果见 validation.md。实际后端使用 HotCRP CLI domain bridge，而非 HTTP bearer API。

## 已核实的接入点

| 需求 | 上游能力 | 新增工作 |
| --- | --- | --- |
| 创建多个会议 | `src/multiconference.php` 根据 conference ID 加载会议配置；`batch/createdb.php`、`lib/createdb.sh` 初始化数据库 | 本地会议入口、ID 分配、数据库与配置 provisioning、创建失败恢复 |
| 调查目标会议 | 上游无此功能 | Codex research job，输出会议名称、年份、track、投稿要求、来源和不确定项 |
| 生成对应表单 | `GET/POST /api/settings`；`SettingValues` 负责配置校验 | 将调查结果转换为白名单配置，先 dry run 校验，再保存 |
| 上传论文 | 原版 submission 页面、文档存储与 paper API | 复用原版，读取提交状态与 PDF 版本 |
| 触发模拟审稿 | `GET /api/papers` 可查询论文；`POST /api/assign` 分配 reviewer | worker 轮询已提交论文，按会议、论文、文档版本、审稿轮次去重 |
| 写入多个 review | `POST /api/review?p=ID` 支持 reviewer 身份、JSON 字段、提交状态 | 给各 agent 独立模拟 reviewer 账户，按实际 review field UID 写入结果 |
| 展示评分和意见 | 原版 review 页面和评分组件 | 增加任务状态与重试入口；沿用原版 review 展示 |

证据：`devel/openapi.json`、`src/api/api_review.php`、`devel/manual/components.md`、`src/multiconference.php`。API 的 `ok: true` 不总等于操作成功；还必须检查 `message_list`、设置保存结果、assignment 的 `valid` 和 review 的实际提交结果。

## 推荐实现

1. HotCRP 使用 PHP + MariaDB，提供原生会议、投稿和审稿页面。每个会议使用独立数据库；共享一份源码。默认只监听本地地址，禁用邮件发送。
2. 本地 Python 服务提供会议创建入口和持久任务队列。会议规则保留来源 URL、获取时间和原始结构化调查结果。数据库创建由受控 provisioner 完成，不把数据库管理权限交给 agent。
3. Codex CLI worker 调用 `codex exec`，使用 JSON schema 限制输出。会议调查启用搜索；审稿任务只接收该论文和已核实的会议规则，不读取其他 reviewer 的结果。
4. 默认三个独立 reviewer，分别关注技术正确性、实验与可复现性、贡献与会议契合度；每人仍输出完整审稿。审稿并发数可配置，任务支持超时、失败重试和服务重启后的中断恢复。
5. 后端读取会议的实际 review form 并校验分数范围和字段 UID，通过 HotCRP API 写回。重试更新已有 review，避免重复创建。全部成功后将本地模拟会议配置为作者可见 review。
6. 用 `$Opt["pages"]` 和 `$Opt["apiFunctions"]` 注册少量扩展入口，而非修改中央路由或直接操作 PaperReview 表。调用凭据留在本地服务，不暴露到浏览器或 agent prompt。

## 必须保留的行为边界

- 公开 CFP 通常不能还原真实 PC 的私有审稿表；未查证项明确显示为“模拟默认值”，不声称官方配置。
- 会议历史 deadline 作为参考信息保留，本地模拟投稿窗口独立开放，避免目标会议过期后无法提交。
- PDF 本地保存；论文文本/图像和任务上下文会随 Codex 请求发送到其配置的服务。除 agent 的搜索/模型调用外，应用运行不依赖远程存储、字体或 CDN。
- 论文正文与搜索内容视为任务资料，不允许其改变任务指令。agent 不持有 HotCRP 管理 token，不直接修改会议数据库。
- 本地模拟 reviewer、模拟评分明确标识；不自动发送真实邮件，不向真实会议投稿。
- 服务端按照论文版本保存审稿快照，论文更新不会静默混用旧 review。PDF 无法提取或上下文过长时明确报错或分段处理，不只看摘要却宣称通读全文。

## 当前运行条件

已安装 PHP 8.1、MariaDB 10.6 及所需扩展，使用本地 loopback 服务运行，无需 Docker。MariaDB 应用账户仅可访问 `hcsim_` 前缀数据库。用户密码未写入项目文件；随机数据库与代理凭据位于被 Git 忽略的 `data/`。

## 验收路径

创建目标会议 → Codex 调查并保存来源 → 初始化独立 HotCRP 会议与表单 → 原生页面上传 PDF 并提交 → 三个独立 agent → 校验并写入三个 review → 原生页面展示评分及意见。另测重复触发、部分失败、重启、更新 PDF、无效 JSON/分数、跨会议数据隔离与作者可见性。
