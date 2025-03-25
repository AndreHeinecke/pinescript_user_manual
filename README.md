# Scrape the pinescript v6 user manual

This repo contiains the state of the tradingview pinescript doc webpage
from march 2025. To update it modify the script accordingly and run it.

scraper\_v6.py - Downloads the TradingView Pine Script v6 User Manual
and combines it into a single Markdown file.
Usage:
    python scraper\_v6.py [--pdf]

- Downloads all chapters of the Pine Script v6 manual as HTML (cached in a "html/" directory).
- Extracts and concatenates the content into one Markdown file (preserving headers, code blocks, etc.).
- Generates a table of contents with links to each chapter section in the Markdown.
- If the --pdf flag is provided, converts the Markdown file to PDF.
- Before PDF conversion, scans the Markdown for .webp image references, converts them to PNG,
  and updates the Markdown links to point to the local images.

Requirements for PDF conversion:
    - Pandoc must be installed and available in the system PATH
      (https://pandoc.org).
    - Pillow is required for image conversion: pip install Pillow.¸

# Example

```
sudo apt-get install pandoc || zypper in pandoc || \
    echo "Install pandoc yourself you lazy bastard! :p"

python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

python scrape_v6.py
python scrape_v6.py --pdf

```

I am providing the md and pdf version of the documentation as fair use.
The script is based on:

    https://github.com/shanedemorais/pinescript_v5_user_manual_pdfs

with the state of that version saved in v5.
