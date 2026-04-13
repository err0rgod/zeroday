import sys
import os
import secrets
import uuid
import bcrypt
import jwt
from datetime import datetime, timedelta
from functools import wraps

# Add project root to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from flask import Flask, render_template, request, redirect, url_for, jsonify, make_response, Response, abort
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from dotenv import load_dotenv

# Load .env
load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env"), override=True)

from lib.content import get_issue_dates, get_issue_data, get_latest_issue, search_articles, delete_issue
from feedgen.feed import FeedGenerator
from sqlalchemy.orm import Session
from lib.db import engine, get_db, PageView, ReadSession, init_db
from lib.validation import validate_and_normalize_email
from lib.notifications import send_verification_email, send_custom_email
from lib.blob_store import (
    add_subscriber, update_subscriber, remove_subscriber,
    get_subscriber, get_subscriber_by_token,
    get_active_verified_emails, count_active_verified, get_recent_subscribers,
)
from lib.health import get_system_health
from sqlalchemy import func

app = Flask(__name__)
# Generate a session secret key if not provided
app.secret_key = os.getenv("FLASK_SECRET_KEY") or secrets.token_hex(32)

# Rate Limiter
limiter = Limiter(
    key_func=get_remote_address,
    app=app,
    default_limits=["500 per day", "100 per hour"],
    storage_uri="memory://",
)

# JWT Configuration
JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY", "fallback_secret_key_change_me")
JWT_ALGORITHM = "HS256"
TOKEN_EXPIRY_HOURS = 24

# --- Auth Decorator ---
def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        token = request.cookies.get("admin_session")
        if not token:
            return redirect(url_for('login_get'))
        try:
            payload = jwt.decode(token, JWT_SECRET_KEY, algorithms=[JWT_ALGORITHM])
            if payload.get("sub") != "admin":
                return redirect(url_for('login_get'))
        except jwt.PyJWTError:
            return redirect(url_for('login_get'))
        return f(*args, **kwargs)
    return decorated

# Initialize DB
init_db()

# Global template functions
@app.context_processor
def utility_processor():
    return {
        'get_latest_issue': get_latest_issue,
        'get_issue_dates': get_issue_dates
    }

# ======================================================================
# Token Utilities
# ======================================================================

def _is_token_expired(created_at_str: str) -> bool:
    if not created_at_str:
        return True
    try:
        created_at = datetime.fromisoformat(created_at_str)
        return datetime.utcnow() - created_at > timedelta(hours=TOKEN_EXPIRY_HOURS)
    except ValueError:
        return True

def _generate_tokens() -> dict:
    return {
        "verification_token": uuid.uuid4().hex,
        "unsubscribe_token": uuid.uuid4().hex,
    }

# ======================================================================
# Routes
# ======================================================================

@app.route("/")
def read_root():
    if request.cookies.get("is_subscribed") == "true":
        return redirect(url_for("read_weekly"))

    dates = get_issue_dates()
    latest_date = dates[0] if dates else None
    latest_issue = get_latest_issue()

    return render_template("index.html", 
                           latest_issue=latest_issue, 
                           latest_date=latest_date, 
                           archive_previews=dates[:3])

@app.route("/issue/<date_str>")
def read_issue(date_str):
    data = get_issue_data(date_str)
    if not data:
        abort(404)
    return render_template("issue.html", issue=data, date_str=date_str)

@app.route("/weekly")
def read_weekly():
    dates = get_issue_dates()
    if not dates:
        abort(404)
    date_str = dates[0]
    data = get_issue_data(date_str)
    return render_template("issue.html", issue=data, date_str=date_str)

@app.route("/archive")
def read_archive():
    dates = get_issue_dates()
    issues = [{"date": d, "data": get_issue_data(d)} for d in dates]
    return render_template("archive.html", issues=issues)

@app.route("/search")
def read_search():
    q = request.args.get("q", "")
    results = search_articles(q) if q else []
    return render_template("search.html", query=q, results=results)

