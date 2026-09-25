# n8n (local, Docker)

| Service | Open | What it is |
|---|---|---|
| n8n | http://localhost:5678 | The workflow editor. The first time you open it, create the owner account. |
| Adminer | http://localhost:8080 | A web UI for the Postgres database where n8n stores its data. |

The containers are n8n, Postgres, Adminer, and `n8n-runners`, which runs Code nodes. Only this PC can reach them. They're only up while Docker Desktop is running, and they start automatically whenever Docker Desktop starts.

## First-time setup

Only needed on a new machine or a fresh copy of this folder. The `.env` here is already set up.

1. Copy the example: `Copy-Item .env.example .env`
2. In `.env`, fill in `POSTGRES_PASSWORD` and `N8N_RUNNERS_AUTH_TOKEN` with long random values. The comment at the top of the file has a command that generates one.
3. Run `docker compose up -d`.

## Everyday commands

Run these in PowerShell from this folder.

| Task | Command |
|---|---|
| Start (also after `stop` or `down`) | `docker compose up -d` |
| Stop (keeps the containers) | `docker compose stop` |
| Stop and remove the containers | `docker compose down` |
| Follow n8n logs | `docker compose logs -f n8n` |
| Update | For a newer n8n, first change `N8N_VERSION` in `.env`. Then `docker compose pull`, then `docker compose up -d` |

None of these commands delete your data. It lives in two Docker volumes:

- `n8n_postgres_data`: the Postgres database with your workflows, credentials and execution history.
- `n8n_data`: n8n's encryption key. Without it, the credentials saved in the database can't be decrypted.

`docker compose down -v` deletes both volumes, so only add `-v` when you mean to wipe n8n.

n8n only changes version when you change `N8N_VERSION` in `.env` (see [releases](https://github.com/n8n-io/n8n/releases)). The n8n and task-runner images both use it, so they always match. Postgres stays on major version 18, because a newer major version can't read the data without an upgrade. Take a [backup](#backup) before updating.

## Adminer

Open http://localhost:8080/?pgsql=postgres&username=n8n&db=n8n to get the login form pre-filled, then enter the `POSTGRES_PASSWORD` value from `.env`.

Editing n8n's own tables by hand can break n8n, so treat them as read-only.

## Using Postgres in your workflows

In n8n, create a Postgres credential with host `postgres`, port `5432`, and the user and password from `.env`. Keep your own tables out of the `n8n` database: create a separate database in Adminer ("Create database") and connect to that one.

## Files for workflows

The `local-files` folder is mounted in the n8n container at `/files`. In the Read/Write Files from Disk node, use paths such as `/files/input.csv`. n8n can't read or write files outside that folder.

## Connect Claude Code (MCP)

`.mcp.json` connects Claude Code to n8n's built-in MCP server at `http://localhost:5678/mcp-server/http`, so Claude can build, run and test workflows in n8n. It holds no secrets.

One-time setup:

1. In n8n, go to **Settings → Instance-level MCP** and click **Enable MCP access**.
2. Start a new Claude Code session in this folder. If it asks whether to use the `n8n` server from `.mcp.json`, approve it.
3. Run `/mcp`, select `n8n`, and choose **Authenticate**. A browser tab opens where you sign in to n8n and allow access.

Claude can't see workflows you build in the editor until you expose them: use **Enable workflows** on the same settings page.

## Backup

Stops everything for a few seconds and saves the database and the encryption key to `backups\n8n-backup-<date>.tar.gz`:

```powershell
docker compose stop
docker run --rm -v n8n_data:/n8n -v n8n_postgres_data:/postgres -v "${PWD}\backups:/backup" alpine tar czf "/backup/n8n-backup-$(Get-Date -Format yyyy-MM-dd).tar.gz" -C / n8n postgres
docker compose up -d
```

Anyone with a backup file can decrypt your saved credentials, so keep backups private.

## Restore

Replaces all n8n data with the backup. Change the file name to the backup you want:

```powershell
docker compose down -v
docker compose create
docker run --rm -v n8n_data:/n8n -v n8n_postgres_data:/postgres -v "${PWD}\backups:/backup" alpine tar xzf /backup/n8n-backup-2026-09-25.tar.gz -C /
docker compose up -d
```

## Changing settings

Edit `docker-compose.yml`, then run `docker compose up -d` to apply.

- **Open n8n from other devices on your network:** change the n8n port line to `"5678:5678"` and add `N8N_SECURE_COOKIE=false` under its `environment` (needed because the connection is plain http). Then browse to `http://<this PC's IP>:5678`.
- **Receive webhooks from the internet:** run a tunnel (ngrok, Cloudflare Tunnel) and set `N8N_WEBHOOK_URL` to its public URL.
- **Postgres login in `.env`:** don't change these values after the first start. They only apply when the database is created, so n8n would lose its connection.

## Code nodes

JavaScript and Python Code nodes run in the `n8n-runners` container. By default, n8n limits what their code can import:

- JavaScript: only `crypto` and `moment`.
- Python: nothing. For example, `import json` fails with "Import of standard library module 'json' is disallowed".

Allowing more modules means replacing the runner's config file (`/etc/n8n-task-runners.json` in `n8n-runners`). See [n8n's task runner docs](https://docs.n8n.io/deploy/host-n8n/configure-n8n/set-up-task-runners).
