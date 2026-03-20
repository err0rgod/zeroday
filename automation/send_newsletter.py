import os
import sys

# Add project root to sys.path so we can import lib
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import resend
from lib.db import SessionLocal, Subscriber
from lib.content import get_latest_issue
from lib.notifications import FROM_EMAIL, BASE_URL

def send_newsletters():
    print("--- Starting Automated Newsletter Dispatch ---")
    
    # 1. Fetch latest issue
    latest_issue = get_latest_issue()
    if not latest_issue:
        print("Error: No issue found to send.")
        return
        
    date_str = latest_issue.get("date", "Latest")
    top_stories = latest_issue.get("top_stories", [])
    
    # Generate the email content
    story_html = ""
    for idx, story in enumerate(top_stories[:3], 1):
        story_html += f"""
        <tr>
            <td style="padding-bottom: 24px;">
                <h3 style="margin: 0 0 8px 0; font-size: 18px; color: #f1f5f9;">{idx}. {story.get('title', '')}</h3>
                <p style="margin: 0; font-size: 15px; color: #cbd5e1; line-height: 1.6;">{story.get('short_summary', '')}</p>
            </td>
        </tr>
        """
        
    base_html = f"""<!DOCTYPE html>
<html lang="en">
<body style="margin:0;padding:0;background-color:#0f172a;font-family:'Segoe UI',Helvetica,Arial,sans-serif;">
  <table width="100%" cellpadding="0" cellspacing="0" style="background-color:#0f172a;padding:40px 0;">
    <tr>
      <td align="center">
        <table width="600" cellpadding="0" cellspacing="0" style="background:#1e293b;border-radius:12px;overflow:hidden;border:1px solid #334155;">
          <tr>
            <td style="background:linear-gradient(135deg,#1e3a5f 0%,#0f172a 100%);padding:36px 40px;text-align:center;">
              <div style="display:inline-block;background:#3b82f6;border-radius:8px;padding:6px 14px;margin-bottom:16px;">
                <span style="color:#fff;font-size:13px;font-weight:700;letter-spacing:2px;text-transform:uppercase;">ZeroDay Weekly</span>
              </div>
              <h1 style="color:#f1f5f9;font-size:26px;font-weight:700;margin:0;line-height:1.3;">
                Issue for {date_str} is out!
              </h1>
            </td>
          </tr>
          <tr>
            <td style="padding:36px 40px;">
              <p style="color:#94a3b8;font-size:15px;line-height:1.7;margin:0 0 28px;">
                Here's a preview of the top cybersecurity stories this week:
              </p>
              <table width="100%" cellpadding="0" cellspacing="0">
                {story_html}
              </table>
              <table cellpadding="0" cellspacing="0" style="margin:16px auto 32px;">
                <tr>
                  <td align="center" style="border-radius:8px;background:linear-gradient(135deg,#3b82f6,#6366f1);">
                    <a href="{BASE_URL}/weekly" style="display:inline-block;padding:14px 36px;color:#ffffff;font-size:15px;font-weight:700;text-decoration:none;border-radius:8px;letter-spacing:0.3px;">Read Full Issue</a>
                  </td>
                </tr>
              </table>
            </td>
          </tr>
          <tr>
            <td style="background:#0f172a;padding:24px 40px;border-top:1px solid #1e293b;text-align:center;">
              <p style="color:#64748b;font-size:12px;margin:0 0 12px;">ZeroDay Weekly &bull; Cybersecurity intelligence, weekly.</p>
              <p style="margin:0;"><a href="{{{{unsubscribe_url}}}}" style="color:#ef4444;font-size:12px;text-decoration:none;">Unsubscribe</a></p>
            </td>
          </tr>
        </table>
      </td>
    </tr>
  </table>
</body>
</html>"""

    # 2. Fetch subscribers
    db = SessionLocal()
    try:
        subscribers = db.query(Subscriber).filter(
            Subscriber.verified_email == True,
            Subscriber.is_active == True
        ).all()
        
        print(f"Found {len(subscribers)} active & verified subscribers.")
        
        if not subscribers:
            return
            
        # 3. Send emails
        success_count = 0
        for sub in subscribers:
            try:
                unsub_url = f"{BASE_URL}/api/unsubscribe?token={sub.unsubscribe_token}"
                customized_html = base_html.replace("{{unsubscribe_url}}", unsub_url)
                
                params: resend.Emails.SendParams = {
                    "from": FROM_EMAIL,
                    "to": [sub.email],
                    "subject": f"ZeroDay Weekly - {date_str} Issue",
                    "html": customized_html,
                }
                resend.Emails.send(params)
                print(f"[{sub.email}] Sent successfully.")
                success_count += 1
            except Exception as e:
                print(f"[{sub.email}] Error sending email: {e}")
                
        print(f"--- Finished! Sent {success_count}/{len(subscribers)} emails. ---")
    finally:
        db.close()

if __name__ == "__main__":
    send_newsletters()
