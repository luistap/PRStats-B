
async def write_match_data(connection, team1_info, team2_info, gen_info):
    map_name, match_type, final_score = gen_info
    map_name = map_name.lower()
    match_type = match_type.lower()
    team1_score, team2_score = map(int, final_score.split('-'))


    # Ensure map and match type exist and get their IDs
    map_id = await ensure_exists(connection, 'Maps', 'map_name', map_name, 'map_id')
    match_type_id = await ensure_exists(connection, 'Match_Types', 'description', match_type, 'match_type_id')

    # Insert the match and get its ID
    match_id = await insert_match(connection, map_id, match_type_id, final_score)

    # Process stats for each team
    await process_team_stats(connection, match_id, team1_info, team1_score, team2_score)
    await process_team_stats(connection, match_id, team2_info, team2_score, team1_score)

    # Update head-to-head records
    await update_h2h_records(connection, team1_info, team2_info, team1_score, team2_score)

async def ensure_exists(connection, table, column, value, id_column):
    """Ensure the entity exists in the database and return its ID. Insert if not exists."""
    query = f"SELECT {id_column} FROM {table} WHERE {column} = $1"
    entity_id = await connection.fetchval(query, value)
    if entity_id is None:
        if table == 'Players':
            # Insert new player since it's expected that new players might not exist
            insert_query = f"INSERT INTO {table} ({column}) VALUES ($1) RETURNING {id_column}"
            entity_id = await connection.fetchval(insert_query, value)
        else:
            # For maps and match types, raise an error as these are expected to be preloaded
            raise ValueError(f"Expected entity '{value}' not found in table '{table}'. Please check your database initialization.")
    return entity_id



async def insert_match(connection, map_id, match_type_id, score):
    """Insert a match record and return the match ID."""
    query = """
        INSERT INTO Matches (map_id, match_type_id, score, date)
        VALUES ($1, $2, $3, NOW())
        RETURNING match_id
    """
    return await connection.fetchval(query, map_id, match_type_id, score)

async def process_team_stats(connection, match_id, team_info, team_score, opponent_score):
    """Insert player stats and update aggregate stats for each player."""
    result = 'w' if team_score > opponent_score else 'l'
    for player_name, stats in team_info.items():
        player_id = await ensure_exists(connection, 'Players', 'name', player_name, 'player_id')
        kills, deaths, assists = stats
        await insert_player_stats(connection, player_id, match_id, kills, deaths, assists, result)
        await update_player_aggregate_stats(connection, player_id, kills, deaths, assists, team_score, opponent_score)

async def insert_player_stats(connection, player_id, match_id, kills, deaths, assists, result):
    """Insert player stats for a single match."""
    query = """
        INSERT INTO Player_Stats (player_id, match_id, kills, deaths, assists, result)
        VALUES ($1, $2, $3, $4, $5, $6)
    """
    await connection.execute(query, player_id, match_id, kills, deaths, assists, result)

async def update_player_aggregate_stats(connection, player_id, kills, deaths, assists, wins, losses):
    """Update aggregate stats for a player."""
    query = """
        INSERT INTO Player_Aggregate_Stats (player_id, map_id, match_type_id, total_kills, total_deaths, total_assists, matches_played, matches_won, matches_lost)
        VALUES ($1, NULL, NULL, $2, $3, $4, 1, $5, $6)
        ON CONFLICT (player_id, map_id, match_type_id)
        DO UPDATE SET
            total_kills = Player_Aggregate_Stats.total_kills + EXCLUDED.total_kills,
            total_deaths = Player_Aggregate_Stats.total_deaths + EXCLUDED.total_deaths,
            total_assists = Player_Aggregate_Stats.total_assists + EXCLUDED.total_assists,
            matches_played = Player_Aggregate_Stats.matches_played + 1,
            matches_won = Player_Aggregate_Stats.matches_won + EXCLUDED.matches_won,
            matches_lost = Player_Aggregate_Stats.matches_lost + EXCLUDED.matches_lost
    """
    await connection.execute(query, player_id, kills, deaths, assists, (1 if wins > losses else 0), (1 if losses > wins else 0))


async def update_h2h_records(connection, team1_info, team2_info, team1_score, team2_score):
    """ Update H2H records for all combinations of players from two teams """
    team1_won = team1_score > team2_score
    for player1 in team1_info.keys():
        player1_id = await ensure_exists(connection, 'Players', 'name', player1, 'player_id')
        for player2 in team2_info.keys():
            player2_id = await ensure_exists(connection, 'Players', 'name', player2, 'player_id')
            if player1_id and player2_id:
                # Ensure player_one_id is always less than player_two_id
                if player1_id < player2_id:
                    await update_individual_h2h_record(connection, player1_id, player2_id, team1_won)
                else:
                    await update_individual_h2h_record(connection, player2_id, player1_id, not team1_won)

async def update_individual_h2h_record(connection, player_one_id, player_two_id, team1_won):
    """ Insert or update an individual H2H record """
    query = """
        INSERT INTO H2H_Records (player_one_id, player_two_id, player_one_wins, player_two_wins)
        VALUES ($1, $2, $3, $4)
        ON CONFLICT (player_one_id, player_two_id)
        DO UPDATE SET
            player_one_wins = H2H_Records.player_one_wins + EXCLUDED.player_one_wins,
            player_two_wins = H2H_Records.player_two_wins + EXCLUDED.player_two_wins;
    """
    wins_for_player_one = 1 if team1_won else 0
    wins_for_player_two = 1 if not team1_won else 0
    await connection.execute(query, player_one_id, player_two_id, wins_for_player_one, wins_for_player_two)


