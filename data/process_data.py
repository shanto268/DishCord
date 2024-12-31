"""
scrape_data_alternative.py

Demonstrates the "Alternative Approach":
    1) Reads a list of Pinterest pins from test_links.txt
    2) For each pin, uses Selenium to open the pin page, then extracts:
        - The external site URL (using <meta property="og:url"> or a "Visit" link)
    3) Navigates to the external site (still with Selenium), attempts to scrape
       the real recipe data (title, image, ingredients, etc.).
    4) Runs these operations in parallel using concurrent.futures
    5) Saves all results to test_data.json.

Requires:
    - python-dotenv
    - selenium
    - concurrent.futures (part of standard library in Python 3)
    - A chromedriver that matches your installed Chrome version
      (and modify CHROMEDRIVER_PATH accordingly)
"""

import json
import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Dict, List, Optional

# For environment variables
from dotenv import load_dotenv
# Selenium imports
from selenium import webdriver
from selenium.common.exceptions import (NoSuchElementException,
                                        TimeoutException, WebDriverException)
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait


def get_pinterest_source_url(
    pinterest_url: str,
    driver_path: str,
    pinterest_email: Optional[str] = None,
    pinterest_password: Optional[str] = None
) -> Optional[str]:
    """
    Given a Pinterest Pin URL, use Selenium to find the external "source" site URL.
    This typically comes from <meta property='og:url'> or a "Visit" link on the page.

    :param pinterest_url: The direct URL to the Pinterest Pin (e.g. https://www.pinterest.com/pin/...)
    :param driver_path: Path to your ChromeDriver
    :param pinterest_email: If you need to log in, pass the email here
    :param pinterest_password: If you need to log in, pass the password here
    :return: The external site URL if found, else None
    """
    options = Options()
    options.add_argument("--headless")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")

    service = Service(driver_path)
    driver = webdriver.Chrome(service=service, options=options)

    external_url = None

    try:
        driver.get(pinterest_url)
        time.sleep(3)

        # (Optional) Log in if credentials are provided
        if pinterest_email and pinterest_password:
            try:
                WebDriverWait(driver, 8).until(
                    EC.presence_of_element_located((By.ID, "email"))
                )
                driver.find_element(By.ID, "email").send_keys(pinterest_email)
                driver.find_element(By.ID, "password").send_keys(pinterest_password)
                driver.find_element(By.XPATH, "//button[@type='submit']").click()
                time.sleep(5)
            except TimeoutException:
                pass

        # Dismiss any popups if present
        try:
            accept_btn = driver.find_element(By.XPATH, "//button[contains(text(),'Accept')]")
            accept_btn.click()
            time.sleep(1)
        except NoSuchElementException:
            pass

        # 1) Try <meta property='og:url'>
        try:
            og_url_elem = driver.find_element(By.CSS_SELECTOR, "meta[property='og:url']")
            candidate = og_url_elem.get_attribute("content") or ""
            if candidate.startswith("http"):
                external_url = candidate
        except NoSuchElementException:
            pass

        # 2) If not found, sometimes there's a "Visit" link or button
        #    that navigates externally. We'll try to find it and extract the href:
        if not external_url:
            try:
                visit_link = driver.find_element(By.XPATH, "//a[contains(text(),'Visit')]")
                candidate = visit_link.get_attribute("href") or ""
                if candidate.startswith("http"):
                    external_url = candidate
            except NoSuchElementException:
                pass

    except WebDriverException as e:
        print(f"[ERROR] WebDriver error while fetching Pinterest pin {pinterest_url} -> {str(e)}")

    finally:
        driver.quit()

    return external_url


