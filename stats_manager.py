class StatsManager:
    def __init__(self):
        self.sessions = {}  # key = session_id (access_code), value = {'team1': {...}, 'team2': {...}}

    def set_teams(self, session_id, team1_info, team2_info):
        self.sessions[session_id] = {'team1': team1_info, 'team2': team2_info}
        print(f"Set teams for session: {session_id}")

    def get_team_info(self, session_id, team):
        return self.sessions.get(session_id, {}).get(team, {})

    def update_stat(self, session_id, team, player, stat_index, value):
        team_info = self.get_team_info(session_id, team)
        if player in team_info:
            if stat_index < len(team_info[player]):
                team_info[player][stat_index] = value
            else:
                print(f"Stat index {stat_index} out of range for {player} in {team}")
        else:
            print(f"Player {player} not found in {team}")

    def update_name(self, session_id, new_name, old_name):
        for team in ['team1', 'team2']:
            team_info = self.get_team_info(session_id, team)
            if old_name in team_info:
                team_info[new_name] = team_info.pop(old_name)

    def clear_session(self, session_id):
        if session_id in self.sessions:
            del self.sessions[session_id]
