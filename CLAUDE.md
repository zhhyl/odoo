# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

# Odoo

This is the Odoo codebase — a suite of open-source business apps (ERP/CRM). The current branch is `20.0`; main development typically targets `master`. Run `git status` before assuming branch state. For version specifics see `odoo/release.py` (MAJOR/MINOR, supported Python versions).

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
