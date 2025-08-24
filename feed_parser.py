import feedparser
from settings import base_url
import urllib, urllib.request
def found_results(generated_search_query, time_range):
    url = f'{base_url}{generated_search_query}+AND+submittedDate:{time_range}'
    data = urllib.request.urlopen(url)
    xml_data = data.read().decode('utf-8')
    feed = feedparser.parse(xml_data)
    results = []
    for entry in feed.entries:
        title = entry.title
        summary = entry.summary
        arxiv_id = entry.id.split('/')[-1]  # extract just the ID part
        authors = [author.name for author in entry.authors]

        results.append({
            "id": arxiv_id,
            "title": title,
            "summary": summary,
            "authors": authors
        })
    return results
