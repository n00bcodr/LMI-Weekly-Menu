import requests
from bs4 import BeautifulSoup
import os
import hashlib
import datetime

# Define the URL of the page
url = "https://www.ericssondining.ie/post/weekly-daily-menu-week-beginning-12-02-2024"

def calculate_hash(file_path):
    """Calculate the SHA-256 hash of the given file."""
    sha256 = hashlib.sha256()
    with open(file_path, 'rb') as f:
        for chunk in iter(lambda: f.read(4096), b""):
            sha256.update(chunk)
    return sha256.hexdigest()

def calculate_hash_from_content(content):
    """Calculate the SHA-256 hash from the image content."""
    sha256 = hashlib.sha256()
    sha256.update(content)
    return sha256.hexdigest()

def send_telegram_photo(photo_path, caption):
    """Send a photo to a Telegram chat."""
    bot_token = os.getenv('BOT_TOKEN')
    chat_id = os.getenv('CHAT_ID')
    url = f"https://api.telegram.org/bot{bot_token}/sendPhoto"
    with open(photo_path, 'rb') as photo:
        files = {'photo': photo}
        data = {'chat_id': chat_id, 'caption': caption}
        response = requests.post(url, files=files, data=data)
    if response.status_code == 200:
        print("Photo sent successfully.")
    else:
        print(f"Failed to send photo. Status code: {response.status_code}")

def get_current_monday(date):
    """Get the Monday of the week in which the current date falls."""
    return date - datetime.timedelta(days=date.weekday())

# Fetch the content from the URL
response = requests.get(url)
response.raise_for_status()  # Ensure we got a valid response

# Parse the HTML content using BeautifulSoup
soup = BeautifulSoup(response.content, 'html.parser')

# Find all image tags with the specific 'data-pin-media' attribute
img_tags = soup.find_all('img', {'data-pin-media': True})

# Check if there are at least two images
if len(img_tags) >= 2:
    # Get the URL of the first image
    first_img_url = img_tags[0]['data-pin-media']

    # Download the first image
    first_img_response = requests.get(first_img_url)
    first_img_response.raise_for_status()  # Ensure we got a valid response

    # Calculate the hash of the first image
    first_img_hash = calculate_hash_from_content(first_img_response.content)

    # Check if the existing image file exists
    img_path = 'weekly_menu.jpg'
    if os.path.exists(img_path):
        # Calculate the hash of the existing image
        existing_hash = calculate_hash(img_path)

        # Compare the hashes
        if first_img_hash == existing_hash:
            print("The first image matches the existing one. Downloading the second image.")

            # Get the URL of the second image
            second_img_url = img_tags[1]['data-pin-media']

            # Download the second image
            second_img_response = requests.get(second_img_url)
            second_img_response.raise_for_status()  # Ensure we got a valid response

            # Save the second image
            with open(img_path, 'wb') as img_file:
                img_file.write(second_img_response.content)
            print(f"Second image downloaded and saved as '{img_path}'")

            # Calculate the Monday of the current week
            today = datetime.date.today()
            current_monday = get_current_monday(today)

            # Prepare the caption
            caption = f"Menu for the week starting {current_monday.strftime('%d %b %Y')}"

            send_telegram_photo(img_path, caption)
        else:
            print("The first image does not match the existing one. No action taken.")
    else:
        print("Existing image file not found. No action taken.")
else:
    print("No images found")
