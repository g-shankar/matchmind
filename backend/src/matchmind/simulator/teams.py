"""Two fictional clubs. No real clubs, players or Premier League data."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Player:
    player_id: str
    name: str
    number: int
    position: str
    line: str  # GK, DEF, MID or FWD
    base: tuple[float, float]  # own attacking frame, ball on the centre spot


@dataclass(frozen=True)
class Team:
    team_id: str
    name: str
    formation: str
    strength: float  # 0.5 is average; nudges pass and dribble success
    players: tuple[Player, ...]
    short_name: str = ""
    primary_color: str = "#ffffff"
    secondary_color: str = "#000000"
    style: str = ""

    @property
    def keeper(self) -> Player:
        return next(p for p in self.players if p.line == "GK")

    def player(self, player_id: str) -> Player:
        for p in self.players:
            if p.player_id == player_id:
                return p
        raise KeyError(f"{player_id} is not in {self.team_id}")


def _team(team_id, name, formation, strength, rows, **display) -> Team:
    players = tuple(
        Player(f"{team_id}-{num}", pname, num, pos, line, base) for num, pname, pos, line, base in rows
    )
    return Team(team_id, name, formation, strength, players, **display)


NORTHBRIDGE = _team(
    "NBR",
    "Northbridge FC",
    "4-3-3",
    0.52,
    [
        (1, "Tomas Reyner", "GK", "GK", (5, 34)),
        (2, "Callum Okafor", "RB", "DEF", (28, 8)),
        (5, "Jonah Vries", "RCB", "DEF", (24, 24)),
        (4, "Marek Lindqvist", "LCB", "DEF", (24, 44)),
        (3, "Ellis Brandt", "LB", "DEF", (28, 60)),
        (6, "Sami Haddad", "CDM", "MID", (40, 34)),
        (8, "Rory Achterberg", "RCM", "MID", (50, 22)),
        (10, "Luca Ferrante", "LCM", "MID", (50, 46)),
        (7, "Dev Mallick", "RW", "FWD", (70, 8)),
        (11, "Kofi Asante", "LW", "FWD", (70, 60)),
        (9, "Adam Kerrigan", "ST", "FWD", (75, 34)),
    ],
    short_name="NBR",
    primary_color="#2f6fde",
    secondary_color="#0d1b3d",
    style="Possession 4-3-3, patient build-up through the half-spaces",
)

HARBOUR_CITY = _team(
    "HCY",
    "Harbour City",
    "4-2-3-1",
    0.50,
    [
        (1, "Niall Prescott", "GK", "GK", (5, 34)),
        (2, "Yusuf Demir", "RB", "DEF", (28, 8)),
        (4, "Owen Castell", "RCB", "DEF", (24, 25)),
        (5, "Bastien Moreau", "LCB", "DEF", (24, 43)),
        (3, "Duarte Nogueira", "LB", "DEF", (28, 60)),
        (6, "Theo Lindgren", "RDM", "MID", (42, 27)),
        (8, "Kai Watanabe", "LDM", "MID", (42, 41)),
        (7, "Mateo Rios", "RAM", "FWD", (62, 10)),
        (10, "Elias Varga", "CAM", "MID", (60, 34)),
        (11, "Jaden Clarke", "LAM", "FWD", (62, 58)),
        (9, "Ivan Petrov", "ST", "FWD", (75, 34)),
    ],
    short_name="HCY",
    primary_color="#f08a24",
    secondary_color="#3a1a05",
    style="Direct 4-2-3-1, high press and quick vertical transitions",
)

TEAMS = {t.team_id: t for t in (NORTHBRIDGE, HARBOUR_CITY)}


def get_team(team_id: str) -> Team:
    try:
        return TEAMS[team_id]
    except KeyError as exc:
        raise KeyError(f"Unknown team '{team_id}'. Known: {', '.join(TEAMS)}") from exc
