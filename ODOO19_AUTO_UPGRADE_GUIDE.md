# Odoo 19 automatic module upgrades on Odoo.sh

## Purpose

This repository now contains a safe, version-based deployment automation for
Odoo.sh. It updates only changed, installed custom modules after a staging
branch push. It does not run a second Odoo server, connect directly to an
Odoo.sh database, or use unsupported post-build hooks.

Odoo.sh officially uses a change in an installed module's manifest version to
trigger an automatic module update for the deployed revision. This is
equivalent to upgrading the module from Apps or with `odoo-bin -u`. See the
[Odoo.sh branch documentation](https://www.odoo.com/documentation/19.0/administration/odoo_sh/getting_started/branches.html)
and the [Odoo 19 CLI reference](https://www.odoo.com/documentation/19.0/developer/reference/cli.html).

## Current repository scope

The authoritative, deployable Odoo modules are repository-root directories:

- `zencore_salesperson_tracking`
- `zencore_field_mobile_bridge`

`ZenCoreFieldFull` is the mobile application. Any nested addon copy beneath it
is intentionally not scanned by this automation. This prevents duplicate
module names and reference files from changing a production manifest version.

At the time this guide was added, the repository only has `main`, and Odoo.sh
shows it as the Production branch. No staging branch exists yet. For safety,
the workflow does not run on `main`.

## Architecture

```text
Developer push to staging
        |
        v
GitHub Actions
  - compares the push range with Git
  - identifies material changes in root custom modules
  - bumps only those manifest versions
  - pushes one bot commit
        |
        v
Odoo.sh build for the bot commit
  - detects changed manifest version
  - upgrades the affected installed module(s)
  - starts the new revision, or restores the previous successful revision
```

The initial source-code push can create an Odoo.sh build before the Actions job
finishes. The subsequent manifest-version commit is the revision that requests
the Odoo.sh module upgrade. This is expected and uses normal Git/Odoo.sh
behavior.

## Files added

- `scripts/odoo_auto_upgrade.py` — Git-aware manifest version manager.
- `scripts/test_odoo_auto_upgrade.py` — standard-library regression tests.
- `.github/workflows/odoo19-auto-upgrade.yml` — staging-only automation.

## Version manager behavior

Run a dry run locally:

```bash
python3 scripts/odoo_auto_upgrade.py --base HEAD~1 --head HEAD
```

Write changes after review:

```bash
python3 scripts/odoo_auto_upgrade.py --base HEAD~1 --head HEAD --write
```

The script:

- reads Git changes between `--base` and `--head`, including renamed files;
- detects only top-level directories containing `__manifest__.py`;
- accepts Odoo 19 versions beginning with `19.0.`;
- increments only the final numeric segment, preserving the existing number of
  version segments and manifest formatting;
- bumps Python, XML, CSV security, data, report, JavaScript, CSS, and other
  material module changes;
- ignores documentation-only changes (`.md`, `.rst`, `.txt`, `.adoc`,
  `.mdx`, and files inside `doc` or `docs` directories);
- does not bump a manifest that changed only its version, preventing a second
  bump for a manual or bot version change;
- reports newly added modules without changing their initial version, because
  installation must remain an explicit Odoo action;
- reports removed modules without attempting an uninstall.

It never scans or changes Odoo core, Enterprise, third-party modules, the
mobile app, or modules outside the repository root.

## GitHub Actions setup

The workflow listens to pushes but executes only for the configured staging
branch. Its safe default is a branch named `staging`.

1. In Odoo.sh, create a **staging** branch by forking `main`.
2. Push/create the matching `staging` branch in GitHub.
3. In GitHub repository **Settings → Secrets and variables → Actions →
   Variables**, add `ODOO_STAGING_BRANCH` with value `staging`.
   This variable is optional only when the branch is exactly named `staging`.
4. In GitHub repository **Settings → Actions → General**, set **Workflow
   permissions** to **Read and write permissions**.
5. Keep the Odoo.sh project connected to this same GitHub repository and
   staging branch.

The workflow uses `contents: write` only for its manifest-version commit. It
has no database credentials, Odoo.sh token, or production-shell access.

### Protected branches

If the staging branch is protected, permit the GitHub Actions bot to push, or
create a fine-grained GitHub token with access only to this repository's
**Contents: Read and write** permission. Store it as
`ODOO_AUTO_UPGRADE_TOKEN` in GitHub Actions secrets. If branch protection does
not allow that identity to bypass the rule, the workflow safely fails at
`git push`; it never force-pushes.

The workflow serializes runs per branch using a concurrency group and uses
normal fast-forward pushes. If a developer push wins a race, the failed bot
push is safe: the newer developer push starts a new workflow run based on the
latest source.

### Loop prevention

The bot commit includes `[skip odoo-auto-upgrade]`, and the job also skips
`github-actions[bot]`. The workflow does not rely on a `GITHUB_TOKEN` push
triggering another Actions run; GitHub may deliberately suppress that trigger.
Odoo.sh still receives the pushed Git revision through its repository
integration.

## Odoo.sh behavior and required manual configuration

No custom Odoo.sh hook is necessary or supported for this design. Odoo.sh
performs the automatic installed-module upgrade when it receives the manifest
version bump. A module that is not installed is not installed automatically.

For staging:

1. Make a small material change to one custom module on `staging`.
2. Push it to GitHub.
3. Wait for the GitHub Actions run to create the `chore(odoo)` manifest commit.
4. In Odoo.sh, wait for the build of that bot commit.
5. Open the build's `update.log` and confirm that only the intended installed
   module was updated.
6. Test the changed feature in the staging database.

For production, merge or promote the already validated staging revision into
`main`. Do not point the workflow at `main` unless you explicitly accept a
maintenance window for every material push. Odoo.sh may temporarily make an
instance unavailable while updating a module. If an update fails, Odoo.sh
reverts the production database and code to the previous successful revision;
consult that failed build's logs.

## Validation matrix

`scripts/test_odoo_auto_upgrade.py` tests the Git/version-management part of
the automation for these cases:

| Scenario | Expected behavior |
| --- | --- |
| Python model change | Affected module final version segment increments. |
| XML view change | Affected module final version segment increments. |
| Security CSV/data XML changes | Each affected module increments once. |
| Multiple module changes | Each changed root module increments independently. |
| Documentation-only change | No manifest change. |
| Version-only manifest change | No second increment. |
| Renamed source file | Owning module increments once. |
| Added module | Reported, not version-bumped or installed automatically. |
| Removed module | Reported, never automatically uninstalled. |

Run the tests locally:

```bash
python3 scripts/test_odoo_auto_upgrade.py
```

The workflow runs the same suite before modifying a manifest. Odoo.sh build
and database-upgrade validation cannot be claimed from a local checkout; carry
out the staging procedure above. To test a failed module upgrade safely,
intentionally use a disposable staging branch with a known-invalid view, check
the failed build's `update.log`, then revert the commit. Never perform this
test against Production.

## Troubleshooting

| Symptom | Check |
| --- | --- |
| Workflow is skipped | Confirm the pushed branch equals `ODOO_STAGING_BRANCH` (or is named `staging`). |
| Bot cannot push | Enable workflow write permission or use a narrowly scoped `ODOO_AUTO_UPGRADE_TOKEN` allowed by branch protection. |
| Odoo.sh did not upgrade | Confirm the bot manifest commit arrived in the Odoo.sh branch, the module is installed, and the version changed. Inspect `update.log`. |
| A module update fails | Read the failed Odoo.sh build log. Odoo.sh keeps the previous successful production revision/database. Fix the module and push a new staging revision. |
| New module is unchanged | Install it explicitly in staging first; later material changes are version-bumped. |
| Only README/docs changed | This is intentional; no database update is needed. |

## Rollback

1. Revert the offending source and generated manifest-version commit on the
   staging branch.
2. Push the revert and confirm the Odoo.sh staging build is successful.
3. Only then promote the safe revision to Production.

If a production module update fails, Odoo.sh automatically keeps/restarts the
previous successful revision and restores the previous database state. Do not
try to repair a live production database by running a separate Odoo process or
by manually invoking broad `-u all` commands.
