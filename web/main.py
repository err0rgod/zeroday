import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env"), override=True)

from fastapi import FastAPI, Request, Form, HTTPException, Depends
from fastapi.responses import HTMLResponse, RedirectResponse, Response, JSONResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
import uvicorn
import os
import uuid
from datetime import datetime, timedelta
from lib.content import get_issue_dates, get_issue_data, get_latest_issue, search_articles
from feedgen.feed import FeedGenerator

from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from sqlalchemy.orm import Session

from lib.db import Base, engine, get_db, PageView, ReadSession, init_db
from lib.validation import validate_and_normalize_email
from lib.notifications import send_verification_email, send_custom_email
from lib.blob_store import (
    load_subscribers, save_subscribers,
    add_subscriber, update_subscriber, remove_subscriber,
    get_subscriber, get_subscriber_by_token,
    get_active_verified_emails, count_active_verified, get_recent_subscribers,
)
from lib.health import get_system_health
import secrets
import uuid

SESSION_TOKENS = set()

class AuthException(Exception):
    pass

def get_current_admin(request: Request):
    token = request.cookies.get("admin_session")
    if not token or token not in SESSION_TOKENS:
        raise AuthException()
    return True

# --- Constants ---
TOKEN_EXPIRY_HOURS = 24

limiter = Limiter(key_func=get_remote_address)
app = FastAPI(title="ZeroDay Weekly")
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

@app.exception_handler(AuthException)
async def auth_exception_handler(request: Request, exc: AuthException):
    return RedirectResponse(url="/login", status_code=302)

# Initialize DB (analytics tables only)
init_db()

templates = Jinja2Templates(directory=os.path.join(os.path.dirname(__file__), "templates"))

templates.env.globals.update(
    get_latest_issue=get_latest_issue,
    get_issue_dates=get_issue_dates
)

try:
    app.mount("/static", StaticFiles(directory=os.path.join(os.path.dirname(__file__), "static")), name="static")
except RuntimeError:
    pass


# ======================================================================
# Token utilities
# ======================================================================

def _is_token_expired(created_at_str: str) -> bool:
    """Check if a verification token has expired (24h). created_at_str is ISO format."""
    if not created_at_str:
        return True
    try:
        created_at = datetime.fromisoformat(created_at_str)
        return datetime.utcnow() - created_at > timedelta(hours=TOKEN_EXPIRY_HOURS)
    except ValueError:
        return True


def _generate_tokens() -> dict:
    """Generate fresh verification and unsubscribe tokens."""
    return {
        "verification_token": uuid.uuid4().hex,
        "unsubscribe_token": uuid.uuid4().hex,
    }


# ======================================================================
# Page routes
# ======================================================================

@app.get("/", response_class=HTMLResponse)
async def read_root(request: Request):
    if request.cookies.get("is_subscribed") == "true":
        return RedirectResponse(url="/weekly", status_code=302)

    latest_date = None
    dates = get_issue_dates()
    if dates:
        latest_date = dates[0]

    latest_issue = get_latest_issue()

    return templates.TemplateResponse(request, "index.html", {
        "request": request,
        "latest_issue": latest_issue,
        "latest_date": latest_date,
        "archive_previews": dates[:3]
    })

@app.get("/issue/{date_str}", response_class=HTMLResponse)
async def read_issue(request: Request, date_str: str):
    data = get_issue_data(date_str)
    if not data:
        raise HTTPException(status_code=404, detail="Issue not found")

    return templates.TemplateResponse(request, "issue.html", {
        "request": request,
        "issue": data,
        "date_str": date_str
    })

@app.get("/weekly", response_class=HTMLResponse)
async def read_weekly(request: Request):
    dates = get_issue_dates()
    if not dates:
        raise HTTPException(status_code=404, detail="No weekly news found")

    date_str = dates[0]
    data = get_issue_data(date_str)

    return templates.TemplateResponse(request, "issue.html", {
        "request": request,
        "issue": data,
        "date_str": date_str
    })

@app.get("/archive", response_class=HTMLResponse)
async def read_archive(request: Request):
    dates = get_issue_dates()
    issues = [{"date": d, "data": get_issue_data(d)} for d in dates]

    return templates.TemplateResponse(request, "archive.html", {
        "request": request,
        "issues": issues
    })

@app.get("/search", response_class=HTMLResponse)
async def read_search(request: Request, q: str = ""):
    results = search_articles(q) if q else []

    return templates.TemplateResponse(request, "search.html", {
        "request": request,
        "query": q,
        "results": results
    })


# ======================================================================
# Subscription API
# ======================================================================

