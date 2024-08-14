# main module for the discord bot
# initialize the bot and set commands as needed

import discord
from discord.ext import commands
from dotenv import load_dotenv
import os
import asyncio
import secrets
import aiohttp
import botutils
from discord import ButtonStyle
from discord.ui import View, Select, Modal, TextInput
from stats_manager import global_stats_manager
import asyncpg
from google.cloud import storage
import requests
from PIL import Image
from google.oauth2 import service_account
from io import BytesIO
import time




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


client = storage.Client(credentials=credentials, project=credentials.project_id)
bucket_name = os.getenv('BUCKET_NAME')
bucket = client.bucket(bucket_name)


token = os.getenv('TOKEN')
channel_send = 880977932892385330

default_pfp = os.getenv('DEFAULT_PFP')

intents = discord.Intents.default()
intents.messages = True
intents.guilds = True
intents.message_content = True
bot = commands.Bot(command_prefix='!', intents=intents)

correction_completed_event = asyncio.Event()
pool = None

async def init_db():

    global pool
    try:
        print("DB_NAME:", os.getenv('DB_NAME'))
        print("USER:", os.getenv('USER'))
        print("PASSWORD:", os.getenv('PASSWORD'))
        print("HOST_NAME:", os.getenv('HOST_NAME'))
        pool = await asyncpg.create_pool(
            database= os.getenv('DB_NAME'),
            user= os.getenv('PGUSER'),
            password= os.getenv('PGPASSWORD'),
            host= os.getenv('HOST_NAME'),
            ssl="require"
        )
        print("Connection pool created successfully")
    except Exception as e:
        print(f"Failed to create pool: {e}")

async def fetch_data():
    try:
        async with pool.acquire() as conn:
            async with conn.transaction():
                result = await conn.fetch("SELECT * FROM some_table")
                return result
    except Exception as e:
        print(f"An error occurred during fetching data: {e}")
        return None

@bot.command(name='getdata')
async def get_data(ctx):
    data = await fetch_data()
    if data:
        message = "\n".join([str(row) for row in data])
        await ctx.send(message)
    else:
        await ctx.send("Failed to fetch data or no data found.")


@bot.event
async def on_ready():
    await init_db()
    print('Bot is ready and connected to the database!')

@bot.event
async def on_close():
    global pool
    if pool:
        await pool.close()
        print("Connection pool closed")

# Define a function to start the bot
async def start_bot():
    await bot.start(token)


@bot.command(name='list', help='Lists all registered player names in multiple embeds')
async def list_players(ctx):
    async with pool.acquire() as connection:
        player_names = await connection.fetch("SELECT name FROM Players ORDER BY name ASC")
        player_names = [p['name'] for p in player_names]

    names_per_embed = 25  # Adjust this number based on your preference for embed density
    embeds = []

    for i in range(0, len(player_names), names_per_embed):
        embed = discord.Embed(
            title="Registered Player Names",
            description="\n".join(player_names[i:i + names_per_embed]),
            color=discord.Color.blue()
        )
        embed.set_footer(text=f"Showing names {i+1} to {min(i+names_per_embed, len(player_names))} of {len(player_names)}")
        embeds.append(embed)

    # Send all embeds in a sequence
    for embed in embeds:
        await ctx.reply(embed=embed, mention_author=True)





async def post_match_summary(team1_info, team2_info, gen_info):

    channel = bot.get_channel(channel_send)
    if channel:
        # Format the message
        message = f"**Match Summary:**\n**Map:** {gen_info[0]}\n**Match Type:** {gen_info[1]}\n**Score:** {gen_info[2]}\n\n"
        message += "**Team 1 Stats:**\n"
        for player, stats in team1_info.items():
            message += f"{player}: Kills: {stats[0]}, Deaths: {stats[1]}, Assists: {stats[2]}\n"
        message += "\n**Team 2 Stats:**\n"
        for player, stats in team2_info.items():
            message += f"{player}: Kills: {stats[0]}, Deaths: {stats[1]}, Assists: {stats[2]}\n"

        # Send the message
        await channel.send(message)



