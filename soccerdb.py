# coding: utf-8
import numpy as np
import pandas as pd
import sqlite3
from lxml import etree
from dataclasses import dataclass

DB_PATH = "./data/database.sqlite"
conn = None


@dataclass
class Player:
    id: int
    name: str
    valid: bool = True


@dataclass
class Team:
    id: int
    api_id: int
    longname: str
    shortname: str


@dataclass
class Match:
    match_id: int
    match_api_id: int
    country: str
    league: str
    hometeam: str
    awayteam: str
    home_goals: int
    away_goals: int
    events: list

    def __str__(self):
        return f"Match(match_id={self.match_id}, match_api_id={self.match_api_id}, country={self.country}, league={self.league}, hometeam={self.hometeam}, awayteam={self.awayteam}, home_goals={self.home_goals}, away_goals={self.away_goals})"

    def clone(self):
        c = Match()
        c.match_id = self.match_id
        c.match_api_id = self.match_api_id
        c.country = self.country
        c.league = self.league
        c.hometeam = self.hometeam
        c.awayteam = self.awayteam
        c.home_goals = self.home_goals
        c.away_goals = self.away_goals
        c.events = list(self.events)

        return c

    def score(self):
        if self.events is not None:
            self.home_goals = sum(
                [
                    1
                    for event in self.events
                    if event["type"] == "goal" and event["team"] == "home"
                ]
            )
            self.away_goals = sum(
                [
                    1
                    for event in self.events
                    if event["type"] == "goal" and event["team"] == "away"
                ]
            )
        return "%s:%s" % (self.home_goals, self.away_goals)

    def result(self):
        if self.home_goals == self.away_goals:
            return "tie"
        if self.home_goals > self.away_goals:
            return "home-win"
        else:
            return "away-win"

    def versus(self):
        return "%s vs. %s" % (self.hometeam, self.awayteam)

    def winner(self):
        r = self.result()
        if r == "tie":
            return None
        if r == "home-win":
            return self.hometeam
        else:
            return self.awayteam

    def __init__(self, dbentry=None):
        if dbentry is None:
            return

        self.dbentry = dbentry

        self.match_id = dbentry["id"].values[0]
        self.match_api_id = dbentry["match_api_id"].values[0]

        self.country = dbentry["CountryName"].values[0]
        self.league = dbentry["LeagueName"].values[0]
        self.hometeam = dbentry["HomeTeamName"].values[0]
        self.awayteam = dbentry["AwayTeamName"].values[0]
        self.home_goals = dbentry["HomeTeamGoal"].values[0]
        self.away_goals = dbentry["AwayTeamGoal"].values[0]
        self.events = []


def get_team(team_id: int, attr="team_api_id"):
    teamdata = teams[teams[attr] == team_id]
    if teamdata.empty:
        return None

    tdata = Team(
        id=teamdata["id"].values[0],
        api_id=teamdata["team_api_id"].values[0],
        longname=teamdata["team_long_name"].values[0],
        shortname=teamdata["team_short_name"].values[0],
    )
    return tdata


def get_player(player_id: int):
    if not type(player_id) is int:
        player_id = player_id.item()
    try:
        prow = players[players["player_api_id"] == player_id]
        return Player(
            id=int(prow.index.values[0]), name=prow.player_name.values[0], valid=True
        )
    except: # noqa
        return Player(id=player_id, name="unknown", valid=False)


def gather_players(player_id_list: list):
    results = []
    for player_id in player_id_list:
        pdata = get_player(player_id)
        if not pdata:
            continue
        results.append(pdata)
    return results


