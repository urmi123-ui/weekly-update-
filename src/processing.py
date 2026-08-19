import re
import emoji
from langdetect import detect, LangDetectException

def is_valid_review(text: str) -> bool:
    """
    Check if review meets quality criteria:
    1. At least 8 words
    2. No emojis
    3. English language
    """
    # 1. Less than 8 words
    if len(text.split()) < 8:
        return False
        
    # 2. Contains emojis
    if emoji.emoji_count(text) > 0:
        return False
        
    # 3. Not in English
    try:
        if detect(text) != 'en':
            return False
    except LangDetectException:
        # If language detection fails (e.g. string is just numbers/punctuation)
        return False
        
    return True


def clean_review_text(text: str) -> str:
    """
    Sanitize raw text to remove formatting anomalies.
    - Strips leading/trailing whitespace
    - Replaces multiple spaces with a single space
    - Replaces multiple newlines with a single space
    """
    if not text:
        return ""
    
    # Replace newlines and carriage returns with a space
    text = re.sub(r'[\r\n]+', ' ', text)
    # Replace multiple spaces with a single space
    text = re.sub(r'\s{2,}', ' ', text)
    
    return text.strip()

def scrub_pii(text: str) -> str:
    """
    Remove Personally Identifiable Information using regex heuristics.
    Scrubs:
    - Emails/UPI IDs
    - Phone numbers (basic heuristic for Indian & international formats)
    """
    if not text:
        return ""
        
    # Scrub Emails and UPI IDs
    # e.g., name@gmail.com or number@ybl
    email_upi_pattern = r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}|[a-zA-Z0-9.\-_]{2,256}@[a-zA-Z]{2,64}'
    text = re.sub(email_upi_pattern, '[EMAIL/UPI]', text)
    
    # Scrub Phone Numbers
    # Matches typical Indian numbers like 9876543210, +91-9876543210, 09876543210
    phone_pattern = r'(?:(?:\+|0{0,2})91[\s-]?)?[6789]\d{9}'
    text = re.sub(phone_pattern, '[PHONE]', text)
    
    # Generic number scrub (if it looks like an account number or a long sequence of digits > 9 digits)
    account_pattern = r'\b\d{10,16}\b'
    text = re.sub(account_pattern, '[ID/ACCOUNT]', text)
    
    return text

def process_reviews(reviews_data: list) -> list:
    """
    Processes a list of raw review dictionaries, sanitizing and scrubbing the text.
    Filters out reviews with < 8 words, emojis, or non-English text.
    Returns a new list with modified 'content'.
    """
    processed = []
    for review in reviews_data:
        # Create a shallow copy to avoid mutating the original data structure unexpectedly
        processed_review = dict(review)
        
        raw_content = processed_review.get('content', '')
        sanitized = clean_review_text(raw_content)
        scrubbed = scrub_pii(sanitized)
        
        # Filter out bad reviews
        if not is_valid_review(scrubbed):
            continue
            
        processed_review['content'] = scrubbed
        
        # Remove unwanted fields
        keys_to_remove = ['reviewId', 'userName', 'userImage', 'reviewCreatedVersion', 'at', 'replyContent', 'repliedAt']
        for k in keys_to_remove:
            processed_review.pop(k, None)
            
        processed.append(processed_review)
        
    return processed

if __name__ == "__main__":
    # Quick test
    sample_text = "The app is great! Call me at 9876543210 or email me at user123@gmail.com. My UPI is user@okhdfcbank. \n\n    Too many bugs though."
    print("Original:", repr(sample_text))
    cleaned = clean_review_text(sample_text)
    print("Cleaned:", repr(cleaned))
    scrubbed = scrub_pii(cleaned)
    print("Scrubbed:", repr(scrubbed))