@bot.command(name='map', help='Get map-specific data')
async def map_stats(ctx, player: str, map_name: str):
    if pool is None:
        await ctx.send("Database connection is not established.")
        return

    try:
        # Fetch player_id based on player name
        player_id = await pool.fetchval(
            "SELECT player_id FROM Players WHERE name = $1", player
        )
        if not player_id:
            await ctx.send("Player not found.")
            return

        # Fetch map_id based on map name
        map_id = await pool.fetchval(
            "SELECT map_id FROM Maps WHERE map_name = $1", map_name
        )
        if map_id is None:
            await ctx.reply("Map not found.")
            return

        # Fetch player stats for the specific map dynamically
        stats = await pool.fetchrow(
            """
            SELECT
                COUNT(*) AS matches_played,
                COUNT(*) FILTER (WHERE ps.result = 'w') AS matches_won,
                COUNT(*) FILTER (WHERE ps.result = 'l') AS matches_lost,
                SUM(ps.kills) AS total_kills,
                SUM(ps.deaths) AS total_deaths
            FROM Player_Stats ps
            JOIN Matches m ON ps.match_id = m.match_id
            WHERE ps.player_id = $1 AND m.map_id = $2
            """, player_id, map_id
        )

        if not stats or stats['matches_played'] == 0:
            await ctx.reply(f"No stats available for {player} on {map_name}.")
            return

        # Calculate K/D ratio, handling division by zero
        kd_ratio = stats['total_kills'] / stats['total_deaths'] if stats['total_deaths'] > 0 else float('inf')

        # Capitalize the first letter of the map name
        map_name_capitalized = map_name.capitalize()

        # Create an embed with a title and fields for each statistic
        embed = discord.Embed(title=f"Stats for {player} on {map_name_capitalized}", color=0x3498db)  # You can change the color code to match your theme
        embed.add_field(name="Matches Played", value=stats['matches_played'], inline=True)
        embed.add_field(name="Matches Won", value=stats['matches_won'], inline=True)
        embed.add_field(name="Matches Lost", value=stats['matches_lost'], inline=True)
        embed.add_field(name="Total Kills", value=stats['total_kills'], inline=True)
        embed.add_field(name="Total Deaths", value=stats['total_deaths'], inline=True)
        embed.add_field(name="K/D Ratio", value=f"{kd_ratio:.2f}", inline=True)

        # Send the embed as a response
        await ctx.reply(embed=embed)
    except Exception as e:
        await ctx.reply(f"An error occurred: {str(e)}")
        print(f"Error: {str(e)}")  # Log the error for debugging purposes



@bot.command(name='h2h', help='Get the head-to-head record between two players')
async def h2h(ctx, player1: str, player2: str):

    # Ensure the database connection
    async with pool.acquire() as connection:

        # do these players exist?
        player1_exists = await botutils.check_player_exists(pool, player1)
        player2_exists = await botutils.check_player_exists(pool, player2)

        if not player1_exists or not player2_exists:

            player_name = player1 if not player1_exists else player2
            # Create an embed message
            embed = discord.Embed(
                title="Player Check",
                description=f"Player name `{player_name}` does not exist in the database.",
                color=discord.Color.red()  # Red color to indicate an issue or non-existence
            )
            embed.set_footer(text="Try checking the spelling or adding them if they're new.")
            await ctx.send(embed=embed)
            return

        # Fetch the H2H record
        record = await fetch_h2h_record(connection, player1, player2)

        if not record:
            await ctx.send("No head-to-head record found between these players.")
            return

        # change to default pfp if no PFP found in db
        if record['player_one_pic'] is None:
            record['player_one_pic'] = default_pfp
        if record['player_two_pic'] is None:
            record['player_two_pic'] = default_pfp

        merged_url = await merge_images(url1=record['player_one_pic'], url2=record['player_two_pic'], standard_size=(256, 256))
        merged_url = generate_image_url(merged_url)
        # Constructing the record description based on player wins
        record_description = f"{record['player_one_name']} has a record of {record['player_one_wins']}-{record['player_two_wins']} against {record['player_two_name']} all-time."

        # Create and send an embed with the record and merged image
        embed = discord.Embed(
            title="Head-to-Head Record",
            description=record_description,
            color=discord.Color.red()
        )
        embed.set_image(url=merged_url) 

        await ctx.reply(embed=embed, mention_author=True)


