import re
import html
import aiohttp
import asyncio
from bs4 import BeautifulSoup
from settings import parser_url_base

def get_abstract(soup):
    try:
        return soup.find('div', class_='ltx_abstract').get_text(" ", strip=True)
    except Exception as e:
        print(f"Warning: Could not extract abstract: {e}")
        return ""

def get_sections(soup):
    return soup.find_all("h2", class_="ltx_title ltx_title_section")

def parse_main_text(all_h2):
    paper_text = {}
    def base_case(tag):
        if not tag: return ""
        text = html.unescape(tag.get_text(" ", strip=True))
        text = re.sub(r"[\u200b\u200c\u200d\ufeff]", "", text)
        text = re.sub(r"\s+", " ", text).strip()
        return text

    def find_sibling(tag):
        return tag.find_next_sibling()

    def find_siblings(tag):
        siblings = []
        current = find_sibling(tag)
        while current:
            if current.name == "h2":
                break
            siblings.append(current)
            current = find_sibling(current)
        return siblings

    def process_section(h2_tag):
        section_title = base_case(h2_tag)
        siblings = find_siblings(h2_tag)
        section_content = []
        
        for sibling in siblings:
            if sibling.name in ["p", "div", "ul", "ol", "li"]:
                content = base_case(sibling)
                if content:
                    section_content.append(content)
        
        return section_title, " ".join(section_content)

    for h2 in all_h2:
        title, content = process_section(h2)
        if title and content:
            paper_text[title] = content

    return paper_text

def extract_tuples(data, parent_key=None):
    result = []

    def dfs(node, current_key):
        if isinstance(node, dict):
            for k, v in node.items():
                new_key = f"{current_key}. {k}" if current_key else k
                dfs(v, new_key)
        elif isinstance(node, list):
            for item in node:
                dfs(item, current_key)
        elif isinstance(node, str):
            result.append([current_key, node])

    dfs(data, parent_key)
    return result

def enhance_json(result):
    res = result["Main"]
    if res:
        res_tuple = extract_tuples(res)
    else:
        res_tuple = [["Summary", result["Abstract"]]]
    result["Tuples"] = res_tuple
    return result

async def get_soup_async(session, result):
    """Async version of get_soup using aiohttp"""
    id = result["id"]
    url = parser_url_base + id
    
    async with session.get(url) as response:
        html_content = await response.text()
        return BeautifulSoup(html_content, "html.parser")

async def parse_paper_async(session, paper):
    """Parse a single paper asynchronously"""
    print(f"Parsing paper: {paper['title'][:50]}...")
    
    try:
        # Get soup asynchronously
        soup = await get_soup_async(session, paper)
        
        # Run CPU-intensive tasks in thread pool
        loop = asyncio.get_event_loop()
        
        # These are CPU-bound, so use thread pool
        abstract = await loop.run_in_executor(None, get_abstract, soup)
        sections = await loop.run_in_executor(None, get_sections, soup)
        main_text = await loop.run_in_executor(None, parse_main_text, sections)
        
        # Build result
        # Construct arXiv URL from ID
        arxiv_url = f"https://arxiv.org/abs/{paper['id']}"
        
        if main_text:
            parsed_paper = {
                "id": paper["id"],
                "title": paper["title"],
                "authors": paper["authors"],
                "url": arxiv_url,
                "Abstract": abstract,
                "Main": main_text
            }
        else:
            parsed_paper = {
                "id": paper["id"],
                "title": paper["title"],
                "authors": paper["authors"],
                "url": arxiv_url,
                "Abstract": paper.get("summary", ""),
                "Main": ""
            }
        
        # Enhance with tuples
        enhanced_paper = await loop.run_in_executor(None, enhance_json, parsed_paper)
        
        return enhanced_paper
        
    except Exception as e:
        print(f"Error parsing paper {paper['title']}: {e}")
        # Return a minimal paper structure on error
        arxiv_url = f"https://arxiv.org/abs/{paper['id']}"
        return {
            "id": paper["id"],
            "title": paper["title"],
            "authors": paper["authors"],
            "url": arxiv_url,
            "Abstract": paper.get("summary", ""),
            "Main": "",
            "Tuples": [["Summary", paper.get("summary", "")]]
        }
