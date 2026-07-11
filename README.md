# Cyberpunk 2077 模组管理器

基于 [AgentScope](https://github.com/agentscope-ai/agentscope) 大模型 Agent 框架的赛博朋克 2077 模组管理方案，参考 [Stardrop](https://github.com/Floogen/Stardrop) 的 Nexus Mods 集成模式。

## 特性

- 🤖 **Agent 驱动**：自然语言或 mod_id 驱动，自动查询、安装、卸载与维护
- 📥 **Nexus v3 集成**：模组详情、批量查询、版本解析、物化依赖、热门/追踪/活动 feed
- 🔗 **智能依赖解析**：v3 物化依赖 → GraphQL `nexusRequirements` → 社区已知前置 → 描述文本解析
- 📦 **收藏夹安装**：解析 Nexus Collection URL，按收藏夹 pin 的**指定文件版本**批量安装
- 🩺 **健康审查**：待安装 / 依赖不全 / 更新检测 / LLM 修复建议，可选自动修复
- 🗂️ **可逆安装**：记录新增文件、创建目录、备份原文件，卸载时反向执行
- 🖥️ **Web 管理页面**：侧边栏多工作区（已安装、待安装、收藏、审查、Agent、设置）
- 🧩 **路径规则**：内置 archive / TweakXL / redscript / CET 等安装路径映射
- 💾 **本地回退**：非 Premium 或 API 下载失败时，可从 `downloads` 目录本地压缩包安装

## 快速开始

### 1. 安装依赖

```bash
cd cyberpunk_mod_manager
pip install -e .
```

### 2. 配置

复制示例配置并填入信息：

```bash
cp config.example.yaml config.yaml
```

编辑 `config.yaml`（**`data_dir` 为必填项**）：

```yaml
data_dir: "D:/CyberpunkModManager/data"
game_path: "D:/Steam/steamapps/common/Cyberpunk 2077"
nexus_api_key: "你的 Nexus API Key"
openai_api_key: "你的 LLM API Key"
model_name: "gpt-4o-mini"
openai_base_url: "https://api.openai.com/v1"
```

配置文件查找顺序：

1. 环境变量 `CP2077_CONFIG` 指定的路径
2. 当前工作目录下的 `config.yaml` / `config.yml` / `config.toml`
3. `~/.cyberpunk_mod_manager/config.yaml`

也可在前端 **设置** 页填写并保存到 `config.yaml`。

> 环境变量（`NEXUS_API_KEY`、`CP2077_GAME_PATH`、`OPENAI_API_KEY`、`MODEL_NAME` 等）仍可使用，且优先级高于配置文件。

### 3. 启动

```bash
python -m cyberpunk_mod_manager
# 或
uvicorn cyberpunk_mod_manager.api.app:app --reload
```

浏览器访问 http://127.0.0.1:8000

侧边栏底部会显示系统状态；Nexus Key 有效时会显示用户名与 Premium 状态。

### 4. 前端开发（Vue 3 + Vite）

Web 界面源码在 `frontend/` 目录：

```bash
cd frontend
npm install
npm run dev      # http://127.0.0.1:5173（/api 代理到后端）
npm run build    # 输出到 src/cyberpunk_mod_manager/web/
```

> 修改前端后需执行 `npm run build`，FastAPI 才会提供最新静态资源。

## 使用方式

### Web 工作区

| 工作区 | 说明 |
|--------|------|
| **Agent 运行** | 对话式安装、卸载、批量维护 |
| **已安装** | 按 mod_id 或本地包安装，查看依赖与卸载计划 |
| **待安装** | 已入库未装进游戏的模组，支持单个/一键清理 |
| **依赖不全** | 已安装但缺少必需前置的模组 |
| **收藏安装** | 粘贴 Collection URL，解析队列后批量安装（按收藏夹指定版本） |
| **健康审查** | 一键审查、更新检测、Nexus 发现（热门/追踪同步/活动 feed） |
| **设置** | 数据目录、游戏路径、API Key 等 |

### Agent 对话示例

- 「帮我安装模组 27967（含依赖）」
- 「列出依赖不全的模组并修复」
- 「检查所有已安装模组是否有更新」
- 「同步我在 Nexus 上追踪的模组」

### 本地安装回退

当 Nexus API 拒绝下载（非 Premium 等）时：

1. 在网站手动下载压缩包
2. 放入 `data_dir/downloads/`（文件名建议含 mod_id，如 `27967_xxx.zip`）
3. 在 Web 页使用「本地压缩包安装」，或让 Agent 调用 `install_local_mod`

## Nexus API 架构（v3）

主客户端 `nexus/client.py` 使用 **v3 REST + GraphQL**：

| 能力 | 接口 |
|------|------|
| 模组详情 | GraphQL + `POST /mods/batch` |
| 文件版本 | `/mods/{id}/files`、`/mod-file-versions/batch` |
| 物化依赖 | `/mod-file-versions/{id}/dependencies/materialized` |
| 依赖范围 | `/mod-file-versions/{id}/dependencies/ranges` |
| 热门模组 | `GET /games/cyberpunk2077/trending-mods` |
| 收藏夹 | GraphQL `collectionRevision`（含 `fileId` + `uid` 版本 pin） |

官方**尚未提供 v3 下载端点**，因此保留极小遗留 shim `nexus/_legacy_v1.py`，仅用于：

- Premium 下载链接（`download_link.json`）
- API Key 校验（`validate.json`）
- 账户追踪列表（`tracked_mods.json`）
- 近期活动 feed（`updated.json`）

其余逻辑均已 v3 化，旧版 `v3_client.py` 与 v1 全量客户端已移除。

### 依赖解析优先级

1. v3 物化依赖（按已安装 `nexus_version_id` 或最新主文件版本）
2. GraphQL `nexusRequirements`（`notes` 识别 optional）
3. 内置 `KNOWN_MOD_DEPENDENCIES` 社区前置表
4. 模组描述中的 Nexus 链接（有结构化数据时启用严格模式，过滤「successor to」等非依赖链接）

## REST API 概览

### 健康与配置

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/health` | 系统状态、Nexus 用户/Premium |
| GET/PUT | `/api/config` | 读取/保存配置 |

### 模组

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/mods` | 列出库存模组 |
| GET | `/api/mods/pending` | 待安装列表 |
| GET | `/api/mods/incomplete` | 依赖不全列表 |
| POST | `/api/mods/install` | 安装模组 |
| POST | `/api/mods/install-with-deps` | 安装并补全依赖 |
| POST | `/api/mods/install-local` | 从本地压缩包安装 |
| POST | `/api/mods/install-local-folder` | 文件夹批量本地安装 |
| POST | `/api/mods/uninstall` | 卸载模组 |
| DELETE | `/api/mods/{mod_id}` | 从库存删除（仅未安装） |
| POST | `/api/mods/cleanup-pending` | 批量清理待安装 |
| GET | `/api/mods/{mod_id}/dependencies` | 依赖报告 |
| GET | `/api/mods/{mod_id}/dependency-ranges` | v3 依赖范围 |
| POST | `/api/mods/check-updates` | 检查更新 |
| POST | `/api/mods/audit` | 健康审查 |
| POST | `/api/mods/audit/start` | 异步审查任务 |
| POST | `/api/mods/check-updates/start` | 异步更新检查 |

### Nexus 发现

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/mods/discovery/trending` | 热门模组 |
| POST | `/api/mods/discovery/sync-tracked` | 同步追踪模组到库存 |
| GET | `/api/mods/discovery/updated-feed` | 近期活动 feed |
| POST | `/api/mods/discovery/batch-status` | 批量查询模组状态 |

### 收藏夹

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/collections/parse` | 解析 Collection URL |
| POST | `/api/collections/install` | 启动批量安装任务 |
| GET | `/api/collections/jobs/{job_id}` | 查询任务进度 |
| GET | `/api/collections/revision` | 检测收藏夹修订是否变更 |

### Agent

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/agent/chat` | 对话（同步） |
| POST | `/api/agent/chat/stream` | 对话（SSE 流式） |
| GET/POST | `/api/agent/sessions` | 会话管理 |

## Agent 工具

| 工具 | 功能 |
|------|------|
| `search_mod` | 查询模组并同步到库存 |
| `check_dependencies` | 检查前置依赖 |
| `install_mod_with_dependencies` | 安装模组并补全依赖（首选） |
| `install_mods_batch` | 批量安装 |
| `install_mod` | 仅安装单个模组 |
| `install_local_mod` / `install_local_folder` | 本地安装 |
| `uninstall_mod` | 卸载模组 |
| `list_mods` / `list_pending_mods` / `list_incomplete_mods` | 库存列表 |
| `check_mod_updates` | 检查 Nexus 更新 |
| `fetch_trending_mods` / `sync_tracked_mods` / `fetch_updated_mod_feed` | Nexus 发现 |
| `batch_mod_status` | 批量查询模组状态 |
| `audit_installation` | 健康审查（可选自动修复） |
| `get_uninstall_plan_tool` | 查看卸载计划 |

## 项目结构

```
src/cyberpunk_mod_manager/
├── config.py              # 配置
├── models/                # Mod、依赖、安装记录等
├── storage/db.py          # SQLite + 迁移
├── nexus/
│   ├── client.py          # v3 REST + GraphQL 统一客户端
│   ├── _legacy_v1.py      # 下载/用户/追踪/feed 遗留 shim
│   ├── dependencies.py    # 依赖解析与同步
│   ├── collections.py     # 收藏夹 GraphQL
│   └── schemas.py         # API 数据结构
├── services/
│   ├── mod_ops.py         # 安装/下载/库存
│   ├── health_audit.py    # 审查与更新检测
│   ├── collection_ops.py  # 收藏夹安装队列
│   └── discovery.py       # trending / tracked / updated
├── installer/             # 安装/卸载引擎 + 路径规则
├── agent/                 # AgentScope Agent + 工具
├── api/                   # FastAPI 路由
├── web/                   # 前端构建产物
└── frontend/              # Vue 3 + Vite 源码
```

详见 [DESIGN.md](./DESIGN.md)（部分章节仍描述早期 v1 架构，以本 README 与代码为准）。

## 卸载记录机制

安装时为每个模组生成 `InstallRecord`，记录：

- `added_files`：新增到游戏目录的文件
- `created_dirs`：创建的目录（卸载时仅在为空时删除）
- `backed_up_files`：被覆盖前备份的原文件

卸载时按记录反向操作，确保干净移除。

## 测试

```bash
cd cyberpunk_mod_manager
pytest tests -q
```

## 许可

见项目根目录许可证文件（如有）。
