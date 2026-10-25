# Live cut

The submitted video is the coded film (`../build.sh final`) with 56 seconds of the
running app spliced in after the crew scene: film 0-44 s, then four screen recordings of
the deployed Azure app, then the film's Azure and end card (106-118 s). Total 112 s.

- `record.js` records the four takes with Playwright at 1920x1080 against the live URL
  (`BASE=` to point it elsewhere): the 34:16 replay with ranked options, the three
  cameras, Fan vs Analyst in English, Spanish and Arabic, and the crew stress test.
- Each take gets a "Live on Azure" caption bar, the music bed and a Kokoro voiceover
  (bm_george). The voiceover uses only numbers from `../facts.json`.
- The cut is mastered to -14 LUFS, H.264 yuv420p 60 fps, AAC 48 kHz, faststart.
