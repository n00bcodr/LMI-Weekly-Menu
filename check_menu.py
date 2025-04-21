import requests
from bs4 import BeautifulSoup
import os
import hashlib
import datetime
import re # Import regex module
from urllib.parse import urljoin # To construct absolute URLs
from io import BytesIO # To handle image data in memory
try:
    import pytesseract
    from PIL import Image # Python Imaging Library
    OCR_ENABLED = True
except ImportError:
    print("OCR libraries (pytesseract, Pillow) not found. OCR check will be skipped.")
    OCR_ENABLED = False

# --- Configuration ---
TARGET_PAGE_URL = "https://www.ericssondining.ie/news"
BASE_URL = "https://www.ericssondining.ie/"
IMAGE_SAVE_PATH = "weekly_menu.jpg"
REQUEST_TIMEOUT = 30

# Expanded Keyword List (lowercase)
OCR_MENU_KEYWORDS = [
    "menu", "week", "soup", "main", "salad", "daily", "special",
    "mon", "tue", "tues", "wed", "thu", "thur", "thurs", "fries", "chips",
    "chicken", "beef", "pork", "fish", "vegetarian", "vegan", "halal",
    "potatoes", "rice", "pasta", "noodles", "burger", "curry", "roast",
    "kitchen", "mash", "enrich"
]
# --- End Configuration ---

# --- Helper Functions ---
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
        # Optionally add more error handling here if needed in production
        return False
    url = f"https://api.telegram.org/bot{bot_token}/sendPhoto"
    try:
        with open(photo_path, 'rb') as photo:
            files = {'photo': photo}
            data = {'chat_id': chat_id, 'caption': caption}
            response_tg = requests.post(url, files=files, data=data, timeout=REQUEST_TIMEOUT + 30) # Longer timeout for upload
            response_tg.raise_for_status() # Check for HTTP errors
        print("Photo sent successfully to Telegram.")
        return True
    except requests.exceptions.RequestException as e:
        print(f"Failed to send photo to Telegram: {e}")
        # Consider logging response_tg.text if available and status_code != 200
        return False
    except FileNotFoundError:
        print(f"Error: Photo file not found at {photo_path} for Telegram.")
        return False

def get_current_monday(date):
    """Get the Monday of the week in which the given date falls."""
    return date - datetime.timedelta(days=date.weekday())
# --- End Helper Functions ---

# --- Find menu link on the /news page ---
latest_menu_post_url = None
try:
    print(f"Fetching news page: {TARGET_PAGE_URL}")
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
    }
    news_page_response = requests.get(TARGET_PAGE_URL, headers=headers, timeout=REQUEST_TIMEOUT)
    news_page_response.raise_for_status()
    news_page_soup = BeautifulSoup(news_page_response.content, 'html.parser')

    gallery_container = news_page_soup.find('div', {'id': 'pro-gallery-pro-blog'})
    if not gallery_container:
         gallery_container = news_page_soup.find('div', {'data-hook': 'gallery-widget-items-container'}) or \
                             news_page_soup.find('div', class_=re.compile(r'pro-gallery'))

    menu_links = []
    if gallery_container:
        potential_links = gallery_container.find_all('a', href=re.compile(r'/post/'))
        for link in potential_links:
             h2_text = link.find('h2')
             link_text = (h2_text.get_text(strip=True) if h2_text else link.get_text(strip=True)).lower()
             href_text = link.get('href', '').lower()
             parent_item = link.find_parent(class_=re.compile(r'gallery-item-container'))
             parent_text = parent_item.get_text(strip=True).lower() if parent_item else ""
             if 'menu' in link_text or 'menu' in href_text or 'menu' in parent_text:
                 menu_links.append(link)

    if menu_links:
        latest_menu_post_url = menu_links[0]['href']
        if not latest_menu_post_url.startswith(('http://', 'https://')):
             latest_menu_post_url = urljoin(BASE_URL, latest_menu_post_url)
        print(f"Found potential menu post link: {latest_menu_post_url}")
    else:
        print(f"Could not find any menu links matching the expected structure on {TARGET_PAGE_URL}")
        exit(1) # Exit if no link found

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
    response = requests.get(latest_menu_post_url, headers=headers, timeout=REQUEST_TIMEOUT)
    response.raise_for_status()
    print(f"Successfully fetched menu post page.")
except requests.exceptions.RequestException as e:
    print(f"Failed to fetch menu post page {latest_menu_post_url}: {e}")
    exit(1)

# Parse the HTML content using BeautifulSoup
soup = BeautifulSoup(response.content, 'html.parser')

