#!/usr/bin/env python3
"""
scraper_v6.py - Downloads the TradingView Pine Script v6 User Manual 
and combines it into a single Markdown file.
Usage:
    python scraper_v6.py [--pdf]

- Downloads all chapters of the Pine Script v6 manual as HTML (cached in a "html/" directory).
- Extracts and concatenates the content into one Markdown file (preserving headers, code blocks, etc.).
- Generates a table of contents with links to each chapter section in the Markdown.
- If the --pdf flag is provided, converts the Markdown file to PDF.
- Before PDF conversion, scans the Markdown for .webp image references, converts them to PNG,
  and updates the Markdown links to point to the local images.

Requirements for PDF conversion:
    - Pandoc must be installed and available in the system PATH 
      (https://pandoc.org).
    - Pillow is required for image conversion: pip install Pillow.

Author: Andre Heinecke <aheinecke@chelydra.at> and o3-mini-high
SPDX-License-Identifier: CC0-1.0
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
from urllib.parse import urlparse
from PIL import Image

# Constants
BASE_URL = "https://www.tradingview.com"
MANUAL_INDEX_URL = BASE_URL + "/pine-script-docs"
HEADERS = {"User-Agent": "Mozilla/5.0"}


def fix_smart_quotes(md_file: str):
    """
    Replace curly quotes with straight quotes in the Markdown file.
    This helps avoid undefined control sequences in the LaTeX conversion.
    """
    with open(md_file, 'r', encoding='utf-8') as f:
        content = f.read()
    # Replace common curly quotes with ASCII quotes.
    content = content.replace("“", '"').replace("”", '"')
    content = content.replace("‘", "'").replace("’", "'")
    with open(md_file, 'w', encoding='utf-8') as f:
        f.write(content)

def compress_pdf(pdf_file: str):
    gs_path = shutil.which("gs")
    if not gs_path:
        logging.warning("Ghostscript not found. Skipping PDF compression. Please install ghostscript.")
        return
    logging.info("Compressing manual")
    result = subprocess.run([
        gs_path, "-sDEVICE=pdfwrite", "-dCompatibilityLevel=1.4",
        "-dPDFSETTINGS=/ebook", "-dNOPAUSE", "-dQUIET",
        "-dBATCH", f"-sOutputFile={pdf_file}_compressed",
        pdf_file])
    if result.returncode != 0:
        logging.error(f"Ghostscritp error:\n{result.stderr}")
    else:
        os.rename(pdf_file + "_compressed", pdf_file)
        logging.info(f"PDF manual compressed to {pdf_file}")


def convert_md_to_pdf(output_md_file: str, pdf_file: str):
    pandoc_path = shutil.which("pandoc")
    if not pandoc_path:
        logging.warning("Pandoc not found. Skipping PDF generation. Please install pandoc.")
        return
    # Pre-process the Markdown file to fix problematic characters.
    fix_smart_quotes(output_md_file)
    logging.info("Converting Markdown to PDF using pandoc (xelatex)...")
    logging.info(output_md_file)

    result = subprocess.run(
        [pandoc_path, output_md_file, "-o", pdf_file,
          "--toc", "-V", "geometry:margin=0.5in",
         "--pdf-engine=xelatex", "--standalone"],
        capture_output=True, text=True
    )
    if result.returncode != 0:
        logging.error(f"Pandoc error:\n{result.stderr}")
    else:
        logging.info(f"PDF manual saved to {pdf_file}")

    compress_pdf(pdf_file)

def filter_unwanted_md(text: str) -> str:
    """
    Remove unwanted lines such as ESLint disable/enable comments,
    Version info, and Theme info.
    """
    patterns = [
        r"\/\* eslint-disable.*\*\/",
        r"\/\* eslint-enable.*\*\/",
        r"VersionVersion.*",
        r"Theme\s+.*",
        r"^\t.*",
        r"^	.*"
    ]
    for pat in patterns:
        text = re.sub(pat, "", text)
    # Remove multiple blank lines
    text = re.sub(r"\n\s*\n", "\n\n", text)
    text = "\n".join([line for line in text.split("\n") if not line.startswith("\t")])
    return text.strip()

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
        div_start = content.rfind(b'<div', 0, pos)
        div_end = content.find(b'</div>', pos)
        if div_start != -1 and div_end != -1:
            content = content[:div_start] + content[div_end+6:]
    return content

def element_to_md(elem, indent=0):
    """
    Recursively convert HTML elements to Markdown text.
    Any <div> element with class "pine-colorizer not-content" is processed as a code block.
    """
    if isinstance(elem, NavigableString):
        text = str(elem)
        # Skip pure whitespace (unless inside a pre block)
        if text.isspace():
            return text if elem.find_parent('pre') else ''
        return text
    md = ""
    name = elem.name
    classes = elem.get("class", [])
    # Check for the code example div and force code block formatting.
    if name == 'div' and "pine-colorizer" in classes and "not-content" in classes:
        code_text = elem.get_text().strip()
        md += "\n```\n" + code_text + "\n```\n\n"
        return md
    # Force code block for <pre> elements or code elements with newlines/long text.
    if name == 'pre' or ("code" in classes and "\n" in elem.get_text()):
        code_text = elem.get_text().rstrip('\n')
        md += "\n```\n" + code_text + "\n```\n\n"
        return md
    elif name == 'code':
        code_text = elem.get_text().strip()
        if "\n" in code_text or len(code_text) > 80:
            md += "\n```\n" + code_text + "\n```\n\n"
        else:
            md += "`" + code_text + "`"
        return md
    elif name in ['h1','h2','h3','h4','h5','h6']:
        level = int(name[1])
        md += "#" * level + " "
        md += "".join(element_to_md(child, indent) for child in elem.children).strip()
        md += "\n\n"
    elif name in ['p','div']:
        content = "".join(element_to_md(child, indent) for child in elem.children).strip()
        if content:
            md += content + "\n\n"
    elif name in ['ul','ol']:
        is_ol = (name == 'ol')
        num = 1
        for li in elem.find_all('li', recursive=False):
            prefix = f"{num}. " if is_ol else "- "
            inner = "".join(element_to_md(child, indent + len(prefix)) for child in li.children).strip()
            inner = inner.replace("\n", "\n" + " " * (indent + len(prefix)))
            md += " " * indent + prefix + inner + "\n"
            if is_ol:
                num += 1
        md += "\n"
    elif name == 'br':
        md += "  \n"
    elif name == 'a':
        href = elem.get('href', '')
        link_text = "".join(element_to_md(child, indent) for child in elem.children).strip() or ''
        if not href:
            md += link_text
        else:
            full_url = href if href.startswith('http') else BASE_URL + href
            if BASE_URL in full_url and '/pine-script-docs' in full_url:
                if '#' in href:
                    frag = href.split('#', 1)[1]
                    md += f"[{link_text}](#{frag})"
                else:
                    page_slug = href.rstrip('/').split('/')[-1] or href.rstrip('/').split('/')[-2]
                    md += f"[{link_text}](#{slugify(page_slug)})"
            else:
                md += f"[{link_text}]({full_url})"
    elif name in ['strong','b']:
        content = "".join(element_to_md(child, indent) for child in elem.children).strip()
        md += f"**{content}**"
    elif name in ['em','i']:
        content = "".join(element_to_md(child, indent) for child in elem.children).strip()
        md += f"*{content}*"
    elif name == 'img':
        alt_text = elem.get('alt', '')
        src = elem.get('src', '')
        if src:
            src_url = src if src.startswith('http') else BASE_URL + src
            md += f"![{alt_text}]({src_url})"
    else:
        md += "".join(element_to_md(child, indent) for child in elem.children)
    return md

def extract_html_to_markdown(html: bytes) -> str:
    """Extract main content from HTML and convert it to Markdown."""
    cleaned_html = clean_html_content(html)
    soup = BeautifulSoup(cleaned_html, 'lxml')
    # Remove leftover navigation, header, and footer elements
    for tag in soup.find_all(['nav', 'aside', 'header', 'footer']):
        tag.decompose()
    body = soup.body or soup
    markdown_text = "".join(element_to_md(child) for child in body.contents)
    return markdown_text.strip()

def process_webp_images_in_md(md_file: str, force=False):
    """
    Scan the Markdown file for .webp image references, convert each to PNG using Pillow,
    store them in an 'images' directory, and update the Markdown links accordingly.
    """
    import re
    os.makedirs("images", exist_ok=True)
    with open(md_file, 'r', encoding='utf-8') as f:
        content = f.read()
    # Regex pattern to match Markdown images: ![alt](url.webp)
    pattern = r'(!\[.*?\]\()([^)]+\.webp)(\))'
    matches = re.findall(pattern, content)
    for prefix, url, suffix in matches:
        logging.info(f"Processing image: {url}")
        # Determine a safe local filename from the URL.
        parsed = urlparse(url)
        base = os.path.basename(parsed.path)
        local_base = os.path.splitext(base)[0] + '.png'
        local_path = os.path.join("images", local_base)
        if not force and os.path.exists(local_path):
            logging.info("skipping existing file")
            content = content.replace(url, local_path)
            continue
        # If URL is remote, download it; if it's local, use it directly.
        if url.startswith("http"):
            try:
                resp = requests.get(url, stream=True, headers=HEADERS)
                resp.raise_for_status()
                temp_file = "temp_image.webp"
                with open(temp_file, "wb") as img_file:
                    for chunk in resp.iter_content(1024):
                        img_file.write(chunk)
            except Exception as e:
                logging.warning(f"Failed to download {url}: {e}")
                continue
            source_file = temp_file
        else:
            source_file = url
            if not os.path.exists(source_file):
                logging.warning(f"Local image {source_file} not found.")
                continue
        try:
            im = Image.open(source_file).convert("RGB")
            im.save(local_path, 'PNG')
            logging.info(f"Converted {url} to {local_path}")
            # Update the Markdown content: replace the .webp link with local_path
            content = content.replace(url, local_path)
        except Exception as e:
            logging.warning(f"Failed to convert image {url}: {e}")
        finally:
            if url.startswith("http") and os.path.exists("temp_image.webp"):
                os.remove("temp_image.webp")
    with open(md_file, 'w', encoding='utf-8') as f:
        f.write(content)

def main(generate_pdf=False, force=False):
    os.makedirs("html", exist_ok=True)
    logging.info(f"Fetching manual index page: {MANUAL_INDEX_URL}")
    resp = requests.get(MANUAL_INDEX_URL, headers=HEADERS)
    resp.raise_for_status()
    soup_index = BeautifulSoup(resp.content, 'lxml')
    chapter_links = soup_index.find_all('a', class_='page-link')
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
        safe_name = chapter_url.strip('/').replace('/', '_')
        if not safe_name.endswith('.html'):
            safe_name += '.html'
        filename = f"{idx:05d}_{safe_name}"
        file_path = os.path.join("html", filename)
        if force or not os.path.exists(file_path):
            logging.info(f"Downloading chapter: {full_url}")
            resp_ch = requests.get(full_url, headers=HEADERS)
            resp_ch.raise_for_status()
            with open(file_path, 'wb') as f:
                f.write(resp_ch.content)
        else:
            logging.info(f"Using cached HTML for {chapter_title}")
        with open(file_path, 'rb') as f:
            html_content = f.read()
        md_content = extract_html_to_markdown(html_content)
        combined_md_parts.append(md_content)
    toc_md = "# Table of Contents\n\n" + "\n".join(toc_lines) + "\n\n"
    full_md = toc_md + "\n\n".join(combined_md_parts)
    full_md = filter_unwanted_md(full_md)
    output_md_file = "PineScript_v6_Manual.md"
    with open(output_md_file, 'w', encoding='utf-8') as out:
        out.write(full_md)
    logging.info(f"Markdown manual saved to {output_md_file}")

    # Process .webp images in the Markdown file.
    process_webp_images_in_md(output_md_file, force)

    if generate_pdf:
        pdf_file = "PineScript_v6_Manual.pdf"
        convert_md_to_pdf(output_md_file, pdf_file)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Combine Pine Script v6 manual into a Markdown (and optional PDF).")
    parser.add_argument("--pdf", action="store_true", help="Also convert the Markdown output to PDF (requires pandoc).")
    parser.add_argument("--force", action="store_true", help="Overwrite existing files")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    main(generate_pdf=args.pdf, force=args.force)