def match_players(match_id: int):
    df = pd.read_sql_query(
        "SELECT * FROM Match WHERE Match.id = :matchid",
        conn,
        params={"matchid": match_id},
    )

    home_fields = [
        "home_player_1",
        "home_player_2",
        "home_player_3",
        "home_player_4",
        "home_player_5",
        "home_player_6",
        "home_player_7",
        "home_player_8",
        "home_player_9",
        "home_player_10",
        "home_player_11",
    ]
    away_fields = [
        "away_player_1",
        "away_player_2",
        "away_player_3",
        "away_player_4",
        "away_player_5",
        "away_player_6",
        "away_player_7",
        "away_player_8",
        "away_player_9",
        "away_player_10",
        "away_player_11",
    ]
    home_players = list(
        filter(
            lambda p: p is not None and p is not np.nan,
            [df[field][0] for field in home_fields],
        )
    )
    away_players = list(
        filter(
            lambda p: p is not None and p is not np.nan,
            [df[field][0] for field in away_fields],
        )
    )

    return gather_players(home_players), gather_players(away_players)


def xml_pp(root):
    """
    Pretty-print a XML subtree.
    """
    return etree.tostring(root, pretty_print=True).decode("utf-8")


def sort_match(events_data: dict):
    events = []
    for events_type, typedevents in events_data.items():
        for event in typedevents:
            events.append(event)
    return list(
        sorted(
            events,
            key=lambda e: (e["minute"], e.get("sortorder", 0), e.get("event_id")),
        )
    )


def dump_event(e, match):
    c = dict(e)
    etype = e["type"]
    eteam = e.get("team", None)
    eminute = e.get("minute", 0)
    ep1 = e.get("player1", None)
    ep2 = e.get("player2", None)
    for field in [
        "type",
        "team",
        "minute",
        "player1",
        "player2",
        "elapsed",
        "elapsed_plus",
    ]:
        if field in c:
            del c[field]

    res = "Event %s @ minute %s (team: %s)\n" % (etype, eminute, eteam)
    if ep1 is not None or ep2 is not None:
        res += "\t%s => %s\n" % (ep1, ep2)

    if c:
        vals = []
        for k, v in c.items():
            s = "%s: %s" % (k, v)
            vals.append(s)
        res += "\t" + ", ".join(vals)

    return res


def parse_event(event_type, elem):
    """
    Parse a single event element.
    """
    result = {"type": event_type}
    IGNORED_FIELDS = set(["comment", "n"])
    RENAME_FIELDS = {
        "event_incident_typefk": "event_type_id",
        "id": "event_id",
        "type": "event_type",
    }
    NUM_FIELDS = set(["elapsed", "sortorder", "elapsed_plus", "event_id"])
    for child in elem.getchildren():
        child_tag = child.tag.lower().strip()
        if child_tag in IGNORED_FIELDS:
            continue
        child_value = child.text
        if child_value is not None:
            child_value = child_value.strip()

        if child_tag.startswith("player") and child_value:
            if str(child_value).lower() == "unknown player":
                child_value = Player(id=-1, name="unknown", valid=False)
            else:
                child_value = get_player(int(child_value))

        if "team" in child_tag:
            child_value = get_team(int(child_value))

        if child_tag in NUM_FIELDS and child_value:
            child_value = int(child_value)

        target_key = RENAME_FIELDS.get(child.tag.lower(), child.tag.lower())
        if child_value is None:
            continue

        result[target_key] = child_value

    if "elapsed_plus" not in result:
        result["elapsed_plus"] = 0

    if "elapsed_plus" in result and "elapsed" in result:
        result["minute"] = result["elapsed"] + result["elapsed_plus"]

    return result


def parse_events(event_type, root):
    """
    Returns parsed objects for all events in the given XML document.
    """
    results = []
    for event_elem in root.xpath("./value"):
        results.append(parse_event(event_type, event_elem))
    return results


def parse_preprocess(text):
    if text is None:
        return None
    text = text.strip()
    if text == "":
        return None
    return etree.fromstring(text)


def parse_field_value(field, value):
    if not field or not value:
        return None

    fieldroot = parse_preprocess(value)
    return parse_events(field, fieldroot)


def matches_with_events():
    """
    Restricted query for matches in the ESDB that contain event data.
    """
    sql = (
        "SELECT Id FROM Match"
        + " WHERE NOT goal IS NULL"
        + " OR NOT shoton IS NULL "
        + " OR NOT shotoff IS NULL "
        + " OR NOT foulcommit IS NULL "
        + " OR NOT card IS NULL "
        + " OR NOT cross IS NULL "
        + " OR NOT corner IS NULL "
        + " OR NOT possession IS NULL"
    )
    df = pd.read_sql_query(sql, conn)
    return df


