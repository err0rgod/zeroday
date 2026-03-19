from fastapi import FastAPI, Request, Form, HTTPException, Depends
from fastapi.responses import HTMLResponse, RedirectResponse, Response, JSONResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
import uvicorn
import json
import os
import uuid
from datetime import datetime, timedelta
from lib.content import get_issue_dates, get_issue_data, get_latest_issue, search_articles, OUTPUT_DIR
from feedgen.feed import FeedGenerator
import re

from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from sqlalchemy.orm import Session

from lib.db import Base, engine, get_db, Subscriber, PageView, ReadSession, init_db
from lib.validation import validate_and_normalize_email, validate_and_format_phone
from lib.notifications import send_verification_email

# --- Constants ---
TOKEN_EXPIRY_HOURS = 24

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.getenv("DATA_DIR", os.path.join(PROJECT_ROOT, "data"))
os.makedirs(DATA_DIR, exist_ok=True)

SUBSCRIBERS_JSON = os.path.join(DATA_DIR, "subscribers.json")

limiter = Limiter(key_func=get_remote_address)
app = FastAPI(title="ZeroDay Weekly")
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# Initialize DB
init_db()

templates = Jinja2Templates(directory=os.path.join(os.path.dirname(__file__), "templates"))

# Make functions available to Jinja
templates.env.globals.update(
    get_latest_issue=get_latest_issue,
    get_issue_dates=get_issue_dates
)

try:
    app.mount("/static", StaticFiles(directory=os.path.join(os.path.dirname(__file__), "static")), name="static")
except RuntimeError:
    pass


# ======================================================================
# Helper: Mirror subscriber to JSON file
# ======================================================================

def _load_json_subscribers() -> list:
    """Load subscribers from JSON file. Returns [] on any error."""
    if not os.path.exists(SUBSCRIBERS_JSON):
        return []
    try:
        with open(SUBSCRIBERS_JSON, "r", encoding="utf-8-sig") as f:
            data = json.load(f)
        if isinstance(data, list):
            return data
    except (json.JSONDecodeError, ValueError, OSError, UnicodeDecodeError):
        pass
    return []


def _save_json_subscribers(data: list):
    """Write subscribers list to JSON file with UTF-8 BOM for Windows compatibility."""
    with open(SUBSCRIBERS_JSON, "w", encoding="utf-8-sig") as f:
        json.dump(data, f, indent=4, ensure_ascii=False)


def _mirror_to_json(email: str, phone: str):
    """Add a subscriber to JSON if not already present (by email)."""
    try:
        subscribers = _load_json_subscribers()
        if any(s.get("email") == email for s in subscribers):
            return  # Already exists
        subscribers.append({
            "email": email,
            "phone": phone,
            "created_at": datetime.now().isoformat()
        })
        _save_json_subscribers(subscribers)
    except Exception as e:
        print(f"Error mirroring to JSON: {e}")


# ======================================================================
# Helper: Token utilities
# ======================================================================

def _is_token_expired(created_at: datetime) -> bool:
    """Check if a verification token has expired (24h)."""
    if not created_at:
        return True
    return datetime.utcnow() - created_at > timedelta(hours=TOKEN_EXPIRY_HOURS)


def _generate_tokens() -> dict:
    """Generate fresh verification and unsubscribe tokens."""
    return {
        "verification_token": uuid.uuid4().hex,
        "verification_token_created_at": datetime.utcnow(),
        "unsubscribe_token": uuid.uuid4().hex,
    }


# ======================================================================
# Page routes
# ======================================================================

