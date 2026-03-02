import time
import random
import urllib.parse
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.chrome.service import Service
from .base import BaseScraper

class LinkedInScraper(BaseScraper):
    def search(self, query: str, location: str):
        print(f"[LinkedIn] Searching for '{query}' in '{location}'...")
        
        base_url = "https://www.linkedin.com/jobs/search"
        encoded_query = urllib.parse.quote(query)
        encoded_location = urllib.parse.quote(location)
        current_job_id = random.randint(3000000000, 4000000000)
        
        # Construct URL similar to manual search. f_E=1 specifically filters for Internship experience level. f_TPR=r604800 filters for past week. sortBy=DD sorts by most recent.
        url = f"{base_url}?keywords={encoded_query}&location={encoded_location}&f_TPR=r604800&f_E=1&sortBy=DD"
        
        self._scrape_url(url)

    def _get_chrome_options(self):
        options = Options()
        options.add_argument("--headless=new") 
        options.add_argument("--disable-gpu")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--disable-extensions")
        options.add_argument("--blink-settings=imagesEnabled=false")
        options.add_argument("--window-size=1200,800")
        options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
        options.page_load_strategy = 'eager'
        return options

    def _scrape_url(self, url: str):
        
        try:
            service = Service(ChromeDriverManager().install())
            driver = webdriver.Chrome(service=service, options=self._get_chrome_options())
        except Exception as e:
            print(f"Error initiating Chrome: {e}")
            return

        try:
            print(f"[LinkedIn] Navigating to {url}")
            driver.get(url)
            time.sleep(random.uniform(3, 6))
            
            # Simple scroll
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight/2);")
            time.sleep(1)
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(2)
            
            # Find job cards
            # Find job cards - try multiple selectors
            selectors = [
                 (By.CLASS_NAME, "base-search-card"),
                 (By.CLASS_NAME, "job-search-card"),
                 (By.XPATH, "//ul[@class='jobs-search__results-list']/li")
            ]
            
            job_cards = []
            for by, val in selectors:
                found = driver.find_elements(by, val)
                if found:
                    job_cards = found
                    break
            
            print(f"[LinkedIn] Found {len(job_cards)} potential jobs.")
            
            for card in job_cards[:15]: 
                try:
                    # Title
                    try:
                        title_elem = card.find_element(By.CLASS_NAME, "base-search-card__title")
                        title = title_elem.get_attribute("innerText").strip()
                    except:
                        try:
                            title = card.find_element(By.TAG_NAME, "h3").get_attribute("innerText").strip()
                        except:
                            title = ""
                        
                    # Company
                    try:
                        company_elem = card.find_element(By.CLASS_NAME, "base-search-card__subtitle")
                        company = company_elem.get_attribute("innerText").strip()
                    except:
                        try:
                            company = card.find_element(By.TAG_NAME, "h4").get_attribute("innerText").strip()
                        except:
                            company = ""
                        
                    # Link
                    try:
                        link_elem = card.find_element(By.CLASS_NAME, "base-card__full-link")
                    except:
                        link_elem = card.find_element(By.TAG_NAME, "a")
                        
                    link = link_elem.get_attribute("href").split('?')[0]

                    # Location
                    location = "Unknown"
                    loc_selectors = [
                        (By.CLASS_NAME, "job-search-card__location"),
                        (By.CLASS_NAME, "base-search-card__metadata"),
                        (By.XPATH, ".//span[contains(@class, 'location')]")
                    ]
                    for b, v in loc_selectors:
                        try:
                            loc_elem = card.find_element(b, v)
                            location = loc_elem.get_attribute("innerText").strip()
                            if location: break
                        except:
                            continue

                    if not title or not company:
                        continue

                    self.results.append({
                        "source": "LinkedIn",
                        "title": title,
                        "company": company,
                        "location": location,
                        "link": link,
                        "status": "new"
                    })
                    print(f"  -> Found: {title} at {company}")
                except Exception as e:
                    continue
                    
        except Exception as e:
            print(f"[LinkedIn] Error during scraping: {e}")
        finally:
            driver.quit()

    def get_job_description(self, url: str) -> str:
        """Navigates to the job URL and scrapes the full job description text."""
        try:
            service = Service(ChromeDriverManager().install())
            driver = webdriver.Chrome(service=service, options=self._get_chrome_options())
            try:
                driver.get(url)
                time.sleep(random.uniform(2, 4))
                
                # Multiple potential classes for the description block on public LinkedIn job pages
                selectors = [
                     (By.CLASS_NAME, "show-more-less-html__markup"),
                     (By.CLASS_NAME, "description__text"),
                     (By.CLASS_NAME, "core-section-container__content")
                ]
                
                text = ""
                for by, val in selectors:
                    try:
                        elem = driver.find_element(by, val)
                        text = elem.get_attribute("innerText").strip()
                        if text:
                            break
                    except:
                        continue
                        
                return text
            finally:
                try:
                    driver.quit()
                except:
                    pass
        except Exception as e:
            print(f"[LinkedIn] Error fetching job description for {url}: {e}")
            return ""


