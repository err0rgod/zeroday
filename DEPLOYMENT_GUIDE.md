# ZeroDaily Deployment Guide

This guide details the procedure for packaging, verifying, and deploying the ZeroDaily backend API to AWS Lambda, S3, and DynamoDB. Follow these instructions precisely to avoid packaging errors or environmental misconfigurations.

---

## Prerequisites

1. **AWS CLI v2** installed and configured with appropriate IAM deployment credentials.
2. **Python 3.9** environment (to match the AWS Lambda runtime).
3. **S3 Deployment Bucket**: `zeroday-scraped-content-prod-339087217625-ap-south-2-an`
4. **Lambda Function**: `zeroday-news-dev-api`
5. **AWS Region**: `ap-south-2`

---

## Key Deployment Safeguards

### 1. Shell Expansion Hazard with Bcrypt Hashes
Admin credentials (`ADMIN_USERNAME` and `ADMIN_PASSWORD`) are stored as Bcrypt-hashed strings. Because Bcrypt hashes contain multiple `$` symbols (e.g. `$2b$12$...`), deploying them directly via CLI environment variables triggers shell parameter expansion. This corrupts the hash value and causes login failures (500/401 errors).
* **Prevention**: Never pass unescaped `$` strings to CLI commands. Instead:
  * Quote them carefully using single quotes (`'$2b$...'`) in bash/zsh, or use escape characters (``$` or `^$`) in Windows command prompts/PowerShell.
  * Prefer updating configuration variables using a clean JSON payload file:
    ```bash
    aws lambda update-function-configuration --function-name zeroday-news-dev-api --environment '{"Variables": {"ADMIN_USERNAME": "$2b$12$...", "ADMIN_PASSWORD": "$2b$12$..."}}'
    ```

### 2. Linux-Compatible Python Dependencies
AWS Lambda runs on a Linux execution environment. Packing dependencies compiled on a Windows/macOS machine will lead to `Runtime.ImportModuleError` (e.g., `No module named 'sqlalchemy'`) because of architecture-specific binaries (like `greenlet`).
* **Prevention**:

  * Download Linux-compatible wheels (`manylinux2014_x86_64` tag) for compiled libraries like `sqlalchemy` and `greenlet` and extract them directly into the deployment package:
    ```bash
    pip install --platform manylinux2014_x86_64 --only-binary=:all: --target ./temp_linux_libs sqlalchemy greenlet
    ```
  * Alternatively, use a containerized environment (e.g., Docker with a Python 3.9-slim image) to run `pip install` when building the package.


---

## Step-by-Step Deployment Procedure

### Step 1: Run Local Verification Tests
Before generating a deployment archive, run the local integration tests to verify the integrity of routes and templates.
```bash
python scratch/test_lifeng_render.py
```
Ensure that:
* The response status is `200 OK`.
* No Jinja2 template rendering errors occur (e.g., missing dictionary attributes).

### Step 2: Build the Lambda Deployment Archive
Construct the ZIP archive containing the application code, web templates, and Linux dependencies.
1. Include all source code files from `lib/` and `web/`.
2. Ensure `web/templates/` and `web/static/` are preserved.
3. Exclude any local caching files, local database files (`*.db`), or environment configuration files (`.env`).
4. Copy the Linux-compatible shared libraries (`SQLAlchemy`, `greenlet`, etc.) to the root level of the ZIP.

### Step 3: Upload the Package to S3
Upload the ZIP to the deployment bucket:
```bash
aws s3 cp lambda_deploy.zip s3://zeroday-scraped-content-prod-339087217625-ap-south-2-an/lambda_deploy.zip --region ap-south-2
```

### Step 4: Trigger the Lambda Code Update
Instruct AWS Lambda to update its function code using the S3 object:
```bash
aws lambda update-function-code --function-name zeroday-news-dev-api --s3-bucket zeroday-scraped-content-prod-339087217625-ap-south-2-an --s3-key lambda_deploy.zip --region ap-south-2
```

### Step 5: Verify Deployment Status
Query the function configuration to verify that the deployment completed successfully:
```bash
aws lambda get-function --function-name zeroday-news-dev-api --region ap-south-2
```
Check that `LastUpdateStatus` changes to `Successful` and the application responds correctly in production.