async def fetch_h2h_record(connection, player1, player2):
    # Fetch player details for both players
    players = await connection.fetch(
        "SELECT player_id, name, profile_pic_url FROM Players WHERE name = $1 OR name = $2",
        player1, player2
    )
    if len(players) < 2:
        return None  # Ensure both players are found

    # Map player names to their data to ensure order
    player_data = {p['name'].lower(): p for p in players}
    player1_data = player_data.get(player1.lower())
    player2_data = player_data.get(player2.lower())

    # Fetch the H2H records
    h2h_query = """
        SELECT 
            player_one_id, player_two_id, player_one_wins, player_two_wins
        FROM H2H_Records
        WHERE (player_one_id = $1 AND player_two_id = $2) 
           OR (player_one_id = $2 AND player_two_id = $1)
    """
    record = await connection.fetchrow(h2h_query, player1_data['player_id'], player2_data['player_id'])
    if not record:
        return None

    # Create a correctly ordered response based on input order, not player_id
    response = {
        'player_one_name': player1,
        'player_two_name': player2,
        'player_one_wins': None,
        'player_two_wins': None,
        'player_one_pic': player1_data['profile_pic_url'],
        'player_two_pic': player2_data['profile_pic_url']
    }

    # Assign wins based on the actual order in the database record
    if player1_data['player_id'] == record['player_one_id']:
        response['player_one_wins'] = record['player_one_wins']
        response['player_two_wins'] = record['player_two_wins']
    else:
        response['player_one_wins'] = record['player_two_wins']
        response['player_two_wins'] = record['player_one_wins']

    return response


async def merge_images(url1, url2, standard_size=(256, 256)):

    response1 = requests.get(url1)
    response2 = requests.get(url2)
    image1 = Image.open(BytesIO(response1.content))
    image2 = Image.open(BytesIO(response2.content))

    image1 = image1.resize(standard_size)
    image2 = image2.resize(standard_size)

    dst = Image.new('RGB', (standard_size[0] * 2, standard_size[1]))
    dst.paste(image1, (0, 0))
    dst.paste(image2, (standard_size[0], 0))

    img_byte_arr = BytesIO()
    dst.save(img_byte_arr, format='PNG')
    img_byte_arr.seek(0)

    file_name = "merged_h2h.png"
    return await upload_to_cloud_storage(img_byte_arr.getvalue(), file_name)


async def upload_to_cloud_storage(image_bytes, file_name):
    """Uploads the image to a cloud storage within the 'merged/' directory and returns the URL."""
    # Prefix the file name with 'merged/' to store it in the correct folder
    merged_file_name = f"merged/{file_name}"
    
    # Create a blob in the bucket at the specified path
    blob = bucket.blob(merged_file_name)
    blob.upload_from_string(image_bytes, content_type='image/png')  # Assuming content type is JPEG

    # Set cache control settings
    blob.cache_control = "no-cache, max-age=0"
    blob.patch()  # Apply the cache control settings

    # Construct and return the public URL for the uploaded image
    public_url = f"https://storage.googleapis.com/{bucket.name}/{blob.name}"
    print(public_url)
    return public_url



def generate_image_url(base_url):
    timestamp = int(time.time())
    return f"{base_url}?v={timestamp}"


@bot.command(name='player', help='Displays general statistics of a player')
async def player_stats(ctx, player_name: str):
    async with pool.acquire() as connection:
        query = """
        SELECT 
            P.profile_pic_url,
            COALESCE(SUM(PS.kills), 0) AS total_kills,
            COALESCE(SUM(PS.deaths), 0) AS total_deaths,
            COUNT(PS.player_id) AS matches_played,
            COALESCE(SUM(CASE WHEN PS.result = 'w' THEN 1 ELSE 0 END), 0) AS matches_won,
            COALESCE(SUM(CASE WHEN PS.result = 'l' THEN 1 ELSE 0 END), 0) AS matches_lost,
            COALESCE(SUM(PS.assists), 0) AS total_assists
        FROM Players P
        LEFT JOIN Player_Stats PS ON P.player_id = PS.player_id
        WHERE P.name = $1
        GROUP BY P.profile_pic_url;
        """
        player = await connection.fetchrow(query, player_name)

        if not player:
            await ctx.send("Player not found.")
            return

        kd_ratio = player['total_kills'] / player['total_deaths'] if player['total_deaths'] > 0 else float(player['total_kills'])
        win_rate = (player['matches_won'] / player['matches_played'] * 100) if player['matches_played'] > 0 else 0
        assists_per_game = player['total_assists'] / player['matches_played'] if player['matches_played'] > 0 else 0

        # Use monospaced font for alignment
        stats_description = (
            f"**Overall KD:** ```{kd_ratio:.2f}```\n"
            f"**Win Rate:** ```{win_rate:.1f}%```\n"
            f"**Total Maps Played:** ```{player['matches_played']}```\n"
            f"**Assists Per Game:** ```{assists_per_game:.1f}```"
        )

        # Create the embed
        embed = discord.Embed(
            title=f"Player Statistics for {player_name}",
            description=stats_description,
            color=discord.Color.red()
        )
        embed.set_thumbnail(url=player['profile_pic_url'])
        embed.set_footer(text="Statistics are updated in real-time based on available data.")

        await ctx.reply(embed=embed, mention_author=True)





