import os
import resend
from dotenv import load_dotenv

# Load environment variables from the root directory's .env
_env_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), ".env")
load_dotenv(_env_path, override=True)

resend.api_key = os.getenv("RESEND_API_KEY", "")
BASE_URL = os.getenv("BASE_URL", "http://localhost:8000").rstrip("/")
FROM_EMAIL = os.getenv("FROM_EMAIL", "ZeroDay Weekly <onboarding@resend.dev>")


def send_verification_email(email: str, token: str) -> bool:
    """
    Send a verification email using the Resend API.
    Returns True on success, False on failure.
    """
    verification_link = f"{BASE_URL}/api/verify-email?token={token}"

    html_body = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0"/>
  <title>Verify your ZeroDay Weekly subscription</title>
</head>
<body style="margin:0;padding:0;background-color:#0f172a;font-family:'Segoe UI',Helvetica,Arial,sans-serif;">
  <table width="100%" cellpadding="0" cellspacing="0" style="background-color:#0f172a;padding:40px 0;">
    <tr>
      <td align="center">
        <table width="600" cellpadding="0" cellspacing="0" style="background:#1e293b;border-radius:12px;overflow:hidden;border:1px solid #334155;">

          <!-- Header -->
          <tr>
            <td style="background:linear-gradient(135deg,#1e3a5f 0%,#0f172a 100%);padding:36px 40px;text-align:center;">
              <div style="display:inline-block;background:#3b82f6;border-radius:8px;padding:6px 14px;margin-bottom:16px;">
                <span style="color:#fff;font-size:13px;font-weight:700;letter-spacing:2px;text-transform:uppercase;">ZeroDay Weekly</span>
              </div>
              <h1 style="color:#f1f5f9;font-size:26px;font-weight:700;margin:0;line-height:1.3;">
                Confirm your subscription
              </h1>
            </td>
          </tr>

          <!-- Body -->
          <tr>
            <td style="padding:36px 40px;">
              <p style="color:#94a3b8;font-size:15px;line-height:1.7;margin:0 0 20px;">
                Hey there
              </p>
              <p style="color:#cbd5e1;font-size:15px;line-height:1.7;margin:0 0 28px;">
                You're one click away from joining <strong style="color:#f1f5f9;">ZeroDay Weekly</strong> — your curated digest of the latest
                cybersecurity news, CVEs, and threat intelligence, delivered straight to your inbox every week.
              </p>

              <!-- CTA Button -->
              <table cellpadding="0" cellspacing="0" style="margin:0 auto 32px;">
                <tr>
                  <td align="center" style="border-radius:8px;background:linear-gradient(135deg,#3b82f6,#6366f1);">
                    <a href="{verification_link}"
                       style="display:inline-block;padding:14px 36px;color:#ffffff;font-size:15px;font-weight:700;text-decoration:none;border-radius:8px;letter-spacing:0.3px;">
                        Verify My Email
                    </a>
                  </td>
                </tr>
              </table>

              <p style="color:#64748b;font-size:13px;line-height:1.6;margin:0 0 12px;">
                Or paste this link into your browser:
              </p>
              <p style="background:#0f172a;border:1px solid #334155;border-radius:6px;padding:12px 16px;margin:0 0 28px;word-break:break-all;">
                <a href="{verification_link}" style="color:#3b82f6;font-size:12px;text-decoration:none;">{verification_link}</a>
              </p>

              <p style="color:#475569;font-size:13px;line-height:1.6;margin:0;">
                 This link expires in <strong>24 hours</strong>. If you didn't subscribe, you can safely ignore this email.
              </p>
            </td>
          </tr>

          <!-- Footer -->
          <tr>
            <td style="background:#0f172a;padding:24px 40px;border-top:1px solid #1e293b;text-align:center;">
              <p style="color:#334155;font-size:12px;margin:0;">
                ZeroDay Weekly &bull; Cybersecurity intelligence, weekly.
              </p>
            </td>
          </tr>

        </table>
      </td>
    </tr>
  </table>
</body>
</html>"""

    try:
        params: resend.Emails.SendParams = {
            "from": FROM_EMAIL,
            "to": [email],
            "subject": " Verify your ZeroDay Weekly subscription",
            "html": html_body,
        }
        response = resend.Emails.send(params)
        print(f"[EMAIL] Sent verification email to {email} | id={response.get('id')}")
        return True
    except Exception as exc:
        print(f"[EMAIL ERROR] Failed to send to {email}: {exc}")
        return False

def send_custom_email(emails: list[str], subject: str, html_body: str) -> bool:
    """
    Broadcasts a custom email to a list of recipients via Resend API.
    Bcc is used to protect subscriber privacy.
    Returns True on success, False on failure.
    """
    if not emails:
        return False
        
    try:
        params: resend.Emails.SendParams = {
            "from": FROM_EMAIL,
            "to": ["undisclosed-recipients@zeroday.news"], # Use a generic 'to' 
            "bcc": emails, # Hide all recipient emails using BCC
            "subject": subject,
            "html": html_body,
        }
        resend.Emails.send(params)
        print(f"[EMAIL] Successfully broadcasted custom email to {len(emails)} subscribers.")
        return True
    except Exception as exc:
        print(f"[EMAIL ERROR] Failed to broadcast custom email: {exc}")
        return False
