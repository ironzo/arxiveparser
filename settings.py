from pydantic import BaseModel

# Select model
model = 'gemini-2.0-flash-001'

# ArXive base URL
base_url = 'https://export.arxiv.org/api/query?search_query='

# Schema for Structured Output (Query)
class Query(BaseModel):
    query: str

# Config for Structured Output (Query)
structured_query_config = {
    'response_mime_type':'application/json',
    'response_schema':Query
}