@bot.command(name='pfp', help='Upload a new profile picture')
async def upload_pfp(ctx, player_name: str):

    # does the username exist?
    if not await botutils.check_player_exists(pool, player_name):
        # Create an embed message
        embed = discord.Embed(
            title="Player Check",
            description=f"Player name `{player_name}` does not exist in the database.",
            color=discord.Color.red()  # Red color to indicate an issue or non-existence
        )
        embed.set_footer(text="Try checking the spelling or adding them if they're new.")
        await ctx.send(embed=embed)
        return

    # Inform the user and start a DM session
    if ctx.author.dm_channel is None:
        await ctx.author.create_dm()
    await ctx.author.dm_channel.send("Please send the new profile picture as an attachment.")
    
    # Listen for the next message from this user in DM
    def check(message):
        return message.author == ctx.author and message.attachments and isinstance(message.channel, discord.DMChannel)

    try:
        message = await bot.wait_for('message', check=check, timeout=300.0)  # 5 minutes timeout
    except asyncio.TimeoutError:
        await ctx.author.dm_channel.send("You did not send an image in time. Please try the command again if you wish to update your profile picture.")
        return

    attachment = message.attachments[0]  # Corrected to use the received message in DM
    file_extension = os.path.splitext(attachment.filename)[1].lower()
    if file_extension not in ['.png', '.jpg', '.jpeg', '.gif']:
        await ctx.author.dm_channel.send("Please upload a valid image file (png, jpg, jpeg, gif).")
        return

    # Set the filename in the bucket
    file_path = f"images/{ctx.author.id}{file_extension}"
    blob = bucket.blob(file_path)

    # Download the image from Discord and upload to Google Cloud Storage
    image_data = await attachment.read()
    blob.upload_from_string(image_data, content_type=attachment.content_type)
    blob.cache_control = "no-cache, max-age=0"  # Advises no caching
    blob.patch()  # Apply the cache control settings

    # Form the public URL
    public_url = f"https://storage.googleapis.com/{bucket.name}/{blob.name}"

    # Use the global pool to execute the update
    try:
        async with pool.acquire() as connection:
            await connection.execute(
                "UPDATE Players SET profile_pic_url = $1 WHERE name = $2",
                public_url, player_name
            )
        await ctx.author.dm_channel.send(f"Profile picture for {player_name} uploaded successfully! URL: {public_url}")
    except Exception as e:
        await ctx.author.dm_channel.send(f"Failed to update profile picture for {player_name} in the database.")
        print(f"Database update error: {e}")


class ConfirmationModal(Modal):
    def __init__(self, title="Enter the correct value", player=None, team1_info=None, team2_info=None, selected_stat=None):
        super().__init__(title=title)
        self.player = player
        self.selected_stat = selected_stat
        self.team1_info = team1_info
        self.team2_info = team2_info
        self.add_item(TextInput(label="Value:", placeholder="Enter the correct value"))

    async def on_submit(self, interaction: discord.Interaction):
        corrected_value = self.children[0].value
        # Determine which team the player is in and the index for the stat
        team = 'team1' if self.player in global_stats_manager.get_team_info('team1') else 'team2'
        stat_indices = {'Kills': 0, 'Deaths': 1, 'Assists': 2}
        
        if self.selected_stat in stat_indices:
            # For numerical stats like Kills, Deaths, Assists
            stat_index = stat_indices[self.selected_stat]
            global_stats_manager.update_stat(team, self.player, stat_index, int(corrected_value))
        elif self.selected_stat == "Name":
            # Special case for updating names
            global_stats_manager.update_name(team, corrected_value, self.player)
            
        embed = discord.Embed(title="Your Modal Results", color=discord.Color.blurple())
        embed.add_field(name="Corrected Value", value=corrected_value, inline=False)
        embed.add_field(name="Updated stats: Team 1", value=botutils.format_player_stats(global_stats_manager.get_team_info('team1')), inline=False)
        embed.add_field(name="Updated stats: Team 2", value=botutils.format_player_stats(global_stats_manager.get_team_info('team2')), inline=False)
        await interaction.response.send_message(embed=embed, ephemeral=True)
        # Reinstate the confirmation view to allow further corrections
        view = ConfirmationView(interaction.user.id, self.team1_info, self.team2_info)
        await interaction.followup.send("Would you like to make more corrections?", view=view)

