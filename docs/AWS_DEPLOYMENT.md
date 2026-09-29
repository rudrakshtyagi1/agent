# Manual AWS deployment

This guide deploys the authenticated monitoring dashboard on one EC2 Linux server.
Caddy serves the built React dashboard and proxies `/api/*` to one FastAPI process.
PostgreSQL stores the durable inbox and traces in a Docker volume. Redis, Qdrant,
Ollama and a Groq credential are not required by this monitoring deployment.
The full evaluation/chaos/diagnosis demo remains local: its unscoped APIs are disabled
outside development. Do not turn on development mode to expose those APIs publicly.

## 1. AWS resources you create

Use an Ubuntu LTS EC2 instance with at least 2 GiB RAM for a small demo; build
performance depends on instance size. Attach encrypted EBS storage with enough room
for database retention, images and backups. Use a stable public address and point a
DNS A record such as `agentguard.example.com` to it. This setup is a single-server
portfolio deployment, not highly available infrastructure. AWS services may incur
charges; configure an AWS Budget and check your account's current eligibility.

Allow inbound TCP 80 and 443. Restrict SSH 22 to your own IP (or use Systems Manager).
Do not expose 8000 or 5432. Install Docker Engine with the Compose plugin using the
[official Ubuntu instructions](https://docs.docker.com/engine/install/ubuntu/).
Use an administrator-controlled server: Docker access grants host-level privileges.

References: [EC2 security group rules](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/security-group-rules-reference.html),
[Caddy automatic HTTPS](https://caddyserver.com/docs/automatic-https).
A resolving domain and reachable ports 80/443 allow Caddy to issue and renew TLS.
The local acceptance run uses HTTP on loopback; public certificate issuance must
be verified on your server after DNS is configured.

## 2. Prepare and launch

```bash
git clone https://github.com/rudrakshtyagi1/agent.git
cd agent
python3 scripts/init_deploy_env.py --domain agentguard.example.com
docker compose --env-file .env.deploy up -d --build --wait
```

Replace the example domain. The generator writes random database and monitoring
credentials into `.env.deploy` with mode 600 and refuses to overwrite an existing
file. Keep the file backed up securely and outside Git. The build context excludes
environment files, local databases and reports. Never put a secret in a `VITE_*`
variable. `GROQ_API_KEY` stays on the computer running the external agent.

The database migration runs before API startup. One process and one API container
are supported. Do not add Uvicorn workers or scale replicas: queue coordination
currently uses a process-local lock. Database/API ports are private to Compose.
Only Caddy publishes ports. PostgreSQL and TLS state persist across recreation.

Open your HTTPS domain. Read the `portfolio` value inside `MONITOR_KEYS` in the
private environment file and enter it into the dashboard's bearer-key field. It is
an operator credential with read/write access to that tenant. Do not publish it or
embed it in the frontend. This is not end-user signup/RBAC.

## 3. Acceptance after deployment

On a trusted machine with Python, install the dependencies and SDK:

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -r backend/requirements.lock -e ./sdk
read -rs -p 'Monitoring key: ' AGENTGUARD_API_KEY; echo
export AGENTGUARD_API_KEY
python scripts/deployment_smoke.py --endpoint https://agentguard.example.com
```

The check sends one synthetic trace and verifies readiness, HTML serving, missing
and invalid credential rejection, disabled local demo routes and worker processing.
It saves a report with no credentials. Keep its trace ID and check restart persistence:

```bash
docker compose --env-file .env.deploy restart api
docker compose --env-file .env.deploy up -d --wait
python scripts/deployment_smoke.py --endpoint https://agentguard.example.com \
  --previous-trace SAVED_TRACE_ID --output artifacts/deployment-restart.json
```

Send the real Groq agent from your laptop with its existing local `.env`:

```bash
python scripts/run_groq_support.py --limit 1 --max-requests 4 --export \
  --monitor-url https://agentguard.example.com
```

Set `AGENTGUARD_API_KEY` to the deployed tenant key on that laptop too. Model inference
runs there; the cloud collects minimized telemetry. Verify the trace in the dashboard.

## 4. Operations, backup and recovery

```bash
docker compose --env-file .env.deploy ps
docker compose --env-file .env.deploy logs --tail 100 api
scripts/backup_database.sh
scripts/verify_backup.sh backups/YOUR_BACKUP.dump
```

`/health` is liveness; `/ready` checks the database and a recent successful worker
cycle. Monitor `/ready` externally after deployment and alert on failures. Container
health status alone does not restart an unhealthy running process. Restart policy
recovers exited containers and host reboots when Docker is enabled.

Back up daily and before updates. The verification script restores to an isolated
temporary database, checks schema and trace count, then removes only that temporary
database. Copy encrypted backups off the instance to a private S3 bucket with an
appropriate IAM role, encryption and lifecycle policy. Set retention to match your
needs. Host-local backups do not protect against losing the server. Verify restoration
regularly and monitor EBS capacity, memory, CPU, queue health and backup freshness.
Trace retention defaults to seven days; log files rotate at 10 MiB, three per service.

For disaster recovery, start a fresh stack/database on a replacement server, stop
`api` and `web`, then restore your selected backup into that new database:

```bash
docker compose --env-file .env.deploy stop api web
docker compose --env-file .env.deploy exec -T db pg_restore \
  --clean --if-exists --exit-on-error --no-owner -U agentguard -d agentguard < backups/YOUR_BACKUP.dump
docker compose --env-file .env.deploy up -d --wait
```

This replaces tables in the target database: use a replacement stack or take a
backup of the target first. Re-run acceptance and update DNS if the address changed.
Never use `docker compose down -v` on a database you need to retain.

## 5. Updates and migrations

Record the current Git SHA, back up and verify the backup, then fetch and check out
the reviewed new commit. Rebuild with `docker compose --env-file .env.deploy up -d
--build --wait`. Run acceptance again. Startup checks the migration revision; it does
not silently run `create_all` in production. Alembic revisions live under
`backend/migrations/versions`. Review future autogenerated migrations before applying.

The initial revision targets a new database. Do not stamp a pre-existing database
without verifying schema equivalence and taking a backup. Local SQLite demo data is
not migrated automatically. For an incompatible schema change, rollback requires the
previous application image/commit plus a verified pre-update backup; do not blindly
run downgrades on valuable data.

Rotate tenant keys in `.env.deploy` and recreate the API using Compose `up -d`.
Update the SDK clients and dashboard key afterward. Never print Compose's resolved
configuration into public logs because it includes interpolated secrets.

## Deployment still requires you

AWS account/region and resources, DNS/domain, firewall rules, budget controls,
secure off-host backups and alert destinations are operator choices. No AWS resource
has been provisioned by this project. The final HTTPS, remote acceptance and real
agent export checks must run after your manual deployment. Human evaluation label
review and real-workload capacity testing remain separate from the synthetic results.
