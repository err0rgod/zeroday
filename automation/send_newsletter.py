import os
import sys
import json

# Add project root to sys.path at index 0 to avoid Linux 'lib' folder collisions
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env"), override=True)

import resend
from lib.content import get_latest_issue
from lib.notifications import FROM_EMAIL, BASE_URL

resend.api_key = os.getenv("RESEND_API_KEY", "")


def _fetch_subscribers_from_blob() -> list:
    """Fetch the latest subscriber list from Azure Blob Storage (subscribers_backup.json)."""
    conn_str = os.getenv("AZURE_STORAGE_CONNECTION_STRING")
    container_name = os.getenv("AZURE_CONTAINER_NAME", "news")

    if not conn_str:
        print("Warning: No Azure connection string found. Falling back to local subscribers.json")
        return _fetch_subscribers_from_local()

    try:
        from azure.storage.blob import BlobServiceClient
        blob_service = BlobServiceClient.from_connection_string(conn_str)
        container_client = blob_service.get_container_client(container_name)
        blob_client = container_client.get_blob_client("subscribers_backup.json")

        data = json.loads(blob_client.download_blob().readall().decode("utf-8-sig"))
        # Only send to active subscribers
        active = [s for s in data if s.get("is_active", True)]
        print(f"Fetched {len(active)} active subscribers from Azure Blob Storage.")
        return active
    except Exception as e:
        print(f"Azure Blob fetch failed: {e}. Falling back to local file.")
        return _fetch_subscribers_from_local()


def _fetch_subscribers_from_local() -> list:
    """Fallback: read subscribers from local subscribers.json file."""
    PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    DATA_DIR = os.getenv("DATA_DIR", os.path.join(PROJECT_ROOT, "data"))
    local_path = os.path.join(DATA_DIR, "subscribers.json")

    if not os.path.exists(local_path):
        print("No local subscribers.json found.")
        return []

    try:
        with open(local_path, "r", encoding="utf-8-sig") as f:
            data = json.load(f)
        return data
    except Exception as e:
        print(f"Failed to read local subscribers.json: {e}")
        return []


def send_newsletters():
    print("--- Starting Automated Newsletter Dispatch ---")

    # 1. Fetch latest issue
    latest_issue = get_latest_issue()
    if not latest_issue:
        print("Error: No issue found to send.")
        return

    date_str = latest_issue.get("date", "Latest")
    top_stories = latest_issue.get("top_stories", [])

    # Generate the email story blocks
    story_html = ""
    for idx, story in enumerate(top_stories[:3], 1):
        story_html += f"""
        <tr>
            <td style="padding: 24px 0; border-bottom: 1px solid #f1f5f9;">
                <h3 style="margin: 0 0 8px 0; font-size: 18px; color: #0f172a; font-weight: 600;">{idx}. {story.get('title', '')}</h3>
                <p style="margin: 0; font-size: 15px; color: #475569; line-height: 1.6;">{story.get('short_summary', '')}</p>
            </td>
        </tr>
        """

    base_html = f"""<!DOCTYPE html>
<html lang="en">
<body style="margin:0;padding:0;background-color:#f8fafc;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Helvetica,Arial,sans-serif;">
  <table width="100%" cellpadding="0" cellspacing="0" style="background-color:#f8fafc;padding:40px 0;">
    <tr>
      <td align="center">
        <table width="600" cellpadding="0" cellspacing="0" style="background:#ffffff;border-radius:12px;overflow:hidden;border:1px solid #e2e8f0;box-shadow:0 4px 6px -1px rgba(0,0,0,0.05);">
          <tr>
            <td style="background:#ffffff;padding:48px 40px 24px;text-align:center;border-bottom:1px solid #f1f5f9;">
              <div style="display:inline-block;background:#f3e8ff;border-radius:6px;padding:6px 14px;margin-bottom:16px;">
                <span style="color:#7e22ce;font-size:12px;font-weight:700;letter-spacing:1.5px;text-transform:uppercase;">ZeroDay Weekly</span>
              </div>
              <h1 style="color:#0f172a;font-size:26px;font-weight:700;margin:0;line-height:1.3;letter-spacing:-0.5px;">
                Issue for {date_str}
              </h1>
            </td>
          </tr>
          <tr>
            <td style="padding:16px 40px 48px;">
              <p style="color:#64748b;font-size:16px;line-height:1.6;margin:0 0 32px;text-align:center;">
                Here are the top cybersecurity stories for this week.
              </p>
              <table width="100%" cellpadding="0" cellspacing="0" style="margin-bottom: 32px;">
                {story_html}
              </table>
              <table cellpadding="0" cellspacing="0" style="margin:0 auto;">
                <tr>
                  <td align="center" style="border-radius:8px;background:linear-gradient(135deg,#8b5cf6,#6366f1);box-shadow:0 4px 14px 0 rgba(139,92,246,0.39);">
                    <a href="{BASE_URL}/weekly" style="display:inline-block;padding:14px 32px;color:#ffffff;font-size:15px;font-weight:600;text-decoration:none;border-radius:8px;letter-spacing:0.3px;">Explore Full Issue</a>
                  </td>
                </tr>
              </table>
            </td>
          </tr>
          <tr>
            <td style="background:#f8fafc;padding:32px 40px;border-top:1px solid #e2e8f0;text-align:center;">
              <p style="color:#94a3b8;font-size:13px;margin:0 0 12px;">ZeroDay Weekly &bull; Cybersecurity intelligence.</p>
              <p style="margin:0;"><a href="{{unsubscribe_url}}" style="color:#cbd5e1;font-size:12px;text-decoration:underline;">Unsubscribe</a></p>
            </td>
          </tr>
        </table>
      </td>
    </tr>
  </table>
</body>
</html>"""

    # 2. Fetch subscribers from Azure Blob — always the latest source of truth
    subscribers = _fetch_subscribers_from_blob()

    print(f"Found {len(subscribers)} active & verified subscribers.")

    if not subscribers:
        return

    # 3. Send personalised emails individually
    success_count = 0
    for sub in subscribers:
        try:
            email = sub.get("email")
            unsub_token = sub.get("unsubscribe_token", "")
            unsub_url = f"{BASE_URL}/api/unsubscribe?token={unsub_token}" if unsub_token else BASE_URL
            customized_html = base_html.replace("{unsubscribe_url}", unsub_url)

            params: resend.Emails.SendParams = {
                "from": FROM_EMAIL,
                "to": [email],
                "subject": f"ZeroDay Weekly - {date_str} Issue",
                "html": customized_html,
            }
            resend.Emails.send(params)
            print(f"[{email}] Sent successfully.")
            success_count += 1
        except Exception as e:
            print(f"[{sub.get('email', '?')}] Error sending email: {e}")

    print(f"--- Finished! Sent {success_count}/{len(subscribers)} emails. ---")


if __name__ == "__main__":
    send_newsletters()
