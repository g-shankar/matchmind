#!/bin/bash
# Start the local launch-check server on 8860; extra env passed through. Prints the pid.
S=/tmp/launch-checks; W=/home/user/wt/launch-checks
cd $W/backend
env MATCHMIND_PORT=8860 MATCHMIND_STATIC_DIR=$W/frontend/dist MATCHMIND_PUBLIC_ORIGIN=http://localhost:8860 \
  MATCHMIND_MATCH_FILE=$W/backend/data/matches/MM-DEMO-001.jsonl PYTHONPATH=$PWD/src "$@" \
  nohup ${PY:-python3} -m matchmind.api >> $S/server.log 2>&1 &
echo $! > $S/server.pid
echo "- server (re)started pid $! env: $*" >> $S/notes.md
echo $!
