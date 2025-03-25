# Scrape the pinescript v6 user manual

This repo contiains the state of the tradingview pinescript doc webpage
from march 2025. To update it modify the script accordingly and run it.

PDF creation requires pandoc
```
$ python scrape_v6.py
$ python scrape_v6.py --pdf

```

I am providing the md and pdf version of the documentation as fair use.
The script is based on:

    https://github.com/shanedemorais/pinescript_v5_user_manual_pdfs

with the state of that version saved in v5.
