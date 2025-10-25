# Imports
import json
import os
import asyncio
import urllib.parse
import aiohttp  # Add this
from dotenv import load_dotenv
from google import genai
from llm import invoke
from settings import model_name, structured_query_config, Query
from prompt_library import query_construction, make_digest, summaries, general_paper_summary
from feed_parser import found_results
from langchain_ollama import ChatOllama
from text_parser import paper_json, enhance_json, parse_paper_async
from summaries import process_paper_paragraphs_parallel, create_general_summary
from telegram_notify import tg_notify, tg_notify_multiple
import asyncio
from concurrent.futures import ThreadPoolExecutor

# HARDCODED FOR NOW:
user_prompt = "RAG"
time_range = "[202508010000+TO+202508020000]"


def load_existing_papers():
    """Load existing papers from JSON file if it exists"""
    papers_path = os.path.join(os.path.dirname(__file__), "papers.json")
    if os.path.exists(papers_path):
        try:
            with open(papers_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, FileNotFoundError):
            return []
    return []

def save_papers_to_json(papers):
    """Save papers to JSON file"""
    papers_path = os.path.join(os.path.dirname(__file__), "papers.json")
    with open(papers_path, "w", encoding="utf-8") as f:
        json.dump(papers, f, ensure_ascii=False, indent=4)

def get_paper_id(paper):
    """Extract unique identifier for a paper (using arXiv ID)"""
    return paper.get("id", "")

def is_paper_already_processed(paper_id, existing_papers):
    """Check if paper is already in our database"""
    for existing_paper in existing_papers:
        if get_paper_id(existing_paper) == paper_id:
            return True
    return False

