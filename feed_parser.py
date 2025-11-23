import feedparser
import urllib.request
import time
from settings import base_url

# Rate limiting for arXiv API (recommended: 3 seconds between requests)
_last_arxiv_request = 0
_ARXIV_RATE_LIMIT = 3.0  # seconds

def found_results(generated_search_query, time_range):
    global _last_arxiv_request
    
    # Rate limiting: wait if needed
    elapsed = time.time() - _last_arxiv_request
    if elapsed < _ARXIV_RATE_LIMIT:
        sleep_time = _ARXIV_RATE_LIMIT - elapsed
        print(f"Rate limiting: waiting {sleep_time:.2f}s before arXiv request")
        time.sleep(sleep_time)
    
    url = f'{base_url}{generated_search_query}+AND+submittedDate:{time_range}'
    # Add timeout to prevent hanging
    data = urllib.request.urlopen(url, timeout=30)
    _last_arxiv_request = time.time()  # Update last request time
    
    xml_data = data.read().decode('utf-8')
    feed = feedparser.parse(xml_data)
    results = []
    for entry in feed.entries:
        title = entry.title
        summary = entry.summary
        arxiv_id = entry.id.split('/')[-1]  # extract just the ID part
        authors = [author.name for author in entry.authors]
        paper_url = entry.id  # This is the full arXiv URL

        results.append({
            "id": arxiv_id,
            "title": title,
            "summary": summary,
            "authors": authors,
            "url": paper_url
        })
    return results
