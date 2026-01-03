# api.jedwal.co

<p align="center">
  <img src="https://raw.githubusercontent.com/smcclure17/api.jedwal.co/refs/heads/main/public/welcome-banner.png" alt="Jedwal welcome banner">
</p>

<p align="center">
    <em>Backend for <a href="https://jedwal.co">Jedwal.co</a>, a simple headless CMS built on Google Drive</em>
</p>

---

## Other repos

Landing frontend: <https://github.com/smcclure17/jedwal.co>

App frontend: <https://github.com/smcclure17/app.jedwal.co>

## Structure

This is primarily a FastAPI REST API built on AWS (using DynamoDB, SQS, S3, etc.), hosted on Lambda.

The main application/package code lives in

```bash
src/jedwal
```

Background and async tasks are handled by workers, typically also Lambda functions triggered by e.g., S3, SQS
or a cron schedule.

They have their own deploy process and live in

```bash
workers/
```

## Development

> [!NOTE]
> **Development is largely reliant on AWS services**, making local development tricky.
>
> [#24](https://github.com/smcclure17/api.jedwal.co/issues/24) Aims to fix this, but it's a WIP.
>
> If you'd like to contribute but are having trouble please contact <hello@jedwal.co>

### Getting started

We use [UV](https://docs.astral.sh/uv/) for package management, make sure you have it installed.

- Clone the repo

    ```bash
    git clone https://github.com/smcclure17/api.jedwal.co.git
    ```

- Install dependencies (including dev dependencies)

    ```bash
    uv sync --all-extras
    ```

- Install pre-commit hooks

```bash
    uv run pre-commit install
```

### Code Quality

We use [Ruff](https://docs.astral.sh/ruff/) for linting and formatting. Pre-commit hooks will run automatically, but you can also run checks manually with

```bash
# Run linter
uv run ruff check --fix --exclude tests/

# Run formatter
uv run ruff format
```

### Tests

Out of the box, you should be able to run unit tests. Run them with

```bash
uv run pytest -m "not integration"
```

Integration tests will require env variables. Reach out to <hello@jedwal.co> for access, then add them to
your `.env` file, following the structure of `.env.example`

Then, run them with

```bash
uv run pytest -m "integration"
```
