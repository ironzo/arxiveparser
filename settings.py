from pydantic import BaseModel

# Select model
#model_name = 'gemini-2.0-flash-001'
model_name = "llama3.1:latest"

# ArXive base URL
base_url = 'https://export.arxiv.org/api/query?search_query='
parser_url_base = 'https://arxiv.org/html/'

# Schema for Structured Output (Query)
class Query(BaseModel):
    query: str

# Config for Structured Output (Query)
structured_query_config = {
    'response_mime_type':'application/json',
    'response_schema':Query
}