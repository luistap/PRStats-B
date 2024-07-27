# helper functions for bot operations


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

        query = "SELECT EXISTS(SELECT 1 FROM Players WHERE name = $1)"
        exists = await connection.fetchval(query, player_name)
        return exists
    

