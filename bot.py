# main module for the discord bot
# initialize the bot and set commands as needed

import discord
from discord.ext import commands, tasks
from dotenv import load_dotenv
import os
import asyncio
import secrets
import aiohttp
import botutils
from discord import ButtonStyle
from discord.ui import View, Select, Modal, TextInput, Button
from stats_manager import global_stats_manager
import asyncpg
from google.cloud import storage
from google.oauth2 import service_account
from discord.utils import get
import gspread

'''
os.environ['GOOGLE_APPLICATION_CREDENTIALS'] = 'service_creds.json'
load_dotenv()
'''


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

stat_ops_id = 1400932740043636807

client = storage.Client(credentials=credentials, project=credentials.project_id)
bucket_name = os.getenv('BUCKET_NAME')
bucket = client.bucket(bucket_name)


token = os.getenv('TOKEN')
channel_send = 1276412274705432650

GUILD_ID = 880977932456194119

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
    bot.add_view(ApplicationView())
    print('Bot is ready and connected to the database!')
    process_sheet_approvals.start()


@bot.event
async def on_close():
    global pool
    if pool:
        await pool.close()
        print("Connection pool closed")

# Define a function to start the bot
async def start_bot():
    await bot.start(token)


class ApplicationView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)  # Set timeout to None for persistence

    @discord.ui.button(label="Apply", style=discord.ButtonStyle.green, custom_id="application:apply")
    async def apply_button(self, interaction: discord.Interaction, button: discord.ui.Button):

        user_id = interaction.user.id
        # do we have a matching ID in the database?
        async with pool.acquire() as connection:
            existing_app = await connection.fetch('SELECT 1 FROM tms_apps WHERE discord_id = $1', user_id)
            if existing_app:
                await interaction.response.send_message("You have already submitted an application.", ephemeral=True)
                return

        modal = app_modal()
        await interaction.response.send_modal(modal)


class app_modal(Modal):
    def __init__(self, title="Application form"):
        super().__init__(title=title)
        self.add_item(TextInput(label="In-game handle"))
        self.add_item(TextInput(label="R6 Tracker Link"))


    async def on_submit(self, interaction: discord.Interaction):

        await interaction.response.send_message("Application sent.", ephemeral=True)
        handle = self.children[0].value
        tracker_link = self.children[1].value
        discord_id = interaction.user.id
        creation_date = interaction.user.created_at
        # check name match in db
        async with pool.acquire() as connection:
            player_id = await connection.fetchval('SELECT player_id FROM Players WHERE name = $1', handle)
            # Insert the new application record
            await connection.execute('''
                INSERT INTO tms_apps (player_id, discord_id, name, tracker_link)
                VALUES ($1, $2, $3, $4)
            ''', player_id, discord_id , handle, tracker_link)
        
        await botutils.add_to_sheet(handle, tracker_link, discord_id, creation_date)
        await botutils.notify_admin(interaction.client)
        return



@bot.command(name='apply')
async def start_application(ctx):
    embed = discord.Embed(
        title="Application Process",
        description="Click the button below to submit a new application.",
        color=discord.Color.orange()
    )
    view = ApplicationView()  # Use the persistent view
    await ctx.send(embed=embed, view=view)



@bot.command(name='list', help='Download a file with all registered player names')
async def list_players(ctx):
    async with pool.acquire() as connection:
        player_names = await connection.fetch("SELECT name FROM Players ORDER BY name ASC")
        player_names = [p['name'] for p in player_names]

    # Write to a text file
    with open('names.txt', 'w') as file:
        file.write('\n'.join(player_names))

    # Send the file in Discord
    with open('names.txt', 'rb') as file:
        await ctx.reply("Here's the list of all registered players:", file=discord.File(file, 'names.txt'))


