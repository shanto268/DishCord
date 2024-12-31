"""
This script does the following:

1) Scroll a Pinterest board to gather pin links.
2) For each pin link, extract the external "source" site URL and then scrape
   that site for recipe data (title, image, ingredients, etc.).

Finally, it saves all results to a JSON file named 'recipes.json'.

Dependencies:
  - selenium
  - concurrent.futures (standard library)
  - python-dotenv (optional, if you use .env for credentials)
  - A matching ChromeDriver for your local Chrome version

Usage:
  python pinterest_scraper.py --board_url <your_pinterest_board>
    [--scroll_count 50]
    [--output_file recipes.json]
    [--driver_path /path/to/chromedriver]
    [--workers 5]
    [--pinterest_email <email> --pinterest_password <pw>]  (optional)

Example:
  python pinterest_scraper.py --board_url https://www.pinterest.com/madihowa/foods/ \
                              --scroll_count 300 \
                              --workers 5

"""

import argparse
import json
import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Dict, List, Optional

# Optional if you store credentials in .env
try:
    from dotenv import load_dotenv
    load_dotenv("../.env")
except ImportError:
    pass

# Selenium
from selenium import webdriver
from selenium.common.exceptions import (NoSuchElementException,
                                        TimeoutException, WebDriverException)
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.wait import WebDriverWait


class PinterestScraper:
    """
    Handles:
      1) Gathering pin links from a specified Pinterest board.
      2) For each pin, extracting the external site and scraping
         the final recipe data.
    """

    def __init__(
        self,
        driver_path: str,
        pinterest_email: Optional[str] = None,
        pinterest_password: Optional[str] = None,
        headless: bool = True
    ):
        """
        :param driver_path: Path to your ChromeDriver executable
        :param pinterest_email: (optional) Email for Pinterest login
        :param pinterest_password: (optional) Password for Pinterest login
        :param headless: Whether to run Chrome in headless mode
        """
        self.driver_path = driver_path
        self.pinterest_email = pinterest_email
        self.pinterest_password = pinterest_password
        self.headless = headless

    def _build_driver(self) -> webdriver.Chrome:
        """Creates and returns a Selenium WebDriver (Chrome) instance."""
        options = Options()
        if self.headless:
            options.add_argument("--headless")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")

        service = Service(self.driver_path)
        return webdriver.Chrome(service=service, options=options)

    def fetch_board_pin_links(
        self,
        board_url: str,
        scroll_count: int = 50,
        max_wait_iterations: int = 10
    ) -> List[str]:
        """
        Scrolls through a Pinterest board to gather pin links.
        Returns a list of unique pin URLs.
        """
        driver = self._build_driver()
        driver.get(board_url)
        time.sleep(5)  # Let the page load

        total_links = set()
        wait_iterations = 0

        for i in range(scroll_count):
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(2)  # Give time for new pins to load

            # Extract links with '/pin/' in them
            anchors = driver.find_elements(By.TAG_NAME, "a")
            links = [a.get_attribute('href') for a in anchors if '/pin/' in (a.get_attribute('href') or '')]

            new_links = set(links) - total_links
            if new_links:
                total_links.update(new_links)
                wait_iterations = 0
            else:
                wait_iterations += 1
                if wait_iterations >= max_wait_iterations:
                    print("[INFO] No new pins found in several iterations. Stopping scroll.")
                    break

        print(f"[INFO] Total pin links collected: {len(total_links)}")
        driver.quit()

        return list(total_links)

    def _login_if_needed(self, driver: webdriver.Chrome):
        """
        If credentials are provided, attempts to log into Pinterest.
        This might help if the board or pins require login to see fully.
        """
        if not self.pinterest_email or not self.pinterest_password:
            return

        # Example logic; adapt to your specific login flow
        try:
            WebDriverWait(driver, 8).until(EC.presence_of_element_located((By.ID, "email")))
            driver.find_element(By.ID, "email").send_keys(self.pinterest_email)
            driver.find_element(By.ID, "password").send_keys(self.pinterest_password)
            driver.find_element(By.XPATH, "//button[@type='submit']").click()
            time.sleep(5)
        except TimeoutException:
            pass

    def _extract_source_url(self, pin_url: str) -> Optional[str]:
        """
        For a given Pinterest pin URL, returns the external "source" site URL if found.
        """
        driver = self._build_driver()
        source_link = None
        try:
            driver.get(pin_url)
            time.sleep(3)
            self._login_if_needed(driver)

            # Dismiss any popups
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
                    source_link = candidate
            except NoSuchElementException:
                pass

            # 2) If not found, sometimes there's a "Visit" link or button
            if not source_link:
                try:
                    visit_btn = driver.find_element(By.XPATH, "//a[contains(text(),'Visit')]")
                    candidate = visit_btn.get_attribute("href") or ""
                    if candidate.startswith("http"):
                        source_link = candidate
                except NoSuchElementException:
                    pass

        except WebDriverException as e:
            print(f"[ERROR] WebDriver error on pin {pin_url} -> {e}")
        finally:
            driver.quit()

        return source_link

    def _scrape_recipe_site(
        self, site_url: str
    ) -> Dict[str, object]:
        """
        Navigates to the real recipe website, attempts to extract
        a 'title', 'image_url', and 'ingredients'. 
        """
        driver = self._build_driver()
        data = {
            "title": None,
            "image_url": None,
            "ingredients": None,
            "extra": {}
        }

        try:
            driver.get(site_url)
            WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.TAG_NAME, "body")))
            time.sleep(2)

            # 1) <title>
            try:
                title = driver.find_element(By.CSS_SELECTOR, 'meta[property="og:title"]').get_attribute('content')
                title_elem = driver.find_element(By.TAG_NAME, "title")
                data["title"] = title
            except NoSuchElementException:
                pass

            # 2) <meta property='og:image'>
            try:
                meta_img = driver.find_element(By.CSS_SELECTOR, "meta[property='og:image']")
                candidate = meta_img.get_attribute("content") or ""
                if candidate.startswith("http"):
                    data["image_url"] = candidate
            except NoSuchElementException:
                pass

            # 3) JSON-LD parsing for ingredients
            try:
                ld_json_elems = driver.find_elements(By.XPATH, "//script[@type='application/ld+json']")
                for elem in ld_json_elems:
                    import json as pyjson
                    raw_text = elem.get_attribute("textContent")
                    try:
                        ld_obj = pyjson.loads(raw_text)
                        if isinstance(ld_obj, list):
                            for obj in ld_obj:
                                if "recipeIngredient" in obj:
                                    data["ingredients"] = obj["recipeIngredient"]
                                    break
                        elif isinstance(ld_obj, dict):
                            if "recipeIngredient" in ld_obj:
                                data["ingredients"] = ld_obj["recipeIngredient"]
                    except Exception:
                        pass

                # Fallback approach: <li class='ingredient'> if still None
                if not data["ingredients"]:
                    potential_lis = driver.find_elements(By.CSS_SELECTOR, "li.ingredient")
                    if potential_lis:
                        data["ingredients"] = [li.text.strip() for li in potential_lis if li.text.strip()]

            except NoSuchElementException:
                pass

        except WebDriverException as e:
            print(f"[ERROR] WebDriver error on site {site_url} -> {e}")
        finally:
            driver.quit()

        return data

    def process_pin(self, pin_url: str) -> Dict[str, object]:
        """
        End-to-end flow for a single Pinterest pin:
          1) Extract source URL
          2) Scrape the source site for recipe data
        Returns a dict with 'pinterest_url', 'source_url', and 'recipe_data'.
        """
        data_out = {
            "pinterest_url": pin_url,
            "source_url": None,
            "recipe_data": None
        }

        src_link = self._extract_source_url(pin_url)
        if src_link:
            data_out["source_url"] = src_link
            # Now scrape the final recipe site
            recipe_data = self._scrape_recipe_site(src_link)
            data_out["recipe_data"] = recipe_data
        else:
            data_out["recipe_data"] = {
                "error": "No external source URL found from Pinterest"
            }

        return data_out

    def scrape_board(
        self,
        board_url: str,
        output_file: str = "recipes.json",
        scroll_count: int = 50,
        max_wait_iterations: int = 10,
        workers: int = 5
    ):
        """
        1) Collects pin URLs from the given board.
        2) For each pin, in parallel, scrapes the recipe data.
        3) Saves the results to `output_file` (JSON).
        """
        # Step 1) Gather pin links
        pin_links = self.fetch_board_pin_links(
            board_url=board_url,
            scroll_count=scroll_count,
            max_wait_iterations=max_wait_iterations
        )

        results = []

        # Step 2) Parallel process each pin
        with ThreadPoolExecutor(max_workers=workers) as executor:
            future_map = {
                executor.submit(self.process_pin, pin): pin for pin in pin_links
            }

            for future in as_completed(future_map):
                pin = future_map[future]
                try:
                    res = future.result()
                    results.append(res)
                except Exception as ex:
                    print(f"[ERROR] Exception scraping pin {pin} -> {ex}")
                    results.append({
                        "pinterest_url": pin,
                        "source_url": None,
                        "recipe_data": {"error": str(ex)},
                    })

        # Step 3) Save all data to output_file
        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(results, f, indent=2, ensure_ascii=False)
        print(f"[INFO] Done! Collected {len(results)} results. See '{output_file}'.")


