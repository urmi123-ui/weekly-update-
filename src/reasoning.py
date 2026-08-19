import json
import os
import time
from dotenv import load_dotenv
from sentence_transformers import SentenceTransformer
import umap
from sklearn.cluster import HDBSCAN
from groq import Groq

# Load environment variables
load_dotenv()
GROQ_API_KEY = os.getenv("GROQ_API_KEY")

if not GROQ_API_KEY or GROQ_API_KEY == "your_groq_api_key_here":
    print("Error: Please set GROQ_API_KEY in your .env file.")
    exit(1)

client = Groq(api_key=GROQ_API_KEY)

def load_reviews(filepath="reviews.json"):
    if not os.path.exists(filepath):
        print(f"File {filepath} not found.")
        return []
    with open(filepath, 'r', encoding='utf-8') as f:
        return json.load(f)

def generate_embeddings(reviews):
    print("Loading embedding model (BAAI/bge-small-en-v1.5)...")
    # This runs locally on CPU, no API key needed
    model = SentenceTransformer('BAAI/bge-small-en-v1.5')
    texts = [r['content'] for r in reviews]
    print(f"Generating embeddings for {len(texts)} reviews...")
    embeddings = model.encode(texts, show_progress_bar=True)
    return embeddings

def cluster_embeddings(embeddings):
    print("Reducing dimensionality with UMAP...")
    # UMAP helps HDBSCAN find clusters in high dimensional space
    reducer = umap.UMAP(n_neighbors=15, n_components=5, metric='cosine', random_state=42)
    reduced_embeddings = reducer.fit_transform(embeddings)
    
    print("Clustering with HDBSCAN...")
    # HDBSCAN from scikit-learn >= 1.3
    clusterer = HDBSCAN(min_cluster_size=10, min_samples=5)
    labels = clusterer.fit_predict(reduced_embeddings)
    return labels

def summarize_cluster(cluster_id, reviews_in_cluster):
    # To respect Groq's strict 12K TPM limit, we only send a sample of the reviews in the cluster
    # We sample a max of 15 reviews to keep the context window small.
    sample_size = min(15, len(reviews_in_cluster))
    sampled_reviews = reviews_in_cluster[:sample_size]
    
    text_block = "\n".join([f"- {r['content']}" for r in sampled_reviews])
    
    prompt = f"""
You are a product manager analyzing user feedback for a fintech app.
Below is a cluster of related reviews from our users:

{text_block}

Task:
1. Identify the overarching theme of this cluster (e.g. "Login Issues", "UI Feedback", "Feature Request").
2. Extract 1-2 representative verbatim quotes. If a review covers multiple topics, extract ONLY the sentence relevant to this cluster's theme. The quote MUST be exact words from the text above.
3. Propose 1 actionable idea for the product or support team based on this feedback.

Format your response as valid JSON:
{{
    "theme": "Theme Name",
    "quotes": ["Exact quote 1", "Exact quote 2"],
    "actionable_idea": "The idea here"
}}
"""
    try:
        response = client.chat.completions.create(
            messages=[{"role": "user", "content": prompt}],
            model="qwen/qwen3.6-27b",
            response_format={"type": "json_object"},
            temperature=0.2,
        )
        return json.loads(response.choices[0].message.content)
    except Exception as e:
        print(f"Error summarizing cluster {cluster_id}: {e}")
        return None

def run_reasoning_engine():
    reviews = load_reviews()
    if not reviews:
        print("No reviews found. Run the scraper first.")
        return
        
    embeddings = generate_embeddings(reviews)
    labels = cluster_embeddings(embeddings)
    
    # Group reviews by cluster label
    clusters = {}
    for i, label in enumerate(labels):
        if label == -1:
            continue # Label -1 is HDBSCAN's "noise" category (outliers)
        if label not in clusters:
            clusters[label] = []
        clusters[label].append(reviews[i])
        
    print(f"Found {len(clusters)} distinct clusters.")
    
    insights = []
    # Process clusters with rate limiting
    # Groq Limits: 30 RPM, 1K RPD, 12K TPM, 100K TPD
    for cluster_id, cluster_reviews in clusters.items():
        print(f"Summarizing cluster {cluster_id} ({len(cluster_reviews)} reviews)...")
        summary = summarize_cluster(cluster_id, cluster_reviews)
        
        if summary:
            # Strict Validation step: ensure quotes exist in the sampled text
            valid_quotes = []
            sampled_texts = " ".join([r['content'] for r in cluster_reviews])
            for q in summary.get('quotes', []):
                # Basic normalization for substring check
                if q.lower().strip() in sampled_texts.lower():
                    valid_quotes.append(q)
                else:
                    print(f"Warning: Hallucinated quote removed - '{q}'")
            
            summary['quotes'] = valid_quotes
            summary['cluster_id'] = int(cluster_id)
            summary['review_count'] = len(cluster_reviews)
            insights.append(summary)
            
        # Rate limiting sleep to respect 12K TPM / 30 RPM
        # Waiting 5 seconds ensures we don't exceed limits.
        time.sleep(5)
        
    with open("insights.json", "w", encoding='utf-8') as f:
        json.dump(insights, f, indent=4)
        
    print("Saved insights to insights.json")

if __name__ == "__main__":
    run_reasoning_engine()
