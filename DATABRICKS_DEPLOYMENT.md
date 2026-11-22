# CareLens on Databricks

App: https://carelens-7474645857742380.aws.databricksapps.com

Workspace: https://dbc-6dd8b941-d971.cloud.databricks.com

- Lakebase project/branch: `carelens/production`
- Database: `databricks_postgres`, schema `healthcare`
- Source folder: `/Workspace/Users/helenx@andrew.cmu.edu/carelens-deploy`
- CLI profile: `carelens`
- Secret resources: `ark-api-key` and `ark-model`, scope `carelens-app`

The root package.json builds the React app. The Python server serves the build
and `/api/*` on the port supplied by Databricks. Local development still uses
DATABASE_URL; deployments use PG variables provided by the database resource
and automatically refreshed Lakebase OAuth credentials.

The initial import uses `python -m app.init_lakebase` with PGHOST, PGUSER,
PGDATABASE and LAKEBASE_ENDPOINT configured. It refuses to overwrite a populated
database. Do not run imports on application startup.

The app role has schema usage and table read access, plus INSERT/UPDATE on the
service scoring cache. UPDATE on only the facilities.updated_at column permits
the scorer’s SELECT FOR SHARE row locks. Agent credentials live in Databricks Secrets, not source.

Deployment is from a workspace upload, not automatic GitHub synchronization.
For later updates, create a fresh staging directory and upload it, then deploy.
Run from the repository root (choose a new staging path each time):

```sh
python scripts/prepare_databricks.py /tmp/carelens-next-deploy
.deployment-tools/databricks sync /tmp/carelens-next-deploy \
  /Workspace/Users/helenx@andrew.cmu.edu/carelens-deploy --profile carelens
.deployment-tools/databricks apps deploy carelens \
  --source-code-path /Workspace/Users/helenx@andrew.cmu.edu/carelens-deploy \
  --profile carelens
```

Never upload `.env`, `.venv`, `.git`, `.deployment-tools`, or `node_modules`.
To inspect logs:

```sh
.deployment-tools/databricks apps logs carelens --profile carelens --tail-lines 50
```

## Public gateway

The public Render URL runs `app.public_gateway`, forwarding the frontend assets
and four allowlisted API routes to the CareLens Databricks App. Search, scoring,
verification and Lakebase connections run inside Databricks. `app.yaml` continues
to start `app.api` there. Visitors do not need a Databricks account.

The gateway uses server-side OAuth M2M credentials and its service principal needs
CAN_USE on the CareLens app. It does not forward browser credentials or cookies,
follow upstream redirects, or accept arbitrary upstream URLs. Only DATABRICKS_HOST,
DATABRICKS_AUTH_TYPE, DATABRICKS_CLIENT_ID and DATABRICKS_CLIENT_SECRET are needed
on Render. The direct Databricks URL still requires authentication.
