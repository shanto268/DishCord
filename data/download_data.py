import time

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By


class PinterestLinkDownloader:
    def __init__(self, driver_path):
        self.driver_path = driver_path

    def setup_driver(self):
        # Configure Chrome options
        options = Options()
        options.add_argument("--headless")  # Run Chrome in headless mode
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")

        # Specify the path to the compatible ChromeDriver
        service = Service(self.driver_path)
        driver = webdriver.Chrome(service=service, options=options)
        return driver

    def fetch_links(self, board_url, output_file, scroll_count=50, max_wait_iterations=10):
        driver = self.setup_driver()
        driver.get(board_url)
        time.sleep(5)  # Allow time for the page to load

        total_links = set()
        wait_iterations = 0  # Count iterations with no new links

        with open(output_file, "w") as f:
            for i in range(scroll_count):
                driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                time.sleep(2)  # Pause for new content to load

                # Extract links to individual pins
                links = [a.get_attribute('href') for a in driver.find_elements(By.TAG_NAME, 'a') if '/pin/' in a.get_attribute('href')]

                # Filter out new links
                new_links = set(links) - total_links
                if new_links:
                    total_links.update(new_links)

                    # Write new links to file incrementally
                    for link in new_links:
                        f.write(link + "\n")
                        print(f"Saved: {link}", flush=True)

                    wait_iterations = 0  # Reset wait iterations if new links are found
                else:
                    wait_iterations += 1

                # Stop if no new links for `max_wait_iterations`
                if wait_iterations >= max_wait_iterations:
                    print("No new links found. Stopping scrolling.")
                    break

            print(f"Total pins collected: {len(total_links)}", flush=True)
        driver.quit()

    def save_links_to_file(self, links, output_file):
        with open(output_file, "w") as f:
            f.write("\n".join(links))
        print(f"Saved {len(links)} links to {output_file}")

if __name__ == "__main__":
    # Path to the ChromeDriver executable
    chromedriver_path = "/usr/local/bin/chromedriver-mac-arm64/chromedriver"

    # Pinterest board URL
    board_url = "https://www.pinterest.com/madihowa/foods/"

    # Output file for links
    output_file = "recipe_links.txt"

    downloader = PinterestLinkDownloader(driver_path=chromedriver_path)
    downloader.fetch_links(board_url=board_url, output_file=output_file, scroll_count=300, max_wait_iterations=10)