@app.get("/", response_class=HTMLResponse)
async def read_root(request: Request):
    latest_date = None
    dates = get_issue_dates()
    if dates:
        latest_date = dates[0]
        
    latest_issue = get_latest_issue()
    
    return templates.TemplateResponse("index.html", {
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
        
    return templates.TemplateResponse("issue.html", {
        "request": request,
        "issue": data,
        "date_str": date_str
    })

@app.get("/archive", response_class=HTMLResponse)
async def read_archive(request: Request):
    dates = get_issue_dates()
    issues = [{"date": d, "data": get_issue_data(d)} for d in dates]
    
    return templates.TemplateResponse("archive.html", {
        "request": request,
        "issues": issues
    })

@app.get("/search", response_class=HTMLResponse)
async def read_search(request: Request, q: str = ""):
    results = search_articles(q) if q else []
    
    return templates.TemplateResponse("search.html", {
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
    whatsapp: str = Form(...),
    b_url: str = Form(None),
    db: Session = Depends(get_db)
):
    # --- Bot protection: honeypot ---
    if b_url:
        return JSONResponse(content={"success": True, "message": "Subscribed"})

    # --- Validate inputs ---
    try:
        normalized_email = validate_and_normalize_email(email)
        normalized_phone = validate_and_format_phone(whatsapp)
    except ValueError as e:
        return JSONResponse(
            content={"success": False, "error": str(e)},
            status_code=400
        )

    # --- Check for existing subscriber ---
    existing = db.query(Subscriber).filter(
        Subscriber.email == normalized_email
    ).first()

    if existing:
        if existing.verified_email and existing.is_active:
            return JSONResponse(
                content={"success": False, "error": "This email is already subscribed."},
                status_code=400
            )
        # Re-subscribe: regenerate tokens if expired
        subscriber = existing
        if _is_token_expired(subscriber.verification_token_created_at):
            tokens = _generate_tokens()
            subscriber.verification_token = tokens["verification_token"]
            subscriber.verification_token_created_at = tokens["verification_token_created_at"]
            subscriber.unsubscribe_token = tokens["unsubscribe_token"]
        subscriber.phone = normalized_phone
        subscriber.is_active = True
    else:
        tokens = _generate_tokens()
        subscriber = Subscriber(
            email=normalized_email,
            phone=normalized_phone,
            verification_token=tokens["verification_token"],
            verification_token_created_at=tokens["verification_token_created_at"],
            unsubscribe_token=tokens["unsubscribe_token"],
        )
        db.add(subscriber)

    db.commit()
    db.refresh(subscriber)

    # --- Mirror to JSON ---
    _mirror_to_json(normalized_email, normalized_phone)

    # --- Send verification email ---
    send_verification_email(normalized_email, subscriber.verification_token)

    return JSONResponse(content={
        "success": True,
        "message": "Verification email sent. Please check your inbox."
    })


# ======================================================================
# Email Verification
# ======================================================================

@app.get("/api/verify-email", response_class=HTMLResponse)
async def verify_email(token: str, db: Session = Depends(get_db)):
    subscriber = db.query(Subscriber).filter(
        Subscriber.verification_token == token
    ).first()

    if not subscriber:
        return HTMLResponse(
            content="<h1>Invalid or expired verification token.</h1>",
            status_code=400
        )

    # Check token expiry
    if _is_token_expired(subscriber.verification_token_created_at):
        return HTMLResponse(content='''
            <html>
                <body style="background:#0f172a; color:#fff; font-family:sans-serif; text-align:center; padding-top:50px;">
                    <h1>Token Expired</h1>
                    <p>This verification link has expired. Please subscribe again to get a new link.</p>
                    <a href="/" style="color:#3b82f6;">Return Home</a>
                </body>
            </html>
        ''', status_code=400)

    subscriber.verified_email = True
    subscriber.is_active = True
    subscriber.verification_token = None  # Invalidate used token
    db.commit()

    # Redirect to the latest issue, or home if none published yet
    dates = get_issue_dates()
    redirect_url = f"/issue/{dates[0]}" if dates else "/"
    return RedirectResponse(url=redirect_url, status_code=302)


# ======================================================================
# Unsubscribe
# ======================================================================

@app.get("/api/unsubscribe", response_class=HTMLResponse)
async def unsubscribe(token: str, db: Session = Depends(get_db)):
    subscriber = db.query(Subscriber).filter(
        Subscriber.unsubscribe_token == token
    ).first()

    if not subscriber:
        return HTMLResponse(
            content="<h1>Invalid unsubscribe link.</h1>",
            status_code=400
        )

    subscriber.is_active = False
    db.commit()

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
# Admin Panel
# ======================================================================
from sqlalchemy import func

@app.get("/lifeng", response_class=HTMLResponse)
async def admin_panel(request: Request, db: Session = Depends(get_db)):
    # Calculate stats
    total_subscribers = db.query(Subscriber).filter(Subscriber.verified_email == True, Subscriber.is_active == True).count()
    total_views = db.query(PageView).count()
    
    avg_read_time_row = db.query(func.avg(ReadSession.duration_seconds)).first()
    avg_read_time = round(avg_read_time_row[0]) if avg_read_time_row and avg_read_time_row[0] else 0
    
    recent_subscribers = db.query(Subscriber).order_by(Subscriber.created_at.desc()).limit(10).all()
    
    return templates.TemplateResponse("lifeng.html", {
        "request": request,
        "total_subscribers": total_subscribers,
        "total_views": total_views,
        "avg_read_time": avg_read_time,
        "recent_subscribers": recent_subscribers
    })

if __name__ == "__main__":
    uvicorn.run("web.main:app", host="0.0.0.0", port=8000, reload=True)
