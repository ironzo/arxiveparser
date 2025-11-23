# Imports
import json
import os
import asyncio
import urllib.parse
import aiohttp
import logging
from dotenv import load_dotenv
import google.generativeai as genai
from llm import invoke
from settings import model_name, structured_query_config, Query
from prompt_library import query_construction, make_digest
from feed_parser import found_results
from langchain_ollama import ChatOllama
from text_parser import parse_paper_async
from summaries import process_paper_paragraphs_parallel, create_general_summary
from telegram_notify import tg_notify, tg_notify_multiple

# Try to import database module
try:
    from db import get_db_manager
    DB_AVAILABLE = True
except ImportError:
    DB_AVAILABLE = False
    print("⚠️  Database module not available. Using JSON fallback.")

# Load environment
load_dotenv()
USE_DATABASE = os.getenv("USE_DATABASE", "false").lower() == "true"

# Setup logging
logger = logging.getLogger(__name__)

def load_existing_papers():
    """Load existing papers from database or JSON file"""
    if USE_DATABASE and DB_AVAILABLE:
        try:
            db = get_db_manager()
            papers = db.get_all_papers()
            logger.info(f"Loaded {len(papers)} papers from database")
            return papers
        except Exception as e:
            logger.error(f"Error loading from database: {e}")
            logger.warning("Falling back to JSON")
    
    # Fallback to JSON
    papers_path = os.path.join(os.path.dirname(__file__), "papers.json")
    if os.path.exists(papers_path):
        try:
            with open(papers_path, "r", encoding="utf-8") as f:
                papers = json.load(f)
                logger.info(f"Loaded {len(papers)} papers from JSON")
                return papers
        except (json.JSONDecodeError, FileNotFoundError):
            return []
    return []

def save_papers(papers):
    """Save papers to database or JSON file"""
    if USE_DATABASE and DB_AVAILABLE:
        try:
            db = get_db_manager()
            success_count = 0
            for paper in papers:
                if db.add_paper(paper):
                    success_count += 1
            logger.info(f"Saved {success_count}/{len(papers)} papers to database")
            return True
        except Exception as e:
            logger.error(f"Error saving to database: {e}")
            logger.warning("Falling back to JSON")
    
    # Fallback to JSON
    papers_path = os.path.join(os.path.dirname(__file__), "papers.json")
    try:
        with open(papers_path, "w", encoding="utf-8") as f:
            json.dump(papers, f, ensure_ascii=False, indent=4)
        logger.info(f"Saved {len(papers)} papers to JSON")
        return True
    except Exception as e:
        logger.error(f"Error saving to JSON: {e}")
        return False

def get_paper_id(paper):
    """Extract unique identifier for a paper (using arXiv ID)"""
    return paper.get("id", "")