async def main_with_params(user_prompt: str, time_range: str, chat_id: str = None):
    """Main function that accepts parameters for processing"""
    
    # Send start notification using existing tg_notify
    tg_notify("🚀 Starting arXiv paper processing...", chat_id=chat_id)

    # Load existing papers
    existing_papers = load_existing_papers()
    print(f"Loaded {len(existing_papers)} existing papers from JSON")

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
    results = []  # Initialize results to avoid undefined variable error

    try:
        print(f"Search query: {search_query}")
        # URL encode the search query to handle spaces and special characters
        search_query = urllib.parse.quote(search_query, safe=':+()%22%2B')
        print(f"URL encoded query: {search_query}")
        results = found_results(search_query, time_range)
        print(f"Found {len(results)} papers from arXiv")
        tg_notify(f"📊 Found {len(results)} papers from arXiv", chat_id=chat_id)
            
    except Exception as e:
        print(f'exception in query generation {e}')
        fallback_query = "(all:%22"+user_prompt.replace(".","").replace(" ","+")+"%22)"
        print(f'Fallback Search query: {fallback_query}')
        results = found_results(fallback_query, time_range)
        print(f"Found {len(results)} papers from arXiv")   

    ### PROCEED with new papers only:
    query_result_ids = [get_paper_id(paper) for paper in results] # collect IDs from parsed papers. Will be used to make digest
    results = [paper for paper in results if not is_paper_already_processed(get_paper_id(paper), existing_papers)]
    # trim new results for testing:
    #results = results[:1]
    print(f"Existing papers len: {len(existing_papers)}. New papers (unique) len: {len(results)}")

    # Step 4: Parse text and add to JSON (PARALLEL VERSION)
    if len(results) > 0:
        print(f"Parsing {len(results)} papers in parallel...")
        
        async with aiohttp.ClientSession() as session:
            # Create tasks for parallel parsing
            parse_tasks = [parse_paper_async(session, paper) for paper in results]
            
            # Process with progress tracking
            parsed_papers = []
            completed_count = 0
            
            for completed_task in asyncio.as_completed(parse_tasks):
                parsed_paper = await completed_task
                parsed_papers.append(parsed_paper)
                completed_count += 1
                print(f'Progress: {completed_count}/{len(results)} papers parsed')
            
            # Update results with parsed papers
            results = parsed_papers
    else:
        print("No new papers to parse")

    ### DEBUG:
    print(f"Results length: {len(results)}")
    print(f"Results type: {type(results)}")
    if len(results) > 1:
        print(f"Results[1] keys: {results[1].keys()}")
    
    # Step 5: Make section summaries for each paper in parallel
    summaries_model = ChatOllama(model=model_name)

    tasks = []

    for i, paper in enumerate(results):
        tasks.append(process_paper_paragraphs_parallel(summaries_model, paper))

    if len(tasks) > 0:
        print(f'Number of papers for section summary processing: {len(tasks)}')
        
        # Create semaphore once for rate limiting
        SEMAPHORE_LIMIT = 5  # Adjust based on your LLM service limits
        semaphore = asyncio.Semaphore(SEMAPHORE_LIMIT)
        
        # Wrap each task with semaphore
        async def limited_task(original_task):
            async with semaphore:
                return await original_task
        
        # Create limited tasks
        limited_tasks = [limited_task(task) for task in tasks]
        
        # Use asyncio.gather for simpler processing
        print("Processing section summaries...")
        section_summaries_list = await asyncio.gather(*limited_tasks)
        print(f"Completed {len(section_summaries_list)} section summaries")
        
        # Store section summaries temporarily
        for i, section_summaries in enumerate(section_summaries_list):
            results[i]["section_summaries"] = section_summaries
    
    # Step 5.5: Create general summaries from section summaries
    print(f'Creating general summaries for {len(results)} papers...')
    
    general_summary_tasks = []
    for i, paper in enumerate(results):
        general_summary_tasks.append(create_general_summary(summaries_model, paper))
    
    if len(general_summary_tasks) > 0:
        general_summaries = await asyncio.gather(*general_summary_tasks)
        for i, general_summary in enumerate(general_summaries):
            results[i]["general_summary"] = general_summary
            print(f'General summary created for paper {i+1}/{len(results)}')
    
    # Step 6: Add new papers to JSON
    if len(results) > 0:
        all_papers = existing_papers + results
        save_papers_to_json(all_papers)
        print(f"Added {len(results)} new papers to JSON. Total papers: {len(all_papers)}")
    else:
        print("No new papers to add to JSON")
        all_papers = existing_papers

    # Step 7: General digest - based on general summaries
    # Get ALL papers (existing + new) that match the query result IDs
    all_papers = load_existing_papers()  # Reload to get the updated JSON
    results_query = [paper for paper in all_papers if get_paper_id(paper) in query_result_ids]
    print(f'Number of papers for digest processing: {len(results_query)}')

    if len(results_query) > 0:
        all_titles = [paper["title"] for paper in results_query]
        all_urls = [paper.get("url", "") for paper in results_query]
        all_general_summaries = [paper.get("general_summary", "") for paper in results_query]
        
        # Filter out papers without general summaries
        papers_with_summaries = []
        titles_with_summaries = []
        urls_with_summaries = []
        
        for i, summary in enumerate(all_general_summaries):
            if summary and summary.strip():  # Only include papers with actual summaries
                papers_with_summaries.append(results_query[i])
                titles_with_summaries.append(all_titles[i])
                urls_with_summaries.append(all_urls[i])
        
        print(f'Papers with summaries for digest: {len(papers_with_summaries)}')
        if len(papers_with_summaries) > 0:
            digest_prompts = make_digest(all_general_summaries, titles_with_summaries)
            digest_messages = [("system", digest_prompts["system"]), ("human", digest_prompts["user"])]
            digest_response = summaries_model.invoke(digest_messages)
            scientific_digest = digest_response.content
            
            # Add paper references with links
            paper_references = "\n\n📚 *Paper References:*\n"
            for i, (title, url) in enumerate(zip(titles_with_summaries, urls_with_summaries), 1):
                # Clean up the title for better markdown formatting
                clean_title = title.replace('\n', ' ').strip()
                paper_references += f"{i}. *{clean_title}*\n   🔗 [Read Paper]({url})\n\n"
                
            final_digest = scientific_digest + paper_references
            digest_text = f"""🎯 *Research Digest - {user_prompt}*
            {final_digest}"""
            
            # Send digest to Telegram using existing tg_notify_multiple
            tg_notify_multiple(digest_text, chat_id=chat_id)
        else:
            print("No papers with summaries found for digest creation")
            tg_notify("⚠️ No papers with summaries found for digest creation", chat_id=chat_id)
    else:
        print("No papers found for digest processing")
        tg_notify("⚠️ No papers found for digest processing", chat_id=chat_id)   


if __name__ == "__main__":
    asyncio.run(main_with_params(user_prompt, time_range))