def scrape_recipe_from_site(
    site_url: str,
    driver_path: str
) -> Dict[str, object]:
    """
    Navigate to the real recipe website and attempt to extract
    some relevant data: 'title', 'image_url', 'ingredients', etc.

    In a real scenario, you would tailor this function to parse the specific
    recipe markup (JSON-LD, microdata, or custom HTML tags).

    :param site_url: The external link to the original recipe site
    :param driver_path: Path to ChromeDriver
    :return: A dictionary with keys:
        - 'title'
        - 'image_url'
        - 'ingredients'
        - 'extra' (any other data or notes)
    """

    options = Options()
    options.add_argument("--headless")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")

    service = Service(driver_path)
    driver = webdriver.Chrome(service=service, options=options)

    result_data = {
        "title": None,
        "image_url": None,
        "ingredients": None,
        "extra": {}
    }

    try:
        driver.get(site_url)
        WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.TAG_NAME, "body")))
        time.sleep(2)

        # Example: Just get the <title> as the recipe title
        try:
            title_elem = driver.find_element(By.TAG_NAME, "title")
            result_data["title"] = title_elem.text.strip()
        except NoSuchElementException:
            pass

        # Example: Try to find <meta property="og:image"> for image
        try:
            meta_img = driver.find_element(By.CSS_SELECTOR, "meta[property='og:image']")
            image_candidate = meta_img.get_attribute("content") or ""
            if image_candidate.startswith("http"):
                result_data["image_url"] = image_candidate
        except NoSuchElementException:
            pass

        # Example: Attempt to find <script type='application/ld+json'> to parse JSON-LD
        # This is how many recipe sites store structured data with "recipeIngredient"
        # If found, parse it and extract ingredients. This won't work on all sites, but it's a common pattern.
        try:
            ld_json_elems = driver.find_elements(By.XPATH, "//script[@type='application/ld+json']")
            for elem in ld_json_elems:
                json_text = elem.get_attribute("textContent")
                # Some sites embed multiple JSON-LD objects in an array
                # We'll do a naive parse and see if we find "recipeIngredient"
                import json as pyjson
                try:
                    ld_obj = pyjson.loads(json_text)
                    # If it's a list, iterate
                    if isinstance(ld_obj, list):
                        for obj in ld_obj:
                            if "recipeIngredient" in obj:
                                result_data["ingredients"] = obj["recipeIngredient"]
                                break
                    elif isinstance(ld_obj, dict):
                        if "recipeIngredient" in ld_obj:
                            result_data["ingredients"] = ld_obj["recipeIngredient"]
                except Exception:
                    pass

            # If we still have no ingredients from JSON-LD, try a fallback approach:
            if not result_data["ingredients"]:
                # Possibly parse <li> elements inside a known class .ingredient
                potential_lis = driver.find_elements(By.CSS_SELECTOR, "li.ingredient")
                if potential_lis:
                    result_data["ingredients"] = [li.text.strip() for li in potential_lis if li.text.strip()]

        except NoSuchElementException:
            pass

    except WebDriverException as e:
        print(f"[ERROR] WebDriver error while fetching site {site_url} -> {str(e)}")

    finally:
        driver.quit()

    return result_data


def process_pinterest_link(
    pinterest_url: str,
    driver_path: str,
    pinterest_email: Optional[str],
    pinterest_password: Optional[str]
) -> Dict[str, object]:
    """
    Orchestrates the entire "alternative approach" for a single link:
      1) Get the external source URL from Pinterest
      2) Scrape the source site for actual recipe data
      3) Return a dictionary with everything

    :param pinterest_url: The direct Pinterest pin link
    :param driver_path: Path to ChromeDriver
    :param pinterest_email: Pinterest login email
    :param pinterest_password: Pinterest login password
    :return: dict containing the final data structure
    """
    data_out = {
        "pinterest_url": pinterest_url,
        "source_url": None,
        "recipe_data": None
    }

    # 1) Get external site
    source_url = get_pinterest_source_url(
        pinterest_url=pinterest_url,
        driver_path=driver_path,
        pinterest_email=pinterest_email,
        pinterest_password=pinterest_password
    )

    if source_url:
        data_out["source_url"] = source_url
        # 2) Scrape the source site
        recipe_info = scrape_recipe_from_site(
            site_url=source_url,
            driver_path=driver_path
        )
        data_out["recipe_data"] = recipe_info
    else:
        # If no external site found, we store None or a message
        data_out["recipe_data"] = {
            "error": "No external source URL found from Pinterest"
        }

    return data_out


def main(file="recipe_links.txt"):
    """
    Main entry point:
      - Loads .env for credentials
      - Reads test_links.txt
      - Parallelizes the scraping of each link
      - Saves results in test_data.json
    """
    # 1) Load environment variables
    load_dotenv("../.env")
    pinterest_email = os.getenv("PINTEREST_EMAIL")
    pinterest_password = os.getenv("PINTEREST_PASSWORD")

    # 2) Read all Pinterest URLs from test_links.txt
    with open(file, "r", encoding="utf-8") as f:
        pinterest_links = [line.strip() for line in f if line.strip()]

    # 3) Path to your local ChromeDriver
    CHROMEDRIVER_PATH = "/usr/local/bin/chromedriver-mac-arm64/chromedriver"

    # 4) Parallel execution
    results = []
    with ThreadPoolExecutor(max_workers=5) as executor:
        # Create a future for each link
        future_map = {
            executor.submit(
                process_pinterest_link,
                link,
                CHROMEDRIVER_PATH,
                pinterest_email,
                pinterest_password
            ): link
            for link in pinterest_links
        }

        # As each future completes, gather the results
        for future in as_completed(future_map):
            link = future_map[future]
            try:
                res = future.result()
                results.append(res)
            except Exception as ex:
                print(f"[ERROR] Exception scraping {link} -> {str(ex)}")
                # Store an error object in results for that link
                results.append({
                    "pinterest_url": link,
                    "source_url": None,
                    "recipe_data": {"error": str(ex)},
                })

    # 5) Save all results into test_data.json
    with open("recipes.json", "w", encoding="utf-8") as outf:
        json.dump(results, outf, indent=2, ensure_ascii=False)

    print(f"Done! Collected {len(results)} results. See 'recipes.json'.")


if __name__ == "__main__":
    main()