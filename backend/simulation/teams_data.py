from typing import Dict, Any, List
from api.schemas import PlayerRef

TEAMS_DATA: Dict[str, Any] = {
    "Manchester Blue": {
        "id": "TEAM_MCF",
        "name": "Manchester Blue",
        "short_name": "MCI",
        "primary_color": "#6CABDD",
        "secondary_color": "#1C2C5B",
        "tactical_system": "3-2-4-1 Positional Dominance",
        "manager": "Pep Sterling",
        "style": {
            "possession_target": 68,
            "press_intensity": "Medium-High Counterpress",
            "build_up_speed": "Methodical Control",
            "chaos_tolerance": "Low (Prefers total structure)"
        },
        "players": [
            PlayerRef(id="MCI_31", name="Ederson", jersey_number=31, position="GK", team_name="Manchester Blue", speed_kmh=0.0, distance_covered_km=1.2),
            PlayerRef(id="MCI_03", name="Ruben Dias", jersey_number=3, position="CB", team_name="Manchester Blue", speed_kmh=24.1, distance_covered_km=4.8),
            PlayerRef(id="MCI_25", name="Manuel Akanji", jersey_number=25, position="CB", team_name="Manchester Blue", speed_kmh=29.4, distance_covered_km=5.1),
            PlayerRef(id="MCI_24", name="Josko Gvardiol", jersey_number=24, position="LB", team_name="Manchester Blue", speed_kmh=31.2, distance_covered_km=6.3),
            PlayerRef(id="MCI_16", name="Rodri", jersey_number=16, position="DM", team_name="Manchester Blue", speed_kmh=26.8, distance_covered_km=7.5),
            PlayerRef(id="MCI_08", name="Mateo Kovacic", jersey_number=8, position="CM", team_name="Manchester Blue", speed_kmh=28.3, distance_covered_km=6.9),
            PlayerRef(id="MCI_17", name="Kevin De Bruyne", jersey_number=17, position="CAM", team_name="Manchester Blue", speed_kmh=30.4, distance_covered_km=7.1),
            PlayerRef(id="MCI_20", name="Bernardo Silva", jersey_number=20, position="CM", team_name="Manchester Blue", speed_kmh=29.0, distance_covered_km=8.2),
            PlayerRef(id="MCI_47", name="Phil Foden", jersey_number=47, position="LW", team_name="Manchester Blue", speed_kmh=33.1, distance_covered_km=6.7),
            PlayerRef(id="MCI_11", name="Jeremy Doku", jersey_number=11, position="RW", team_name="Manchester Blue", speed_kmh=35.2, distance_covered_km=5.9),
            PlayerRef(id="MCI_09", name="Erling Haaland", jersey_number=9, position="ST", team_name="Manchester Blue", speed_kmh=34.8, distance_covered_km=4.9),
        ]
    },
    "North London Red": {
        "id": "TEAM_ARS",
        "name": "North London Red",
        "short_name": "ARS",
        "primary_color": "#EF0107",
        "secondary_color": "#063672",
        "tactical_system": "4-3-3 High Pressing & Transition",
        "manager": "Mikel Artman",
        "style": {
            "possession_target": 52,
            "press_intensity": "Aggressive High Block (PPDA 7.2)",
            "build_up_speed": "Direct Vertical Transitions",
            "chaos_tolerance": "High (Exploits defensive disorganization)"
        },
        "players": [
            PlayerRef(id="ARS_22", name="David Raya", jersey_number=22, position="GK", team_name="North London Red", speed_kmh=0.0, distance_covered_km=1.4),
            PlayerRef(id="ARS_02", name="William Saliba", jersey_number=2, position="CB", team_name="North London Red", speed_kmh=32.4, distance_covered_km=5.3),
            PlayerRef(id="ARS_06", name="Gabriel", jersey_number=6, position="CB", team_name="North London Red", speed_kmh=30.8, distance_covered_km=5.1),
            PlayerRef(id="ARS_04", name="Ben White", jersey_number=4, position="RB", team_name="North London Red", speed_kmh=31.5, distance_covered_km=6.5),
            PlayerRef(id="ARS_12", name="Jurrien Timber", jersey_number=12, position="LB", team_name="North London Red", speed_kmh=32.1, distance_covered_km=6.4),
            PlayerRef(id="ARS_41", name="Declan Rice", jersey_number=41, position="DM", team_name="North London Red", speed_kmh=31.9, distance_covered_km=8.1),
            PlayerRef(id="ARS_08", name="Martin Odegaard", jersey_number=8, position="CAM", team_name="North London Red", speed_kmh=29.7, distance_covered_km=7.8),
            PlayerRef(id="ARS_23", name="Mikel Merino", jersey_number=23, position="CM", team_name="North London Red", speed_kmh=27.9, distance_covered_km=6.8),
            PlayerRef(id="ARS_07", name="Bukayo Saka", jersey_number=7, position="RW", team_name="North London Red", speed_kmh=34.3, distance_covered_km=7.2),
            PlayerRef(id="ARS_11", name="Gabriel Martinelli", jersey_number=11, position="LW", team_name="North London Red", speed_kmh=35.6, distance_covered_km=6.9),
            PlayerRef(id="ARS_29", name="Kai Havertz", jersey_number=29, position="ST", team_name="North London Red", speed_kmh=33.2, distance_covered_km=7.4),
        ]
    }
}
