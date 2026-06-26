import os
import time
import resend
from typing import Dict, Any
from lib.content import get_issue_dates

def check_aws_s3() -> Dict[str, Any]:
    """Check connectivity to AWS S3 Storage."""
    bucket_name = os.getenv("S3_BUCKET_NAME", "zeroday-news-issues")
    try:
        import boto3
        start_time = time.time()
        s3 = boto3.client("s3")
        
        # Try to list one object to confirm access
        s3.list_objects_v2(Bucket=bucket_name, MaxKeys=1)
        
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

def check_dynamodb() -> Dict[str, Any]:
    """Check if DynamoDB is responsive."""
    table_name = os.getenv("DYNAMODB_TABLE") or os.getenv("DYNAMODB_TABLE_NAME", "zeroday-subscribers")
    try:
        import boto3
        start_time = time.time()
        dynamodb = boto3.resource("dynamodb")
        table = dynamodb.Table(table_name)
        # Check table status
        status = table.table_status
        duration = round((time.time() - start_time) * 1000)
        return {"status": "healthy", "message": f"Responsive ({status}, {duration}ms)"}
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

def get_system_health(db=None) -> Dict[str, Dict[str, Any]]:
    """Run all health checks and return the summary."""
    return {
        "aws_s3": check_aws_s3(),
        "resend": check_resend_api(),
        "dynamodb": check_dynamodb(),
        "content": check_content_freshness()
    }
