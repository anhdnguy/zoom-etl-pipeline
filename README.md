# Zoom ETL Pipeline

A production data pipeline that extracts Zoom metadata (users, meetings, participants), transforms it, and loads it into an S3 data lake. Built with Python, Apache Airflow 3, and deployed on AWS ECS Fargate via Terraform.

## Architecture

```
                          ┌─────────────────────────────────────────────┐
                          │              ECS Fargate Cluster             │
                          │                                             │
  Zoom API ──────────────▶│  Airflow  ─▶  Scheduler  ─▶  Celery Worker │──▶ S3 Data Lake ──▶ Glue Crawler ──▶ Power BI
  (Server-to-Server OAuth)│  API Server   (DAG parse)    (ETL tasks)    │   (Parquet)        (Catalog)
                          │       ▲           │               │         │
                          │       │      Cloud Map DNS        │         │
                          │  Internal ALB     ▼               ▼         │
                          │            Triggerer         ElastiCache    │
                          │                              Redis (broker) │
                          └──────────────────┬──────────────────────────┘
                                             │
                                        RDS PostgreSQL
                                        (metadata DB)
```

## Tech Stack

**ETL:** Python, Zoom REST API (Server-to-Server OAuth), pandas, boto3

**Orchestration:** Apache Airflow 3 with CeleryExecutor, dynamic task mapping

**Infrastructure:** Terraform (14 modules), AWS ECS Fargate, RDS PostgreSQL, ElastiCache Redis, S3, Glue, CloudWatch, Secrets Manager

**Networking:** Private VPC with NAT gateway, VPC endpoints (S3, ECR, Secrets Manager, CloudWatch, SQS), Cloud Map service discovery, internal ALB

## Project Structure

```
├── src/                        # Core ETL library
│   ├── clients/                # Zoom API client with OAuth token management
│   │   ├── zoom_client.py      # Paginated API requests, error handling
│   │   ├── zoom_token.py       # Redis-backed token cache with distributed locking
│   │   └── zoom_exceptions.py  # Typed exception hierarchy
│   ├── services/               # Business logic (user, meeting, participant extraction)
│   ├── transforms/             # Data normalization
│   └── storage/                # S3 parquet writer with partitioning
├── airflow/
│   └── dags/etl_process.py     # DAG with dynamic task mapping and chunked processing
├── infra/
│   ├── modules/                # 14 Terraform modules
│   │   ├── network/            # VPC, subnets, NAT, security groups, VPC endpoints
│   │   ├── ecs/                # ECS cluster, Cloud Map, capacity providers
│   │   ├── airflow/            # Reusable ECS service (4 instances: webserver, scheduler, triggerer, worker)
│   │   ├── database/           # RDS PostgreSQL with enhanced monitoring
│   │   ├── redis/              # ElastiCache for Celery broker
│   │   ├── alb/                # Application Load Balancer
│   │   ├── iam/                # Task roles, execution roles, Lambda roles
│   │   ├── secrets/            # Secrets Manager
│   │   ├── datalake/           # S3 bucket, Glue crawlers, lifecycle policies
│   │   └── ...                 # ECR, SQS, Lambda, CloudFront, downloader
│   └── envs/prod/              # Environment-specific configuration
├── Dockerfile                  # Single image for all Airflow components
├── docker-compose.yaml         # Local development environment
└── setup.py
```

## Key Design Decisions

**Single Docker image, four ECS services.** The same image runs as webserver, scheduler, triggerer, or worker — determined by the ECS task definition `command` override. This simplifies CI/CD to one build pipeline.

**Redis-backed OAuth token with distributed locking.** The `ZoomTokenProvider` uses Redis `SET NX` with a Lua-script release to prevent thundering herd on token refresh when multiple workers start simultaneously.

**Reusable Terraform module for Airflow services.** The `airflow` module is instantiated four times with different parameters (command, CPU/memory, health check, ALB attachment). All security groups are centralized in the `network` module to avoid circular dependencies.

**Dynamic task mapping in the DAG.** User IDs are chunked and fanned out to parallel workers using Airflow's `.expand()`, with meeting details and participants processed in separate task groups downstream.

**VPC endpoints for cost and latency.** S3, ECR, Secrets Manager, CloudWatch Logs, and SQS all use interface/gateway endpoints to avoid NAT gateway data processing charges.

## Running Locally

```bash
cp .env.example .env  # Fill in Zoom credentials
docker-compose up -d
# Airflow UI: http://localhost:8080
```

## Deploying to AWS

```bash
cd infra/envs/prod
terraform init
terraform plan -out=tfplan
terraform apply tfplan

# Initialize Airflow DB (one-time)
aws ecs run-task --cluster <cluster> --task-definition <webserver-td> \
  --overrides '{"containerOverrides":[{"name":"webserver","command":["airflow","db","migrate"]}]}' ...

# Build and push
docker build -t airflow .
docker tag airflow <ecr-uri>:$(git rev-parse --short HEAD)
docker push <ecr-uri>:$(git rev-parse --short HEAD)
```
