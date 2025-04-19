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
IMAGE_SAVE_PATH = "weekly_menu.jpg" # Save to the root of the repo
REQUEST_TIMEOUT = 30 # Seconds for HTTP requests
OCR_MENU_KEYWORDS = ["menu", "monday", "tuesday", "wednesday", "thursday", "friday", "soup", "main", "salad", "€"]
# --- End Configuration ---

# --- Helper Functions (Keep as they are) ---
def calculate_hash(file_path):
    # ... (calculate_hash function code) ...
    sha256 = hashlib.sha256()
    try:
        with open(file_path, 'rb') as f:
            for chunk in iter(lambda: f.read(4096), b""):
                sha256.update(chunk)
        return sha256.hexdigest()
    except FileNotFoundError:
        return None

def send_telegram_photo(photo_path, caption):
    # ... (send_telegram_photo function code - currently commented out at the end) ...
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
            response_tg = requests.post(url, files=files, data=data, timeout=REQUEST_TIMEOUT + 30)
            response_tg.raise_for_status()
        print("Photo sent successfully.")
        return True
    except requests.exceptions.RequestException as e:
        print(f"Failed to send photo: {e}")
        return False
    except FileNotFoundError:
        print(f"Error: Photo file not found at {photo_path}")
        return False

def get_current_monday(date):
    # ... (get_current_monday function code) ...
     return date - datetime.timedelta(days=date.weekday())
# --- End Helper Functions ---

# --- Updated Strategy: Find menu link on the /news page ---
latest_menu_post_url = None
try:
    print(f"Fetching news page: {TARGET_PAGE_URL}")
    headers = { # Keep the User-Agent header
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
    }
    news_page_response = requests.get(TARGET_PAGE_URL, headers=headers, timeout=REQUEST_TIMEOUT)
    news_page_response.raise_for_status()
    news_page_soup = BeautifulSoup(news_page_response.content, 'html.parser')

    # Find the gallery container
    gallery_container = news_page_soup.find('div', {'id': 'pro-gallery-pro-blog'})
    if not gallery_container:
         gallery_container = news_page_soup.find('div', {'data-hook': 'gallery-widget-items-container'}) or \
                             news_page_soup.find('div', class_=re.compile(r'pro-gallery'))

    menu_links = []
    if gallery_container:
        # Find links within the gallery that CONTAIN /post/ in the href
        potential_links = gallery_container.find_all(
            'a',
            href=re.compile(r'/post/') # <-- CHANGED: Look for /post/ anywhere in href
        )

        # Further filter these links to ensure they are likely menu posts
        for link in potential_links:
             h2_text = link.find('h2')
             link_text = (h2_text.get_text(strip=True) if h2_text else link.get_text(strip=True)).lower()
             href_text = link.get('href', '').lower()
             parent_item = link.find_parent(class_=re.compile(r'gallery-item-container'))
             parent_text = parent_item.get_text(strip=True).lower() if parent_item else ""

             if 'menu' in link_text or 'menu' in href_text or 'menu' in parent_text:
                 menu_links.append(link)

    if menu_links:
        # Use the href directly as it's absolute
        latest_menu_post_url = menu_links[0]['href']
        # Optional: Double-check it's a valid absolute URL starting with http
        if not latest_menu_post_url.startswith(('http://', 'https://')):
             print(f"Warning: Found link {latest_menu_post_url} does not look like an absolute URL. Attempting to join with base.")
             latest_menu_post_url = urljoin(BASE_URL, latest_menu_post_url)

        print(f"Found potential menu post link: {latest_menu_post_url}")
    else:
        print(f"Could not find any menu links matching the expected structure on {TARGET_PAGE_URL}")

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
    # Pass headers here too for consistency
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
img_alt_text = ""

# ... (Keep the image extraction logic using data-pin-media and fallbacks as it was) ...
img_tag_pin = soup.find('img', {'data-pin-media': True})
if img_tag_pin and img_tag_pin.get('data-pin-media'):
    potential_url = urljoin(latest_menu_post_url, img_tag_pin['data-pin-media'])
    potential_alt = img_tag_pin.get('alt', '').lower()
    if "menu" in potential_alt or not potential_alt:
        img_url = potential_url
        img_alt_text = potential_alt
        print(f"Found image URL using 'data-pin-media': {img_url}")
    else:
        print(f"Found image with 'data-pin-media', but alt text '{potential_alt}' doesn't suggest it's a menu. Continuing search.")

