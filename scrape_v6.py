#!/usr/bin/env python3
"""
scrape_v6.py - Downloads the TradingView Pine Script v6 User Manual and combines it into a single Markdown file.
Usage:
    python scrape_v6.py [--pdf]

- Downloads all chapters of the Pine Script v6 manual as HTML (cached in a "html/" directory).
- Extracts and concatenates the content into one Markdown file (preserving headers, code blocks, etc.).
- Generates a table of contents with links to each chapter section in the Markdown.
- If the --pdf flag is provided, converts the Markdown file to PDF.
 
Requirements for PDF conversion:
    - Pandoc must be installed and available in the system PATH (https://pandoc.org).
    Alternatively, you can use other tools such as markdown-pdf (Node.js) or WeasyPrint (pip install weasyprint) to convert the Markdown to PDF.
"""
import os
import re
import sys
import argparse
import logging
import requests
from bs4 import BeautifulSoup, NavigableString
import shutil
import subprocess

# Constants
BASE_URL = "https://www.tradingview.com"
MANUAL_INDEX_URL = BASE_URL + "/pine-script-docs"
HEADERS = {"User-Agent": "Mozilla/5.0"}

def slugify(text: str) -> str:
    """Convert text to a slug suitable for Markdown anchor links."""
    slug = re.sub(r'[^0-9a-zA-Z\s-]', '', text)
    return slug.strip().lower().replace(' ', '-')

def clean_html_content(html: bytes) -> bytes:
    """Remove navigation menu and 'On this page' sections from the HTML content."""
    content = html
    # Remove breadcrumb navigation (the menu at the top of each page)
    start = content.find(b'<div class="breadcrumb"')
    if start != -1:
        end = content.find(b'</div>', start)
        if end != -1:
            content = content[:start] + content[end+6:]
    # Remove "On this page" table of contents (if any)
    marker = b'<h2>On this page'
    pos = content.find(marker)
    if pos != -1:
        # Find the enclosing <div> for the "On this page" section
        div_start = content.rfind(b'<div', 0, pos)
        div_end = content.find(b'</div>', pos)
        if div_start != -1 and div_end != -1:
            content = content[:div_start] + content[div_end+6:]
    return content

def extract_html_to_markdown(html: bytes) -> str:
    """Extract main content from HTML and convert it to Markdown."""
    # Clean out irrelevant HTML parts to avoid parsing issues
    cleaned_html = clean_html_content(html)
    soup = BeautifulSoup(cleaned_html, 'lxml')
    # Remove any leftover nav, header, footer elements
    for tag in soup.find_all(['nav', 'aside', 'header', 'footer']):
        tag.decompose()
    # Recursive function to convert HTML elements to Markdown text
    def element_to_md(elem, indent=0):
        if isinstance(elem, NavigableString):
            text = str(elem)
            # If whitespace text, skip it (except inside <pre>)
            if text.isspace():
                return text if elem.find_parent('pre') else ''
            return text
        md = ""
        name = elem.name
        if name in ['h1','h2','h3','h4','h5','h6']:
            level = int(name[1])
            md += "#" * level + " "
            md += "".join(element_to_md(child, indent) for child in elem.children).strip()
            md += "\n\n"
        elif name in ['p','div']:
            # Convert block-level elements (paragraphs, generic divs)
            content = "".join(element_to_md(child, indent) for child in elem.children).strip()
            if content:
                md += content + "\n\n"
        elif name in ['ul','ol']:
            # Convert lists
            is_ol = (name == 'ol')
            num = 1
            for li in elem.find_all('li', recursive=False):
                prefix = f"{num}. " if is_ol else "- "
                # Indent nested list items
                inner = "".join(element_to_md(child, indent + len(prefix)) for child in li.children).strip()
                # Indent any newlines in list item content to keep proper formatting
                inner = inner.replace("\n", "\n" + " " * (indent + len(prefix)))
                md += " " * indent + prefix + inner + "\n"
                if is_ol:
                    num += 1
            md += "\n"
        elif name == 'pre':
            # Code block
            code_text = elem.get_text()
            code_text = code_text.rstrip('\n')  # remove trailing newlines
            md += "```\n" + code_text + "\n```\n\n"
        elif name == 'code':
            # Inline code (skip if handled as part of <pre>)
            if elem.find_parent('pre'):
                md += elem.get_text()
            else:
                code_text = elem.get_text()
                if '`' in code_text:
                    md += "``" + code_text + "``"
                else:
                    md += "`" + code_text + "`"
        elif name == 'a':
            # Hyperlink
            href = elem.get('href', '')
            link_text = "".join(element_to_md(child, indent) for child in elem.children).strip() or ''
            if not href:
                md += link_text
            else:
                full_url = href if href.startswith('http') else BASE_URL + href
                # Internal manual link -> convert to anchor link
                if BASE_URL in full_url and '/pine-script-docs' in full_url:
                    if '#' in href:
                        frag = href.split('#', 1)[1]
                        md += f"[{link_text}](#{frag})"
                    else:
                        page_slug = href.rstrip('/').split('/')[-1] or href.rstrip('/').split('/')[-2]
                        md += f"[{link_text}](#{slugify(page_slug)})"
                else:
                    # External link
                    md += f"[{link_text}]({full_url})"
        elif name in ['strong','b']:
            content = "".join(element_to_md(child, indent) for child in elem.children).strip()
            md += f"**{content}**"
        elif name in ['em','i']:
            content = "".join(element_to_md(child, indent) for child in elem.children).strip()
            md += f"*{content}*"
        elif name == 'img':
            # Image -> Markdown image syntax
            alt_text = elem.get('alt', '')
            src = elem.get('src', '')
            if src:
                src_url = src if src.startswith('http') else BASE_URL + src
                md += f"![{alt_text}]({src_url})"
        elif name == 'br':
            md += "  \n"
        else:
            # Default: process children recursively (for any tags not explicitly handled)
            md += "".join(element_to_md(child, indent) for child in elem.children)
        return md
    # Convert all top-level children of body to markdown
    body = soup.body or soup
    markdown_text = "".join(element_to_md(child) for child in body.contents)
    return markdown_text.strip()

