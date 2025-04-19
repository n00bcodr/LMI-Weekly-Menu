import requests
from bs4 import BeautifulSoup
import os
import hashlib
import datetime
import re
from urllib.parse import urljoin

# --- Configuration ---
# Target the /news page specifically
TARGET_PAGE_URL = "https://www.ericssondining.ie/news"
BASE_URL = "https://www.ericssondining.ie/" # Still needed for joining relative URLs
IMAGE_SAVE_PATH = "weekly_menu.jpg"
REQUEST_TIMEOUT = 30 # Seconds for HTTP requests
# --- End Configuration ---

def calculate_hash(file_path):
    """Calculate the SHA-256 hash of the given file."""
    sha256 = hashlib.sha256()
    try:
        with open(file_path, 'rb') as f:
            for chunk in iter(lambda: f.read(4096), b""):
                sha256.update(chunk)
        return sha256.hexdigest()
    except FileNotFoundError:
        return None

def send_telegram_photo(photo_path, caption):
    """Send a photo to a Telegram chat."""
    bot_token = os.getenv('BOT_TOKEN')
    chat_id = os.getenv('CHAT_ID')
    if not bot_token or not chat_id:
        print("Error: BOT_TOKEN or CHAT_ID environment variables not set.")
        return False
    url = f"https://api.telegram.org/bot{bot_token}/sendPhoto"
    try:
        with open(photo_path, 'rb') as photo:
            files = {'photo': photo}
            data = {'chat_id': chat_id, 'caption': caption}
            response = requests.post(url, files=files, data=data, timeout=REQUEST_TIMEOUT + 30) # Longer timeout for upload
            response.raise_for_status()
        print("Photo sent successfully.")
        return True
    except requests.exceptions.RequestException as e:
        print(f"Failed to send photo: {e}")
        # Consider printing response.text for more details if needed
        # print(f"Response text: {response.text if 'response' in locals() else 'No response'}")
        return False
    except FileNotFoundError:
        print(f"Error: Photo file not found at {photo_path}")
        return False

def get_current_monday(date):
    """Get the Monday of the week in which the given date falls."""
    return date - datetime.timedelta(days=date.weekday())

# --- Strategy: Find menu link on the /news page ---
latest_menu_post_url = None
try:
    print(f"Fetching news page: {TARGET_PAGE_URL}")
    news_page_response = requests.get(TARGET_PAGE_URL, timeout=REQUEST_TIMEOUT)
    news_page_response.raise_for_status()
    news_page_soup = BeautifulSoup(news_page_response.content, 'html.parser')

    # Find links containing '/post/' and 'menu' (case-insensitive) in text or href
    # On a blog feed page, the first match is very likely the latest post.
    menu_links = news_page_soup.find_all(
        lambda tag: tag.name == 'a' and \
                    tag.get('href', '').startswith('/post/') and \
                    ('menu' in tag.get_text(strip=True).lower() or \
                     'menu' in tag.get('href', '').lower())
    )

    if menu_links:
        # Assume the first relevant link found is the latest one
        relative_url = menu_links[0]['href']
        # Ensure the URL is absolute using the BASE_URL
        latest_menu_post_url = urljoin(BASE_URL, relative_url)
        print(f"Found potential menu post link: {latest_menu_post_url}")
    else:
        print(f"Could not find any menu links matching '/post/' and 'menu' on {TARGET_PAGE_URL}")

except requests.exceptions.RequestException as e:
    print(f"Error fetching news page {TARGET_PAGE_URL}: {e}")
    exit(1)

if not latest_menu_post_url:
    print("Failed to find the menu post URL. Exiting.")
    exit(1)
# --- End Strategy ---

# --- Proceed with the found URL ---
try:
    print(f"Fetching menu post page: {latest_menu_post_url}")
    response = requests.get(latest_menu_post_url, timeout=REQUEST_TIMEOUT)
    response.raise_for_status()
    print(f"Successfully fetched menu post page.")

except requests.exceptions.RequestException as e:
    print(f"Failed to fetch menu post page {latest_menu_post_url}: {e}")
    exit(1)

# Parse the HTML content using BeautifulSoup
soup = BeautifulSoup(response.content, 'html.parser')

# --- Image Extraction Logic ---
img_url = None

