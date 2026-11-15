# Vikunja Map

<img width="1387" height="659" alt="image" src="https://github.com/user-attachments/assets/50a4fbd9-c345-4f4c-b745-49ccce8cb7c7" />

<img width="1052" height="714" alt="image" src="https://github.com/user-attachments/assets/d60f697b-08a0-4f85-8fdc-be8259be5e92" />

A single-page **dependency map** for [Vikunja](https://vikunja.io): a
force-directed graph of every project, task and relation, plus a **leverage
panel** ("what does this task unblock, and how heavy is it") and a
**critical-path** view. Reads everything live from the Vikunja REST API.

Vikunja can list task relations and draw them on the Gantt chart, but it has no
whole-instance graph. This fills that gap: you see the clusters, the bottlenecks
that gate everything downstream, and the longest blocking chain at a glance.

> Read-only. It never writes to Vikunja.

## Features

- **Constellation graph** — tasks as nodes, coloured by project; red arrows are
  `blocks`, grey dashed lines are `related`. Done tasks are faded, higher-priority
  tasks are larger.
- **Leverage panel** — click a task to see how many tasks it unblocks directly,
  the full downstream set, and the longest chain starting from it.
- **Critical path** — the longest chain of `blocks` among **open** tasks.
- **Full tree** — every project (nested) and task with status, priority, labels
  and relation counts.
- **Done/cancelled excluded from the maths** — completed tasks stay visible but
  are bridged (traversed, not counted), so counts reflect remaining work.
- Dark/light aware, responsive, no build step, no database.

## How it works

`mapgen.py` fetches projects, tasks and relations from the API and renders a
self-contained HTML page (the only external dependency is
[vis-network](https://visjs.github.io/vis-network/), loaded from a CDN). Two
front-ends share that code:

- **Service** (`app.py`) — a tiny Flask app that regenerates the page on every
  request. Run it in the container.
- **CLI** (`cli.py`) — writes a static HTML snapshot to a file.

## Configuration

| Variable | Meaning |
|---|---|
| `VIKUNJA_URL` | Base URL of your instance (e.g. `https://vikunja.example.com`). `/api/v1` is appended if missing. |
| `VIKUNJA_TOKEN` | Vikunja API token (*Settings → API Tokens*). A **read-only** token is enough. |
| `CACHE_TTL` | Cache in seconds. `0` = always fresh (default). Raise to 30–60 for frequent refreshes. |

The token is only ever read from the environment — keep it in your `.env`
(see `.env.example`) and never commit it.

## Quick start (Docker)

```bash
cp .env.example .env     # set VIKUNJA_URL and VIKUNJA_TOKEN
docker compose up -d --build
# open http://localhost:8000
```

## Run locally (no Docker)

```bash
python3 -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt
export VIKUNJA_URL=https://vikunja.example.com
export VIKUNJA_TOKEN=your-read-only-token
python app.py            # http://127.0.0.1:8000
```

## Static snapshot (CLI)

```bash
export VIKUNJA_URL=https://vikunja.example.com
export VIKUNJA_TOKEN=your-read-only-token
python cli.py vikunja-map.html
```

## Behind a reverse proxy (Traefik)

See `docker-compose.traefik.yml` for a full example. It serves the app without
publishing a host port. You **must** adjust three things to your setup:

1. the `Host(...)` rule (your hostname),
2. the external **network name** (the network your Traefik is on), and
3. the **middleware** name, if you add one — it must already exist in your
   Traefik config, with the right provider suffix (`@file` or `@docker`).
   A missing/misnamed middleware makes Traefik answer `404 page not found`.

## Notes & limitations

- One render queries **every** project. With `CACHE_TTL=0`, each refresh makes
  one API call per project. Raise `CACHE_TTL` if you keep the page open.
- The leverage **weight** uses task priority as a proxy for effort, since
  Vikunja has no native estimate field. Swap in your own sizing (e.g. labels)
  by changing `eff()` in `mapgen.py`.
- Saved filters (negative project IDs) are ignored.

## License

MIT — see [LICENSE](LICENSE). Set your name in the copyright line.

## Acknowledgements

Built on [vis-network](https://visjs.github.io/vis-network/) and the
[Vikunja](https://vikunja.io) API.