def is_paper_already_processed(paper_id, existing_papers=None):
    """Check if paper is already in our database or JSON"""
    if USE_DATABASE and DB_AVAILABLE:
        try:
            db = get_db_manager()
            return db.paper_exists(paper_id)
        except Exception as e:
            logger.error(f"Error checking paper existence in database: {e}")
    
    # Fallback to checking in memory list
    if existing_papers:
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
        # Step 1: Validate API key and make client
        load_dotenv()
        api_key = os.getenv('API_KEY')
        if not api_key:
            error_msg = "CRITICAL: API_KEY not found in environment. Cannot use Gemini model."
            print(error_msg)
            tg_notify(f"❌ {error_msg}", chat_id=chat_id)
            raise ValueError("API_KEY must be set in .env file to use Gemini model")
        
        try:
            client = genai.Client(api_key=api_key)
            # Step 2: Making LLM-made search query
            llm_response = invoke(client, model_name, query_construction, user_prompt, structured_query_config)
            search_query = json.loads(llm_response.text)['query']
        except Exception as e:
            error_msg = f"Error with Gemini API: {str(e)}"
            print(error_msg)
            tg_notify(f"⚠️ {error_msg}\nUsing fallback query...", chat_id=chat_id)
            # Use fallback query
            search_query = f'all:"{user_prompt}"'

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
    print(f"Existing papers len: {len(existing_papers)}. New papers (unique) len: {len(results)}")

    # Step 4: Parse text and add to JSON (PARALLEL VERSION with error recovery)
    if len(results) > 0:
        print(f"Parsing {len(results)} papers in parallel...")
        
        # Create session with timeout
        timeout = aiohttp.ClientTimeout(total=60, connect=10)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            # Create tasks for parallel parsing
            parse_tasks = [parse_paper_async(session, paper) for paper in results]
            
            # Process with progress tracking and error recovery
            parsed_papers = []
            failed_papers = []
            completed_count = 0
            
            for completed_task in asyncio.as_completed(parse_tasks):
                try:
                    parsed_paper = await completed_task
                    if parsed_paper:  # Check if paper was successfully parsed
                        parsed_papers.append(parsed_paper)
                    completed_count += 1
                    print(f'Progress: {completed_count}/{len(results)} papers parsed')
                except Exception as e:
                    failed_papers.append(str(e))
                    completed_count += 1
                    print(f'Error parsing paper {completed_count}/{len(results)}: {e}')
                    continue  # Continue with next paper
            
            # Update results with successfully parsed papers
            results = parsed_papers
            
            # Notify about failures if any
            if failed_papers:
                print(f"⚠️ Failed to parse {len(failed_papers)} paper(s)")
                if len(parsed_papers) == 0:
                    tg_notify(f"⚠️ Failed to parse all papers. Please try again later.", chat_id=chat_id)
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
        
        # Wrap each task with semaphore and error handling
        async def limited_task(original_task):
            async with semaphore:
                try:
                    return await original_task
                except Exception as e:
                    print(f"Error in section summary: {e}")
                    return []  # Return empty list on error
        
        # Create limited tasks
        limited_tasks = [limited_task(task) for task in tasks]
        
        # Use asyncio.gather with return_exceptions for better error handling
        print("Processing section summaries...")
        section_summaries_list = await asyncio.gather(*limited_tasks, return_exceptions=True)
        print(f"Completed {len(section_summaries_list)} section summaries")
        
        # Store section summaries temporarily, handle errors
        for i, section_summaries in enumerate(section_summaries_list):
            if isinstance(section_summaries, Exception):
                print(f"Error in paper {i}: {section_summaries}")
                results[i]["section_summaries"] = []
            else:
                results[i]["section_summaries"] = section_summaries
    
    # Step 5.5: Create general summaries from section summaries
    print(f'Creating general summaries for {len(results)} papers...')
    
    general_summary_tasks = []
    for i, paper in enumerate(results):
        general_summary_tasks.append(create_general_summary(summaries_model, paper))
    
    if len(general_summary_tasks) > 0:
        general_summaries = await asyncio.gather(*general_summary_tasks, return_exceptions=True)
        for i, general_summary in enumerate(general_summaries):
            if isinstance(general_summary, Exception):
                print(f'Error creating general summary for paper {i+1}: {general_summary}')
                results[i]["general_summary"] = ""
            else:
                results[i]["general_summary"] = general_summary
                print(f'General summary created for paper {i+1}/{len(results)}')
    
    # Step 6: Add new papers to database/JSON
    if len(results) > 0:
        if USE_DATABASE and DB_AVAILABLE:
            # Save individual papers to database
            save_papers(results)
            print(f"Added {len(results)} new papers to database")
        else:
            # Save all papers to JSON (traditional method)
            all_papers = existing_papers + results
            save_papers(all_papers)
            print(f"Added {len(results)} new papers to JSON. Total papers: {len(all_papers)}")
    else:
        print("No new papers to add")
        all_papers = existing_papers

    # Step 7: General digest - based on general summaries
    # Get ALL papers (existing + new) that match the query result IDs
    if USE_DATABASE and DB_AVAILABLE:
        # Get papers directly from database by IDs
        try:
            db = get_db_manager()
            results_query = db.get_papers_by_ids(query_result_ids)
        except Exception as e:
            logger.error(f"Error getting papers from database: {e}")
            results_query = results  # Fallback to just new papers
    else:
        # Load from JSON
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
    # For standalone testing only
    test_user_prompt = "RAG"
    test_time_range = "[202508010000+TO+202508020000]"
    asyncio.run(main_with_params(test_user_prompt, test_time_range))