# ======================================================================
# API Endpoints
# ======================================================================

@app.route("/api/subscribe", methods=["POST"])
@limiter.limit("5/hour")
def subscribe():
    email = request.form.get("email")
    b_url = request.form.get("b_url") # Honeypot

    if b_url:
        return jsonify({"success": True, "message": "Subscribed"})

    if not email:
        return jsonify({"success": False, "error": "Email is required"}), 400

    try:
        normalized_email = validate_and_normalize_email(email)
    except ValueError as e:
        return jsonify({"success": False, "error": str(e)}), 400

    existing = get_subscriber(normalized_email)

    if existing:
        if existing.get("verified_email") and existing.get("is_active", True):
            resp = jsonify({"success": False, "error": "This email is already subscribed."})
            response = make_response(resp)
            response.set_cookie("is_subscribed", "true", max_age=31536000)
            return response, 400

        existing_token = existing.get("verification_token")
        token_created = existing.get("verification_token_created_at", "")
        if existing_token and not _is_token_expired(token_created):
            send_verification_email(normalized_email, existing_token)
        else:
            tokens = _generate_tokens()
            update_subscriber(
                normalized_email,
                verification_token=tokens["verification_token"],
                verification_token_created_at=datetime.utcnow().isoformat(),
                unsubscribe_token=tokens["unsubscribe_token"],
                is_active=True,
            )
            send_verification_email(normalized_email, tokens["verification_token"])
    else:
        tokens = _generate_tokens()
        now = datetime.utcnow().isoformat()
        add_subscriber(
            email=normalized_email,
            verification_token=tokens["verification_token"],
            verification_token_created_at=now,
            unsubscribe_token=tokens["unsubscribe_token"],
            created_at=now,
        )
        send_verification_email(normalized_email, tokens["verification_token"])

    return jsonify({"success": True, "message": "Verification email sent. Please check your inbox."})

@app.route("/api/verify-email")
def verify_email():
    token = request.args.get("token")
    subscriber = get_subscriber_by_token("verification_token", token)

    if not subscriber:
        return "<h1>Invalid or expired verification token.</h1>", 400

    if subscriber.get("verified_email") and subscriber.get("is_active", True):
        dates = get_issue_dates()
        redirect_url = url_for("read_issue", date_str=dates[0]) if dates else url_for("read_root")
        response = make_response(redirect(redirect_url))
        response.set_cookie("is_subscribed", "true", max_age=31536000)
        return response

    if _is_token_expired(subscriber.get("verification_token_created_at", "")):
        return '''
            <html>
                <body style="background:#0f172a; color:#fff; font-family:sans-serif; text-align:center; padding-top:50px;">
                    <h1>Token Expired</h1>
                    <p>This verification link has expired. Please subscribe again to get a new link.</p>
                    <a href="/" style="color:#3b82f6;">Return Home</a>
                </body>
            </html>
        ''', 400

    update_subscriber(
        subscriber["email"],
        verified_email=True,
        is_active=True,
    )

    dates = get_issue_dates()
    redirect_url = url_for("read_issue", date_str=dates[0]) if dates else url_for("read_root")
    response = make_response(redirect(redirect_url))
    response.set_cookie("is_subscribed", "true", max_age=31536000)
    return response

@app.route("/api/unsubscribe")
def unsubscribe():
    token = request.args.get("token")
    subscriber = get_subscriber_by_token("unsubscribe_token", token)

    if not subscriber:
        return "<h1>Invalid unsubscribe link.</h1>", 400

    update_subscriber(subscriber["email"], is_active=False)
    return '''
        <html>
            <body style="background:#0f172a; color:#fff; font-family:sans-serif; text-align:center; padding-top:50px;">
                <h1>Unsubscribed</h1>
                <p>You have been removed from ZeroDaily. Sorry to see you go.</p>
                <p style="color:#94a3b8; margin-top:20px;">Changed your mind? <a href="/" style="color:#3b82f6;">Re-subscribe here</a>.</p>
            </body>
        </html>
    '''