def main():

    pinterest_email = os.getenv("PINTEREST_EMAIL")
    pinterest_password = os.getenv("PINTEREST_PASSWORD")

    parser = argparse.ArgumentParser(description="Scrape a Pinterest board and extract recipes.")
    parser.add_argument("--board_url", required=True, help="URL of the Pinterest board")
    parser.add_argument("--driver_path", default="/usr/local/bin/chromedriver", help="Path to ChromeDriver")
    parser.add_argument("--scroll_count", type=int, default=50, help="Number of scroll iterations on the board")
    parser.add_argument("--max_wait_iterations", type=int, default=10, help="Max consecutive scrolls with no new pins before stopping")
    parser.add_argument("--output_file", default="recipes_test.json", help="Output JSON file for the final data")
    parser.add_argument("--workers", type=int, default=5, help="Number of parallel threads for processing pins")
    parser.add_argument("--no-headless", dest="headless", action="store_false", help="If set, runs Chrome in visible mode instead of headless")



    args = parser.parse_args()

    scraper = PinterestScraper(
        driver_path=args.driver_path,
        pinterest_email=pinterest_email,
        pinterest_password=pinterest_password,
        headless=args.headless
    )

    scraper.scrape_board(
        board_url=args.board_url,
        output_file=args.output_file,
        scroll_count=args.scroll_count,
        max_wait_iterations=args.max_wait_iterations,
        workers=args.workers
    )


if __name__ == "__main__":
    main()