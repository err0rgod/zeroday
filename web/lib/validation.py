from email_validator import validate_email, EmailNotValidError
import phonenumbers

# Disposable email domains to block
DISPOSABLE_DOMAINS = {
    "mailinator.com", "guerrillamail.com", "10minutemail.com", 
    "tempmail.com", "yopmail.com", "dropmail.me", "temp-mail.org",
    "throwaway.email", "trashmail.com", "sharklasers.com"
}

# Obvious bot/test email patterns
BOT_EMAILS = {
    "test@test.com", "admin@admin.com", "user@user.com",
    "root@root.com", "info@info.com", "a@a.com"
}

# Keywords that indicate fake/test emails
FAKE_KEYWORDS = {"test", "temp", "fake", "dummy", "example", "spam"}

def validate_and_normalize_email(email: str) -> str:
    """
    Validates an email address against format, disposable domains,
    known bot addresses, and suspicious keywords.
    Returns the normalized email or raises ValueError.
    """
    try:
        valid = validate_email(email, check_deliverability=False)
        normalized_email = valid.normalized
        
        domain = valid.domain.lower()
        if domain in DISPOSABLE_DOMAINS:
            raise ValueError("Disposable email addresses are not allowed.")
        
        # Block known bot emails
        if normalized_email.lower() in BOT_EMAILS:
            raise ValueError("This email address is not allowed.")
        
        # Block emails with suspicious keywords in local part
        local_part = normalized_email.split("@")[0].lower()
        for keyword in FAKE_KEYWORDS:
            if keyword in local_part:
                raise ValueError("Temporary or test email addresses are not allowed.")
            
        return normalized_email
    except EmailNotValidError as e:
        raise ValueError(str(e))

def validate_and_format_phone(phone: str) -> str:
    """
    Validates a phone number and formats it to E.164 standard.
    Returns the E.164 string or raises ValueError.
    """
    try:
        parsed = phonenumbers.parse(phone, None)
        if not phonenumbers.is_valid_number(parsed):
            raise ValueError("Invalid phone number.")
            
        return phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.E164)
    except phonenumbers.NumberParseException:
        raise ValueError("Invalid phone format. Please include country code (e.g. +1).")
