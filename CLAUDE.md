# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

# Odoo

This is the Odoo codebase — a suite of open-source business apps (ERP/CRM). The current branch is `20.0`; main development typically targets `master`. Run `git status` before assuming branch state. For version specifics see `odoo/release.py` (MAJOR/MINOR, supported Python versions).

## Code-Review Workflow（每次改完程式碼必做）

**任何程式碼修改，在 `git commit` 之前，都必須在一個全新的 session 做一次 code review。** 審查者不能是寫程式碼的那個 session：新 session 沒有作者的預設前提，才會像最嚴謹的同事一樣重讀一次 diff 與周邊程式碼，找出作者自己想不到的缺陷——尤其是「改 A 壞到 B」這種回歸。

（環境需求見下方 **Environment Requirements**，指令見 **Common Commands**。）

### 流程

1. **開一個新 session**，工作目錄就是目前這個 checkout（改動還沒 commit），開場直接說：

   > 請 code review 目前工作目錄的變更，依 `skills/odoo-review/SKILL.md` 的流程執行（rules pass + merits pass），並讀它指定的 guideline 章節。

   本 repo 的 `skills/` **尚未安裝**成 Claude Code skill（沒有 `.claude/skills/`），所以不能直接輸入 `/odoo-review`——要在 prompt 指明 SKILL.md 路徑，或先把 `skills/` 複製到 `.claude/skills/`。

2. **審查 session 只回報 finding，不修改檔案。** 修正由作者 session 做，改完再開一個新 session 複審，直到沒有阻擋性缺陷為止。審查者若自己動手改，就等於「審查者也是作者」，抵銷了這條規則的意義。

3. **審查範圍**：
   - `git status --porcelain` 看全部改動（**新檔沒有 diff**，要另外列出）
   - `git diff HEAD` 看變更（要用 `HEAD` 當比較點，空參數只看得到 unstaged，會漏掉已 `git add` 的部分）
   - diff 看不到的「另一半」——其他 `mfg_custom_*` / `plm_custom_*` 模組、`depends` 的安裝順序、`ir.access.csv`、mail template、view 的 xpath

4. **在 UAT 實跑驗證**（本機沒有 PostgreSQL / Docker，UAT 是唯一能跑 Odoo 的環境；主機 `admin-icd@10.84.84.125`，程式碼在 `/opt/project/odoo`）。

   **順序很重要：先 build（不重啟）→ 用一次性容器跑測試與升級 → 最後才讓常駐伺服器用新 image 起來。** 反過來做，常駐伺服器就會以「新程式碼 + 舊 schema」開機，任何讀到新欄位的 request 都會炸 SQL error。

   ```bash
   # 在 repo 根目錄執行。模組清單會自動跟著新增的模組長。
   # （用 tr 不要用 paste -sd,：BSD 的 paste 參數格式不同）
   MODS=$(find addons -maxdepth 1 -type d \( -name 'mfg_custom_*' -o -name 'plm_custom_*' \) \
          | sort | xargs -n1 basename | tr '\n' ',' | sed 's/,$//')

   # 用 shell function 取代變數：zsh 不會對未加引號的變數做字元分割，
   # 寫成 SSH="ssh ..." 再 $SSH '...' 會把整串當成一個指令而失敗。
   uat() { ssh -o StrictHostKeyChecking=accept-new -i "$HOME/.ssh/icdserver" \
               admin-icd@10.84.84.125 "$@"; }
   ```

   ```bash
   # a. 同步**所有**自訂模組（模組互相咬得很深，只同步一個會讓測試失真）
   for m in $(find addons -maxdepth 1 -type d \( -name 'mfg_custom_*' -o -name 'plm_custom_*' \) | sort); do
     rsync -az --delete --exclude '__pycache__' --exclude '*.pyc' \
       -e "ssh -o StrictHostKeyChecking=accept-new -i $HOME/.ssh/icdserver" \
       "$m/" "admin-icd@10.84.84.125:/opt/project/odoo/$m/"
   done
   # 驗證同步結果（遠端 git status 應該列出跟本機一樣的檔案）
   uat 'cd /opt/project/odoo && git status --short'

   # b. 只重建映像，**先不要**重啟常駐伺服器。
   #    這台機器的 build context 約 1.1GB（.git 已被 .dockerignore 排除），
   #    改動 addons 會讓 Dockerfile 最後的 COPY 層失效 → 重建約需 5-7 分鐘，
   #    屬正常現象，不是卡住。
   uat 'cd /opt/project/odoo && docker compose build odoo'

   # c. 測試庫全新安裝 + 跑全套測試。用一次性容器跑 → 跑的是新 image，
   #    不影響常駐伺服器。測試庫必須 DROP + -i，post_install 測試才會執行。
   uat 'cd /opt/project/odoo && docker compose exec -T db \
       psql -U odoo -d postgres -c "DROP DATABASE IF EXISTS odoo_test WITH (FORCE);"'
   uat "cd /opt/project/odoo && docker compose run --rm odoo -d odoo_test \
       --db-filter='^odoo_test\$' --test-enable --stop-after-init \
       --test-tags=mfg_custom,plm_custom -i $MODS"

   # d. 正式庫升級。**有 schema 變更時要先停常駐伺服器**，
   #    避免兩個 Odoo process 同時寫同一個 DB。
   uat 'cd /opt/project/odoo && docker compose stop odoo'
   uat "cd /opt/project/odoo && docker compose run --rm odoo -d odoo -u <模組> --stop-after-init"
   uat 'cd /opt/project/odoo && docker compose up -d'   # 常駐伺服器用新 image 起來

   # e. 確認結果：失敗數與錯誤數都必須是 0，而且測試筆數 N 要 > 0
   #    （N = 0 代表 --test-tags 沒選到測試，是假通過）
   uat 'docker exec odoo-odoo-1 sh -c "grep -E \"tests.result\" /var/log/odoo/odoo.log | tail -3"'
   ```

   測試摘要會寫進 `odoo.log`（容器有 `ODOO_RC` 環境變數，`odoo-bin` 讀得到
   `/etc/odoo/odoo.conf`，裡面的 `logfile` 指向 `/var/log/odoo/odoo.log`）。
   這份 log 是常駐伺服器與一次性容器共用的 named volume、跨容器重建會保留，
   所以要看**時間戳**確認是剛才那次 run 的結果。

