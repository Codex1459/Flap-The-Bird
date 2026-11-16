# Flap the Bird 

A clean, beginner-friendly **Flap the Bird** game built in Python using strictly **`tkinter`** and **`Pillow`** (zero external game libraries/no Pygame).

---

## Key Features
- **Easy & Relaxed Gameplay**: Wider vertical pipe gap (`165px`), generous horizontal spacing (`235px`), floatier gravity, and forgiving hitboxes.
- **Gentle Dynamic Speed**: Starts at a gentle `2.2 px/frame` and gradually ramps up as your score climbs (capped at `4.0 px/frame`).
- **Chunk-Based Ground Terrain**: Modular chunks scroll left, get deleted when off-screen, and respawn seamlessly on the right.
- **4 Selectable Birds**: Yellow, Red, Blue, Gold with individual chirps (<kbd>B</kbd> key or click).
- **3 Background Themes**: Day, Night, Sunset with matching pipe colors & cozy 10% volume continuous music loops (<kbd>T</kbd> key or click).
- **Instant Medals**: Bronze (0-2), Silver (3-5), Gold (6-9), Platinum (10+) appear instantly on Game Over.

---

## Directory Structure

```text
Flap-The-Bird/
├── .venv/                   # Python virtual environment
├── assets/                  # Categorized game assets
│   ├── birds/               # 4 selectable bird types (3-frame animation each)
│   │   ├── yellow/          # Classic Yellow
│   │   ├── red/             # Crimson Fury
│   │   ├── blue/            # Sky Blue Jay
│   │   └── gold/            # Golden Phoenix
│   ├── ground_chunks/       # Modular ground terrain segments
│   │   ├── chunk_0.png      # Classic turf
│   │   ├── chunk_1.png      # Wildflower variant
│   │   ├── chunk_2.png      # Pebble variant
│   │   └── chunk_3.png      # Green sprout variant
│   ├── medals/              # Reward medals for score card
│   │   ├── bronze.png       # Score 0 - 2 (Instant reward)
│   │   ├── silver.png       # Score 3 - 5
│   │   ├── gold.png         # Score 6 - 9
│   │   └── platinum.png     # Score 10+
│   ├── sounds/              # Lightweight sound effects & cozy 10% volume BGM
│   │   ├── flap.wav         # Acoustic wing flap swoop
│   │   ├── point.wav        # Score point blip
│   │   ├── hit.wav          # Collision thud
│   │   ├── select_bird*.wav # Distinct chirps for bird skin selections
│   │   ├── select_theme*.wav# Distinct chimes for theme switches
│   │   ├── bgm_day.wav      # Cozy daytime background music loop (10% volume)
│   │   ├── bgm_night.wav    # Cozy midnight background music loop (10% volume)
│   │   └── bgm_sunset.wav   # Cozy twilight background music loop (10% volume)
│   ├── themes/              # 3 atmospheric background themes & matching pipes
│   │   ├── day/             # Day Sky + Classic Green Pipes
│   │   ├── night/           # Night City + Emerald Pipes
│   │   └── sunset/          # Sunset Dusk + Bronze Pipes
│   └── ui/                  # UI banners
│       ├── game_over.png    # Game Over banner
│       └── start_message.png# Start screen banner
├── highscore.txt            # Persistent local high score
├── main.py                  # Main executable Python game script
├── README.md                # Project documentation
└── run.bat                  # One-click game launcher
```

---

## Controls

| Action | Control Key / Input |
|---|---|
| **Flap / Jump** | **`Spacebar`** or **`Left Mouse Click`** |
| **Switch Bird** | **`B` key** or **Click Bird Selector Pill** (Plays custom bird chirp) |
| **Switch Theme** | **`T` key** or **Click Theme Selector Pill** (Plays custom theme chime & switches BGM) |
| **Mute / Unmute Music** | **`M` key** |
| **Play Again / Restart** | **`Spacebar`** or **Click "PLAY AGAIN" Button** |

---

## How to Run

### Method 1: One-Click Auto-Launcher (Recommended)
Simply double-click **[`run.bat`](file:///<user>/<directory>/<directory>/run.bat)**.
- Automatically checks if Python is installed.
- Automatically creates `.venv` if it doesn't exist.
- Automatically installs required dependencies from `requirements.txt`.
- Automatically launches `main.py`.

### Method 2: Manual Terminal Run
```powershell
pip install -r requirements.txt
python main.py
```
