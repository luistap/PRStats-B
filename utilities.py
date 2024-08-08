# MAIN MODULE FOR UTILITY FUNCTIONS USED BY THE BACKEND SERVER

import cloudinary
import cloudinary.uploader
import cloudinary.api
import requests
import os
import re
import asyncpg
import bot
from fuzzywuzzy import process
from psycopg2 import OperationalError
from google.cloud import vision
from dotenv import load_dotenv
from google.oauth2 import service_account



# Configure your Cloudinary credentials
cloudinary.config(
    cloud_name= os.getenv('CLOUD_NAME'),  # Your cloud name
    api_key= os.getenv('API_KEY'),  # Your API key
    api_secret= os.getenv('API_SECRET'),  # Your API secret
)


HIGH_CONFIDENCE = 90
LOW_CONFIDENCE = 50

credentials = service_account.Credentials.from_service_account_info({
    "type": os.getenv("GOOGLE_TYPE"),
    "project_id": os.getenv("GOOGLE_PROJECT_ID"),
    "private_key_id": os.getenv("GOOGLE_PRIVATE_KEY_ID"),
    "private_key": os.getenv("GOOGLE_PRIVATE_KEY"),
    "client_email": os.getenv("GOOGLE_CLIENT_EMAIL"),
    "client_id": os.getenv("GOOGLE_CLIENT_ID"),
    "auth_uri": os.getenv("GOOGLE_AUTH_URI"),
    "token_uri": os.getenv("GOOGLE_TOKEN_URI"),
    "auth_provider_x509_cert_url": os.getenv("GOOGLE_AUTH_PROVIDER_X509_CERT_URL"),
    "client_x509_cert_url": os.getenv("GOOGLE_CLIENT_X509_CERT_URL")
})

client = vision.ImageAnnotatorClient(credentials=credentials)

def detect_text_path(image_path):
    """Use Google Vision API for OCR."""
    with open(image_path, "rb") as image_file:
        content = image_file.read()
    image = vision.Image(content=content)
    response = client.text_detection(image=image)
    texts = response.text_annotations
    return texts[0].description if texts else "No text found"


def detect_text_byte(byte_content):
    """Use Google Vision API for OCR."""
    image = vision.Image(content=byte_content)
    response = client.text_detection(image=image)
    texts = response.text_annotations
    return texts[0].description if texts else "No text found"


def process_team_stats(file_path):
    """Uploads an image to Cloudinary, applies color inversion and contrast enhancement, and saves it locally."""
    # Upload the image and apply the 'negate' effect to invert colors followed by increasing contrast
    response = cloudinary.uploader.upload(
        file_path,
        transformation=[
            {'effect': "negate"},  # First, invert the colors
            {'effect': "improve:outdoor"}  # Then enhance contrast
        ]
    )
    processed_image_url = response['url']
    print("Processed image URL:", processed_image_url)

    # Download the processed image and save it locally
    image_data = requests.get(processed_image_url).content
    local_filename = "processed_image.png"  # Local filename to save the image
    with open(local_filename, 'wb') as file:
        file.write(image_data)
    print(f"Processed image saved locally as {local_filename}")
    return local_filename


def convert_path(path):
    return path.replace("\\", "/")

def clean_and_convert_stats(stats_text):
    cleaned_stats = []
    for stat in stats_text:
        # Remove non-numeric characters except the '-' for negative numbers if applicable
        cleaned_stat = re.sub(r'[^\d-]', '', stat)
        # Try converting to int, handle the case where the conversion isn't possible
        try:
            cleaned_stats.append(int(cleaned_stat))
        except ValueError:
            print(f"Warning: Unable to convert '{stat}' to an integer.")
            # Optionally, append a default value or handle the error as needed
            cleaned_stats.append(0)  # Append zero or any other default value
    return cleaned_stats

def process_team(names_path : str, stats_path : str, team_dict : dict):

    import scan
    names_text = detect_text_path(names_path)
    stats_path_processed = process_team_stats(stats_path)
    stats_text = scan.process_stats(stats_path_processed)
    names_text = names_text.splitlines()
    for index in range(len(names_text)):
        stats_as_ints = clean_and_convert_stats(stats_text[index])
        team_dict[names_text[index]] = stats_as_ints
    return

async def create_connection():
    try:
        conn = await asyncpg.connect(
            database= os.getenv('DB_NAME'),
            user= os.getenv('USER'),
            password= os.getenv('PASSWORD'),
            host= os.getenv('HOST_NAME'),
            ssl="require"
        )
        print("Connection to the PostgreSQL database successful")
        return conn
    except Exception as e:
        print(f"An error occurred: {e}")
        return None

# remove new line chars from scoreboard strings
def clean_board(scbd):
    cleaned_scbd = {}
    for name, stats in scbd.items():
        # Remove the newline character from the name and any other unwanted characters
        cleaned_name = name.replace('\n', '').strip()
        # Assign the stats to the cleaned name in the new dictionary
        cleaned_scbd[cleaned_name] = stats
    return cleaned_scbd


async def process_names(names, list_of_names, user_id, team_info):

    if not list_of_names:
        # list is empty, db empty, return right away
        return

    for name in names:
        name_to_write = None
        # check exact matching
        name_to_write = get_exact_match(name, list_of_names)
        if name_to_write is None:
            # get next best match
            name_to_write = get_fuzzy_match(name, list_of_names, user_id)
            if name_to_write is not None:
                # fuzzy match found, replace current key
                team_info[name_to_write] = team_info.pop(name)

            

def get_fuzzy_match(name, list_of_names, user_id):

    best_match, score = process.extractOne(name, list_of_names)
    if score >= HIGH_CONFIDENCE:
        return best_match
    elif LOW_CONFIDENCE <= score < HIGH_CONFIDENCE:
        # prompt user for selection
        return bot.prompt_correction(user_id, name)
    else:
        return None



# define whether or not an exact match exists for a name
def get_exact_match(name, list_of_names):

    for username in list_of_names:
        if username.lower() == name.lower():
            return name
    # no exact match found
    return None


# obtain a list of all known player names from db
def get_all_player_names(connection):
    query = "SELECT name FROM players;"
    with connection.cursor() as cursor:
        cursor.execute(query)
        # Fetch all rows, each containing one name
        names = [row[0] for row in cursor.fetchall()]
    return names 

