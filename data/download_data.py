import json
import os
import time

import requests
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from tqdm import tqdm


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

class PinterestImageDownloader:
    def __init__(self, output_dir):
        self.output_dir = output_dir
        os.makedirs(self.output_dir, exist_ok=True)

    @staticmethod
    def download_image(url, output_path):
        """
        Downloads an image from a given URL and saves it to the specified path.
        """
        try:
            response = requests.get(url, stream=True)
            if response.status_code == 200:
                with open(output_path, "wb") as f:
                    for chunk in response.iter_content(1024):
                        f.write(chunk)
                return True
            else:
                print(f"Failed to download {url}. Status code: {response.status_code}")
                return False
        except Exception as e:
            print(f"Error downloading image {url}: {e}")
            return False

    def download_images(self, links_file, json_file):
        """
        Downloads images from Pinterest links in `links_file`, saves them to `output_dir`,
        and writes metadata (including dates) to `json_file`.
        """
        if not os.path.exists(links_file):
            print(f"Links file {links_file} does not exist.")
            return

        # Load links from the file
        with open(links_file, "r") as f:
            links = [line.strip() for line in f if line.strip()]

        metadata = []

        # Iterate through links and download images
        for i, link in enumerate(tqdm(links, desc="Downloading images")):
            try:
                response = requests.get(link)
                if response.status_code != 200:
                    print(f"Failed to fetch page: {link}")
                    continue

                # Extract image URL (assuming Pinterest uses <meta property="og:image"> for images)
                soup = BeautifulSoup(response.text, "html.parser")

                # Extract image URL
                image_url = None
                meta_tag = soup.find("meta", property="og:image")
                if meta_tag and meta_tag.get("content"):
                    image_url = meta_tag["content"]

                # Fallback to finding <img> tags
                if not image_url:
                    img_tag = soup.find("img", class_="GrowthUnauthPinImage__Image")
                    if img_tag and img_tag.get("src"):
                        image_url = img_tag["src"]

                if not image_url:
                    print(f"No image found at {link}")
                    continue

                # Extract pin date (if available)
                date_added = None
                time_tag = soup.find("meta", property="og:updated_time")
                if time_tag and time_tag.get("content"):
                    date_added = time_tag["content"]

                # Alternative methods to find the date (depending on Pinterest's structure changes)
                if not date_added:
                    date_tag = soup.find("meta", property="og:created_time")
                    if date_tag and date_tag.get("content"):
                        date_added = date_tag["content"]

                if not date_added:
                    print(f"No date information found for {link}")

                # Define the output file path
                image_filename = f"image_{i + 1}.jpg"
                image_path = os.path.join(self.output_dir, image_filename)

                # Download the image
                if self.download_image(image_url, image_path):
                    metadata.append({
                        "link": link,
                        "image_path": image_path,
                        "date_added": date_added
                    })

            except Exception as e:
                print(f"Error processing link {link}: {e}")

        # Save metadata to JSON
        with open(json_file, "w") as f:
            json.dump(metadata, f, indent=4)
        print(f"Downloaded {len(metadata)} images and saved metadata to {json_file}")


if __name__ == "__main__":
    # Path to the ChromeDriver executable
    chromedriver_path = "/usr/local/bin/chromedriver-mac-arm64/chromedriver"

    # Pinterest board URL
    board_url = "https://www.pinterest.com/madihowa/foods/"

    # Output file for links
    output_file = "recipe_links.txt"

    downloader = PinterestLinkDownloader(driver_path=chromedriver_path)
    downloader.fetch_links(board_url=board_url, output_file=output_file, scroll_count=300, max_wait_iterations=10)

    """
    # Path to the ChromeDriver executable
    chromedriver_path = "/usr/local/bin/chromedriver-mac-arm64/chromedriver"

    # Pinterest board URL
    board_url = "https://www.pinterest.com/madihowa/clothes/"
    download_folder="/Users/shanto/Programming/DishCord/data/outfits"
    JSON_OUTPUT_FILE = "image_mappings.json"

    # Initialize classes
    link_downloader = PinterestLinkDownloader(driver_path=chromedriver_path)
    image_downloader = PinterestImageDownloader(output_dir=download_folder)

    # Fetch links from a Pinterest board
    output_links_file = "../data/outfits_links.txt"
    link_downloader.fetch_links(board_url, output_links_file)

    # Download images and save metadata
    output_json_file = "../data/outfits.json"
    image_downloader.download_images(output_links_file, output_json_file)
    """