class StatCorrectionSelect(Select):
    def __init__(self, player, team1_info, team2_info):
        self.player = player
        self.team1_info = team1_info
        self.team2_info = team2_info
        options = [
            discord.SelectOption(label="Name", description="Correct the player's name"),
            discord.SelectOption(label="Kills", description="Correct the number of kills"),
            discord.SelectOption(label="Deaths", description="Correct the number of deaths"),
            discord.SelectOption(label="Assists", description="Correct the number of assists"),
        ]
        super().__init__(placeholder="Select the stat to correct", min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction):
        selected_stat = self.values[0]
        modal = ConfirmationModal(title=f"Correcting {selected_stat} for {self.player}", 
                                  player=self.player, team1_info=self.team1_info, team2_info=self.team2_info, selected_stat=self.values[0])
        await interaction.response.send_modal(modal)

class PlayerSelect(Select):
    def __init__(self, team1_info, team2_info):
        self.team1_info = team1_info
        self.team2_info = team2_info
        options = [
            discord.SelectOption(label=player, description="Team 1") for player in team1_info
        ] + [
            discord.SelectOption(label=player, description="Team 2") for player in team2_info
        ]
        super().__init__(placeholder="Choose a player to correct", min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction):
        selected_player = self.values[0]
        self.view.clear_items()  # Clear previous items in the view
        self.view.add_item(StatCorrectionSelect(selected_player, self.team1_info, self.team2_info))
        await interaction.response.edit_message(content=f"You selected {selected_player}. What needs correction?", view=self.view)

class ConfirmationView(View):
    def __init__(self, user_id, team1_info, team2_info):
        super().__init__(timeout=180)
        self.user_id = user_id
        self.team1_info = team1_info
        self.team2_info = team2_info
        self.add_item(PlayerSelect(team1_info, team2_info))

    @discord.ui.button(label="Done", style=ButtonStyle.green, custom_id="confirm_done")
    async def confirm_done(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message("Corrections are complete. Thank you!", ephemeral=True)
        correction_completed_event.set()
        

async def confirm_stats(user_id, team1_info, team2_info):
    user = await bot.fetch_user(user_id)
    if user:
        raw_team1 = botutils.format_player_stats(team1_info)
        raw_team2 = botutils.format_player_stats(team2_info)
        dm_channel = await user.create_dm()
        view = ConfirmationView(user_id, team1_info, team2_info)
        await dm_channel.send("Please review the stats and make corrections as needed.\n" + raw_team1 + "\n" + raw_team2, view=view)
        await correction_completed_event.wait()  # Wait until the corrections are confirmed as done
        correction_completed_event.clear()  # Reset the event for future use


# obtain correction from user mid-pipeline
async def prompt_correction(user_id, extracted_name):
    user = await bot.fetch_user(user_id)
    if user:
        dm_channel = await user.create_dm()
        message = (f"OCR extracted the name '{extracted_name}'. "
                   "Please reply with the correct name.")
        await dm_channel.send(message)

@bot.command(name='upload', help='Fetch a screenshot from users and provide an access code.')
async def upload(ctx):
    if not ctx.author.guild_permissions.administrator:
        await ctx.send("You do not have permission to perform this action.")
        return

    # Generate a temporary access code
    access_code = secrets.token_urlsafe(8)  # Generates a secure random token

    # Send the access code to the user's DM
    try:
        message = f"Your access code is: ```{access_code}```\nIt will expire in 5 minutes."
        await ctx.author.send(message)
        await ctx.send("Access code sent to your DMs.")
        # Prepare to send the access code and user ID to the backend
        backend_url = 'http://127.0.0.1:8000/store_access_code/'
        json_data = {
            'user_id': str(ctx.author.id),
            'access_code': access_code
        }

        # Send data to backend using aiohttp
        async with aiohttp.ClientSession() as session:
            headers = {'Content-Type': 'application/json'}  # Ensuring headers are set
            async with session.post(backend_url, json=json_data, headers=headers) as response:
                if response.status == 200:
                    print("Access code successfully sent to backend.")
                else:
                    print("Failed to send access code to backend.")
                    await ctx.send("Failed to process access code.")
    except Exception as e:
        print(f"Error: {str(e)}")
        await ctx.send("Failed to send DM. Please check your DM settings.")

