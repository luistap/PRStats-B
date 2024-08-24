# helper functions for bot operations

import gspread
import os
from google.oauth2 import service_account

STAT_TYPE_ORDER = ["Kills", "Deaths", "Assists"]

def format_player_stats(team_info):
    formatted_message = ""
    for player, stats in team_info.items():
        formatted_message += f"{player}: Kills - {stats[0]}, Deaths - {stats[1]}, Assists - {stats[2]}\n"
    return formatted_message


async def check_player_exists(pool, player_name):
    """
    Check if a player exists in the database by name.

    :param connection: The database connection object.
    :param player_name: The name of the player to check.
    :return: True if the player exists, False otherwise.
    """

    async with pool.acquire() as connection:

        query = "SELECT EXISTS(SELECT 1 FROM Players WHERE name ILIKE $1)"
        exists = await connection.fetchval(query, player_name)
        return exists
    

async def add_to_sheet(name, tracker_link, discord_id):
    # Define the scope of the application
    scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/spreadsheets', 'https://www.googleapis.com/auth/drive.file', 'https://www.googleapis.com/auth/drive']

    # Gather service account info from environment variables
    service_account_info = {
        "type": os.getenv("GOOGLE_TYPE"),
        "project_id": os.getenv("GOOGLE_PROJECT_ID"),
        "private_key_id": os.getenv("GOOGLE_PRIVATE_KEY_ID"),
        "private_key": os.getenv("GOOGLE_PRIVATE_KEY").replace('\\n', '\n'),  # Ensuring proper new line handling
        "client_email": os.getenv("GOOGLE_CLIENT_EMAIL"),
        "client_id": os.getenv("GOOGLE_CLIENT_ID"),
        "auth_uri": os.getenv("GOOGLE_AUTH_URI"),
        "token_uri": os.getenv("GOOGLE_TOKEN_URI"),
        "auth_provider_x509_cert_url": os.getenv("GOOGLE_AUTH_PROVIDER_X509_CERT_URL"),
        "client_x509_cert_url": os.getenv("GOOGLE_CLIENT_X509_CERT_URL")
    }

    # Authenticate using the service account
    creds = service_account.Credentials.from_service_account_info(service_account_info, scopes=scope)
    client = gspread.authorize(creds)

    # Open the spreadsheet by its title
    sheet = client.open("Packrunners: TMs").sheet1  # Access the first sheet in the spreadsheet
    # Append a row with the new data
    sheet.append_row([name, tracker_link, str(discord_id)])