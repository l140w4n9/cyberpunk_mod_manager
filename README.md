# Cyberpunk 2077 模组管理器

基于 [AgentScope](https://github.com/agentscope-ai/agentscope) 大模型 Agent 框架的赛博朋克 2077 模组管理方案，参考 [Stardrop](https://github.com/Floogen/Stardrop) 的 Nexus Mods 集成模式。

## 特性

- 🤖 **Agent 驱动**：给出模组 ID，Agent 自动完成下载、安装、记录卸载方式
- 📥 **自动下载**：通过 Nexus Mods API 按 mod_id 下载模组文件
- 🗂️ **可逆安装**：安装时记录所有文件操作（新增文件、创建目录、备份原文件），卸载时反向执行
- 🖥️ **Web 管理页面**：模组列表、一键安装/卸载、卸载计划预览、Agent 对话
- 🧩 **路径规则**：内置 Cyberpunk 2077 各类模组文件（archive / TweakXL / redscript / CET）的安装路径映射

## 快速开始

### 1. 安装依赖

```bash
cd cyberpunk_mod_manager
pip install -e .
```

### 2. 配置

通过配置文件 `config.yaml` 配置。复制示例文件并填入你的信息：

```bash
cp config.example.yaml config.yaml
```

编辑 `config.yaml`：

```yaml
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

> 环境变量（`NEXUS_API_KEY`、`CP2077_GAME_PATH`、`OPENAI_API_KEY`、`MODEL_NAME` 等）仍可使用，且优先级高于配置文件，便于在容器/CI 中覆盖。

### 3. 启动

```bash
python -m cyberpunk_mod_manager
# 或
uvicorn cyberpunk_mod_manager.api.app:app --reload
```

打开浏览器访问 http://127.0.0.1:8000

## 使用方式

### 方式一：Web 页面
- 在左上输入框填入模组 ID（Nexus mod_id），点击「安装」
- 模组列表显示所有已安装模组与状态
- 点击「卸载」按记录反向移除
- 右侧「卸载计划预览」可查看某模组的完整卸载计划

### 方式二：Agent 对话
- 在右下对话框输入模组 ID 或自然语言
- 例如：「帮我安装模组 10752」「列出所有模组」「卸载模组 10752」
- Agent 会自主调用工具完成全流程

## 架构设计

详见 [DESIGN.md](./DESIGN.md)。

```
src/cyberpunk_mod_manager/
├── config.py              # 配置
├── models/                # 数据模型 (Mod, InstallRecord, Setting)
├── storage/db.py          # SQLite 存储层
├── nexus/                 # Nexus Mods API 客户端
├── installer/             # 安装/卸载引擎 + 路径规则
├── agent/                 # AgentScope Agent + 工具
├── api/                   # FastAPI 路由
└── web/                   # 前端页面
```

## 卸载记录机制

安装时为每个模组生成 `InstallRecord`，记录：
- `added_files`：新增到游戏目录的文件列表
- `created_dirs`：创建的目录（卸载时仅在为空时删除）
- `backed_up_files`：被覆盖前备份的原文件（用于恢复）

卸载时按记录反向操作，确保干净移除。