def match_parse_texts(match: Match):
    text_fields = [
        "goal",
        "shoton",
        "shotoff",
        "foulcommit",
        "card",
        "cross",
        "corner",
        "possession",
    ]
    results = {}
    sql = "SELECT " + ", ".join(text_fields) + " FROM Match WHERE Match.id = :matchid"
    df = pd.read_sql_query(sql, conn, params={"matchid": match.match_id.item()})

    for field in text_fields:
        if df[field].empty:
            continue
        fieldvalue = df[field].values[0]
        parsed = parse_field_value(field, fieldvalue)
        if parsed is not None:
            results[field] = parsed

    return results


def get_match_data(match_id):
    match_dbentry = matches[matches["id"] == match_id]
    if match_dbentry.empty:
        return None
    obj = Match(match_dbentry)
    return obj


match_event_cache = {}


def fill_events(match: Match):
    """
    Attaches cached events to the given Match object and filters invalid ones (e.g. events without enough data).
    """
    if match.match_id in match_event_cache:
        match.events = match_event_cache[match.match_id]
        return True

    match_events = match_parse_texts(match)
    match_events = sort_match(match_events)
    for event in match_events:
        if "team" not in event or event["team"] is None:
            event["invalid"] = True
            continue

        if "del" in event and event["del"] == 1:
            event["invalid"] = True

        if "card_type" in event:
            if event["card_type"].startswith("y"):
                event["card_type"] = "y"
            if event["card_type"].startswith("r"):
                event["card_type"] = "r"

        event_type = event.get("type", None)
        if event_type == "possession":
            if "homepos" not in event and "awaypos" not in event:
                event["invalid"] = True
                print(event_type, event)

        eteam = event["team"]
        if eteam.longname == match.hometeam:
            eteam = "home"
        elif eteam.longname == match.awayteam:
            eteam = "away"
        else:
            if eteam.longname not in [match.hometeam, match.awayteam]:
                event["invalid"] = True
        event["team"] = eteam
    match_events = list(
        filter(
            lambda e: "invalid" not in event or not event["invalid"] == True,
            match_events,
        )
    )
    match_events = list(
        sorted(match_events, key=lambda evt: (evt["minute"], -evt.get("sort_order", 0)))
    )

    match.events = match_events
    match_event_cache[match.match_id] = match_events
    return True


# retrieve a random game from the database that has detail information on events
def random_game_id():
    field_criteria = [
        "goal",
        "shoton",
        "shotoff",
        "foulcommit",
        "card",
        "cross",
        "corner",
        "possession",
    ]
    field_criteria = ["NOT %s IS NULL" % x for x in field_criteria]
    field_criteria = " OR ".join(field_criteria)

    df = int(
        pd.read_sql_query("SELECT id FROM Match WHERE " + field_criteria, conn)
        .sample(n=1)["id"]
        .values[0]
    )
    return df


def synthesize_match(match):
    newmatch = match.clone()
    newmatch.match_id = -1
    newmatch.match_api_id = -1

    sample_country = countries.sample(n=1)
    sample_country_name = sample_country["name"].values[0]
    newmatch.country = sample_country_name

    print("new country", sample_country_name)
    sample_league = leagues[leagues["CountryName"] == sample_country_name].sample(n=1)
    sample_league_name = sample_league["LeagueName"].values[0]
    sample_league_id = sample_league["id"].values[0]
    print("new league", sample_league_name)
    newmatch.league = sample_league_name

    league_matches = matches[matches["LeagueId"] == sample_league_id]
    league_hometeams = league_matches["HomeTeamId"]
    league_awayteams = league_matches["AwayTeamId"]
    league_teams = pd.concat([league_hometeams, league_awayteams])
    new_hometeam_id, new_awayteam_id = np.random.choice(league_teams.unique(), 2)

    sampled_hometeam = get_team(new_hometeam_id, "id")
    sampled_awayteam = get_team(new_awayteam_id, "id")
    print("new home team", sampled_hometeam)
    print("new away team", sampled_awayteam)

    newmatch.hometeam = sampled_hometeam.longname
    newmatch.awayteam = sampled_awayteam.longname

    #    for event in newmatch.events:
    #        if 'team' in event and event['team']:
    #            original_team = event['team']
    #            newteam = sampled_hometeam
    #            if original_team is match.awayteam:
    #                newteam = sampled_awayteam
    #            event['team'] = newteam

    return newmatch