@app.post("/api/subscribe")
@limiter.limit("5/hour")
async def subscribe(
    request: Request,
    email: str = Form(...),
    b_url: str = Form(None),
):
    # --- Bot protection: honeypot ---
    if b_url:
        return JSONResponse(content={"success": True, "message": "Subscribed"})

    # --- Validate email ---
    try:
        normalized_email = validate_and_normalize_email(email)
    except ValueError as e:
        return JSONResponse(content={"success": False, "error": str(e)}, status_code=400)

    # --- Check blob for existing subscriber ---
    existing = get_subscriber(normalized_email)

    if existing:
        if existing.get("verified_email") and existing.get("is_active", True):
            response = JSONResponse(
                content={"success": False, "error": "This email is already subscribed."},
                status_code=400
            )
            response.set_cookie("is_subscribed", "true", max_age=31536000)
            return response

        # Reuse existing token if still valid; only regenerate if expired
        existing_token = existing.get("verification_token")
        token_created = existing.get("verification_token_created_at", "")
        if existing_token and not _is_token_expired(token_created):
            # Token still valid — just resend the same email
            send_verification_email(normalized_email, existing_token)
        else:
            # Token expired or missing — generate fresh tokens
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

    return JSONResponse(content={
        "success": True,
        "message": "Verification email sent. Please check your inbox."
    })


# ======================================================================
# Email Verification
# ======================================================================

@app.get("/api/verify-email", response_class=HTMLResponse)
async def verify_email(token: str):
    subscriber = get_subscriber_by_token("verification_token", token)

    if not subscriber:
        return HTMLResponse(
            content="<h1>Invalid or expired verification token.</h1>",
            status_code=400
        )

    if _is_token_expired(subscriber.get("verification_token_created_at", "")):
        return HTMLResponse(content='''
            <html>
                <body style="background:#0f172a; color:#fff; font-family:sans-serif; text-align:center; padding-top:50px;">
                    <h1>Token Expired</h1>
                    <p>This verification link has expired. Please subscribe again to get a new link.</p>
                    <a href="/" style="color:#3b82f6;">Return Home</a>
                </body>
            </html>
        ''', status_code=400)

    update_subscriber(
        subscriber["email"],
        verified_email=True,
        is_active=True,
        verification_token=None,
    )

    dates = get_issue_dates()
    redirect_url = f"/issue/{dates[0]}" if dates else "/"
    response = RedirectResponse(url=redirect_url, status_code=302)
    response.set_cookie("is_subscribed", "true", max_age=31536000)
    return response


# ======================================================================
# Unsubscribe
# ======================================================================

@app.get("/api/unsubscribe", response_class=HTMLResponse)
async def unsubscribe(token: str):
    subscriber = get_subscriber_by_token("unsubscribe_token", token)

    if not subscriber:
        return HTMLResponse(
            content="<h1>Invalid unsubscribe link.</h1>",
            status_code=400
        )

    update_subscriber(subscriber["email"], is_active=False)

    return HTMLResponse(content='''
        <html>
            <body style="background:#0f172a; color:#fff; font-family:sans-serif; text-align:center; padding-top:50px;">
                <h1>Unsubscribed</h1>
                <p>You have been removed from ZeroDay Weekly. Sorry to see you go.</p>
                <p style="color:#94a3b8; margin-top:20px;">Changed your mind? <a href="/" style="color:#3b82f6;">Re-subscribe here</a>.</p>
            </body>
        </html>
    ''')


# ======================================================================
# RSS Feed
# ======================================================================

@app.get("/rss.xml")
async def get_rss():
    fg = FeedGenerator()
    fg.title("ZeroDay Weekly")
    fg.link(href="http://localhost:8000", rel="alternate")
    fg.description("Weekly insights on cybersecurity news, vulnerabilities, and research.")
    fg.language("en")

    dates = get_issue_dates()
    for d in dates[:5]:
        issue = get_issue_data(d)
        if not issue: continue

        fe = fg.add_entry()
        fe.title(f"Issue {d}")
        fe.link(href=f"http://localhost:8000/issue/{d}")

        desc_parts = []
        for top_story in issue.get("top_stories", []):
            desc_parts.append(f"<b>{top_story.get('title')}</b><br/>{top_story.get('short_summary')}<br/>")

        fe.description("".join(desc_parts))
        try:
            fe.pubDate(datetime.strptime(d, "%Y-%m-%d").replace(tzinfo=None).astimezone())
        except ValueError:
            pass

    return Response(content=fg.rss_str(pretty=True), media_type="application/xml")


# ======================================================================
# Tracking API
# ======================================================================

from pydantic import BaseModel

class TrackViewReq(BaseModel):
    path: str

class TrackTimeReq(BaseModel):
    path: str
    duration_seconds: int

