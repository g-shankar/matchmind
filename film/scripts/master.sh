#!/usr/bin/env bash
# Loudness (-14 LUFS integrated, -1 dBTP), mux with the rendered picture,
# and the delivery extras: music-only track and a contact sheet.
#   scripts/master.sh out/picture.mp4 out/pitchpulse-demo.mp4
set -euo pipefail
cd "$(dirname "$0")/.."
pic=${1:-out/picture.mp4}
final=${2:-out/pitchpulse-demo.mp4}
a=out/audio

norm() {  # two-pass loudnorm: $1 in, $2 out
  local m
  m=$(ffmpeg -hide_banner -nostats -i "$1" -af loudnorm=I=-14:TP=-2:LRA=11:print_format=json -f null - 2>&1 | sed -n '/^{/,/^}/p')
  ffmpeg -y -hide_banner -loglevel error -i "$1" -af "loudnorm=I=-14:TP=-2:LRA=11:linear=true:\
measured_I=$(jq -r .input_i <<<"$m"):measured_TP=$(jq -r .input_tp <<<"$m"):\
measured_LRA=$(jq -r .input_lra <<<"$m"):measured_thresh=$(jq -r .input_thresh <<<"$m"):\
offset=$(jq -r .target_offset <<<"$m")" -ar 48000 "$2"
}
norm $a/mix.wav $a/mix-master.wav
norm $a/music.wav $a/music-master.wav
ffmpeg -y -hide_banner -loglevel error -i $a/music-master.wav -c:a aac -b:a 192k -ar 48000 out/music-only.m4a

ffmpeg -y -hide_banner -loglevel error -i "$pic" -i $a/mix-master.wav -map 0:v -map 1:a \
  -c:v libx264 -preset slow -crf 18 -pix_fmt yuv420p -movflags +faststart \
  -c:a aac -b:a 192k -ar 48000 -shortest "$final"

# 16-frame contact sheet, evenly spaced
dur=$(ffprobe -v error -show_entries format=duration -of csv=p=0 "$final")
ffmpeg -y -hide_banner -loglevel error -i "$final" -vf "fps=16/${dur},scale=480:-1,tile=4x4" -frames:v 1 out/contact-sheet.jpg

ffmpeg -hide_banner -nostats -i "$final" -af ebur128=peak=true -f null - 2>&1 | grep -A12 Summary | grep -E "I:|Peak:" || true
ffprobe -v error -show_entries stream=codec_name,pix_fmt,width,height,r_frame_rate,sample_rate -of compact "$final"