async def post_match_summary(team1_info, team2_info, gen_info):
    channel = bot.get_channel(channel_send)
    if channel:
        # Creating the embed
        embed = discord.Embed(
            title="Match Summary",
            description=f"**Map:** {gen_info[0]}\n**Match Type:** {gen_info[1]}\n**Score:** {gen_info[2]}",
            color=discord.Color.blue()  # You can change the color as needed
        )
        
        # Team 1 Stats
        team1_stats = "\n".join([f"{player}: Kills: {stats[0]}, Deaths: {stats[1]}, Assists: {stats[2]}" for player, stats in team1_info.items()])
        embed.add_field(name="Team 1 Stats", value=team1_stats, inline=False)
        
        # Team 2 Stats
        team2_stats = "\n".join([f"{player}: Kills: {stats[0]}, Deaths: {stats[1]}, Assists: {stats[2]}" for player, stats in team2_info.items()])
        embed.add_field(name="Team 2 Stats", value=team2_stats, inline=False)

        # Send the message with the embed
        await channel.send(embed=embed)



@bot.command(name='map', help='Get map-specific data')
async def map_stats(ctx, player: str, map_name: str):
    if pool is None:
        await ctx.send("Database connection is not established.")
        return

    try:
        # Fetch player_id based on player name
        player_id = await pool.fetchval(
            "SELECT player_id FROM Players WHERE name ILIKE $1", player
        )
        if not player_id:
            await ctx.send("Player not found.")
            return

        # Fetch map_id based on map name
        map_id = await pool.fetchval(
            "SELECT map_id FROM Maps WHERE map_name ILIKE $1", map_name
        )
        if map_id is None:
            await ctx.reply("Map not found.")
            return
        
        full_name = await pool.fetchval(
            "SELECT full_name FROM Maps WHERE map_name ILIKE $1", map_name
        )
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
            await ctx.reply(f"No stats available for {player} on {full_name}.")
            return

        # Calculate K/D ratio, handling division by zero
        kd_ratio = stats['total_kills'] / stats['total_deaths'] if stats['total_deaths'] > 0 else float('inf')

        # Capitalize the first letter of the map name
        map_name_capitalized = full_name.capitalize()

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

        # Constructing the record description based on player wins
        record_description = f"{record['player_one_name']} has a record of {record['player_one_wins']}-{record['player_two_wins']} against {record['player_two_name']} all-time."

        # Create and send an embed with the record and merged image
        embed = discord.Embed(
            title="Head-to-Head Record",
            description=record_description,
            color=discord.Color.red()
        )

        await ctx.reply(embed=embed, mention_author=True)


async def fetch_h2h_record(connection, player1, player2):
    # Fetch player details for both players
    players = await connection.fetch(
        "SELECT player_id, name FROM Players WHERE name ILIKE $1 OR name ILIKE $2",
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
        'player_one_name': player1_data['name'],
        'player_two_name': player2_data['name'],
        'player_one_wins': None,
        'player_two_wins': None
    }

    # Assign wins based on the actual order in the database record
    if player1_data['player_id'] == record['player_one_id']:
        response['player_one_wins'] = record['player_one_wins']
        response['player_two_wins'] = record['player_two_wins']
    else:
        response['player_one_wins'] = record['player_two_wins']
        response['player_two_wins'] = record['player_one_wins']

    return response