# Try finding the image tag with the specific 'data-pin-media' attribute first
img_tag_pin = soup.find('img', {'data-pin-media': True})
if img_tag_pin and img_tag_pin.get('data-pin-media'):
    img_url = urljoin(latest_menu_post_url, img_tag_pin['data-pin-media'])
    print(f"Found image URL using 'data-pin-media': {img_url}")

# Fallback 1: Look for specific Wix Blog post image structures
if not img_url:
    print("Attribute 'data-pin-media' not found or empty. Trying Wix Blog image selector.")
    # Wix blog posts often wrap the main image in a structure like this:
    # Look for a figure or div with a role="figure", then find the img inside
    figure_tag = soup.find(['figure', 'div'], attrs={'role': 'figure'})
    if figure_tag:
        main_img = figure_tag.find('img', {'src': True})
        if main_img:
            img_url = urljoin(latest_menu_post_url, main_img['src'])
            print(f"Found image URL using Wix Blog figure structure: {img_url}")

# Fallback 2: Generic search within <article> (less reliable)
if not img_url:
    print("Wix Blog selector failed. Trying generic article image search.")
    article_body = soup.find('article')
    if article_body:
        all_imgs = article_body.find_all('img', {'src': True})
        if all_imgs:
           # Prioritize images with width/height attributes, assuming the menu is large
           # Use get with default 0 to handle missing attributes gracefully
           main_img = max(all_imgs, key=lambda img: int(img.get('width', 0)) * int(img.get('height', 0)), default=None)
           if main_img:
                img_url = urljoin(latest_menu_post_url, main_img['src'])
                print(f"Found image URL using largest image in article (fallback): {img_url}")
           else: # If no dimensions, take the first one as a guess
                img_url = urljoin(latest_menu_post_url, all_imgs[0]['src'])
                print(f"Found image URL using first image in article (fallback): {img_url}")
# --- End Image Extraction Logic ---

if img_url:
    try:
        # Download the image
        print(f"Downloading image from: {img_url}")
        img_response = requests.get(img_url, timeout=60) # Longer timeout for image download
        img_response.raise_for_status()

        # Calculate hash of existing image
        existing_hash = calculate_hash(IMAGE_SAVE_PATH)

        # Calculate hash of new image content
        new_hash = hashlib.sha256(img_response.content).hexdigest()

        if existing_hash == new_hash:
            print("The new image is the same as the existing one. No update needed.")
        else:
            print("The new image is different. Updating and sending notification.")
            # Save the new image
            with open(IMAGE_SAVE_PATH, 'wb') as img_file:
                img_file.write(img_response.content)
            print(f"Image updated and saved as '{IMAGE_SAVE_PATH}'")

            # --- Caption Generation ---
            caption_date_str = "this week"
            try:
                # Attempt to extract date from the URL
                match = re.search(r'(\d{2}[-.]\d{2}[-.]\d{2,4})', latest_menu_post_url)
                if match:
                    date_part = match.group(1).replace('.', '-') # Normalize separator
                    parsed_date = None
                    for fmt in ('%d-%m-%y', '%d-%m-%Y'):
                        try:
                            parsed_date = datetime.datetime.strptime(date_part, fmt).date()
                            break
                        except ValueError:
                            continue
                    if parsed_date:
                         menu_monday = get_current_monday(parsed_date)
                         caption_date_str = f"week starting {menu_monday.strftime('%d %b %Y')}"
                    else:
                         print(f"Could not parse date '{date_part}' from URL {latest_menu_post_url}.")
                else: # Fallback if no date found in URL
                     today = datetime.date.today()
                     current_monday = get_current_monday(today)
                     caption_date_str = f"week starting {current_monday.strftime('%d %b %Y')}"
            except Exception as e:
                 print(f"Error parsing date for caption: {e}")
                 today = datetime.date.today()
                 current_monday = get_current_monday(today)
                 caption_date_str = f"week starting {current_monday.strftime('%d %b %Y')}"
            # --- End Caption Generation ---

            caption = f"Ericsson Dining Menu - {caption_date_str}\nSource: {latest_menu_post_url}"
            send_telegram_photo(IMAGE_SAVE_PATH, caption)

    except requests.exceptions.RequestException as e:
        print(f"Error downloading image {img_url}: {e}")
    except Exception as e:
        print(f"An unexpected error occurred during image processing: {e}")

else:
    print(f"Could not find menu image URL on the post page: {latest_menu_post_url}")
    exit(1) # Exit if no image URL could be extracted