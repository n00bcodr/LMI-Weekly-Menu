import requests
from bs4 import BeautifulSoup
import os
import hashlib
import datetime

# Define the path to save the image
img_path = "weekly_menu.jpg"  # Save to the root of the repo

def calculate_hash(file_path):
    """Calculate the SHA-256 hash of the given file."""
    sha256 = hashlib.sha256()
    with open(file_path, 'rb') as f:
        for chunk in iter(lambda: f.read(4096), b""):
            sha256.update(chunk)
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

# Calculate last Monday and coming Monday
today = datetime.date.today()
weekday = today.weekday()  # Monday = 0, Sunday = 6

if weekday >= 5:  # Saturday (5) or Sunday (6)
    last_monday = get_current_monday(today)
    this_monday = last_monday + datetime.timedelta(days=7)
else:
    last_monday = get_current_monday(today - datetime.timedelta(days=7))
    this_monday = get_current_monday(today)

# Try last Monday first
url_template = "https://www.ericssondining.ie/post/menu-{}"
for monday in [last_monday, this_monday]:
    url = url_template.format(monday.strftime('%d-%m-%y'))
    try:
        response = requests.get(url)
        response.raise_for_status()
        print(f"Found menu at: {url}")
        break
    except requests.HTTPError:
        print(f"Menu not found at: {url}")
        continue
else:
    print("No menu found for last or this Monday.")
    exit()

# Parse the HTML content using BeautifulSoup
soup = BeautifulSoup(response.content, 'html.parser')

# Find the image tag with the specific 'data-pin-media' attribute
img_tag = soup.find('img', {'data-pin-media': True})

if img_tag:
    # Get the URL of the image from the 'data-pin-media' attribute
    img_url = img_tag['data-pin-media']

    # Download the image
    img_response = requests.get(img_url)
    img_response.raise_for_status()  # Ensure we got a valid response

    # Check if the image already exists
    if os.path.exists(img_path):
        # Calculate the hash of the existing image
        existing_hash = calculate_hash(img_path)

        # Save the new image to a temporary file
        temp_img_path = 'temp_weekly_menu.jpg'
        with open(temp_img_path, 'wb') as temp_img_file:
            temp_img_file.write(img_response.content)

        # Calculate the hash of the new image
        new_hash = calculate_hash(temp_img_path)

        # Compare the hashes
        if existing_hash == new_hash:
            print("The new image is the same as the existing one. No update needed.")
            # Remove the temporary file
            os.remove(temp_img_path)
        else:
            print("The new image is different. Updating the image.")
            # Replace the existing image with the new image
            os.replace(temp_img_path, img_path)

            # Calculate the Monday of the current week
            current_monday = get_current_monday(datetime.date.today())

            # Prepare the caption
            caption = f"Menu for the week starting {current_monday.strftime('%d %b %Y')}"

            send_telegram_photo(img_path, caption)
    else:
        # Save the new image as it doesn't exist
        with open(img_path, 'wb') as img_file:
            img_file.write(img_response.content)
        print(f"Image downloaded and saved as '{img_path}'")

        # Calculate the Monday of the current week
        current_monday = get_current_monday(datetime.date.today())

        # Prepare the caption
        caption = f"Menu for the week starting {current_monday.strftime('%d %b %Y')}"
        print (caption)
        send_telegram_photo(img_path, caption)
else:
    print("Image not found.")
