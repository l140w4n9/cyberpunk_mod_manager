# Cyberpunk 2077 Mod Manager

> 🌐 Language / 语言: **English** | [简体中文](./README.zh.md)

An LLM-powered mod manager for Cyberpunk 2077 built on the [AgentScope](https://github.com/agentscope-ai/agentscope) agent framework, inspired by [Stardrop](https://github.com/Floogen/Stardrop)'s Nexus Mods integration.

## ✨ Features

- 🤖 **Agent-driven**: Query, install, uninstall and maintain mods via natural language or `mod_id`; supports SSE streaming chat and multi-session management
- 📥 **Nexus v3 integration**: Mod details, batch queries, version resolution, materialized dependencies, trending / tracked / activity feeds
- 🔗 **Official dependency resolution**: v3 materialized dependencies → GraphQL `nexusRequirements` → built-in community prerequisite table (never inferred from description text)
- 📦 **Collection install**: Parse a Nexus Collection URL and batch-install the **specific file versions** pinned by the collection, with revision-change detection
- 🧠 **LLM install plan**: Three modes — `llm_first` / `hybrid` / `rules_only`; unmatched files are routed by an LLM, with preview-before-execute
- 🩺 **Health audit**: Pending / incomplete-deps / update detection / LLM repair suggestions, optional auto-fix, async tasks supported
- 🗂️ **Reversible installs**: Records added files, created dirs and backed-up files; uninstall replays the record in reverse, with a plan-preview step
- 🖥️ **Web UI**: Sidebar multi-workspace (Installed, Pending, Collections, Audit, Agent, Settings), built with Vue 3 + Vite
- 🧩 **Path rules**: Built-in mappings for archive / TweakXL / redscript / CET etc., multi-game ready via `game_domain` + `game_profiles/`
- 💾 **Local fallback**: When Nexus API refuses downloads (non-Premium), install from local archives in `downloads/` or scan a local folder for batch install
- 🌍 **Localized UI**: `ui_locale` supports `zh` / `en`; switch from the sidebar and it persists to config

## Quick Start

### 1. Install dependencies

```bash
cd cyberpunk_mod_manager
pip install -e .
```

### 2. Configure

Copy the example config and fill in your details:

```bash
cp config.example.yaml config.yaml
```

Edit `config.yaml` (**`data_dir` is required**):

```yaml
data_dir: "D:/CyberpunkModManager/data"
game_path: "D:/Steam/steamapps/common/Cyberpunk 2077"
game_domain: cyberpunk2077          # Nexus game domain; selects which path-rule profile to load
openai_api_key: "your LLM API Key"
model_name: "gpt-4o-mini"
openai_base_url: "https://api.openai.com/v1"
install_plan_mode: llm_first        # llm_first | hybrid | rules_only
ui_locale: en                       # zh | en
```

Config lookup order:

1. Path pointed to by the `CP2077_CONFIG` environment variable
2. `config.yaml` / `config.yml` / `config.toml` in the current working directory
3. `~/.cyberpunk_mod_manager/config.yaml`

You can also fill in the form on the frontend **Settings** page and save it to `config.yaml`.
You can also configure everything in the web **Settings** page and use **Connect Nexus account** for OAuth (tokens are encrypted locally).

> Nexus OAuth Client ID is set by the developer in `src/cyberpunk_mod_manager/nexus/credentials.py` (or via `NEXUS_OAUTH_CLIENT_ID` at build time); end users do not configure it.
>
> Environment variables (`CP2077_GAME_PATH`, `OPENAI_API_KEY`, `MODEL_NAME`, etc.) still work and take precedence over the config file.

### 3. Launch

```bash
python -m cyberpunk_mod_manager
# or
uvicorn cyberpunk_mod_manager.api.app:app --reload
```

Open http://127.0.0.1:8000 in your browser.

The sidebar footer shows system status; when the Nexus key is valid it also shows your username and Premium state.

### 4. Frontend development (Vue 3 + Vite)

The web UI source lives in `frontend/`:

```bash
cd frontend
npm install
npm run dev      # http://127.0.0.1:5173 (/api proxied to the backend)
npm run build    # outputs to src/cyberpunk_mod_manager/web/
```

> After changing the frontend, run `npm run build` so FastAPI serves the latest static assets.

## Usage

### Web workspaces

| Workspace | Description |
|-----------|-------------|
| **Agent** | Conversational install / uninstall / batch maintenance |
| **Installed** | Install by mod_id or local package; view dependencies and uninstall plan |
| **Pending** | Mods in inventory but not yet installed; single / one-click cleanup |
| **Incomplete** | Installed mods missing required prerequisites |
| **Collections** | Paste a Collection URL, parse the queue, then batch-install (collection-pinned versions) |
| **Audit** | One-click audit, update detection, Nexus discovery (trending / tracked sync / activity feed) |
| **Settings** | Data directory, game path, API keys, etc. |

### Agent chat examples

- "Install mod 27967 with dependencies"
- "List mods with incomplete dependencies and fix them"
- "Check all installed mods for updates"
- "Sync the mods I track on Nexus"

### Local install fallback

When the Nexus API refuses download (non-Premium, etc.):

1. Manually download the archive from the website
2. Place it in `data_dir/downloads/` (filename should contain the mod_id, e.g. `27967_xxx.zip`)
3. Use "Install local archive" on the web page, or have the Agent call `install_local_mod`

### Premium vs. non-Premium functionality

The application adapts to the user's Nexus account tier. **Direct API downloads require a Premium account**; non-Premium users get the full metadata/audit experience but must download archives manually.

| Feature | Premium | Non-Premium |
|---------|:-------:|:-----------:|
| Mod search & details | ✅ | ✅ |
| Dependency resolution | ✅ | ✅ |
| Health audit & update detection | ✅ | ✅ |
| Trending / tracked / activity feed | ✅ | ✅ |
| **Direct API download** | ✅ | ❌ |
| **Collection batch auto-download** | ✅ | ❌ (manual download) |
| **Install from local archive** | ✅ | ✅ |

The sidebar footer shows the connected username and Premium status (OAuth JWT / `validate.json`) so users know which features are available.

## Nexus API architecture (v3)

The main client `nexus/client.py` uses **v3 REST + GraphQL**:

| Capability | Endpoint |
|------------|----------|
| Mod details | GraphQL + `POST /mods/batch` |
| File versions | `/mods/{id}/files`, `/mod-file-versions/batch` |
| Materialized deps | `/mod-file-versions/{id}/dependencies/materialized` |
| Dependency ranges | `/mod-file-versions/{id}/dependencies/ranges` |
| Trending mods | `GET /games/cyberpunk2077/trending-mods` |
| Collections | GraphQL `collectionRevision` (with `fileId` + `uid` version pin) |

Nexus **does not yet offer a v3 download endpoint**, so a tiny legacy shim `nexus/_legacy_v1.py` is retained, only for:

- Premium download links (`download_link.json`, Bearer auth)
- OAuth session validation (`validate.json`, Bearer auth)
- Account tracked list (`tracked_mods.json`)
- Recent activity feed (`updated.json`)

Everything else has been migrated to v3; the old `v3_client.py` and the full v1 client have been removed.

### Dependency resolution priority

1. v3 materialized dependencies (by installed `nexus_version_id` or latest main file version)
2. GraphQL `nexusRequirements` (`notes` field marks optional)
3. Built-in `KNOWN_MOD_DEPENDENCIES` community prerequisite table (explicit hard-coded supplements)

We no longer scan mod descriptions / HTML for Nexus links, avoiding false positives from credits, recommendations, or prequel links.

## REST API overview

### Health & config

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/health` | System status, Nexus connection/Premium |
| GET/PUT | `/api/config` | Read/save config (no secret plaintext) |
| POST | `/api/nexus/auth/start` | Start OAuth PKCE flow |
| GET | `/api/nexus/auth/callback` | OAuth callback (browser) |
| DELETE | `/api/nexus/auth` | Disconnect Nexus account |

### Mods

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/mods` | List inventory mods |
| GET | `/api/mods/pending` | Pending list |
| GET | `/api/mods/incomplete` | Incomplete-deps list |
| POST | `/api/mods/install` | Install a mod |
| POST | `/api/mods/install-with-deps` | Install and fill dependencies |
| POST | `/api/mods/install-local` | Install from a local archive |
| POST | `/api/mods/install-local-folder` | Batch install from a local folder |
| POST | `/api/mods/uninstall` | Uninstall a mod |
| DELETE | `/api/mods/{mod_id}` | Delete from inventory (only if not installed) |
| POST | `/api/mods/cleanup-pending` | Batch cleanup of pending |
| GET | `/api/mods/{mod_id}/dependencies` | Dependency report |
| GET | `/api/mods/{mod_id}/dependency-ranges` | v3 dependency ranges |
| POST | `/api/mods/check-updates` | Check for updates |
| POST | `/api/mods/audit` | Health audit |
| POST | `/api/mods/audit/start` | Async audit task |
| POST | `/api/mods/check-updates/start` | Async update-check task |

### Nexus discovery

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/mods/discovery/trending` | Trending mods |
| POST | `/api/mods/discovery/sync-tracked` | Sync tracked mods into inventory |
| GET | `/api/mods/discovery/updated-feed` | Recent activity feed |
| POST | `/api/mods/discovery/batch-status` | Batch query mod status |

### Collections

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/collections/parse` | Parse a Collection URL |
| POST | `/api/collections/install` | Start a batch install job |
| GET | `/api/collections/jobs/{job_id}` | Query job progress |
| GET | `/api/collections/revision` | Detect collection revision change |

### Agent

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/agent/chat` | Chat (sync) |
| POST | `/api/agent/chat/stream` | Chat (SSE streaming) |
| GET/POST | `/api/agent/sessions` | Session management |

## Agent tools

| Tool | Function |
|------|----------|
| `search_mod` | Query a mod and sync to inventory |
| `check_dependencies` | Check prerequisites |
| `install_mod_with_dependencies` | Install a mod and fill dependencies (preferred) |
| `install_mods_batch` | Batch install |
| `install_mod` | Install a single mod only |
| `preview_install_plan` | Preview the LLM install plan (no execution) |
| `install_local_mod` / `install_local_folder` | Install from local archive / folder |
| `scan_local_folder_tool` | Scan a local folder structure |
| `uninstall_mod` | Uninstall a mod |
| `uninstall_mod_with_plan_review` | Preview the uninstall plan before removing |
| `list_mods` / `list_pending_mods` / `list_incomplete_mods` | Inventory listings |
| `check_mod_updates` | Check Nexus for updates |
| `fetch_trending_mods` / `sync_tracked_mods` / `fetch_updated_mod_feed` | Nexus discovery |
| `batch_mod_status` | Batch query mod status |
| `audit_installation` | Health audit (optional auto-fix) |
| `get_uninstall_plan_tool` | View the uninstall plan |

## Project structure

```
src/cyberpunk_mod_manager/
├── config.py              # Configuration
├── models/                # Mod, dependency, install record, etc.
├── storage/db.py          # SQLite + migrations
├── nexus/
│   ├── client.py          # Unified v3 REST + GraphQL client
│   ├── _legacy_v1.py      # Legacy shim for download/user/tracked/feed
│   ├── dependencies.py    # Dependency resolution & sync
│   ├── collections.py     # Collections GraphQL
│   └── schemas.py         # API data structures
├── services/
│   ├── mod_ops.py         # Install / download / inventory
│   ├── health_audit.py    # Audit & update detection
│   ├── collection_ops.py  # Collection install queue
│   ├── install_plan.py    # LLM / hybrid / rules install planning
│   └── discovery.py       # trending / tracked / updated
├── installer/             # Install / uninstall engine + path rules
├── agent/                 # AgentScope Agent + tools
├── api/                   # FastAPI routes
├── web/                   # Built frontend assets
└── frontend/              # Vue 3 + Vite source
```

See [DESIGN.md](./DESIGN.md) for the original design doc (some sections still describe the early v1 architecture; this README and the code are authoritative).

## Uninstall record mechanism

Each install generates an `InstallRecord` capturing:

- `added_files`: files added to the game directory
- `created_dirs`: directories created (deleted on uninstall only if empty)
- `backed_up_files`: originals backed up before being overwritten

Uninstall replays the record in reverse, ensuring a clean removal.

## Testing

```bash
cd cyberpunk_mod_manager
pytest tests -q
```

## License

See the license file in the project root (if present).