@app.route("/rss.xml")
def get_rss():
    fg = FeedGenerator()
    fg.title("ZeroDaily")
    fg.link(href=request.url_root, rel="alternate")
    fg.description("Weekly insights on cybersecurity news, vulnerabilities, and research.")
    fg.language("en")

    dates = get_issue_dates()
    for d in dates[:5]:
        issue = get_issue_data(d)
        if not issue: continue

        fe = fg.add_entry()
        fe.title(f"Issue {d}")
        fe.link(href=url_for("read_issue", date_str=d, _external=True))

        desc_parts = []
        for top_story in issue.get("top_stories", []):
            desc_parts.append(f"<b>{top_story.get('title')}</b><br/>{top_story.get('short_summary')}<br/>")

        fe.description("".join(desc_parts))
        try:
            fe.pubDate(datetime.strptime(d, "%Y-%m-%d").replace(tzinfo=None).astimezone())
        except ValueError:
            pass

    return Response(fg.rss_str(pretty=True), mimetype='application/xml')

@app.route("/sitemap.xml")
def sitemap():
    base_url = request.url_root.rstrip('/')
    urls = [
        {"loc": f"{base_url}/", "changefreq": "daily", "priority": "1.0"},
        {"loc": f"{base_url}/weekly", "changefreq": "daily", "priority": "0.9"},
        {"loc": f"{base_url}/archive", "changefreq": "weekly", "priority": "0.8"},
        {"loc": f"{base_url}/rss.xml", "changefreq": "weekly", "priority": "0.3"},
    ]

    for date_str in get_issue_dates():
        urls.append({
            "loc": f"{base_url}/issue/{date_str}",
            "lastmod": date_str,
            "changefreq": "weekly",
            "priority": "0.7",
        })

    sitemap_items = []
    for item in urls:
        sitemap_entries = [f"<loc>{item['loc']}</loc>"]
        if item.get("lastmod"):
            sitemap_entries.append(f"<lastmod>{item['lastmod']}</lastmod>")
        sitemap_entries.append(f"<changefreq>{item['changefreq']}</changefreq>")
        sitemap_entries.append(f"<priority>{item['priority']}</priority>")
        sitemap_items.append("".join(["<url>", *sitemap_entries, "</url>"]))

    sitemap_xml = "<?xml version=\"1.0\" encoding=\"UTF-8\"?>\n"
    sitemap_xml += "<urlset xmlns=\"http://www.sitemaps.org/schemas/sitemap/0.9\">\n"
    sitemap_xml += "\n".join(sitemap_items)
    sitemap_xml += "\n</urlset>"

    return Response(sitemap_xml, mimetype='application/xml')

@app.route("/robots.txt")
def robots_txt():
    sitemap_url = url_for('sitemap', _external=True)
    robots_lines = [
        "User-agent: *",
        "Disallow: /lifeng",
        "Disallow: /login",
        "Disallow: /admin",
        "Disallow: /api/track/view",
        "Disallow: /api/track/time",
        "Allow: /",
        "",
        f"Sitemap: {sitemap_url}",
    ]
    return Response("\n".join(robots_lines), mimetype='text/plain')

# ======================================================================
# Tracking API
# ======================================================================

@app.route("/api/track/view", methods=["POST"])
def track_view():
    data = request.get_json()
    path = data.get("path")
    if path:
        db = next(get_db())
        view = PageView(path=path)
        db.add(view)
        db.commit()
    return jsonify({"success": True})

@app.route("/api/track/time", methods=["POST"])
def track_time():
    data = request.get_json() or {}
    path = data.get("path")
    duration = data.get("duration_seconds")
    if path and duration is not None:
        db = next(get_db())
        session = ReadSession(path=path, duration_seconds=duration)
        db.add(session)
        db.commit()
    return jsonify({"success": True})

# ======================================================================
# Admin Panel & Authentication
# ======================================================================