5. **確認 lint 沒有新增問題**。自訂模組本來就不符合 repo 的 ruff 規則（尾逗號、未使用匯入、匯入排序、全形標點…），所以只能比對 baseline 差異，不能看絕對數字。

   **在 repo 根目錄執行**——`ruff.toml` 在根目錄，對 repo 外的路徑 ruff 會改用 cwd 找到的設定檔，規則集會整個不一樣（實測同一份檔案在根目錄是 67 個錯誤、在 `/tmp` 是 27 個）。
   **用 `git archive` 取 HEAD 版本當 baseline，不要用 `git stash`**——stash 會把未追蹤的新檔也收進去，中途中斷就只剩 stash 裡有變更：

   ```bash
   rm -rf /tmp/lint-base && mkdir -p /tmp/lint-base
   git archive HEAD addons/<模組> | tar -x -C /tmp/lint-base
   python3 -m ruff check --extend-ignore RUF002,RUF003 /tmp/lint-base/addons/<模組>/ | tail -2   # baseline
   python3 -m ruff check --extend-ignore RUF002,RUF003 addons/<模組>/ | tail -2                      # 改動後
   rm -rf /tmp/lint-base
   ```

   - `RUF002` / `RUF003` 是中文全形標點造成的大量錯誤（`ruff.toml` 已忽略 `RUF001`），這兩個要另外加
   - **不要加 `--select`**：加了會改用自訂規則集，量到的東西跟 repo 政策無關
   - **全新模組沒有 baseline**：`git archive HEAD addons/<新模組>` 會 fatal，ruff 會把「路徑不存在」算成 1 個錯誤 → baseline 視為 0，新模組的 lint 錯誤數應該要是 0
   - 本機 `python3` 是 3.9，只用來跑 ruff，跟 Odoo 執行用的直譯器無關；`ruff` 不在 PATH，要用 `python3 -m ruff`

6. **i18n**：新增或修改可翻譯字串後，重新匯出 `.pot`。要在**已經換成新 image 的常駐容器**裡跑（步驟 4 的 `docker compose up -d` 之後），輸出檔先落在容器內再 `docker cp` 出來——`docker compose run --rm` 的容器結束就被刪掉，檔案拿不出來：

   ```bash
   uat 'docker exec odoo-odoo-1 python3 /opt/odoo/src/odoo-bin i18n export \
       -d odoo_test <模組> -o /tmp/<模組>.pot'
   uat 'docker cp odoo-odoo-1:/tmp/<模組>.pot /tmp/'
   scp -o StrictHostKeyChecking=accept-new -i $HOME/.ssh/icdserver \
       admin-icd@10.84.84.125:/tmp/<模組>.pot /tmp/
   cp /tmp/<模組>.pot addons/<模組>/i18n/<模組>.pot
   ```

   `.po` **不要手改**（見下方 **Contribution Notes** / **Common Pitfalls**，由 Weblate 依 `.pot` 同步）。若中文介面要立刻看到新字串，先把新字串手動加進 `.po`（來源字串本來就是中文，`msgstr` 留空即可）。

