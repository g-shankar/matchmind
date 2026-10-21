# PitchPulse AI ⚽
### *The Real-Time Synthetic Match Insights & Narrative Engine for Premier League Studio*

> Built for the **Inside the Game Developer Hackathon**  
> Powered by **Microsoft Azure** (Azure OpenAI GPT-4o, Azure AI Translator, Azure Event Hubs)

[![Azure](https://img.shields.io/badge/Azure-OpenAI%20%7C%20Translator%20%7C%20EventHubs-0078D4?logo=microsoftazure)](https://azure.microsoft.com/)
[![FastAPI](https://img.shields.io/badge/Backend-FastAPI%20%26%20WebSockets-009688?logo=fastapi)](https://fastapi.tiangolo.com/)
[![React](https://img.shields.io/badge/Frontend-React%20%2B%20TypeScript%20%2B%20Tailwind-61DAFB?logo=react)](https://react.dev/)

---

## 🌟 Executive Summary

Football stories do not start and end with the scoreline. **PitchPulse AI** is an AI insights and broadcast narrative engine running on Azure that transforms high-frequency synthetic football events into explainable match intelligence, synchronized broadcast overlays, and hyper-personalized fan experiences in real time.

---

## ⚡ The 5-Stage Pipeline

```
┌─────────────────┐     ┌─────────────────────┐     ┌──────────────────────┐     ┌─────────────────────┐     ┌──────────────────────┐
│ Stage 1: INGEST │ ──> │ Stage 2: INTERPRET  │ ──> │   Stage 3: EXPLAIN   │ ──> │   Stage 4: RENDER   │ ──> │ Stage 5: PERSONALIZE │
│ Synthetic match │     │ Pass Difficulty,    │     │ Azure OpenAI GPT-4o  │     │ Studio Radar &      │     │ 4 Fan Personas &     │
│ telemetry stream│     │ Control vs Chaos    │     │ "Why It Matters"     │     │ Broadcast Overlays  │     │ 5 Global Languages   │
└─────────────────┘     └─────────────────────┘     └──────────────────────┘     └─────────────────────┘     └──────────────────────┘
```

1. **Ingest:** Streams sub-second synthetic football events (passes, tackles, shots, pressures, player vectors) on a standard $105\text{m} \times 68\text{m}$ pitch.
2. **Interpret:** Real-time state aggregation:
   - **Pass Difficulty Rating (PDR):** Multi-factor completion difficulty based on distance, defender pressure, and opponents in the passing lane.
   - **Control vs. Chaos Index (CCI):** Rolling sliding-window index quantifying positional suffocation ($+1.0$) vs. end-to-end chaos ($-1.0$).
   - **Speed & Velocity Milestones:** Instant alerts on rocket shots ($>100\text{ km/h}$) and driven deliveries ($>75\text{ km/h}$).
   - **Auto-Eventing Simulation:** Automated vision inference pipeline (YOLOv8 + ByteTrack) with sub-25ms latency.
3. **Explain:** Azure OpenAI (GPT-4o) synthesizes "Why it Matters" explanations rather than dry stats, unearthing the tactical cause and momentum consequence of every key moment.
4. **Render:** Studio Director command center + transparent broadcast overlay canvas (`/overlay`) ready for streaming integration (OBS / vMix).
5. **Personalize:**
   - **4 Audience Modes:** *Casual Fan*, *Tactical Analyst*, *Fantasy Scout*, and *Player Cam Spotlight*.
   - **13 Languages:** 5 hand-written studio languages (English, Spanish, French, Arabic, Japanese) plus 8 world languages (Portuguese, German, Hindi, Simplified Chinese, Kiswahili, Indonesian, Turkish, Korean) translated by Azure AI Translator and fact-checked again; off until switched on, then shown in English with a clear note (see `docs/LANGUAGES.md`).

---

## 🏗️ Architecture

```
                                [ SYNTHETIC MATCH SIMULATOR ]
                                 (Markov Event Engine - 105x68m)
                                               │
                                               ▼  (JSON Event Stream)
                                    [ AZURE EVENT HUBS ]
                                               │
                   ┌───────────────────────────┴───────────────────────────┐
                   ▼                                                       ▼
       [ ANALYTICS & STATE ENGINE ]                             [ AZURE COSMOS DB ]
        - Pass Difficulty Rating (PDR)                           - Match Metadata & Rosters
        - Control vs Chaos Index (CCI)                           - Historical Tactics
        - Ball & Shot Speeds                                     - Player Profiles
                   │                                                       │
                   └───────────────────────────┬───────────────────────────┘
                                               ▼
                                   [ NARRATIVE & INSIGHTS ENGINE ]
                                      (Azure OpenAI - GPT-4o)
                                      - Contextual "Why It Matters"
                                      - Turning Points & Tactical Traps
                                      - Automated Halftime / FT Recaps
                                               │
                   ┌───────────────────────────┴───────────────────────────┐
                   ▼                                                       ▼
      [ AZURE AI TRANSLATOR ]                                  [ FASTAPI WEBSOCKET HUB ]
       - Multilingual Localization                              - Real-time Sub-100ms Push
       (PT, DE, HI, ZH, SW, ID, TR, KO)                                    │
                   │                                                       │
                   └───────────────────────────┬───────────────────────────┘
                                               ▼
                              [ REACT / VITE BROADCAST & FAN APP ]
              ┌────────────────────────────────┼────────────────────────────────┐
              ▼                                ▼                                ▼
      [ STUDIO DIRECTOR ]            [ BROADCAST OVERLAYS ]           [ FAN PERSONALIZER ]
       - Live 2D Pitch Radar          - Transparent Lower-Thirds       - Casual / Tactical Modes
       - Control/Chaos Gauge          - Official PL Scorebug           - Player Spotlight Cam
       - Interactive Narrative Stream - Telemetry Badges               - FPL Impact Lens
```

---

## 🚀 Quickstart Guide

### 1. Prerequisites
- **Python 3.11+** installed
- **Node.js 18+** installed

### 2. Run the Backend Server
```powershell
cd backend
python -m pip install -r requirements.txt
python -m uvicorn api.main:app --reload --port 8000
```
*Backend runs at:* `http://localhost:8000` (WebSocket at `ws://localhost:8000/ws/match`)

### 3. Run the Frontend Dashboard
In a separate terminal:
```powershell
cd frontend
npm install
npm run dev
```
*Frontend runs at:* `http://localhost:3000`

---

## ☁️ Azure Cloud Configuration (Hybrid Mode)

PitchPulse AI features a **Hybrid Service Provider Pattern**: it operates out-of-the-box in high-fidelity local emulation mode, and automatically unlocks live Azure Cloud capabilities when configured:

1. Open `backend/.env`.
2. Add your Azure OpenAI and Translator credentials:
   ```ini
   AZURE_OPENAI_API_KEY=your_azure_openai_key
   AZURE_OPENAI_ENDPOINT=https://your-resource.openai.azure.com/
   AZURE_OPENAI_DEPLOYMENT=gpt-4o
   # Translator: keyless (Microsoft Entra ID), custom subdomain endpoint; both switches on
   MATCHMIND_TRANSLATOR_ENABLED=true
   AZURE_TRANSLATOR_ENDPOINT=https://<your-translator>.cognitiveservices.azure.com/
   ```
3. Restart the backend: `python -m uvicorn api.main:app --reload --port 8000`.

To provision resources directly in your Azure subscription, deploy the Bicep template:
```powershell
az deployment group create --resource-group <your-rg> --template-file deployment/azure_bicep/main.bicep
```

---

## 🎮 Features & UI Modes

| Mode | Target User | Key Capabilities |
| :--- | :--- | :--- |
| **Studio Director** | Broadcasters, Hosts, Pundits | Interactive 2D Pitch, live trajectory vectors, Control vs. Chaos gauge, simulation playback speed ($1\times, 2\times, 5\times$), automated recaps. |
| **Broadcast Overlay** | Live Streamers (OBS / vMix) | Transparent background, official Premier League style scorebug, dynamic lower-thirds for goals, rocket shots ($>100\text{ km/h}$), and line breaks. |
| **Fan Personalizer** | Everyday Fans & Analysts | Instant Persona switching (Casual, Tactical, Fantasy, Player Cam), dedicated Player Spotlight Cam tracking sprint speeds & distance covered. |