@app.route("/login")
def login_get():
    return render_template("login.html")

@app.route("/login", methods=["POST"])
def login_post():
    username = request.form.get("username")
    password = request.form.get("password")

    stored_username_hash = os.getenv("ADMIN_USERNAME", "").encode('utf-8')
    stored_password_hash = os.getenv("ADMIN_PASSWORD", "").encode('utf-8')

    try:
        correct_username = bcrypt.checkpw(username.encode('utf-8'), stored_username_hash)
    except Exception:
        correct_username = False
        
    try:
        correct_password = bcrypt.checkpw(password.encode('utf-8'), stored_password_hash)
    except Exception:
        correct_password = False

    if not (correct_username and correct_password):
        return render_template("login.html", error_msg="Invalid username or password."), 401

    # Generate JWT
    token = jwt.encode({
        "sub": "admin",
        "exp": datetime.utcnow() + timedelta(hours=TOKEN_EXPIRY_HOURS)
    }, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)

    response = make_response(redirect(url_for("admin_panel")))
    response.set_cookie("admin_session", token, httponly=True, max_age=86400, samesite='Lax')
    return response

@app.route("/logout")
def logout():
    response = make_response(redirect(url_for("login_get")))
    response.delete_cookie("admin_session")
    return response

@app.route("/lifeng")
@admin_required
def admin_panel():
    db = next(get_db())
    total_subscribers = count_active_verified()
    recent_subscribers = get_recent_subscribers(limit=10)

    total_views = db.query(PageView).count()
    avg_read_time_row = db.query(func.avg(ReadSession.duration_seconds)).first()
    avg_read_time = round(avg_read_time_row[0]) if avg_read_time_row and avg_read_time_row[0] else 0

    top_pages_query = db.query(PageView.path, func.count(PageView.id).label('views')).group_by(PageView.path).order_by(func.count(PageView.id).desc()).limit(5).all()
    top_pages = [{"path": p.path, "views": p.views} for p in top_pages_query]

    engaging_pages_query = db.query(ReadSession.path, func.avg(ReadSession.duration_seconds).label('avg_time')).group_by(ReadSession.path).order_by(func.avg(ReadSession.duration_seconds).desc()).limit(5).all()
    engaging_pages = [{"path": p.path, "avg_time": round(p.avg_time)} for p in engaging_pages_query]

    health = get_system_health(db)
    all_issues = get_issue_dates()

    return render_template("lifeng.html",
                           total_subscribers=total_subscribers,
                           total_views=total_views,
                           avg_read_time=avg_read_time,
                           recent_subscribers=recent_subscribers,
                           top_pages=top_pages,
                           engaging_pages=engaging_pages,
                           health=health,
                           all_issues=all_issues)

@app.route("/admin/delete-subscriber", methods=["POST"])
@admin_required
def admin_delete_subscriber():
    email = request.form.get("email")
    remove_subscriber(email)
    return redirect(url_for("admin_panel", msg="deleted"))

@app.route("/admin/delete-issue", methods=["POST"])
@admin_required
def admin_delete_issue():
    date_str = request.form.get("date_str")
    if date_str:
        delete_issue(date_str)
    return redirect(url_for("admin_panel", msg="issue_deleted"))

@app.route("/admin/send-email", methods=["POST"])
@admin_required
def admin_send_email():
    target_email = request.form.get("target_email")
    subject = request.form.get("subject")
    body = request.form.get("body")
    try:
        if target_email:
            emails = [target_email]
        else:
            emails = get_active_verified_emails()
            
        if not emails:
            return redirect(url_for("admin_panel", error="no_subscribers"))

        success = send_custom_email(emails, subject, body)
        if success:
            return redirect(url_for("admin_panel", msg="sent"))
        else:
            return redirect(url_for("admin_panel", error="send_failed"))
    except Exception as e:
        print(f"Error sending custom email: {e}")
        return redirect(url_for("admin_panel", error="exception"))

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000, debug=True)
