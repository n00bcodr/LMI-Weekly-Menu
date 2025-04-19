import requests
from bs4 import BeautifulSoup
import os
import hashlib
import datetime
import re
from urllib.parse import urljoin
from io import BytesIO # <-- Add: To handle image data in memory
try:
    import pytesseract
    from PIL import Image # <-- Add: Python Imaging Library
    OCR_ENABLED = True
except ImportError:
    print("OCR libraries (pytesseract, Pillow) not found. OCR check will be skipped.")
    OCR_ENABLED = False


# --- Configuration ---
# Target the /news page specifically
TARGET_PAGE_URL = "https://www.ericssondining.ie/news"
BASE_URL = "https://www.ericssondining.ie/" # Still needed for joining relative URLs
IMAGE_SAVE_PATH = "weekly_menu.jpg"
REQUEST_TIMEOUT = 30 # Seconds for HTTP requests

# Keywords to look for in OCR text to confirm it's a menu
OCR_MENU_KEYWORDS = ["menu", "monday", "tuesday", "wednesday", "thursday", "friday", "soup", "main", "salad", "€"]
# --- End Configuration ---

# (Keep calculate_hash, send_telegram_photo, get_current_monday functions as they are)
# ...

# --- Strategy: Find menu link on the /news page ---
# (Keep the link finding logic as it is)
# ... Link finding logic ends with 'if not latest_menu_post_url: ... exit(1)'

# --- Proceed with the found URL ---
# (Keep the post page fetching logic as it is)
# ... Post page fetching logic ends with 'except requests.exceptions.RequestException as e: ... exit(1)'


# Parse the HTML content using BeautifulSoup
soup = BeautifulSoup(response.content, 'html.parser')

# --- Image Extraction Logic ---
# (Keep the image URL extraction logic as it is)
# ... Image extraction logic ends with 'if not img_url: ... print("Wix Blog selector failed...")'

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
                # Load image from bytes
                img_from_bytes = Image.open(BytesIO(image_content))
                # Extract text
                extracted_text = pytesseract.image_to_string(img_from_bytes).lower()
                # Check for keywords
                found_keywords = [keyword for keyword in OCR_MENU_KEYWORDS if keyword in extracted_text]

                if len(found_keywords) > 1: # Require at least 2 keywords to be reasonably sure
                    is_confirmed_menu = True
                    print(f"OCR check passed. Found keywords: {found_keywords}")
                else:
                    print(f"OCR check failed. Found keywords: {found_keywords}. Does not seem like a menu.")
                    # Optional: Save text for debugging
                    # with open("ocr_debug.txt", "w") as f:
                    #     f.write(extracted_text)
            except Exception as ocr_error:
                print(f"Error during OCR processing: {ocr_error}")
                # Decide if you want to proceed without OCR confirmation on error,
                # or treat it as a failure. Let's treat it as inconclusive (skip confirmation).
                is_confirmed_menu = False # Set to True if you want to ignore OCR errors
        else:
            print("OCR libraries not available, skipping content check.")
            is_confirmed_menu = True # Assume it's a menu if OCR is disabled/unavailable

        # --- Hash Comparison and Notification ---
        if is_confirmed_menu:
            # Calculate hash of existing image
            existing_hash = calculate_hash(IMAGE_SAVE_PATH)
            # Calculate hash of new image content
            new_hash = hashlib.sha256(image_content).hexdigest()

            if existing_hash == new_hash:
                print("The new image is the same as the existing one (and confirmed as menu if OCR ran). No update needed.")
            else:
                print("The new image is different (and confirmed as menu if OCR ran). Updating and sending notification.")
                # Save the new image
                with open(IMAGE_SAVE_PATH, 'wb') as img_file:
                    img_file.write(image_content)
                print(f"Image updated and saved as '{IMAGE_SAVE_PATH}'")

                # --- Caption Generation ---
                # ...
                caption = f"Ericsson Dining Menu - {caption_date_str}\nSource: {latest_menu_post_url}"
                # --- Temporarily disable Telegram sending for testing ---
                print("Skipping Telegram notification for testing.")
                # send_telegram_photo(IMAGE_SAVE_PATH, caption) #
                # --- End temporary disable ---
        else:
             print("Image content check failed (via OCR). Skipping hash comparison and notification.")

    except requests.exceptions.RequestException as e:
        print(f"Error downloading image {img_url}: {e}")
    except Exception as e:
        print(f"An unexpected error occurred during image processing: {e}")

else:
    print(f"Could not find menu image URL on the post page: {latest_menu_post_url}")
    exit(1) # Exit if no image URL could be extracted