# api.jedwal.co

FastAPI app powering the backend for [Jedwal](https://jedwal.co), a tool to turn Google Sheets into REST APIs.

## Taxonomy

### API

The API routes are served via a FastAPI/Starlette ASGI web server.

### Auth

[Google Oauth](https://developers.google.com/identity/protocols/oauth2) is used for user authentication, integrated with Starlette sessions.

### Infrastructure

The app is hosted on AWS via a Cloudformation Template. We use AWS SAM to configure the app as a Serverless project. Front to back, the infrastructure is:

- **ECR**: Repository containing the App's Docker Image
- **Lambda**: Serverless function that executes containers from the Docker image
- **DynamoDB**: Data storage to persist user data and spreadsheet API configurations
- **API Gateway**: Gateway to route HTTPS traffic to the Lambda function
- **CloudFront**: CDN to cache JSON responses via custom headers emitted from the REST API
- **Route53**: DNS hosting to hook up the API to <https://api.jedwal.co>

The Cloudformation template used to deploy this stack is in [lambda.yaml](./lambda.yaml)

Alternatively, we could deploy this as an ECS Fargate service. See [ecs.yaml](./ecs.yaml)

## Database Schema

The application uses a single-table design pattern in DynamoDB with primary keys and global
secondary indexes (GSIs) to support different access patterns.

### Primary Table Structure

- **Primary Key**: Composite key consisting of `PK` (Partition Key) and `SK` (Sort Key)
- **Format**:
  - For sheets: `PK = "SHEET#{uuid}"`, `SK = "#METADATA"`
  - For users: `PK = "USER#{userId}"`, `SK = "#PROFILE"`
  - For email lookups: `PK = "EMAIL#{email}"`, `SK = "#LOOKUP"`
  - For organizations: `PK = "ORG#{orgId}"`, `SK = "#METADATA"`

### Global Secondary Indexes

#### GSI1: Owner-Based Access

GSI1 enables efficient querying of resources by owner (user or organization):

- **GSI1PK**: Either `USER#{userId}` or `ORG#{orgId}`
- **GSI1SK**: `SHEET#{uuid}` for sheets, other values for different resource types
- **Use cases**:
  - List all sheets owned by a user
  - List all sheets owned by an organization
  - Fetch organization memberships for a user

#### GSI2: API Name Lookups

GSI2 enables efficient lookups of sheets by their API name:

- **GSI2PK**: Always set to `"API"` (constant partition key)
- **GSI2SK**: `API#{apiName}` format
- **Use cases**:
  - Look up a sheet by its API name (for API endpoints)
  - Check if an API name is already in use
  - Enforce uniqueness of API names

### Access Patterns

The table design supports these access patterns:

- **API Endpoints**: Fetch sheet data by API name using GSI2
- **User/Org Dashboards**: List all sheets for a user/org using GSI1
- **Authentication**: Look up users by email address
- **Organization Management**: Check memberships and permissions
- **Analytics Tracking**: Track usage consistently via UUIDs, even if API names change

## Local Development

Local development is a litle scuffed until we figure out/wire up local auth (Google Oauth) and storage (DynamoDB).

### Setup

If necessary, install Python, pyenv, and virtualenv.

```bash
brew update
brew install python pyenv pyenv-virtualenv
```

Install Python 3.12

```bash
pyenv install 3.12
```

Create a virtualenv for this project. We'll use "jedwal" as the name

```bash
pyenv virtualenv 3.12 jedwal
```

Activate the environment

```bash
pyenv activate jedwal
```

#### Dependencies

Install the necessary requirements

```bash
pip install -r requirements.txt
```

Install the local packages

```bash
pip install -e .
```

### Execution

Run the FastAPI dev server with

```bash
fastapi dev api.py  # served to localhost:8000
```