# --- Image Extraction Logic ---
img_url = None
# (Keep the image extraction logic using data-pin-media and fallbacks)
img_tag_pin = soup.find('img', {'data-pin-media': True})
if img_tag_pin and img_tag_pin.get('data-pin-media'):
    img_url = urljoin(latest_menu_post_url, img_tag_pin['data-pin-media'])
    print(f"Found image URL using 'data-pin-media': {img_url}")

if not img_url:
    print("Attribute 'data-pin-media' not found. Trying Wix Blog image selector.")
    figure_tag = soup.find(['figure', 'div'], attrs={'role': 'figure'})
    if figure_tag:
        main_img = figure_tag.find('img', {'src': True})
        if main_img:
            img_url = urljoin(latest_menu_post_url, main_img['src'])
            print(f"Found image URL using Wix Blog figure structure: {img_url}")

if not img_url:
    print("Wix Blog selector failed. Trying generic article image search.")
    article_body = soup.find('article')
    if article_body:
        all_imgs = article_body.find_all('img', {'src': True})
        if all_imgs:
           main_img = max(all_imgs, key=lambda img: int(img.get('width', 0)) * int(img.get('height', 0)), default=None)
           if main_img:
                img_url = urljoin(latest_menu_post_url, main_img['src'])
                print(f"Found image URL using largest image in article (fallback): {img_url}")
# --- End Image Extraction Logic ---

# --- Download and Process Image ---
if img_url:
    try:
        print(f"Downloading image from: {img_url}")
        img_response = requests.get(img_url, headers=headers, timeout=60)
        img_response.raise_for_status()
        image_content = img_response.content

        # --- OCR Check ---
        is_confirmed_menu = False
        if OCR_ENABLED:
            print("Performing OCR check on the downloaded image...")
            try:
                img_from_bytes = Image.open(BytesIO(image_content))
                img_gray = img_from_bytes.convert('L') # Use grayscale
                custom_config = r'--psm 6' # Use PSM 6
                extracted_text = pytesseract.image_to_string(img_gray, config=custom_config).lower()
                print(f"Extracted text: {extracted_text}")
                # Check for keywords in the extracted text
                found_keywords = [keyword for keyword in OCR_MENU_KEYWORDS if keyword in extracted_text]
                # Require at least 4 keywords
                if len(found_keywords) > 4:
                    is_confirmed_menu = True
                    print(f"OCR check passed. Found keywords: {found_keywords}")
                else:
                    print(f"OCR check failed. Found keywords: {found_keywords}. Does not seem like a menu.")
            except Exception as ocr_error:
                print(f"Error during OCR processing: {ocr_error}")
                is_confirmed_menu = False # Treat OCR error as failure
        else:
            print("OCR libraries not available, skipping content check.")
            is_confirmed_menu = True # Assume menu if OCR disabled

        # --- Hash Comparison and Notification ---
        if is_confirmed_menu:
            existing_hash = calculate_hash(IMAGE_SAVE_PATH)
            new_hash = hashlib.sha256(image_content).hexdigest()
            if existing_hash == new_hash:
                print("The new image is the same as the existing one (and confirmed as menu if OCR ran). No update needed.")
            else:
                print("The new image is different (and confirmed as menu if OCR ran). Updating and sending notification.")
                with open(IMAGE_SAVE_PATH, 'wb') as img_file:
                    img_file.write(image_content)
                print(f"Image updated and saved as '{IMAGE_SAVE_PATH}'")

                # --- Caption Generation ---
                try:
                    # Get the current date when the script runs
                    today = datetime.date.today()
                    # Calculate the Monday of the current week
                    current_monday = get_current_monday(today)
                    # Format the date string
                    caption_date_str = f"{current_monday.strftime('%d %b %Y')}"

                except Exception as e:
                     # Fallback in case of unexpected error during date calculation
                     print(f"Error generating caption date: {e}")
                     caption_date_str = "current week"
                # --- End Caption Generation ---

                caption = f"Menu of the week starting {caption_date_str}\nSource: {latest_menu_post_url}"
                # Print the caption to console
                print(f"{caption}")

                # --- Telegram ---
                print("Sending a notification through telegram...")
                send_telegram_photo(IMAGE_SAVE_PATH, caption)
                # --- End Telegram ---
        else:
             print("Image content check failed (via OCR). Skipping hash comparison and notification.")

    except requests.exceptions.RequestException as e:
        print(f"Error downloading image {img_url}: {e}")
    except Exception as e:
        print(f"An unexpected error occurred during image processing: {e}")

else:
    print(f"Could not find menu image URL on the post page: {latest_menu_post_url}")
    exit(1)