def main(generate_pdf=False):
    os.makedirs("html", exist_ok=True)
    # Fetch the index page to find all chapters
    logging.info(f"Fetching manual index page: {MANUAL_INDEX_URL}")
    resp = requests.get(MANUAL_INDEX_URL, headers=HEADERS)
    resp.raise_for_status()
    soup_index = BeautifulSoup(resp.content, 'lxml')
    chapter_links = soup_index.find_all('a', class_='page-link')
    # Filter out anchors that are within-page links (with '#')
    chapter_links = [a for a in chapter_links if a.get('href') and '#' not in a['href']]
    logging.info(f"Found {len(chapter_links)} chapters.")
    combined_md_parts = []
    toc_lines = []
    for idx, a in enumerate(chapter_links, start=1):
        chapter_url = a['href']
        full_url = chapter_url if chapter_url.startswith('http') else BASE_URL + chapter_url
        chapter_title = a.get_text().strip()
        anchor = slugify(chapter_title)
        toc_lines.append(f"- [{chapter_title}](#{anchor})")
        # Determine local HTML filename for caching
        safe_name = chapter_url.strip('/').replace('/', '_')
        if not safe_name.endswith('.html'):
            safe_name += '.html'
        filename = f"{idx:05d}_{safe_name}"
        file_path = os.path.join("html", filename)
        # Download chapter page if not already cached
        if not os.path.exists(file_path):
            logging.info(f"Downloading chapter: {full_url}")
            resp_ch = requests.get(full_url, headers=HEADERS)
            resp_ch.raise_for_status()
            with open(file_path, 'wb') as f:
                f.write(resp_ch.content)
        else:
            logging.info(f"Using cached HTML for {chapter_title}")
        # Read the HTML file and convert to Markdown
        with open(file_path, 'rb') as f:
            html_content = f.read()
        md_content = extract_html_to_markdown(html_content)
        combined_md_parts.append(md_content)
    # Assemble Markdown with table of contents at top
    toc_md = "# Table of Contents\n\n" + "\n".join(toc_lines) + "\n\n"
    full_md = toc_md + "\n\n".join(combined_md_parts)
    output_md_file = "PineScript_v6_Manual.md"
    with open(output_md_file, 'w', encoding='utf-8') as out:
        out.write(full_md)
    logging.info(f"Markdown manual saved to {output_md_file}")
    if generate_pdf:
        pdf_file = "PineScript_v6_Manual.pdf"
        pandoc_path = shutil.which("pandoc")
        if pandoc_path:
            logging.info("Converting Markdown to PDF using pandoc...")
            subprocess.run([pandoc_path, output_md_file, "-o", pdf_file])
            logging.info(f"PDF manual saved to {pdf_file}")
        else:
            logging.warning("Pandoc not found. Skipping PDF generation. Please install pandoc or use an alternative tool to create the PDF.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Combine Pine Script v6 manual into a Markdown (and optional PDF).")
    parser.add_argument("--pdf", action="store_true", help="Also convert the Markdown output to PDF (requires pandoc).")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    main(generate_pdf=args.pdf)