# !player command, for tournament stats
@bot.command(name='player', help='Displays general statistics of a player')
async def player_stats(ctx, player_name: str):
    async with pool.acquire() as connection:
        query = """
        SELECT 
            P.name AS registered_name,
            COALESCE(SUM(PS.kills), 0) AS total_kills,
            COALESCE(SUM(PS.deaths), 0) AS total_deaths,
            COUNT(PS.player_id) AS matches_played,
            COALESCE(SUM(CASE WHEN PS.result = 'w' THEN 1 ELSE 0 END), 0) AS matches_won,
            COALESCE(SUM(CASE WHEN PS.result = 'l' THEN 1 ELSE 0 END), 0) AS matches_lost,
            COALESCE(SUM(PS.assists), 0) AS total_assists
        FROM Players P
        LEFT JOIN Player_Stats PS ON P.player_id = PS.player_id
        WHERE P.name ILIKE $1
        GROUP BY P.name;
        """
        player = await connection.fetchrow(query, player_name)

        if not player:
            embed = discord.Embed(
                title="Player Check",
                description=f"Player name `{player_name}` does not exist in the database.",
                color=discord.Color.red()
            )
            embed.set_footer(text="Try checking the spelling or adding them if they're new.")
            await ctx.reply(embed=embed)
            return

        kd_ratio = player['total_kills'] / player['total_deaths'] if player['total_deaths'] > 0 else float(player['total_kills'])
        win_rate = (player['matches_won'] / player['matches_played'] * 100) if player['matches_played'] > 0 else 0
        assists_per_game = player['total_assists'] / player['matches_played'] if player['matches_played'] > 0 else 0
        kills_per_game = player['total_kills'] / player['matches_played'] if player['matches_played'] > 0 else 0

        stats_description = (
            f"**Overall KD:** ```{kd_ratio:.2f}```\n"
            f"**Win Rate:** ```{win_rate:.1f}%```\n"
            f"**Total Maps Played:** ```{player['matches_played']}```\n"
            f"**Kills / Game:** ```{kills_per_game:.1f}```\n"
            f"**Assists / Game:** ```{assists_per_game:.1f}```"
        )

        embed = discord.Embed(
            title=f"Player Statistics for {player['registered_name']}",
            description=stats_description,
            color=discord.Color.red()
        )
        embed.set_footer(text="Statistics are updated in real-time based on available data.")

        await ctx.reply(embed=embed, mention_author=True)



class ConfirmationModal(Modal):
    def __init__(self, title, player, session_id, selected_stat=None):
        super().__init__(title=title)
        self.player = player
        self.selected_stat = selected_stat
        self.session_id = session_id
        self.add_item(TextInput(label="Value:", placeholder="Enter the correct value"))

    async def on_submit(self, interaction: discord.Interaction):
        corrected_value = self.children[0].value
        # Determine which team the player is in and the index for the stat
        team = 'team1' if self.player in global_stats_manager.get_team_info(self.session_id, 'team1') else 'team2'
        stat_indices = {'Kills': 0, 'Deaths': 1, 'Assists': 2}
        
        if self.selected_stat in stat_indices:
            # For numerical stats like Kills, Deaths, Assists
            stat_index = stat_indices[self.selected_stat]
            global_stats_manager.update_stat(self.session_id, team, self.player, stat_index, int(corrected_value))
        elif self.selected_stat == "Name":
            # Special case for updating names
            global_stats_manager.update_name(self.session_id, corrected_value, self.player)
            
        embed = discord.Embed(title="Your Modal Results", color=discord.Color.blurple())
        embed.add_field(name="Corrected Value", value=corrected_value, inline=False)
        embed.add_field(name="Updated stats: Team 1", value=botutils.format_player_stats(global_stats_manager.get_team_info(self.session_id, 'team1')), inline=False)
        embed.add_field(name="Updated stats: Team 2", value=botutils.format_player_stats(global_stats_manager.get_team_info(self.session_id, 'team2')), inline=False)
        await interaction.response.send_message(embed=embed, ephemeral=True)
        # Reinstate the confirmation view to allow further corrections
        view = ConfirmationView(interaction.user.id, self.session_id)
        await interaction.followup.send("Would you like to make more corrections?", view=view)

class StatCorrectionSelect(Select):
    def __init__(self, player, session_id):
        self.player = player
        self.session_id = session_id
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
                                  player=self.player, session_id=self.session_id, selected_stat=self.values[0])
        await interaction.response.send_modal(modal)

class PlayerSelect(Select):
    def __init__(self, team1_info, team2_info, session_id):
        self.team1_info = team1_info
        self.team2_info = team2_info
        self.session_id = session_id
        options = [
            discord.SelectOption(label=player, description="Team 1") for player in team1_info
        ] + [
            discord.SelectOption(label=player, description="Team 2") for player in team2_info
        ]
        super().__init__(placeholder="Choose a player to correct", min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction):
        selected_player = self.values[0]
        self.view.clear_items()  # Clear previous items in the view
        self.view.add_item(StatCorrectionSelect(selected_player, self.session_id))
        await interaction.response.edit_message(content=f"You selected {selected_player}. What needs correction?", view=self.view)