@app.post("/api/track/view")
async def track_view(req: TrackViewReq, db: Session = Depends(get_db)):
    view = PageView(path=req.path)
    db.add(view)
    db.commit()
    return {"success": True}

@app.post("/api/track/time")
async def track_time(req: TrackTimeReq, db: Session = Depends(get_db)):
    session = ReadSession(path=req.path, duration_seconds=req.duration_seconds)
    db.add(session)
    db.commit()
    return {"success": True}


# ======================================================================
# Admin Panel & Authentication
# ======================================================================
from sqlalchemy import func

@app.get("/login", response_class=HTMLResponse)
async def login_get(request: Request):
    return templates.TemplateResponse(request, "login.html", {"request": request})

@app.post("/login", response_class=HTMLResponse)
async def login_post(request: Request, username: str = Form(...), password: str = Form(...)):
    correct_username = secrets.compare_digest(username, os.getenv("ADMIN_USERNAME", "admin"))
    correct_password = secrets.compare_digest(password, os.getenv("ADMIN_PASSWORD", "secret"))

    if not (correct_username and correct_password):
        return templates.TemplateResponse(request, "login.html", {
            "request": request,
            "error_msg": "Invalid username or password."
        }, status_code=401)

    token = uuid.uuid4().hex
    SESSION_TOKENS.add(token)

    response = RedirectResponse(url="/lifeng", status_code=302)
    response.set_cookie(key="admin_session", value=token, httponly=True, max_age=86400)
    return response

@app.get("/logout")
async def logout(request: Request):
    token = request.cookies.get("admin_session")
    if token in SESSION_TOKENS:
        SESSION_TOKENS.remove(token)
    response = RedirectResponse(url="/login", status_code=302)
    response.delete_cookie("admin_session")
    return response

@app.get("/lifeng", response_class=HTMLResponse)
async def admin_panel(request: Request, db: Session = Depends(get_db), admin: bool = Depends(get_current_admin)):
    # Subscriber stats from blob
    total_subscribers = count_active_verified()
    recent_subscribers = get_recent_subscribers(limit=10)

    # Analytics from SQLite
    total_views = db.query(PageView).count()
    avg_read_time_row = db.query(func.avg(ReadSession.duration_seconds)).first()
    avg_read_time = round(avg_read_time_row[0]) if avg_read_time_row and avg_read_time_row[0] else 0

    top_pages_query = db.query(PageView.path, func.count(PageView.id).label('views')).group_by(PageView.path).order_by(func.count(PageView.id).desc()).limit(5).all()
    top_pages = [{"path": p.path, "views": p.views} for p in top_pages_query]

    engaging_pages_query = db.query(ReadSession.path, func.avg(ReadSession.duration_seconds).label('avg_time')).group_by(ReadSession.path).order_by(func.avg(ReadSession.duration_seconds).desc()).limit(5).all()
    engaging_pages = [{"path": p.path, "avg_time": round(p.avg_time)} for p in engaging_pages_query]

    # System Health Checks
    health = get_system_health(db)
    
    # Issues List
    all_issues = get_issue_dates()

    return templates.TemplateResponse(request, "lifeng.html", {
        "request": request,
        "total_subscribers": total_subscribers,
        "total_views": total_views,
        "avg_read_time": avg_read_time,
        "recent_subscribers": recent_subscribers,
        "top_pages": top_pages,
        "engaging_pages": engaging_pages,
        "health": health,
        "all_issues": all_issues,
    })

@app.post("/admin/delete-subscriber", response_class=RedirectResponse)
async def admin_delete_subscriber(
    request: Request,
    email: str = Form(...),
    admin: bool = Depends(get_current_admin)
):
    remove_subscriber(email)
    return RedirectResponse(url="/lifeng?msg=deleted", status_code=302)

@app.post("/admin/send-email", response_class=RedirectResponse)
async def admin_send_email(
    request: Request,
    subject: str = Form(...),
    body: str = Form(...),
    admin: bool = Depends(get_current_admin)
):
    try:
        emails = get_active_verified_emails()

        if not emails:
            return RedirectResponse(url="/lifeng?error=no_subscribers", status_code=302)

        success = send_custom_email(emails, subject, body)

        if success:
            return RedirectResponse(url="/lifeng?msg=sent", status_code=302)
        else:
            return RedirectResponse(url="/lifeng?error=send_failed", status_code=302)

    except Exception as e:
        print(f"Error sending custom email: {e}")
        return RedirectResponse(url="/lifeng?error=exception", status_code=302)

if __name__ == "__main__":
    uvicorn.run("web.main:app", host="0.0.0.0", port=8000, reload=True, reload_dirs=["web", "lib"])
