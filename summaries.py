from prompt_library import summaries, general_paper_summary
import asyncio

async def make_summary(llm, elements):
    """
        Input - elements -> TUPLES (list element with [0] - title, [1] - text; llm 
        Output - LLM-generated summaries for 1 paragraph
    """
    print(f"Making summary for {elements[0]}")
    user_prompt = f"""
        Given the paragraph title and paragraph text. 
        Return the consise summary of paragraph text.

        # Paragpraph Title:
        {elements[0]}

        # Paragraph Text:
        {elements[1]}

        Return the summary of the paragraph text only.
        """
    messages = [("system", summaries), ("human", user_prompt)]
    try:
        # Use ainvoke for async LLM calls
        res = await llm.ainvoke(messages)
        summary = res.content
    except Exception as e:
        print(f"Warning: Error generating summary for {elements[0]}: {e}")
        summary = elements[1]  # Use original text as fallback
    return summary

async def process_paper_paragraphs_parallel(llm, paper):
    """
    Process all paragraphs of a paper in parallel.
    """
    paper_tuples = paper["Tuples"]
    if not paper_tuples:
        print(f"No tuples found in paper: {paper['title']}")
        return []

    # Process all paragraphs in parallel
    tasks = []
    for tuple_data in paper_tuples:
        task = make_summary(llm, tuple_data)
        tasks.append(task)
    
    summaries = await asyncio.gather(*tasks)
    
    # Return the summaries as tuples (title, text, summary)
    result_tuples = []
    for i, summary in enumerate(summaries):
        result_tuples.append([paper_tuples[i][0], paper_tuples[i][1], summary])
    
    return result_tuples

async def create_general_summary(llm, paper):
    """
    Create a comprehensive general summary of the paper using section summaries.
    """
    print(f"Creating general summary for: {paper['title'][:50]}...")
    
    # Get section summaries
    section_summaries = paper.get("section_summaries", [])
    if not section_summaries:
        print(f"No section summaries found for paper: {paper['title']}")
        return ""
    
    # Build the prompt with paper information
    general_summary_prompt = f"""
        Paper Title: {paper['title']}
        Abstract: {paper.get('Abstract', 'No abstract available')}
        
        Section Summaries:
    """
    
    # Add each section summary
    for section in section_summaries:
        if len(section) >= 3:  # [title, text, summary]
            general_summary_prompt += f"\n\n**{section[0]}:**\n{section[2]}"
    
    messages = [("system", general_paper_summary), ("human", general_summary_prompt)]
    
    try:
        res = await llm.ainvoke(messages)
        return res.content
    except Exception as e:
        print(f"Error creating general summary for {paper['title']}: {e}")
        return ""