class ConfirmationView(View):
    def __init__(self, user_id, session_id):
        super().__init__(timeout=None)
        self.user_id = user_id
        team1_info = global_stats_manager.get_team_info(session_id, 'team1')
        team2_info = global_stats_manager.get_team_info(session_id, 'team2')
        self.session_id = session_id
        self.add_item(PlayerSelect(team1_info, team2_info, session_id))

    @discord.ui.button(label="Done", style=ButtonStyle.green, custom_id="confirm_done")
    async def confirm_done(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message("Corrections are complete. Thank you!", ephemeral=True)
        correction_completed_event.set()


async def confirm_stats(user_id, session_id):
    user = await bot.fetch_user(user_id)
    if user:
        team1_info = global_stats_manager.get_team_info(session_id, 'team1')
        team2_info = global_stats_manager.get_team_info(session_id, 'team2')
        raw_team1 = botutils.format_player_stats(team1_info)
        raw_team2 = botutils.format_player_stats(team2_info)
        dm_channel = await user.create_dm()
        view = ConfirmationView(user_id, session_id)
        await dm_channel.send("Please review the stats and make corrections as needed.\n" + raw_team1 + "\n" + raw_team2, view=view)
        await correction_completed_event.wait()  # Wait until the corrections are confirmed as done
        correction_completed_event.clear()  # Reset the event for future use

@bot.command(name='upload', help='Fetch a screenshot from users and provide an access code.')
async def upload(ctx):
    if not any(role.id == stat_ops_id for role in ctx.author.roles):
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





# APP PROCESSING FUNCTION(S)

@tasks.loop(minutes=1)
async def process_sheet_approvals():
    try:
        print("🔁 Checking Google Sheet for new approvals...")

        # Setup creds and Sheets API
        scope = [
            'https://spreadsheets.google.com/feeds',
            'https://www.googleapis.com/auth/spreadsheets',
            'https://www.googleapis.com/auth/drive.file',
            'https://www.googleapis.com/auth/drive'
        ]
        service_account_info = {
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
        }
        creds = service_account.Credentials.from_service_account_info(service_account_info, scopes=scope)
        client = gspread.authorize(creds)

        # Open sheet and pull all data
        sheet = client.open("Packrunners TMs").sheet1
        rows = sheet.get_all_values()

        for i, row in enumerate(rows[1:], start=2):  # skip header, start at row 2
            if len(row) < 5:
                continue

            name, tracker_link, discord_id, created_at, approved, denied = row[:6]
            approved = str(approved).strip().lower()
            denied = str(denied).strip().lower()
            already_processed = len(row) >= 7 and row[6].strip().lower().startswith("processed")


            if (approved in ["TRUE", "true"] or denied in ["true", "TRUE"]) and not already_processed:
                # Fetch member
                guild = await bot.fetch_guild(GUILD_ID)
                member = guild.get_member(int(discord_id)) or await guild.fetch_member(int(discord_id))

                if member is None:
                    print(f"⚠️ Couldn't find member with ID {discord_id}")
                    continue

                role_name = "Accepted" if approved.lower() == "true" else "Denied"
                
                # Assign role
                role = get(guild.roles, name=role_name)  # ✅ use exact role name here
                if role:
                    await member.add_roles(role)
                    print(f"✅ Gave role to {member.display_name}")

                # Update DB (PostgreSQL)
                async with pool.acquire() as conn:
                    await conn.execute("""
                        UPDATE tms_apps
                        SET approval_status = $1
                        WHERE discord_id::text = $2
                    """, role_name, discord_id)

                # Mark the sheet row as processed
                sheet.update(            
                        f"G{i}",
                        [["Processed"]],
                        value_input_option="USER_ENTERED"   
                    )

    except Exception as e:
        print("Error in approval sync:", e)


