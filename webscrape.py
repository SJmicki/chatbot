import pandas as pd
import numpy as np
import requests
import re
from bs4 import BeautifulSoup

class WebScrape:
    def __init__(self, headers, ticker, filing_type, latest_nth_report):
        self.headers = headers
        self.ticker = ticker
        self.filing_type = filing_type
        self.latest_nth_report = latest_nth_report
        self.ticker_cik_dic = self.get_company_tickers()
        self.cik = self.ticker_cik_dic.get(self.ticker)
        self.url = None
        self.report_name = None
        self.filing_content = None

    def get_company_tickers(self):
        """Fetch all company tickers and their corresponding CIK numbers."""
        response = requests.get(
            "https://www.sec.gov/files/company_tickers.json",
            headers=self.headers
        )
        ticker_json = pd.DataFrame.from_dict(response.json(), orient='index')
        ticker_json['cik_str'] = ticker_json['cik_str'].astype(str).str.zfill(10)
        return dict(zip(ticker_json['ticker'], ticker_json['cik_str']))

    def get_filing_metadata(self):
        """Fetch filing metadata for the given CIK."""
        response = requests.get(
            f'https://data.sec.gov/submissions/CIK{self.cik}.json',
            headers=self.headers
        )
        return response.json()

    def get_target_forms(self):
        """Extract target forms from filing metadata."""
        filing_metadata = self.get_filing_metadata()
        recent_forms = pd.DataFrame.from_dict(
            filing_metadata['filings']['recent']
        )
        recent_forms['accessionNumber'] = recent_forms['accessionNumber'].str.replace("-", "")
        target_forms = recent_forms.loc[recent_forms.form == self.filing_type].reset_index(drop=True)
        target_forms.sort_values('reportDate', ascending=False, inplace=True)
        return target_forms

    def get_filing_url(self):
        """Construct URL for the specified filing report, handling out-of-bounds errors."""
        target_forms = self.get_target_forms()
        if self.latest_nth_report >= len(target_forms) or self.latest_nth_report < 0:
            raise IndexError("The requested report index is out of range.")
        
        accession_number = target_forms.loc[self.latest_nth_report, 'accessionNumber']
        document_suffix = target_forms.loc[self.latest_nth_report, 'primaryDocument']
        self.report_name = target_forms.loc[self.latest_nth_report,'reportDate'] + " " + target_forms.loc[self.latest_nth_report,'form']
        self.url = f'https://www.sec.gov/Archives/edgar/data/{self.cik}/{accession_number}/{document_suffix}' 
        return self.url

    def fetch_filing_content(self):
        """Fetch filing document content from the given URL and store it in the class."""
        self.get_filing_url()
        response = requests.get(self.url, headers=self.headers)
        response.raise_for_status()
        self.filing_content = response
        return self.filing_content

    def extract_table_sections_from_response(self, response):
        """Extract table sections from HTML response and remove them from the document unless they contain keywords."""
        soup = BeautifulSoup(response.content, "lxml")
        table_sections = []
        table_style_re = re.compile(r"margin-bottom\s*:\s*\d+pt", re.IGNORECASE)
        keyword_re = re.compile(r"Item\s*\d|Management’s Discussion and Analysis", re.IGNORECASE)
        
        all_tables = soup.find_all("table")
        for table in all_tables:
            if table_style_re.search(table.get("style", "")):
                # Check if the table contains key phrases in its spans
                if any(keyword_re.search(span.get_text()) for span in table.find_all("span")):
                    continue  # Skip removal if key phrase is found
                
                table_sections.append(table.decode_contents().strip())
                table.decompose()
        
        return soup, table_sections

    def find_last_div_containing_text(self, soup, text_pattern):
        """Find the last <div> element containing text matching the given pattern."""
        matching_divs = [div for div in soup.find_all("div", style=True)
                         if re.search(text_pattern, div.get_text(), re.IGNORECASE)]
        return matching_divs[-1] if matching_divs else None

    def extract_text_until_next_item(self, start_div, pattern):
        """Extract text from a starting div until the next item (stop pattern)."""
        if not start_div:
            return "Desired section not found."
        
        item_text = []
        current = start_div
        while current:
            item_text.append(current.get_text(strip=True))
            current = current.find_next_sibling("div")
            if current and re.search(pattern, current.get_text(), re.IGNORECASE):
                break
        
        return " ".join(item_text).strip().replace("\xa0", "")

    def retain_text_after_last_occurrence(self, text, pattern):
        """Retain only the text after the last occurrence of the specified pattern."""
        matches = list(re.finditer(pattern, text, re.IGNORECASE))
        if matches:
            return text[matches[-1].end()-5:].strip()
        return text

    def extract_mda_section(self):
        """Extract MD&A section from the given filing URL."""
        if not self.filing_content:
            self.fetch_filing_content()
        
        response = requests.get(self.get_filing_url(), headers=self.headers)
        response.raise_for_status()
        
        modified_soup, _ = self.extract_table_sections_from_response(response)
        
        if self.filing_type == '10-Q':
            current_item_pattern = r"Item\s*2[^\w]+Management.*?Discussion.*?and.*?Analysis"
            next_item_pattern = r"Item\s*3"
            last_item_pattern = r"Item\s*2"
        elif self.filing_type == '10-K':
            current_item_pattern = r"Item\s*7[^\w]+Management.*?Discussion.*?and.*?Analysis"
            next_item_pattern = r"Item\s*8"
            last_item_pattern = r"Item\s*7"
        else:
            return "Unsupported form type."
        
        last_item_div = self.find_last_div_containing_text(modified_soup, current_item_pattern)
        extracted_text = self.extract_text_until_next_item(last_item_div, next_item_pattern)
        final_text = self.retain_text_after_last_occurrence(extracted_text, last_item_pattern)
        
        return final_text
