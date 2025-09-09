# Imports
import json
import os
from dotenv import load_dotenv
from google import genai
from llm import invoke
from settings import model_name, structured_query_config, Query
from prompt_library import query_construction
from feed_parser import found_results
from langchain_ollama import ChatOllama
from text_parser import paper_json, enhance_json
from summaries import make_summary, make_summary_all_paper

# User Input:
user_prompt = "Agents"
time_range = "[202508010000+TO+202508020000]" # TO DO: nice util func to convert DT to this.


### GEMINI:
if model_name == 'gemini-2.0-flash-001':
    # Step 1: Making Client
    load_dotenv()
    api_key = os.getenv('API_KEY')
    client = genai.Client(api_key=api_key)
    # Step 2: Making LLM-made search query
    llm_response = invoke(client, model_name, query_construction, user_prompt, structured_query_config)
    search_query = json.loads(llm_response.text)['query']

### OLLAMA:
else:
    # Step 1: Make Model with StrOutput
    model = ChatOllama(model=model_name)
    llm = model.with_structured_output(Query)

    # Step 2: Prepare Prompt and Invoke
    message = [("system", query_construction), ("human", user_prompt)]
    llm_response = llm.invoke(message)
    search_query = llm_response.query

# Step 3: Parsing ArXive
try:
    print(f"Search query: {search_query}")
    results = found_results(search_query, time_range)
    # for tests use 2 results only
    results = results[:2]
    print(f"Papers count: {len(results)}")
except Exception as e:
    print(f'exception in query generation {e}')
    fallback_query = "(all:%22"+user_prompt.replace(".","").replace(" ","+")+"%22)"
    print(f'Fallback Search query: {fallback_query}')
    results = found_results(fallback_query, time_range)
    print(f"Papers count: {len(results)}")   
# Enhance each result with parsed text:
enhanced_results = []
for i in range(len(results)):
    print(f"Working on paper no. {i+1}...")
    paper_jsn = paper_json(results[i])
    enhanced_jsn = enhance_json(paper_jsn)
    enhanced_results.append(enhanced_jsn)

# Step 4: Make summaries for each pargraph
# model for summaries is Ollama only (due to large volume of text)
summaries_model = ChatOllama(model=model_name)
for i in range(len(enhanced_results)):
    print(f"Making summaries for paper {i+1}/{len(enhanced_results)}...")
    tuples = enhanced_results[i]["Tuples"]
    for j in range(len(tuples)):
        print(f"Summarizing {j+1} / {len(tuples)} paragraph...")
        print(type(tuples[j]))
        print(tuples[j])
        summary = make_summary(summaries_model, tuples[j])
        tuples[j].append(summary)

# Step 5: Make summary for the entire paper
for i in range(len(enhanced_results)):
    print(f"Making general summary for paper {i+1}...")
    paper = enhanced_results[i]
    paper_summary = make_summary_all_paper(summaries_model, paper)
    # Add paper_summary
    paper["general_summary"] = paper_summary
    
# save enhanced_results with summaries to JSON
with open("papers.json", "w", encoding="utf-8") as f:
    json.dump(enhanced_results, f, ensure_ascii=False, indent=4)