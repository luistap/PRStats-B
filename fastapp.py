# BACKEND SERVER AND DATA PIPELINE MODULE
# ALL OTHER MODULES SHALL BE BEST REGARDED AS CLIENTS OF THIS BACKEND

import uvicorn
import os
import datetime
import utilities
import asyncio
from fastapi import FastAPI, File, UploadFile, HTTPException, Form
from fastapi.middleware.cors import CORSMiddleware
from write import write_match_data
from pydantic import BaseModel
from bot import start_bot, confirm_stats, post_match_summary
from stats_manager import global_stats_manager


# define global instances
codes = {}
app = FastAPI()

# Add CORS middleware for development flexibility
app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://scoreboard-packrunners.onrender.com"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class AccessCodeData(BaseModel):
    user_id: str
    access_code: str


async def cleanup_codes(interval: int = 300):
    while True:
        current_time = datetime.datetime.now()
        expired_keys = [key for key, val in codes.items() if val['expires'] < current_time]
        for key in expired_keys:
            del codes[key]
        await asyncio.sleep(interval)


@app.post("/store_access_code/")
async def store_access_code(data: AccessCodeData):
    expiration_time = datetime.datetime.now() + datetime.timedelta(minutes=5)
    codes[data.access_code] = {'user_id': data.user_id, 'expires': expiration_time}
    return {"message": "Access code stored"}


@app.post("/upload/")
async def upload_image(
    team1_names: UploadFile = File(...), 
    team2_names: UploadFile = File(...), 
    team1_stats: UploadFile = File(...), 
    team2_stats: UploadFile = File(...),
    access_code: str = Form(...),
    map: str = Form(...),
    final_score: str = Form(...),
    match_type: str = Form(...)
):
    print("Endpoint Hit: Received images for processing.")
    if access_code in codes and datetime.datetime.now() < codes[access_code]['expires']:
        user_id = codes[access_code]['user_id']
        files = {
            "team1_names": team1_names,
            "team2_names": team2_names,
            "team1_stats": team1_stats,
            "team2_stats": team2_stats
        }

        paths = {}
        for label, file in files.items():
            image_data = await file.read()
            if image_data:  # Check if data is actually received
                print(f"Data for {label} received, size {len(image_data)} bytes")
            else:
                print(f"No data received for {label}")
                continue  # Skip further processing for this file
            paths[label] = save_image(image_data, label)

        gen_info = [map, match_type, final_score]
        team1_info = {}
        team2_info = {}

        # files are saved now process each team
        utilities.process_team(paths['team1_names'], paths['team1_stats'], team1_info)
        utilities.process_team(paths['team2_names'], paths['team2_stats'], team2_info)
        team1_info = utilities.clean_board(team1_info)
        team2_info = utilities.clean_board(team2_info)

        # establish connection to the database
        connection = await utilities.create_connection()
     #   db_names = utilities.get_all_player_names(connection)

       # await utilities.process_names(team1_info.keys(), db_names, user_id, team1_info)
       # await utilities.process_names(team2_info.keys(), db_names, user_id, team2_info)
        
        global_stats_manager.set_teams(team1_info, team2_info)

        await confirm_stats(user_id, team1_info, team2_info)

        team1_info = global_stats_manager.get_team_info('team1')
        team2_info = global_stats_manager.get_team_info('team2')
        # team1 and team2 info now correct, write to the db

        # we write to the db here
        # Assuming conn is your active database connection
        await post_match_summary(team1_info, team2_info, gen_info)
        await write_match_data(connection, team1_info, team2_info, gen_info)

        del codes[access_code]  # delete access code post-write
    else:
        raise HTTPException(status_code=403, detail="Invalid or expired access code.")
    return

def save_image(image_data, label):
    """Save the image to a temporary directory and return the path."""
    os.makedirs('temp_images', exist_ok=True)
    file_path = f'temp_images/{label}.png'
    with open(file_path, 'wb') as image_file:
        image_file.write(image_data)
    return file_path

@app.get("/ping")
def ping():
    return {"message": "pong"}


async def main():

    asyncio.create_task(cleanup_codes())
    # Create a task for the bot
    bot_task = asyncio.create_task(start_bot())
    # Start the FastAPI app
    config = uvicorn.Config(app, host="0.0.0.0", port=8000)
    server = uvicorn.Server(config)
    await server.serve()
    # Wait for the bot task to finish (it generally won't unless there's an error or shutdown)
    await bot_task

if __name__ == "__main__":
    asyncio.run(main())
