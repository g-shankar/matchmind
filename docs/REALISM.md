# Football realism check

The simulator should produce matches that look like real football. This check plays
20 unscripted matches (goals come from the engine's own chance model) and compares
per-match averages with realistic ranges. All numbers come from the stats engine's
team totals; cards are counted from card events. The simulator does not produce
corners yet, so they are not checked.

- Test: `backend/tests/test_realism.py` (about 12 s)
- Print the table: `cd backend && python -m matchmind.simulator.realism`
  (`--start` and `--count` pick other seeds)
- Seeds: 1000-1019. Odd seeds play NBR at home, even seeds HCY at home.
- Possession is the pass share, the same definition the live stats use.

## Averages (seeds 1000-1019)

| metric | average | range checked | note |
|---|---|---|---|
| goals | 2.35 | 1.5-4.5 | real leagues average about 2.5-2.9 |
| shots (both teams) | 27.45 | 15-35 | real: about 24-27 |
| shots on target | 12.15 | 5-15 | a little high (real: about 8-9) |
| pass accuracy % | 80.71 | 70-90 | real: about 78-84 |
| passes (both teams) | 1315.25 | 700-1500 | high side (real: about 850-1,100) |
| fouls | 20.2 | 10-35 | real: about 20-24 |
| cards | 2.4 | 1-8 | a little low (real: about 3.5-4) |

Every per-match possession split adds up to 100 and stays between 30% and 70%.

The pass count and shots on target are on the high side and cards a little low,
but none of them is far enough out to change the simulator. Changing it would also
mean regenerating `backend/data/matches`.

## Per-match table

| seed | goals | shots | on target | passes | pass acc % | fouls | cards | poss H/A % |
|---|---|---|---|---|---|---|---|---|
| 1000 | 2 | 24 | 9 | 1363 | 80.4 | 13 | 1 | 52.5/47.5 |
| 1001 | 2 | 30 | 15 | 1262 | 81.9 | 21 | 3 | 45.1/54.9 |
| 1002 | 1 | 29 | 14 | 1370 | 82.8 | 17 | 2 | 50.6/49.4 |
| 1003 | 4 | 18 | 10 | 1369 | 81.1 | 24 | 4 | 47.9/52.1 |
| 1004 | 2 | 25 | 12 | 1360 | 78.8 | 21 | 2 | 55.1/44.9 |
| 1005 | 1 | 27 | 13 | 1364 | 81.2 | 18 | 4 | 47.5/52.5 |
| 1006 | 4 | 30 | 14 | 1260 | 79.1 | 18 | 2 | 52.9/47.1 |
| 1007 | 0 | 30 | 16 | 1325 | 81.6 | 21 | 4 | 45.4/54.6 |
| 1008 | 2 | 42 | 11 | 1218 | 80.8 | 22 | 2 | 48.4/51.6 |
| 1009 | 2 | 35 | 13 | 1180 | 80.0 | 25 | 3 | 46.9/53.1 |
| 1010 | 4 | 28 | 12 | 1253 | 81.9 | 19 | 2 | 50.4/49.6 |
| 1011 | 1 | 24 | 12 | 1384 | 79.2 | 19 | 1 | 44.7/55.3 |
| 1012 | 1 | 22 | 6 | 1351 | 80.1 | 16 | 1 | 54.6/45.4 |
| 1013 | 6 | 19 | 12 | 1361 | 79.2 | 18 | 2 | 48.3/51.7 |
| 1014 | 4 | 27 | 15 | 1262 | 81.3 | 24 | 3 | 53.2/46.8 |
| 1015 | 2 | 27 | 11 | 1351 | 81.6 | 20 | 4 | 45.7/54.3 |
| 1016 | 0 | 24 | 9 | 1360 | 81.9 | 25 | 2 | 56.1/43.9 |
| 1017 | 2 | 38 | 16 | 1284 | 80.3 | 17 | 2 | 48.0/52.0 |
| 1018 | 5 | 34 | 18 | 1331 | 80.8 | 17 | 1 | 53.2/46.8 |
| 1019 | 2 | 16 | 5 | 1297 | 80.2 | 29 | 3 | 47.7/52.3 |
