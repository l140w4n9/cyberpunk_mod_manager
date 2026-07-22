# Developer-only Nexus API probes

Scripts in this directory (`_probe_*.py`, `probe_*.py`) are **not** shipped with the application.

They exist for local API exploration during development and may reference legacy patterns. The production app uses OAuth 2.0 + PKCE (`src/cyberpunk_mod_manager/nexus/oauth.py`) and Bearer authentication only.

**Web scraping scripts are forbidden** by Nexus ToS and must not be added to this repository. Collection data is fetched exclusively via the official GraphQL API (`nexus/collections.py`).

Do not include these scripts in end-user releases or Nexus review builds.