def connect():
    global conn
    if conn is None:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        initialize_model(conn)
    return conn


def count():
    """
    Number of matches in the database.
    """
    qry = pd.read_sql_query("SELECT COUNT(*) as matches FROM Match", conn)
    return qry["matches"][0]


players = player_attributes = countries = leagues = teams = matches = None


def initialize_model(conn):
    """
    Reads global information on leagues and players from the database.
    """
    global players, player_attributes, countries, leagues, teams, matches
    players = pd.read_sql_query("SELECT * FROM Player", conn)
    players.set_index("id", inplace=True)
    # convert to datetime
    players["birthday"] = pd.to_datetime(players["birthday"])
    # calculate player age for text generation
    now = pd.to_datetime("now")
    players["age"] = ((now - players["birthday"]).dt.days / 365).astype(int)
    players

    player_attributes = pd.read_sql_query(
        "SELECT id, player_fifa_api_id, player_api_id, preferred_foot, attacking_work_rate, defensive_work_rate FROM Player_Attributes",
        conn,
    )
    player_attributes

    # countries
    countries = pd.read_sql_query("SELECT * FROM Country", conn)

    # leagues
    leagues = pd.read_sql_query(
        "SELECT League.id, League.name AS LeagueName, Country.Name AS CountryName FROM League LEFT JOIN Country ON League.country_id = Country.id",
        conn,
    )

    teams = pd.read_sql_query("SELECT * FROM Team", conn)

    # gather match overview data
    matches = pd.read_sql_query(
        """SELECT
            Match.id, Match.match_api_id, Country.name AS CountryName, League.id AS LeagueId, League.name AS LeagueName,
            HomeTeam.id AS HomeTeamId, HomeTeam.team_long_name AS HomeTeamName, Match.home_team_goal AS HomeTeamGoal,
            AwayTeam.id AS AwayTeamId, AwayTeam.team_long_name AS AwayTeamName, Match.away_team_goal AS AwayTeamGoal,
            DATETIME(Match.date) AS MatchDate
        FROM Match
        LEFT JOIN Country ON Country.id = Match.country_id
        LEFT JOIN Team AS HomeTeam ON Match.home_team_api_id = HomeTeam.team_api_id
        LEFT JOIN Team AS AwayTeam ON Match.away_team_api_id = AwayTeam.team_api_id
        LEFT JOIN League ON League.id = Match.league_id""",
        conn,
    )
    matches["MatchDate"] = pd.to_datetime(matches["MatchDate"])
    matches["Result"] = "-"

    matches.loc[matches["AwayTeamGoal"] == matches["HomeTeamGoal"], "Result"] = "tie"
    matches.loc[
        matches["AwayTeamGoal"] < matches["HomeTeamGoal"], "Result"
    ] = "home-win"
    matches.loc[
        matches["AwayTeamGoal"] > matches["HomeTeamGoal"], "Result"
    ] = "away-win"
    matches


def disconnect():
    global conn
    if conn is not None:
        conn.close()
    conn = None


if __name__ == "__main__":
    connect()

    # retrieve a random game from the database that has detail information on events
    random_template_match = random_game_id()

    random_match = get_match_data(random_template_match)

    fill_events(random_match)
    print("\treal")
    print(random_match)
    print(
        random_match.score(), "\t", random_match.result(), "\t", random_match.winner()
    )
    for event in random_match.events:
        print(dump_event(event, random_match))

