import type { PlayerInfo, TeamInfo, Teams } from '../api/contract';

export interface PlayerRef extends PlayerInfo {
  team: TeamInfo;
  side: 'home' | 'away';
}

export function teamById(teams: Teams | null, teamId: string | null | undefined): TeamInfo | null {
  if (!teams || !teamId) return null;
  if (teams.home.team_id === teamId) return teams.home;
  if (teams.away.team_id === teamId) return teams.away;
  return null;
}

export function sideOf(teams: Teams | null, teamId: string | null | undefined): 'home' | 'away' | null {
  if (!teams || !teamId) return null;
  return teams.home.team_id === teamId ? 'home' : teams.away.team_id === teamId ? 'away' : null;
}

export function playerById(teams: Teams | null, playerId: string | null | undefined): PlayerRef | null {
  if (!teams || !playerId) return null;
  for (const side of ['home', 'away'] as const) {
    const p = teams[side].players.find((x) => x.player_id === playerId);
    if (p) return { ...p, team: teams[side], side };
  }
  return null;
}

export const playerName = (teams: Teams | null, playerId: string | null | undefined) =>
  playerById(teams, playerId)?.name ?? '';

// Short display name: "Kofi Asante" -> "K. Asante".
export const shortName = (name: string) => {
  const parts = name.trim().split(/\s+/);
  return parts.length > 1 ? `${parts[0][0]}. ${parts.slice(1).join(' ')}` : name;
};

export const teamColor = (teams: Teams | null, teamId: string | null | undefined, fallback = '#94a3b8') =>
  teamById(teams, teamId)?.primary_color ?? fallback;

// Away kit drawn lighter when both primaries are too close to tell apart on the pitch.
export function pitchColors(teams: Teams | null): { home: string; away: string } {
  if (!teams) return { home: '#60a5fa', away: '#f87171' };
  return { home: teams.home.primary_color, away: teams.away.primary_color };
}
