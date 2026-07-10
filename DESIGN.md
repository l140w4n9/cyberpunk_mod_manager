# Cyberpunk 2077 模组管理器 — 设计文档

基于 AgentScope 大模型 Agent 框架，参考 Stardrop（Stardew Valley 模组管理器）的 Nexus 集成模式，
实现对赛博朋克 2077 模组的自动下载、安装、卸载记录与可视化管理。

---

## 1. 总体架构

```
┌──────────────────────────────────────────────────────────────┐
│                        Web 管理页面 (前端)                      │
│              Vue/React + AgentScope AG-UI 协议                 │
└───────────────┬──────────────────────────────────┬───────────┘
                │ HTTP/SSE                          │ AG-UI 流式
┌───────────────▼──────────────────┐  ┌────────────▼────────────┐
│        FastAPI 服务层              │  │   AgentScope Agent       │
│  (模组 CRUD / 安装任务 / 静态页面)  │  │  (ReAct + Toolkit)       │
└───────────────┬──────────────────┘  └────────────┬────────────┘
                │                                  │ 工具调用
┌───────────────▼──────────────────────────────────▼────────────┐
│                      核心业务层 (core)                          │
│  NexusClient │ Installer │ UninstallRegistry │ ModInventory   │
└───────────────┬──────────────────────────────────┬────────────┘
                │                                  │
┌───────────────▼──────────────┐  ┌────────────────▼────────────┐
│   Nexus Mods API (下载源)     │  │   本地存储 (SQLite + 文件)    │
└──────────────────────────────┘  └─────────────────────────────┘
```

## 2. 模组 ID 与下载源

- **模组 ID** = Nexus Mods 的 `mod_id`（整数），游戏域名为 `cyberpunk2077`
- API 基址：`https://api.nexusmods.com/v1/games/cyberpunk2077/mods/{mod_id}`
- 需要用户提供 Nexus API Key（参考 Stardrop `NexusClient.CreateClient`）
- 下载流程：`mod_id` → 查询文件列表 → 选最新主文件 → 获取下载链接 → 下载 zip

## 3. 安装与卸载记录机制（核心）

### 3.1 安装流程
1. 下载模组压缩包到 `downloads/` 目录
2. 解压到临时目录分析结构
3. 根据 mod 安装规则（`install_rules`）将文件复制到游戏对应路径
4. **记录每一条文件操作到 `install_manifest` 表**，形成"卸载计划"
5. 更新模组库存状态为已安装

### 3.2 卸载计划记录
安装时为每个模组生成一条 `InstallRecord`，包含：
- 所有新增的文件路径列表（相对游戏目录）
- 所有创建的目录（仅当为空时删除）
- 写入的配置项（用于回滚）
- 依赖框架信息

卸载时按记录反向操作：删除文件 → 清理空目录 → 恢复配置 → 更新库存。

### 3.3 Cyberpunk 2077 安装路径映射
| 文件类型 | 目标路径 |
|---------|---------|
| `.archive` | `archive/pc/mod/` |
| `.xl` (ArchiveXL) | `archive/pc/mod/` |
| `.yaml`/`.tweak` (TweakXL) | `r6/tweaks/` |
| `.reds` (redscript) | `plugins/cyber_engine_tweaks/mods/` 或 redscript 目录 |
| CET lua 脚本 | `bin/x64/plugins/cyber_engine_tweaks/mods/` |
| `r6/scripts/` | `r6/scripts/` |
| `bin/` | `bin/x64/` |

## 4. AgentScope Agent 设计

采用 ReAct Agent，注册以下工具组：

| 工具 | 功能 |
|------|------|
| `search_mod` | 按 mod_id 或名称查询模组信息 |
| `download_mod` | 根据 mod_id 下载模组文件 |
| `install_mod` | 安装已下载模组并记录卸载计划 |
| `uninstall_mod` | 按卸载记录移除模组 |
| `list_mods` | 列出已安装模组 |
| `enable_mod` / `disable_mod` | 启用/禁用模组 |
| `check_dependencies` | 检查模组依赖与框架 |
| `get_game_path` | 获取/设置游戏安装路径 |

Agent 系统提示词指导其：接收用户自然语言或 mod_id → 调用工具完成全流程 → 返回结构化结果。

## 5. 数据模型 (SQLite)

- `mods` — 模组库存（id, nexus_mod_id, name, version, status, installed_at）
- `install_records` — 卸载计划（mod_id, files_json, dirs_json, config_json）
- `download_tasks` — 下载任务（id, mod_id, file_id, status, path）
- `settings` — 配置（game_path, nexus_api_key, ...）

## 6. Web 管理页面

- 模组列表（状态、版本、缩略图、启用开关）
- 按 mod_id 安装输入框 + Agent 对话框（AG-UI 流式）
- 模组详情（依赖、卸载计划预览）
- 设置页（游戏路径、API Key）

## 7. 目录结构

```
cyberpunk_mod_manager/
├── pyproject.toml
├── DESIGN.md
├── README.md
├── src/
│   └── cyberpunk_mod_manager/
│       ├── __init__.py
│       ├── config.py              # 配置管理
│       ├── models/                # 数据模型 (SQLModel)
│       │   ├── mod.py
│       │   ├── install_record.py
│       │   └── settings.py
│       ├── storage/               # SQLite 存储层
│       │   └── db.py
│       ├── nexus/                 # Nexus Mods API 客户端
│       │   ├── client.py
│       │   └── schemas.py
│       ├── installer/             # 安装/卸载引擎
│       │   ├── engine.py
│       │   ├── rules.py           # 路径映射规则
│       │   └── uninstall.py
│       ├── agent/                 # AgentScope Agent
│       │   ├── agent.py
│       │   ├── tools.py           # 工具注册
│       │   └── prompt.py
│       ├── api/                   # FastAPI 路由
│       │   ├── app.py
│       │   ├── routes_mods.py
│       │   └── routes_agent.py
│       └── web/                   # 前端静态资源
│           └── index.html
├── downloads/                     # 下载缓存
└── tests/
```
