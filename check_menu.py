import requests
from bs4 import BeautifulSoup
import os
import hashlib
import datetime
import re
from urllib.parse import urljoin
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
            response_tg = requests.post(url, files=files, data=data, timeout=REQUEST_TIMEOUT + 30) # Longer timeout for upload
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
    menu_links = news_page_soup.find_all(
        lambda tag: tag.name == 'a' and \
                    tag.get('href', '').startswith('/post/') and \
                    ('menu' in tag.get_text(strip=True).lower() or \
                     'menu' in tag.get('href', '').lower())
    )

    if menu_links:
        relative_url = menu_links[0]['href']
        latest_menu_post_url = urljoin(BASE_URL, relative_url)
        print(f"Found potential menu post link: {latest_menu_post_url}")
    else:
        print(f"Could not find any menu links matching '/post/' and 'menu' on {TARGET_PAGE_URL}")

except requests.exceptions.RequestException as e:
    print(f"Error fetching news page {TARGET_PAGE_URL}: {e}")
    exit(1) # Exit if fetching the news page fails

if not latest_menu_post_url:
    print("Failed to find the menu post URL. Exiting.")
    exit(1) # Exit if no link was found
# --- End Strategy ---

# --- Proceed with the found URL ---
# <<< This block was missing in the code you provided >>>
try:
    print(f"Fetching menu post page: {latest_menu_post_url}")
    # Fetch the specific post page and assign to 'response'
    response = requests.get(latest_menu_post_url, timeout=REQUEST_TIMEOUT)
    response.raise_for_status() # Check if the fetch was successful
    print(f"Successfully fetched menu post page.")

except requests.exceptions.RequestException as e:
    # If requests.get() fails, print error and exit
    print(f"Failed to fetch menu post page {latest_menu_post_url}: {e}")
    exit(1) # Exit here if fetching fails
# <<< End of missing block >>>

# Now 'response' should be defined before this line is reached
# Parse the HTML content using BeautifulSoup
soup = BeautifulSoup(response.content, 'html.parser')

# --- Image Extraction Logic ---
img_url = None
img_alt_text = "" # Initialize variable for alt text

# Try finding the image tag with the specific 'data-pin-media' attribute first
img_tag_pin = soup.find('img', {'data-pin-media': True})
if img_tag_pin and img_tag_pin.get('data-pin-media'):
    potential_url = urljoin(latest_menu_post_url, img_tag_pin['data-pin-media'])
    potential_alt = img_tag_pin.get('alt', '').lower() # Get alt text
    # Optional check for keywords in alt text
    if "menu" in potential_alt or not potential_alt: # Accept if "menu" is in alt, or if alt is empty/missing
        img_url = potential_url
        img_alt_text = potential_alt
        print(f"Found image URL using 'data-pin-media': {img_url}")
    else:
        print(f"Found image with 'data-pin-media', but alt text '{potential_alt}' doesn't suggest it's a menu. Continuing search.")


# Fallback 1: Look for specific Wix Blog post image structures
if not img_url:
    print("Attribute 'data-pin-media' not found or alt text unsuitable. Trying Wix Blog image selector.")
    figure_tag = soup.find(['figure', 'div'], attrs={'role': 'figure'})
    if figure_tag:
        main_img = figure_tag.find('img', {'src': True})
        if main_img:
            potential_url = urljoin(latest_menu_post_url, main_img['src'])
            potential_alt = main_img.get('alt', '').lower() # Get alt text
            if "menu" in potential_alt or not potential_alt:
                 img_url = potential_url
                 img_alt_text = potential_alt
                 print(f"Found image URL using Wix Blog figure structure: {img_url}")
            else:
                 print(f"Found image with Wix figure structure, but alt text '{potential_alt}' doesn't suggest it's a menu. Continuing search.")


# Fallback 2: Generic search within <article> (less reliable)
if not img_url:
    print("Wix Blog selector failed or alt text unsuitable. Trying generic article image search.")
    article_body = soup.find('article')
    if article_body:
        all_imgs = article_body.find_all('img', {'src': True})
        if all_imgs:
           main_img = max(all_imgs, key=lambda img: int(img.get('width', 0)) * int(img.get('height', 0)), default=None)
           if main_img:
                potential_url = urljoin(latest_menu_post_url, main_img['src'])
                potential_alt = main_img.get('alt', '').lower() # Get alt text
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
        # Download the image
        print(f"Downloading image from: {img_url}")
        img_response = requests.get(img_url, timeout=60) # Longer timeout for image download
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

                if len(found_keywords) > 1: # Require at least 2 keywords
                    is_confirmed_menu = True
                    print(f"OCR check passed. Found keywords: {found_keywords}")
                else:
                    print(f"OCR check failed. Found keywords: {found_keywords}. Does not seem like a menu.")
            except Exception as ocr_error:
                print(f"Error during OCR processing: {ocr_error}")
                is_confirmed_menu = False # Treat OCR error as failure to confirm
        else:
            print("OCR libraries not available, skipping content check.")
            is_confirmed_menu = True # Assume it's a menu if OCR is disabled

        # --- Hash Comparison and Notification ---
        if is_confirmed_menu:
            existing_hash = calculate_hash(IMAGE_SAVE_PATH)
            new_hash = hashlib.sha256(image_content).hexdigest()

            if existing_hash == new_hash:
                print("The new image is the same as the existing one (and confirmed as menu if OCR ran). No update needed.")
            else:
                print("The new image is different (and confirmed as menu if OCR ran). Updating.") # Removed mention of sending notification
                with open(IMAGE_SAVE_PATH, 'wb') as img_file:
                    img_file.write(image_content)
                print(f"Image updated and saved as '{IMAGE_SAVE_PATH}'")

                # --- Caption Generation ---
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
                # --- End Caption Generation ---

                caption = f"Ericsson Dining Menu - {caption_date_str}\nSource: {latest_menu_post_url}"

                # --- Temporarily disable Telegram sending for testing ---
                print("Skipping Telegram notification for testing.")
                # print(f"Caption that would be sent: {caption}") # Optional: print caption for checking
                # send_telegram_photo(IMAGE_SAVE_PATH, caption) # Keep this commented out
                # --- End temporary disable ---
        else:
             print("Image content check failed (via OCR). Skipping hash comparison.") # Removed mention of notification

    except requests.exceptions.RequestException as e:
        print(f"Error downloading image {img_url}: {e}")
    except Exception as e:
        print(f"An unexpected error occurred during image processing: {e}")

else:
    print(f"Could not find menu image URL on the post page: {latest_menu_post_url}")
    exit(1) # Exit if no image URL could be extracted