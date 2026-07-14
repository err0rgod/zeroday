# ZeroDaily

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Live Website](https://img.shields.io/badge/Live-zerodaily.in-blue)](https://zerodaily.in)

**ZeroDaily** is a high-performance, serverless, and automated cybersecurity newsletter platform that aggregates, summarizes, and broadcasts threat intelligence, CVEs, and security news. 

The live platform is accessible at: **[zerodaily.in](https://zerodaily.in)**

---

## Architectural Overview

For a detailed breakdown of the serverless architecture, AWS infrastructure, and data flows, please refer to the [Architecture Documentation](ARCHITECTURE.md).

---

## Key Features

* **Automated Intelligence Ingestion**: Integrated parser utilities digest security feeds and employ Groq/OpenAI APIs to summarize technical CVEs into readable, engaging updates.
* **Robust Double Opt-In Flow**: Protects against spam using cryptographic verification tokens. Generates unique verification and unsubscribe tokens per subscriber, with email deliverability managed through the Resend API.
* **Analytics & Engagement Telemetry**: Custom JavaScript trackers log page-views and active reading session durations. The Flask endpoint logs session lengths and computes average read times to gauge content interest.
* **Security Hardening**:
  * Configurations loaded safely via environment variables.
* **Continuous Integration**: Integrated GitHub Actions CI/CD pipeline automates syntax testing and verifies build dependencies on every push.
* **Daily Hack Roasts**: Features a witty daily summary of recent hacks. Long security stories are neatly collapsed by default to keep the reading experience focused.
* **SEO-Engine Ready**: Automatically updates an XML sitemap and a standard RSS feed dynamically. Includes a robots.txt configuration.
* **Telemetry Dashboard**: An internal interface to monitor total/recent subscribers, database metrics, and system health status.

---

## Directory Structure

```text
├── D:\zeroday/
│   ├── .github/                # GitHub Actions CI/CD workflows
│   ├── web/                    # Flask Application & Web Layer
│   │   ├── static/             # Local fallbacks for branding assets
│   │   ├── templates/          # Jinja2 HTML templates
│   │   └── main.py             # App entrypoint, routing, tracking, and dashboard endpoints
│   ├── lib/                    # Core Business & Infrastructure Logic
│   │   ├── blob_store.py       # Subscribers storage layer
│   │   ├── content.py          # Issues content fetching, caching, and text search
│   │   ├── db.py               # SQLAlchemy SQLite engine setup
│   │   ├── health.py           # Multi-point system dependency diagnostic checks
│   │   ├── notifications.py    # Resend email client integration
│   │   └── validation.py       # Email normalization & parsing safety checks
│   ├── data/                   # Local database storage volume directory
│   ├── build_zip.py            # Deployment archiver that handles AWS Linux ZIP rules
│   ├── handler.py              # WSGI adapter for Lambda invocation
│   └── DEPLOYMENT_GUIDE.md     # Full step-by-step AWS Lambda deployment manual
```

---

## Environment Variables Configuration

| Environment Variable | Description |
|---|---|
| `AWS_REGION` | The region where S3 bucket and DynamoDB tables reside (e.g., `us-east-1`). |
| `S3_BUCKET_NAME` | The Amazon S3 bucket name holding asset and issues JSON files. |
| `DYNAMODB_TABLE` | The Amazon DynamoDB table storing subscriber list profiles. |
| `RESEND_API_KEY` | Transactional email client key used for delivering double opt-in mails. |
| `GROQ_API_KEY` / `OPENAI_API_KEY` | API tokens used during daily news ingestion. |
| `FLASK_SECRET_KEY` | Web application session signing key. |

---

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.
