# Imports
import json
import os
from dotenv import load_dotenv
from google import genai
from llm import invoke
from settings import model, structured_query_config
from prompt_library import query_construction
from feed_parser import found_results

# User Input:
user_prompt = "Retrieval Augmented Generation. Agents. Tools."
time_range = "[202508010000+TO+202508080000]" # TO DO: nice util func to convert DT to this.

# Step 1: Making Client
load_dotenv()
api_key = os.getenv('API_KEY')
client = genai.Client(api_key=api_key)

# Step 2: Making LLM-made search query
llm_response = invoke(client, model, query_construction, user_prompt, structured_query_config)
search_query = json.loads(llm_response.text)

# Step 3: Parsing ArXive
results = found_results(search_query['query'], time_range)
print(results)