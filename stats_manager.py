class StatsManager:
    def __init__(self):
        self.team1_info = {}
        self.team2_info = {}

    def get_team_info(self, team):
        if team == 'team1':
            return self.team1_info
        elif team == 'team2':
            return self.team2_info
    
    def set_teams(self, team1_info, team2_info):
        self.team1_info = team1_info
        self.team2_info = team2_info
        print("set teams")

    def update_team_info(self, team, player, stats):
        team_info = self.get_team_info(team)
        if team_info is not None:
            team_info[player] = stats

    def update_name(self, team, new_name, old_name):
        team_info = self.get_team_info(team)
        if old_name in team_info:
            # Capture the current stats under the old name
            player_stats = team_info.pop(old_name)
            # Assign these stats to the new name
            team_info[new_name] = player_stats

    def update_stat(self, team, player, stat_index, value):
        team_info = self.get_team_info(team)
        if player in team_info:
            # Ensure the stat_index is valid for the stats list
            if stat_index < len(team_info[player]):
                team_info[player][stat_index] = value
            else:
                # Optionally handle the case where the stat_index is out of range
                print(f"Stat index {stat_index} is out of range for player {player}")

# Create a global instance that can be imported and used throughout your application
global_stats_manager = StatsManager()
