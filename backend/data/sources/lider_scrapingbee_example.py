"""
Example: Lider ScrapingBee Connector
=====================================
A reference implementation for bypassing PerimeterX in Lider.cl 
using the ScrapingBee API (https://www.scrapingbee.com/).

ScrapingBee handles:
- Proxy rotation (residential/mobile)
- Headless browser execution
- PerimeterX challenge resolution

To use this, you would:
1. Sign up for ScrapingBee and get an API key.
2. Replace 'YOUR_API_KEY' below.
3. Integrate this logic back into lider_scraper.py.
"""

import requests
import json
import os

SCRAPINGBEE_API_KEY = os.environ.get("SCRAPINGBEE_API_KEY", "") # safe

def scrape_lider_with_scrapingbee(query, page=1):
    """
    Scrapes Lider search results via ScrapingBee.
    """
    target_url = f"https://www.lider.cl/supermercado/search?query={query}&page={page}"
    
    # ScrapingBee parameters:
    # - premium_proxy=True: Uses residential IPs (harder to block).
    # - render_js=True: Executes JavaScript to solve PX.
    # - wait_for=5000: Wait for hydration.
    params = {
        'api_key': SCRAPINGBEE_API_KEY,
        'url': target_url,
        'render_js': 'true',
        'premium_proxy': 'true',
        'wait_for': '5000', # Wait 5s for the page to hydrate
        'block_ads': 'true'
    }
    
    print(f"  [ScrapingBee] Requesting: {target_url}")
    response = requests.get('https://app.scrapingbee.com/api/v1', params=params)
    
    if response.status_code == 200:
        # Now we parse the HTML directly as PerimeterX was solved by the proxy.
        # Alternatively, we could intercept the __NEXT_DATA__ from the body.
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(response.text, 'html.parser')
        
        script = soup.find("script", id="__NEXT_DATA__")
        if script:
            data = json.loads(script.string)
            print("  [ScrapingBee] Successfully extracted NEXT_DATA!")
            return data
        else:
            print("  [ScrapingBee] NEXT_DATA tag missing in response.")
            return None
    else:
        print(f"  [ScrapingBee ERROR] Status: {response.status_code}")
        print(response.text)
        return None

if __name__ == "__main__":
    # Test run
    # Note: This will only work if you have a valid API Key.
    res = scrape_lider_with_scrapingbee("leche")
    if res:
        print("Scrape successful! Data received.")
