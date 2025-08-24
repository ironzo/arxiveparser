# Imports
import json
import os
from dotenv import load_dotenv
from google import genai
from llm import invoke
from settings import model, structured_query_config, Query
from prompt_library import query_construction
from feed_parser import found_results
from langchain_ollama import ChatOllama
from text_parser import paper_json

# User Input:
user_prompt = "Retrieval Augmented Generation. Agents. Tools."
time_range = "[202508010000+TO+202508020000]" # TO DO: nice util func to convert DT to this.


### GEMINI:
if model == 'gemini-2.0-flash-001':
    # Step 1: Making Client
    load_dotenv()
    api_key = os.getenv('API_KEY')
    client = genai.Client(api_key=api_key)

    # Step 2: Making LLM-made search query
    llm_response = invoke(client, model, query_construction, user_prompt, structured_query_config)
    search_query = json.loads(llm_response.text)['query']

### OLLAMA:
else:
    # Step 1: Make Model with StrOutput
    model = ChatOllama(model=model)
    llm = model.with_structured_output(Query)

    # Step 2: Prepare Prompt and Invoke
    llm_response = llm.invoke(query_construction+' '+user_prompt)
    search_query = llm_response.query

# Step 3: Parsing ArXive
print(f"Search query: {search_query}")
results = found_results(search_query, time_range)
print(f"Papers count: {len(results)}")
# Enhance each result with parsed text:
enhanced_results = []
for i in range(len(results)):
    print(f"Working on paper no. {i+1}...")
    enhanced_results.append(paper_json(results[i]))
# save enhanced_results to JSON
with open("papers.json", "w", encoding="utf-8") as f:
    json.dump(enhanced_results, f, ensure_ascii=False, indent=4)