from prompt_library import summaries, general_paper_summary

def make_summary(llm, elements):
    """
    Input - elements (list element with [0] - title, [1] - text; llm 
    Output - LLM-generated summaries
    """
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
        res = llm.invoke(messages)
        summary = res.content
    except:
        summary = elements[1]
    return summary

def make_summary_all_paper(llm, paper_dict):
    """
    Input - dictionary wiht parsed paper info, including summaries.
    Output - summary of the entire paper
    """
    paper_title = paper_dict["title"]
    abstract = paper_dict["Abstract"]
    section_summaries = ""
    for i in range(len(paper_dict["Tuples"])):
        if len(paper_dict["Tuples"][i])>=3:
            section_summaries +=f"Paragraph Title:\n{paper_dict['Tuples'][i][0]}\n\nParagraph Summary:\n{paper_dict['Tuples'][i][2]}\n\n\n"
    user_prompt = f"""
    Please create a comprehensive summary of the following research paper:

    **Paper Title:** {paper_title}

    **Abstract:** {abstract}

    **Section Summaries:**
    {section_summaries}

    Generate a detailed summary following the structure and guidelines provided in the system prompt.
    """
    messages = [("system", general_paper_summary), ("human", user_prompt)]
    try:
        res = llm.invoke(messages)
        summary = res.content
    except:
        summary = abstract
    return summary