if not img_url:
    print("Attribute 'data-pin-media' not found or alt text unsuitable. Trying Wix Blog image selector.")
    figure_tag = soup.find(['figure', 'div'], attrs={'role': 'figure'})
    if figure_tag:
        main_img = figure_tag.find('img', {'src': True})
        if main_img:
            potential_url = urljoin(latest_menu_post_url, main_img['src'])
            potential_alt = main_img.get('alt', '').lower()
            if "menu" in potential_alt or not potential_alt:
                 img_url = potential_url
                 img_alt_text = potential_alt
                 print(f"Found image URL using Wix Blog figure structure: {img_url}")
            else:
                 print(f"Found image with Wix figure structure, but alt text '{potential_alt}' doesn't suggest it's a menu. Continuing search.")

if not img_url:
    print("Wix Blog selector failed or alt text unsuitable. Trying generic article image search.")
    article_body = soup.find('article')
    if article_body:
        all_imgs = article_body.find_all('img', {'src': True})
        if all_imgs:
           main_img = max(all_imgs, key=lambda img: int(img.get('width', 0)) * int(img.get('height', 0)), default=None)
           if main_img:
                potential_url = urljoin(latest_menu_post_url, main_img['src'])
                potential_alt = main_img.get('alt', '').lower()
                if "menu" in potential_alt or not potential_alt:
                    img_url = potential_url
                    img_alt_text = potential_alt
                    print(f"Found image URL using largest image in article (fallback): {img_url}")
                else:
                     print(f"Found largest image in article, but alt text '{potential_alt}' doesn't suggest it's a menu.")
# --- End Image Extraction Logic ---

# --- Download and Process Image ---
if img_url:
    try:
        print(f"Downloading image from: {img_url}")
        img_response = requests.get(img_url, headers=headers, timeout=60) # Pass headers here too
        img_response.raise_for_status()
        image_content = img_response.content

        # --- OCR Check ---
        is_confirmed_menu = False
        if OCR_ENABLED:
            print("Performing OCR check on the downloaded image...")
            try:
                img_from_bytes = Image.open(BytesIO(image_content))
                extracted_text = pytesseract.image_to_string(img_from_bytes).lower()
                found_keywords = [keyword for keyword in OCR_MENU_KEYWORDS if keyword in extracted_text]
                if len(found_keywords) > 1:
                    is_confirmed_menu = True
                    print(f"OCR check passed. Found keywords: {found_keywords}")
                else:
                    print(f"OCR check failed. Found keywords: {found_keywords}. Does not seem like a menu.")
            except Exception as ocr_error:
                print(f"Error during OCR processing: {ocr_error}")
                is_confirmed_menu = False
        else:
            print("OCR libraries not available, skipping content check.")
            is_confirmed_menu = True

        # --- Hash Comparison and Notification ---
        if is_confirmed_menu:
            existing_hash = calculate_hash(IMAGE_SAVE_PATH)
            new_hash = hashlib.sha256(image_content).hexdigest()
            if existing_hash == new_hash:
                print("The new image is the same as the existing one (and confirmed as menu if OCR ran). No update needed.")
            else:
                print("The new image is different (and confirmed as menu if OCR ran). Updating.")
                with open(IMAGE_SAVE_PATH, 'wb') as img_file:
                    img_file.write(image_content)
                print(f"Image updated and saved as '{IMAGE_SAVE_PATH}'")
                # --- Caption Generation ---
                # ... (Caption generation logic) ...
                caption_date_str = "this week"
                try:
                    match = re.search(r'(\d{2}[-.]\d{2}[-.]\d{2,4})', latest_menu_post_url)
                    if match:
                        date_part = match.group(1).replace('.', '-')
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
                    else:
                         today = datetime.date.today()
                         current_monday = get_current_monday(today)
                         caption_date_str = f"week starting {current_monday.strftime('%d %b %Y')}"
                except Exception as e:
                     print(f"Error parsing date for caption: {e}")
                     today = datetime.date.today()
                     current_monday = get_current_monday(today)
                     caption_date_str = f"week starting {current_monday.strftime('%d %b %Y')}"
                caption = f"Ericsson Dining Menu - {caption_date_str}\nSource: {latest_menu_post_url}"
                # --- Temporarily disable Telegram sending for testing ---
                print("Skipping Telegram notification for testing.")
                # send_telegram_photo(IMAGE_SAVE_PATH, caption) # Keep this commented out
                # --- End temporary disable ---
        else:
             print("Image content check failed (via OCR). Skipping hash comparison.")

    except requests.exceptions.RequestException as e:
        print(f"Error downloading image {img_url}: {e}")
    except Exception as e:
        print(f"An unexpected error occurred during image processing: {e}")

else:
    print(f"Could not find menu image URL on the post page: {latest_menu_post_url}")
    exit(1)