### 這個 repo 特有的審查重點

- **跨模組共用的 mixin**：改 `mfg_custom.approval.mixin`（定義在 `mfg_custom_approval`）會影響 5 個下游模組——`mfg_custom_issue`、`mfg_custom_purchase_approval`、`mfg_custom_quality`、`plm_custom_eco`、`plm_custom_feasibility`；`mfg_custom.model.mixin`（定義在 `mfg_custom_base`）目前只有 `mfg_custom_approval` 的測試模型繼承。**動手前先 grep 繼承者清單。**
- **同一個標準模型的多處 `_inherit`**：`mrp.production` 有 3 處、`res.users` 有 2 處。欄位名衝突、`@api.depends` 互相影響都要確認。
- `mfg_custom_base` 是全部 12 個自訂模組的共同地基，改它等於改全部；它的群組（`group_user` / `group_manager` / `group_engineering` / `group_quality`）被每個模組的 `ir.access.csv` 引用。
- `__manifest__.py` 新增 `depends` → Odoo 會依相依圖自動排序安裝；但若本模組的 `data` 檔要引用**另一個模組**的資料記錄（群組、mail template、序號），那個相依必須寫在 `depends` 裡，靠 `data` 內的排列順序沒有用。
- `data` 清單內部順序：`security/` 要排最前面（後面的資料檔會引用群組 xmlid）——12 個自訂模組都遵守這個慣例。
- 新增模型 → `security/ir.access.csv` 要有對應 ACL 列。Odoo 20 用 `ir.access`（欄位是 `id,name,model_id,group_id/id,operation,domain`），不是舊版的 `ir.model.access`；且 CSV **檔名決定套用到的模型**（`odoo/tools/convert.py`），不能只放註解列。
- 群組 / ACL 變更 → 影響所有既有使用者，要評估權限擴張範圍。
- schema 變更（新增欄位）→ 確認是否需要 `migrations/` 遷移腳本（參考 `mfg_custom_approval/migrations/`）。
- **新增測試檔一定要加** `@tagged("post_install", "-at_install", "mfg_custom", "plm_custom")`——`--test-tags=mfg_custom,plm_custom` 靠的就是這個 decorator 選測試，漏了會靜默跑 0 個測試而「假通過」。

## Environment Requirements

- **Python**: `>= 3.12` and `<= 3.14` (see `MIN_PY_VERSION` / `MAX_PY_VERSION` in `odoo/release.py`).
- **PostgreSQL**: `>= 16` (`MIN_PG_VERSION` in `odoo/release.py`).
- **Node**: required only for JS asset building inside addons that ship a frontend (e.g. `web/`, `web_studio/`). Each such addon has its own `package.json` and Yarn-based toolchain; do not run `npm install` at the repo root.
- **Pinned dependencies**: see `requirements.txt`. Install via `pip install -r requirements.txt` (or `.txt[.section]` for extras like `requirements.txt[ldap]`).
- **Lint**: `ruff >= 0.16.1` — config in `ruff.toml`. CLI flags worth knowing: `--extend-select RST` comes from `setup.cfg` (flake8 compat).

## Common Commands

The CLI entry point is `odoo-bin` (a tiny shim around `odoo.cli.main`). The packaged script is `setup/odoo`. Always invoke via `./odoo-bin` or `python odoo-bin`.

```bash
# Start the server (reads ./odoo.conf or flags)
./odoo-bin -d mydb --addons-path=addons,odoo/addons

# Run server then drop into a Python shell with registry loaded
./odoo-bin shell -d mydb --addons-path=addons,odoo/addons

# Scaffold a new addon
./odoo-bin scaffold my_module addons/

# Run python tests for one module
./odoo-bin -d mydb --test-enable --stop-after-init \
    --test-tags=/test_my_module --addons-path=addons,odoo/addons -i my_module

# Run a single python test method
./odoo-bin -d mydb --test-enable --stop-after-init \
    --test-tags=/test_my_module:test_class.test_method \
    --addons-path=addons,odoo/addons

# Run lint-only checks (uses the test_lint addon)
./odoo-bin -d mydb --test-enable --stop-after-init \
    --test-tags=/test_lint --addons-path=addons,odoo/addons -i test_lint

# Update / migrate a database
./odoo-bin -d mydb --update=module_name --addons-path=addons,odoo/addons
./odoo-bin -d mydb --upgrade-path=odoo/upgrade --addons-path=addons,odoo/addons

# Other useful subcommands (see odoo/cli/)
./odoo-bin db create|drop|duplicate -d <name>
./odoo-bin i18n export|import ...
./odoo-bin neutralize -d <name>
./odoo-bin populate (only for addons that ship a populate/ directory)

# Lint (Python only)
ruff check path/to/file.py
ruff format path/to/file.py
```

