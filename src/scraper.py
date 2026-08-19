import os
import json
from datetime import datetime, timedelta
from typing import List, Dict, Any
from google_play_scraper import reviews, Sort
from processing import process_reviews

def fetch_recent_reviews(app_id: str, weeks: int = 8) -> List[Dict[str, Any]]:
    """
    Fetches reviews for the given app_id from the last N weeks.
    
    Args:
        app_id (str): The Google Play Store app package name (e.g., 'com.nextbillion.groww')
        weeks (int): Number of weeks to look back.
        
    Returns:
        List[Dict]: A list of review dictionaries within the specified time window.
    """
    cutoff_date = datetime.now() - timedelta(weeks=weeks)
    all_reviews = []
    continuation_token = None
    
    # Google Play Scraper fetches reviews in batches. 
    # We iterate and fetch batches until the dates of the reviews in the batch are older than our cutoff.
    while True:
        result, continuation_token = reviews(
            app_id,
            lang='en', # fetch english reviews by default
            country='in', # default to India for Groww
            sort=Sort.NEWEST, # important: sort by newest to stop when we hit older dates
            count=100,
            continuation_token=continuation_token
        )
        
        if not result:
            break
            
        valid_reviews = []
        reached_cutoff = False
        
        for review in result:
            review_date = review.get('at')
            if review_date and review_date < cutoff_date:
                reached_cutoff = True
                break # Since it's sorted by newest, all subsequent reviews will be older
            valid_reviews.append(review)
            
        all_reviews.extend(valid_reviews)
        
        if reached_cutoff or not continuation_token:
            break
            
    return all_reviews

if __name__ == "__main__":
    # Quick test/demonstration
    app_package = os.getenv("TARGET_APP_PACKAGE", "com.nextbillion.groww")
    print(f"Fetching reviews for {app_package} for the last 10 weeks...")
    recent_reviews = fetch_recent_reviews(app_package, weeks=10)
    print(f"Fetched {len(recent_reviews)} raw reviews.")
    
    # Process reviews (scrubs PII and filters out < 8 words, emojis, non-English)
    processed_reviews = process_reviews(recent_reviews)
    print(f"Retained {len(processed_reviews)} reviews after processing and filtering.")
    
    # Save the raw/actual reviews to raw_reviews.json
    raw_output_file = "raw_reviews.json"
    with open(raw_output_file, 'w', encoding='utf-8') as f:
        json.dump(recent_reviews, f, indent=4, default=str)
    print(f"Saved actual raw reviews to {raw_output_file}!")
    
    # Save the processed/normalized reviews to reviews.json
    output_file = "reviews.json"
    with open(output_file, 'w', encoding='utf-8') as f:
        # We use default=str so that datetime objects in the reviews are converted to strings
        json.dump(processed_reviews, f, indent=4, default=str)
        
    print(f"Saved normalized reviews to {output_file}!")


