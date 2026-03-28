import os
import time
import json
import resend
from typing import Dict, Any
from sqlalchemy import text
from sqlalchemy.orm import Session
from azure.storage.blob import BlobServiceClient
from lib.content import get_issue_dates

def check_azure_blob() -> Dict[str, Any]:
    """Check connectivity to Azure Blob Storage."""
    conn_str = os.getenv("AZURE_STORAGE_CONNECTION_STRING")
    container_name = os.getenv("AZURE_CONTAINER_NAME", "news")
    if not conn_str:
        return {"status": "unhealthy", "message": "Connection string missing"}
    
    try:
        start_time = time.time()
        blob_service = BlobServiceClient.from_connection_string(conn_str, connection_timeout=5)
        container_client = blob_service.get_container_client(container_name)
        
        if not container_client.exists():
            return {"status": "unhealthy", "message": f"Container '{container_name}' not found"}
        
        # Try to list one blob to confirm access
        next(container_client.list_blobs(), None)
        
        duration = round((time.time() - start_time) * 1000)
        return {"status": "healthy", "message": f"Connected ({duration}ms)"}
    except Exception as e:
        return {"status": "unhealthy", "message": str(e)}

def check_resend_api() -> Dict[str, Any]:
    """Check if Resend API key is valid and has sufficient permissions."""
    api_key = os.getenv("RESEND_API_KEY")
    if not api_key:
        return {"status": "unhealthy", "message": "API key missing"}
    
    resend.api_key = api_key
    try:
        start_time = time.time()
        # This requires 'Full Access' permissions. 
        # If it's 'Sending Only', it will return a 403.
        resend.api_keys.list()
        duration = round((time.time() - start_time) * 1000)
        return {"status": "healthy", "message": f"Valid ({duration}ms)"}
    except Exception as e:
        err_msg = str(e)
        if "403" in err_msg:
            return {"status": "partial", "message": "Sending Only (cannot list keys)"}
        return {"status": "unhealthy", "message": err_msg}

def check_local_db(db: Session) -> Dict[str, Any]:
    """Check if local SQLite database is responsive."""
    try:
        start_time = time.time()
        db.execute(text("SELECT 1"))
        duration = round((time.time() - start_time) * 1000)
        return {"status": "healthy", "message": f"Responsive ({duration}ms)"}
    except Exception as e:
        return {"status": "unhealthy", "message": str(e)}

def check_content_freshness() -> Dict[str, Any]:
    """Check if the content system is serving issues."""
    try:
        dates = get_issue_dates()
        if not dates:
            return {"status": "warning", "message": "No issues found in storage"}
        return {"status": "healthy", "message": f"{len(dates)} issues found"}
    except Exception as e:
        return {"status": "unhealthy", "message": str(e)}

def get_system_health(db: Session) -> Dict[str, Dict[str, Any]]:
    """Run all health checks and return the summary."""
    return {
        "azure": check_azure_blob(),
        "resend": check_resend_api(),
        "database": check_local_db(db),
        "content": check_content_freshness()
    }