JS unit tests run in the browser via the `hoot` framework (see `web/static/lib/hoot/`). The frontend test bundles are declared in `addons/web/__manifest__.py` under `web.assets_unit_tests*`.

## Repository Layout

```
odoo/                  # The "odoo" Python package: the server itself
  release.py           # version + Python/PG supported-version constants
  init.py              # imported very early; sets up gevent/DBAPI monkeypatches
  orm/                 # ORM core: Registry, Environment, Transaction, fields
                        # base class, decorators (@model, @depends, ...), NewId
  api/                 # Re-exports the ORM's public API (Environment, ormcache,
                        # @depends, SUPERUSER_ID, types like DomainType)
  models/              # Base classes for addon models (Model, TransientModel,
                        # AbstractModel) — see "Big Picture" below
  fields/              # Field type implementations consumed by the ORM
  http/                # WSGI dispatcher, routing, sessions, controllers
  service/             # Long-running services (cron, live chat bus, etc.)
  modules/             # Module discovery, graph resolution, loading, migrations
  tests/               # Test runner base classes (TransactionCase, HttpCase,
                        # tagged tests, run-test entrypoint)
  cli/                 # Subcommands reachable via odoo-bin (server, shell,
                        # scaffold, db, i18n, neutralize, populate, ...)
  tools/               # Standalone utilities (config, sql_db, image, i18n,
                        # mail, translate, file/conversion helpers)
  upgrade/             # SQL/data migration scripts that ship with the version
  upgrade_code/        # Python helpers referenced by upgrade scripts
  addons/              # "Kernel" addons that the server itself requires
                        # (notably `base`, `test_*`, `web` lives elsewhere)

addons/                # All other addon modules. Two big families:
                        # - community/app addons (account, sale, stock, website, ...)
                        # - `web/`                : the Odoo web client (JS/SCSS)
                        # Sub-trees with their own layout:
                        #   <addon>/__manifest__.py   # required, declares deps/data/assets
                        #   <addon>/__init__.py       # imports models/, controllers/
                        #   <addon>/models/           # python models
                        #   <addon>/views/            # XML views + actions
                        #   <addon>/data/             # XML/CSV demo + master data
                        #   <addon>/security/         # ir.access.csv + groups XML
                        #   <addon>/controllers/      # HTTP routes
                        #   <addon>/report/           # QWeb PDF reports
                        #   <addon>/static/src/       # JS + SCSS
                        #   <addon>/static/tests/     # JS unit tests
                        #   <addon>/tests/            # Python unit tests
                        #   <addon>/wizard/, populate/, i18n/, ...

debian/                # Debian packaging — not used during development.
setup/                 # Installable script `odoo`, packaging bits, Docker,
                        # win32 helpers, sandboxing, IOT box builder.
skills/                # Odoo's own Skills library (see "Skills" below).
doc/cla/               # CLA-related docs only.
.github/               # PR template only — no CI to wire up locally.
```

## Big-Picture Architecture

### ORM (`odoo/orm/` and friends)

The ORM is the spine of the server. One `Registry` instance exists per database; it exposes the `Environment` (cursor, user, context, registry) threaded through every model method call.

- `odoo/orm/registry.py`     → builds the registry by loading module graphs.
- `odoo/orm/environments.py` → `Environment`, `Transaction`. The env is implicitly passed in via `self` on model methods; do not pass it around manually.
- `odoo/orm/identifiers.py`  → `NewId` (the placeholder id for records not yet flushed to the DB — important when reasoning about `create()` and `flush()`).
- `odoo/orm/decorators.py`   → `@model`, `@depends`, `@constrains`, `@onchange`, `@private`, `@readonly`, ... Use these instead of writing override hooks by hand.
- `odoo/orm/cache.py`        → `ormcache` — keyed on `(cr, self._name, self._context)`-like tuples; clear with `self.env.clear_caches()` (avoid in tight loops).
- `odoo/orm/types.py`        → domain/list/value type aliases (`DomainType`, `CommandValue`, etc.) used in `Command` operations and method signatures.
- `odoo/orm/utils.py`        → `SUPERUSER_ID`.

`odoo/api/__init__.py` re-exports the public surface so addon code can `from odoo import api, fields, models` and `from odoo.api import Environment`. Do **not** import private names from `odoo.orm.*` directly; they are organized as separate packages to avoid merge conflicts.

