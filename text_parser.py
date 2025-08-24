import requests, re, html
from bs4 import BeautifulSoup
from bs4.element import Tag
from settings import parser_url_base

def get_soup(result):
    id = result["id"]
    url_html = requests.get(parser_url_base+id).text
    return BeautifulSoup(url_html, "html.parser")

def get_abstract(soup):
    try:
        return soup.find('div', class_='ltx_abstract').get_text(" ", strip=True)
    except:
        return ""

def get_sections(soup):
    return soup.find_all("h2", class_="ltx_title ltx_title_section")

def parse_main_text(all_h2, paper_text):

    def base_case(tag):
        if not tag: return ""
        text = html.unescape(tag.get_text(" ", strip=True))
        text = re.sub(r"[\u200b\u200c\u200d\ufeff]", "", text)
        text = re.sub(r"\s+", " ", text).strip()
        return text

    def find_sibling(tag):
        return tag.find_next_sibling()

    def dfs(node):
        if node is None:
            return []
        acc, cur = [], node
        while cur:
            # compute hdr for THIS cur; only look at direct children
            hdr = cur.find(
                lambda t: isinstance(t, Tag) and any("title" in c for c in (t.get("class") or [])),
                recursive=False
            )
            label = base_case(hdr) if hdr else base_case(cur)

            # your existing child-pick logic (keep as-is)
            first_child = next(
                (c for c in cur.children
                 if isinstance(c, Tag) and (
                     'ltx_section' in (c.get('class') or []) or
                     'ltx_para'    in (c.get('class') or []) or
                     c.name == 'p'
                 )), None
            )

            if hdr and first_child:
                acc.append({label: dfs(first_child)})
            else:
                acc.append(label)

            cur = find_sibling(cur)
        return acc

    for h2 in all_h2:
        if isinstance(h2, Tag):
            key = base_case(h2)
            first = find_sibling(h2)
            paper_text[key] = dfs(first)

    return paper_text

def paper_json(result):
    soup = get_soup(result)
    abstract = get_abstract(soup)
    sections = get_sections(soup)
    paper_text = {
                    "id":result["id"],
                    "title":result["title"],
                    "authors":result["authors"],
                    "Abstract":abstract
                }
    return parse_main_text(sections, paper_text)

    