`odoo/models/__init__.py` (re-exported as `odoo.models`) provides the `BaseModel`, `Model`, `TransientModel`, and `AbstractModel` base classes that every concrete addon model subclasses.

### Module loading

Modules are discovered from `--addons-path` (default includes `addons/` and `odoo/addons/`) and resolved into a graph (`odoo/modules/module_graph.py`), then loaded in topological order by `odoo/modules/loading.py`. What a module ships is declared in `__manifest__.py`: `depends`, `data` (XML/CSV always loaded), `demo` (only on demo databases), `assets` (JS/SCSS bundles referenced by XML via `t-call-assets`), `installable`, `auto_install`, `bootstrap`, `category`, ...

Always anchor view inheritance on `xpath` expressions that select by stable `name` attributes — extension-by-position is forbidden (see skills/odoo-guidelines/guidelines/xml.md).

### HTTP layer (`odoo/http/`)

`odoo/http/router.py` + `routing_map.py` build a per-host route map. `odoo/http/dispatcher.py` runs requests inside a `Transaction`, mirroring the ORM's transactional model. Controllers live under each addon's `controllers/` and are decorated with `@http.route()`. Sessions live in `odoo/http/session.py`; the public session storage is `odoo/addons/base/models/res_users.py`.

### Services (`odoo/service/`)

Long-running workers: `server.py` (the gevent/prefork server), `model.py` (cron / queue jobs), `common.py` (XML-RPC dispatch). Crons are dispatched by `addons/base/models/ir_cron.py`; jobs are tracked in `ir.cron` rows.

### Tests (`odoo/tests/`)

- `TransactionCase` / `SavepointCase` / `HttpCase` are the base test classes an addon's `tests/` directory should subclass (see `odoo/tests/common.py`).
- Tests are tagged with `tagged()` decorators; selectors are passed to `--test-tags` (e.g. `--test-tags=/test_sale,-post_install`).
- The `addons/test_*` modules are the "official" test addons (located under `odoo/addons/`). Run them with `-i test_*` + the module's tag.
- A "lint-only" pass is provided by `odoo/addons/test_lint/`; it is invoked separately with the `/test_lint` tag and is what Ruff/flake8-style checks run inside CI.
- Frontend tests live under each addon's `static/tests/` and use Hoot (a custom test runner; entrypoint in `addons/web/static/lib/hoot/`).

## Skills (this repo ships its own)

`skills/` contains Odoo's official Skills library for agentic development. When installed into a Claude/Copilot/Codex workspace (see `skills/README.md`), they bias reviews and authoring toward Odoo conventions. Always invoke them when relevant:

- `odoo-guidelines`        — module structure, Python/ORM, fields, views, controllers, reports, security, perf, tests.
- `odoo-web-guidelines`    — JS / Owl templates / SCSS under `static/`.
- `odoo-review`            — code review checklist.
- `odoo-security`          — security review checklist.
- `odoo-git`               — git workflows, branch policy, PR conventions.

These mirror the [Odoo Developer Guidelines](https://www.odoo.com/documentation/latest/contributing/development/coding_guidelines.html) and the "stable version" rules (see `skills/odoo-guidelines/guidelines/stable.md`). Reach for them on any non-trivial change — especially anything in `addons/`.

## Contribution Notes

- Branch policy: `master` is the development branch; `20.0` (this branch) is a stable release. Backports must follow the rules in `skills/odoo-guidelines/guidelines/stable.md` and the wiki (linked from `CONTRIBUTING.md`).
- PR template at `.github/PULL_REQUEST_TEMPLATE.md` requires a CLA signature.
- Source code license: LGPL-3 (`LICENSE`, `COPYRIGHT`).
- Translation sources: `.weblate.json` configures Weblate; `addons/*/i18n/*.po` are auto-generated and shouldn't be hand-edited.
- `git blame` should skip the commits listed in `.git-blame-ignore-revs` (run `git config blame.ignoreRevsFile .git-blame-ignore-revs` once per clone).

## Common Pitfalls

- Forgetting to add `--addons-path=addons,odoo/addons` — without it, the `base` module won't be found and the server won't start.
- Importing from `odoo.orm.*` directly instead of through `odoo.api`. Stick to `from odoo import api, fields, models` and friends; the internal split exists to reduce merge conflicts.
- Using `sudo -u postgres` on macOS without first exporting `PGUSER`/`PGHOST`, or running as `root` — the server actively refuses both (`check_postgres_user`, `check_root_user` in `odoo/cli/server.py`).
- Editing generated `.po` files; let Weblate handle translations.
