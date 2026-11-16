import tkinter as tk
from PIL import Image, ImageTk
import random
import math
import os
import sys
import threading
import time
import ctypes

# Native sound support (Windows winsound / fallback to silent)
SOUND_ENABLED = False
if sys.platform == "win32":
    try:
        import winsound
        SOUND_ENABLED = True
    except ImportError:
        SOUND_ENABLED = False


# ==============================================================================
# 1. GAME SETTINGS & CONSTANTS (Easily tweak gameplay here!)
# ==============================================================================

WINDOW_WIDTH = 400       # Game screen width
WINDOW_HEIGHT = 600      # Game screen height
GROUND_Y = 490           # Height where the ground terrain starts
CHUNK_WIDTH = 100        # Width of each modular ground chunk (4-5 chunks on screen)

# Relaxed & beginner-friendly physics numbers
GRAVITY = 0.38           # Gentler downward pull for floatier, controlled flight
JUMP_STRENGTH = -6.6     # Smoother upward flap boost
BASE_SCROLL_SPEED = 2.2  # Accessible starting scroll speed
MAX_SCROLL_SPEED = 4.0   # Comfortable maximum speed cap
SPEED_INCREMENT = 0.07   # Gentle dynamic speed ramp per point scored
PIPE_GAP = 165           # Wider, more forgiving vertical gap (+20px clearance)
PIPE_DISTANCE = 235      # More breathing room between consecutive pipes
BGM_VOLUME = 0.10        # Fixed background music volume (10%)

# Available Bird & Theme options
BIRD_TYPES = ["yellow", "red", "blue", "gold"]
BIRD_NAMES = {
    "yellow": "CLASSIC YELLOW",
    "red": "CRIMSON FURY",
    "blue": "SKY BLUE JAY",
    "gold": "GOLDEN PHOENIX"
}

THEME_TYPES = ["day", "night", "sunset"]
THEME_NAMES = {
    "day": "DAY SKY",
    "night": "NIGHT CITY",
    "sunset": "SUNSET DUSK"
}


# ==============================================================================
# 2. AUDIO & BACKGROUND MUSIC ENGINE
# ==============================================================================

class SoundPlayer:
    """Plays sound effects asynchronously without freezing the game."""

    @staticmethod
    def play(sound_name):
        if not SOUND_ENABLED:
            return
        path = f"assets/sounds/{sound_name}.wav"
        # Friendly fallbacks for bird/theme sounds
        if not os.path.exists(path):
            if sound_name.startswith("select_bird"):
                path = "assets/sounds/select_bird.wav"
            elif sound_name.startswith("select_theme"):
                path = "assets/sounds/select_theme.wav"

        if os.path.exists(path):
            try:
                winsound.PlaySound(path, winsound.SND_FILENAME | winsound.SND_ASYNC)
            except Exception:
                pass


class MusicPlayer:
    """
    Manages cozy background music loops matching the active theme.
    Runs in a single dedicated background thread via Windows MCI.
    Automatically loops the song infinitely and switches tracks when the theme changes.
    """

    _target_theme = None
    _thread = None
    _stop_event = threading.Event()
    _is_muted = False
    _lock = threading.Lock()

    @classmethod
    def start(cls, initial_theme="day"):
        """Ensures the background music worker thread is running."""
        if not SOUND_ENABLED:
            return
        with cls._lock:
            cls._target_theme = initial_theme
        if cls._thread is None or not cls._thread.is_alive():
            cls._stop_event.clear()
            cls._thread = threading.Thread(target=cls._worker, daemon=True)
            cls._thread.start()

    @classmethod
    def play_theme(cls, theme_name):
        """Switches continuous music loop to the selected theme (Day, Night, Sunset)."""
        with cls._lock:
            cls._target_theme = theme_name
        cls.start(theme_name)

    @classmethod
    def toggle_mute(cls):
        """Toggles background music on / off."""
        cls._is_muted = not cls._is_muted
        return cls._is_muted

    @classmethod
    def stop(cls):
        """Stops background music completely (called on window close)."""
        cls._stop_event.set()
        if cls._thread and cls._thread.is_alive():
            cls._thread.join(timeout=0.4)

    @classmethod
    def _worker(cls):
        """Single persistent worker loop that monitors and loops theme BGM seamlessly."""
        if sys.platform != "win32":
            return
        winmm = ctypes.windll.winmm
        buf = ctypes.create_unicode_buffer(128)
        active_theme = None

        def close_device():
            nonlocal active_theme
            if active_theme is not None:
                try:
                    winmm.mciSendStringW("stop flap_bgm", None, 0, None)
                    winmm.mciSendStringW("close flap_bgm", None, 0, None)
                except Exception:
                    pass
                active_theme = None

        while not cls._stop_event.is_set():
            time.sleep(0.05)

            if cls._is_muted:
                close_device()
                continue

            with cls._lock:
                target = cls._target_theme

            if target is None:
                continue

            # 1. If active theme changed, switch tracks smoothly
            if target != active_theme:
                path = os.path.abspath(f"assets/sounds/bgm_{target}.wav")
                if os.path.exists(path):
                    close_device()
                    res_open = winmm.mciSendStringW(f'open "{path}" type waveaudio alias flap_bgm', None, 0, None)
                    if res_open == 0:
                        winmm.mciSendStringW("play flap_bgm from 0", None, 0, None)
                        active_theme = target
                continue

            # 2. Check track status: if ended, loop from 0 continuously!
            winmm.mciSendStringW("status flap_bgm mode", buf, 128, None)
            mode = buf.value.lower()
            if mode == "stopped":
                winmm.mciSendStringW("play flap_bgm from 0", None, 0, None)

        close_device()


# ==============================================================================
# 3. MODULAR GROUND CHUNK SYSTEM
# ==============================================================================

class GroundChunk:
    """Represents a single segment of the ground terrain."""

    def __init__(self, canvas, x, image):
        self.canvas = canvas
        self.x = x
        self.image = image
        # Create canvas image for this chunk
        self.item_id = self.canvas.create_image(
            self.x, GROUND_Y,
            image=self.image,
            anchor="nw",
            tags="ground"
        )
        # Keep ground below the bird and UI
        self.canvas.tag_lower(self.item_id, "bird")

    def move(self, speed):
        """Moves the chunk to the left."""
        self.x -= speed
        self.canvas.coords(self.item_id, self.x, GROUND_Y)

    def is_offscreen(self):
        """Returns True when chunk has completely left the screen."""
        return (self.x + CHUNK_WIDTH) <= 0

    def destroy(self):
        """Deletes chunk from canvas to free memory."""
        self.canvas.delete(self.item_id)


class GroundChunkManager:
    """
    Chunk-Based Infinite Terrain Manager:
    1. Scrolls all ground chunks to the left.
    2. Deletes chunks when they reach the left screen edge.
    3. Spawns new random chunks seamlessly at the right edge.
    """

    def __init__(self, canvas, chunk_images):
        self.canvas = canvas
        self.chunk_images = chunk_images
        self.chunks = []
        self.reset()

    def reset(self):
        """Clears existing chunks and seeds new ones across the screen."""
        for chunk in self.chunks:
            chunk.destroy()
        self.chunks.clear()

        # Fill screen with chunks + extra padding off-screen to the right
        num_chunks = (WINDOW_WIDTH // CHUNK_WIDTH) + 2
        for i in range(num_chunks):
            chunk = GroundChunk(self.canvas, i * CHUNK_WIDTH, random.choice(self.chunk_images))
            self.chunks.append(chunk)

    def update(self, speed):
        """Moves chunks, deletes off-screen chunks, and spawns new ones."""
        # 1. Move all chunks
        for chunk in self.chunks:
            chunk.move(speed)

        # 2. Delete leftmost chunk if off-screen
        while len(self.chunks) > 0 and self.chunks[0].is_offscreen():
            old_chunk = self.chunks.pop(0)
            old_chunk.destroy()

            # 3. Connect new chunk at the right edge
            new_x = self.chunks[-1].x + CHUNK_WIDTH
            new_chunk = GroundChunk(self.canvas, new_x, random.choice(self.chunk_images))
            self.chunks.append(new_chunk)


# ==============================================================================
# 4. MAIN FLAP THE BIRD GAME CLASS
# ==============================================================================

class FlapTheBirdGame:
    def __init__(self, root):
        self.root = root
        self.root.title("Flap the Bird")
        self.root.geometry(f"{WINDOW_WIDTH}x{WINDOW_HEIGHT}")
        self.root.resizable(False, False)

        # Center window on monitor
        screen_w = self.root.winfo_screenwidth()
        screen_h = self.root.winfo_screenheight()
        pos_x = (screen_w - WINDOW_WIDTH) // 2
        pos_y = (screen_h - WINDOW_HEIGHT) // 2
        self.root.geometry(f"+{pos_x}+{pos_y}")

        # Tkinter Drawing Canvas
        self.canvas = tk.Canvas(self.root, width=WINDOW_WIDTH, height=WINDOW_HEIGHT, highlightthickness=0)
        self.canvas.pack()

        # Active Bird & Theme selections
        self.bird_index = 0
        self.current_bird = BIRD_TYPES[self.bird_index]
        self.theme_index = 0
        self.current_theme = THEME_TYPES[self.theme_index]

        # Load game assets and high score
        self.load_assets()
        self.high_score = self.load_high_score()

        # Build permanent canvas layers (Background -> Pipes -> Ground -> Bird -> UI)
        self.build_canvas_layers()

        # Initialize ground chunks
        self.ground_manager = GroundChunkManager(self.canvas, self.img_ground_chunks)

        # Key and mouse controls
        self.root.bind("<space>", self.on_jump)
        self.root.bind("<b>", lambda e: self.cycle_bird())
        self.root.bind("<B>", lambda e: self.cycle_bird())
        self.root.bind("<t>", lambda e: self.cycle_theme())
        self.root.bind("<T>", lambda e: self.cycle_theme())
        self.root.bind("<m>", lambda e: self.toggle_music())
        self.root.bind("<M>", lambda e: self.toggle_music())
        self.canvas.bind("<Button-1>", self.on_click)
        self.canvas.bind("<Motion>", self.on_mouse_move)

        # Clean shutdown when closing window
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

        # High-FPS timing & start game
        self.last_frame_time = time.perf_counter()
        self.reset_game()
        MusicPlayer.play_theme(self.current_theme)
        self.game_loop()

    # --------------------------------------------------------------------------
    # ASSET LOADING & ROTATION CACHE
    # --------------------------------------------------------------------------
    def load_assets(self):
        """Loads all images and sets up bird rotation cache."""
        # 1. Backgrounds & Pipes for each theme
        self.img_backgrounds = {}
        self.img_pipes_top = {}
        self.img_pipes_bottom = {}
        for th in THEME_TYPES:
            self.img_backgrounds[th] = ImageTk.PhotoImage(Image.open(f"assets/themes/{th}/background.png"))
            self.img_pipes_top[th] = ImageTk.PhotoImage(Image.open(f"assets/themes/{th}/pipe_top.png"))
            self.img_pipes_bottom[th] = ImageTk.PhotoImage(Image.open(f"assets/themes/{th}/pipe_bottom.png"))

        # 2. Modular ground chunk variants
        self.img_ground_chunks = [
            ImageTk.PhotoImage(Image.open(f"assets/ground_chunks/chunk_{i}.png"))
            for i in range(4)
        ]

        # 3. UI Banners
        self.img_start = ImageTk.PhotoImage(Image.open("assets/ui/start_message.png"))
        self.img_game_over = ImageTk.PhotoImage(Image.open("assets/ui/game_over.png"))

        # 4. Medals
        self.img_medals = {
            "bronze": ImageTk.PhotoImage(Image.open("assets/medals/bronze.png")),
            "silver": ImageTk.PhotoImage(Image.open("assets/medals/silver.png")),
            "gold": ImageTk.PhotoImage(Image.open("assets/medals/gold.png")),
            "platinum": ImageTk.PhotoImage(Image.open("assets/medals/platinum.png"))
        }

        # 5. Raw PIL Bird images for rotation
        self.bird_pil_frames = {}
        for b_id in BIRD_TYPES:
            self.bird_pil_frames[b_id] = [
                Image.open(f"assets/birds/{b_id}/bird.png").convert("RGBA"),
                Image.open(f"assets/birds/{b_id}/bird_up.png").convert("RGBA"),
                Image.open(f"assets/birds/{b_id}/bird_down.png").convert("RGBA")
            ]
        self.rotated_cache = {}

    def get_rotated_bird(self, bird_id, frame_idx, angle):
        """Returns a smoothly rotated bird image from cache."""
        rounded_angle = int(round(angle / 5.0) * 5)
        rounded_angle = max(-75, min(25, rounded_angle))
        key = (bird_id, frame_idx, rounded_angle)
        if key not in self.rotated_cache:
            pil_img = self.bird_pil_frames[bird_id][frame_idx]
            rot = pil_img.rotate(rounded_angle, resample=Image.Resampling.BICUBIC)
            self.rotated_cache[key] = ImageTk.PhotoImage(rot)
        return self.rotated_cache[key]

    # --------------------------------------------------------------------------
    # HIGH SCORE FILE MANAGEMENT
    # --------------------------------------------------------------------------
    def load_high_score(self):
        """Reads best score from highscore.txt."""
        if os.path.exists("highscore.txt"):
            try:
                with open("highscore.txt", "r") as f:
                    return int(f.read().strip())
            except Exception:
                pass
        return 0

    def save_high_score(self):
        """Saves best score to highscore.txt."""
        try:
            with open("highscore.txt", "w") as f:
                f.write(str(self.high_score))
        except Exception:
            pass

    # --------------------------------------------------------------------------
    # CANVAS LAYER INITIALIZATION (Permanent items for smooth 60 FPS)
    # --------------------------------------------------------------------------
    def build_canvas_layers(self):
        """Creates permanent canvas items with proper z-ordering."""
        # Layer 1: Background
        self.item_background = self.canvas.create_image(
            0, 0, image=self.img_backgrounds[self.current_theme], anchor="nw", tags="bg"
        )

        # Layer 2: Pipes Pool (3 reusable pairs)
        self.pipe_items = []
        for _ in range(3):
            top_id = self.canvas.create_image(-200, -200, image=self.img_pipes_top[self.current_theme], anchor="sw", tags="pipe")
            bot_id = self.canvas.create_image(-200, -200, image=self.img_pipes_bottom[self.current_theme], anchor="nw", tags="pipe")
            self.pipe_items.append({"top": top_id, "bottom": bot_id})

        # Layer 4: Bird
        first_sprite = self.get_rotated_bird(self.current_bird, 0, 0)
        self.item_bird = self.canvas.create_image(100, 250, image=first_sprite, anchor="center", tags="bird")

        # Layer 5: UI Elements (Score, Pills, Banners)
        self.item_score_shadow = self.canvas.create_text(202, 62, text="0", fill="#1e1e1e", font=("Helvetica", 36, "bold"), state="hidden", tags="ui")
        self.item_score = self.canvas.create_text(200, 60, text="0", fill="#ffffff", font=("Helvetica", 36, "bold"), state="hidden", tags="ui")

        # Start Screen UI
        self.item_ui_start = self.canvas.create_image(200, 160, image=self.img_start, anchor="center", state="normal", tags="ui")

        # Bird Selector Button Pill (x: 60-340, y: 285-325)
        self.item_pill_bird_bg = self.canvas.create_rectangle(60, 285, 340, 325, fill="#f47920", outline="#ffffff", width=2, state="normal", tags="ui")
        self.item_pill_bird_txt = self.canvas.create_text(200, 305, text=f"BIRD: < {BIRD_NAMES[self.current_bird]} >", fill="#ffffff", font=("Helvetica", 11, "bold"), state="normal", tags="ui")

        # Theme Selector Button Pill (x: 60-340, y: 340-380)
        self.item_pill_theme_bg = self.canvas.create_rectangle(60, 340, 340, 380, fill="#2b5c8f", outline="#ffffff", width=2, state="normal", tags="ui")
        self.item_pill_theme_txt = self.canvas.create_text(200, 360, text=f"THEME: < {THEME_NAMES[self.current_theme]} >", fill="#ffffff", font=("Helvetica", 11, "bold"), state="normal", tags="ui")

        self.item_pill_hint = self.canvas.create_text(200, 405, text="[B] Bird   •   [T] Theme   •   [M] Mute BGM", fill="#ffffff", font=("Helvetica", 9, "bold"), state="normal", tags="ui")

        # Game Over UI Group
        self.item_ui_gameover = self.canvas.create_image(200, 160, image=self.img_game_over, anchor="center", state="hidden", tags="ui")
        self.item_card_bg = self.canvas.create_rectangle(60, 220, 340, 350, fill="#ded895", outline="#503214", width=3, state="hidden", tags="ui")
        self.item_card_medal = self.canvas.create_image(115, 285, image=self.img_medals["bronze"], anchor="center", state="hidden", tags="ui")

        self.item_card_lbl_score = self.canvas.create_text(240, 245, text="SCORE", fill="#e65100", font=("Helvetica", 11, "bold"), state="hidden", tags="ui")
        self.item_card_val_score = self.canvas.create_text(240, 270, text="0", fill="#ffffff", font=("Helvetica", 20, "bold"), state="hidden", tags="ui")
        self.item_card_lbl_best = self.canvas.create_text(240, 300, text="BEST", fill="#e65100", font=("Helvetica", 11, "bold"), state="hidden", tags="ui")
        self.item_card_val_best = self.canvas.create_text(240, 325, text="0", fill="#ffffff", font=("Helvetica", 20, "bold"), state="hidden", tags="ui")

        self.item_btn_rect = self.canvas.create_rectangle(120, 380, 280, 430, fill="#f47920", outline="#ffffff", width=2, state="hidden", tags="ui")
        self.item_btn_text = self.canvas.create_text(200, 405, text="PLAY AGAIN", fill="#ffffff", font=("Helvetica", 14, "bold"), state="hidden", tags="ui")
        self.item_restart_hint = self.canvas.create_text(200, 450, text="(or press SPACEBAR to restart)", fill="#ffffff", font=("Helvetica", 10, "bold"), state="hidden", tags="ui")

    # --------------------------------------------------------------------------
    # BIRD, THEME & MUSIC TOGGLES
    # --------------------------------------------------------------------------
    def cycle_bird(self):
        """Cycles to the next bird character skin & plays its custom chirp."""
        self.bird_index = (self.bird_index + 1) % len(BIRD_TYPES)
        self.current_bird = BIRD_TYPES[self.bird_index]
        self.canvas.itemconfig(self.item_pill_bird_txt, text=f"BIRD: < {BIRD_NAMES[self.current_bird]} >")
        SoundPlayer.play(f"select_bird_{self.current_bird}")

    def cycle_theme(self):
        """Cycles to the next background theme & starts its cozy music loop."""
        self.theme_index = (self.theme_index + 1) % len(THEME_TYPES)
        self.current_theme = THEME_TYPES[self.theme_index]

        # Update background image
        self.canvas.itemconfig(self.item_background, image=self.img_backgrounds[self.current_theme])

        # Update pipes to matching theme colors
        for pipe_pair in self.pipe_items:
            self.canvas.itemconfig(pipe_pair["top"], image=self.img_pipes_top[self.current_theme])
            self.canvas.itemconfig(pipe_pair["bottom"], image=self.img_pipes_bottom[self.current_theme])

        self.canvas.itemconfig(self.item_pill_theme_txt, text=f"THEME: < {THEME_NAMES[self.current_theme]} >")
        SoundPlayer.play(f"select_theme_{self.current_theme}")
        MusicPlayer.play_theme(self.current_theme)

    def toggle_music(self):
        """Toggles music on/off."""
        is_muted = MusicPlayer.toggle_mute()
        print(f"[Music] {'Muted' if is_muted else 'Playing'}")

    def on_close(self):
        """Clean shutdown of background threads and timer resolution."""
        if sys.platform == "win32":
            try:
                ctypes.windll.winmm.timeEndPeriod(1)
            except Exception:
                pass
        MusicPlayer.stop()
        self.root.destroy()

    # --------------------------------------------------------------------------
    # GAME STATE MANAGEMENT
    # --------------------------------------------------------------------------
    def reset_game(self):
        """Resets bird, pipes, and ground to the start screen state."""
        self.bird_x = 100
        self.bird_y = 220
        self.bird_velocity = 0.0
        self.bird_angle = 0.0

        self.bird_frame_idx = 0
        self.bird_anim_counter = 0.0
        self.start_bob_counter = 0.0
        self.last_frame_time = time.perf_counter()

        # Reset pipes
        self.pipes = []
        self.spawn_pipe(420)
        self.spawn_pipe(420 + PIPE_DISTANCE)

        # Reset ground chunks
        self.ground_manager.reset()

        self.game_state = "START"
        self.score = 0
        self.update_ui_state()

    def spawn_pipe(self, x_pos):
        """Creates a top & bottom pipe pair with a random center opening."""
        gap_center = random.randint(180, 330)
        top_y = gap_center - (PIPE_GAP // 2)
        bottom_y = gap_center + (PIPE_GAP // 2)
        self.pipes.append({
            "x": x_pos,
            "top_y": top_y,
            "bottom_y": bottom_y,
            "passed": False
        })

    # --------------------------------------------------------------------------
    # CONTROLS (SPACEBAR & MOUSE CLICKS)
    # --------------------------------------------------------------------------
    def on_jump(self, event=None):
        """Spacebar jump control."""
        if self.game_state == "START":
            self.game_state = "PLAYING"
            self.last_frame_time = time.perf_counter()
            self.bird_velocity = JUMP_STRENGTH
            SoundPlayer.play("flap")
            self.update_ui_state()

        elif self.game_state == "PLAYING":
            self.bird_velocity = JUMP_STRENGTH
            SoundPlayer.play("flap")

        elif self.game_state == "GAMEOVER":
            self.reset_game()

    def on_click(self, event):
        """Mouse click control."""
        if self.game_state == "START":
            # Clicked on Bird selector pill (y: 285-325)
            if 60 <= event.x <= 340 and 285 <= event.y <= 325:
                self.cycle_bird()
                return

            # Clicked on Theme selector pill (y: 340-380)
            if 60 <= event.x <= 340 and 340 <= event.y <= 380:
                self.cycle_theme()
                return

            self.on_jump()

        elif self.game_state == "GAMEOVER":
            self.reset_game()

        else:
            self.on_jump()

    def on_mouse_move(self, event):
        """Highlights buttons when hovering over them."""
        if self.game_state == "START":
            if 60 <= event.x <= 340 and 285 <= event.y <= 325:
                self.canvas.itemconfig(self.item_pill_bird_bg, fill="#ff9933")
                self.canvas.config(cursor="hand2")
            elif 60 <= event.x <= 340 and 340 <= event.y <= 380:
                self.canvas.itemconfig(self.item_pill_theme_bg, fill="#3d7ab8")
                self.canvas.config(cursor="hand2")
            else:
                self.canvas.itemconfig(self.item_pill_bird_bg, fill="#f47920")
                self.canvas.itemconfig(self.item_pill_theme_bg, fill="#2b5c8f")
                self.canvas.config(cursor="")

        elif self.game_state == "GAMEOVER":
            if 120 <= event.x <= 280 and 380 <= event.y <= 430:
                self.canvas.itemconfig(self.item_btn_rect, fill="#f7d02c", outline="#ffffff")
                self.canvas.itemconfig(self.item_btn_text, fill="#503214")
                self.canvas.config(cursor="hand2")
            else:
                self.canvas.itemconfig(self.item_btn_rect, fill="#f47920", outline="#ffffff")
                self.canvas.itemconfig(self.item_btn_text, fill="#ffffff")
                self.canvas.config(cursor="")
        else:
            self.canvas.config(cursor="")

    # --------------------------------------------------------------------------
    # HIGH-REFRESH RATE LOOP (120-140 FPS) & DYNAMIC SPEED
    # --------------------------------------------------------------------------
    def get_current_speed(self):
        """Calculates dynamic speed: starts at BASE_SCROLL_SPEED and ramps up with score."""
        bonus = min(MAX_SCROLL_SPEED - BASE_SCROLL_SPEED, self.score * SPEED_INCREMENT)
        return BASE_SCROLL_SPEED + bonus

    def game_loop(self):
        """Runs at ultra-smooth high FPS (up to ~140 FPS with sub-frame delta-time physics)."""
        now = time.perf_counter()
        dt = now - self.last_frame_time
        self.last_frame_time = now

        # Clamp dt between 1ms and 50ms (prevents large jumps if window paused/dragged)
        dt = max(0.001, min(0.05, dt))

        # Time factor normalized to 60 FPS reference:
        # At 60 FPS: time_factor = 1.0
        # At 140 FPS: time_factor = 0.43 (2.3x smoother updates!)
        time_factor = dt * 60.0

        self.update_physics(time_factor)
        self.update_canvas_positions()
        # 7ms delay for ~140 FPS target
        self.root.after(7, self.game_loop)

    def update_physics(self, time_factor=1.0):
        """Updates bird movement, ground chunks, pipes, and checks collisions with delta-time."""
        # 1. Animate flapping wings (every 5 standard frames)
        self.bird_anim_counter += time_factor
        if self.bird_anim_counter >= 5.0:
            self.bird_anim_counter = 0.0
            self.bird_frame_idx = (self.bird_frame_idx + 1) % 3

        # State 1: START SCREEN (Bird floats gently up and down)
        if self.game_state == "START":
            self.start_bob_counter += 0.08 * time_factor
            self.bird_y = 220 + math.sin(self.start_bob_counter) * 6.0
            self.bird_angle = 0.0
            self.ground_manager.update(1.2 * time_factor)
            return

        # State 2: PLAYING
        if self.game_state == "PLAYING":
            # Dynamic speed increases as you score points!
            current_speed = self.get_current_speed()

            # Move ground chunks (chunks delete when reaching left edge)
            self.ground_manager.update(current_speed * time_factor)

            # Apply gravity to bird
            self.bird_velocity += GRAVITY * time_factor
            self.bird_y += self.bird_velocity * time_factor

            # Smoothly tilt bird based on velocity
            target_angle = max(-75.0, min(25.0, -self.bird_velocity * 4.5))
            self.bird_angle += (target_angle - self.bird_angle) * min(1.0, 0.22 * time_factor)

            # Move pipes to the left
            for pipe in self.pipes:
                pipe["x"] -= current_speed * time_factor

                # Score point when bird passes the pipe
                if not pipe["passed"] and (self.bird_x > pipe["x"] + 33):
                    pipe["passed"] = True
                    self.score += 1
                    SoundPlayer.play("point")
                    if self.score > self.high_score:
                        self.high_score = self.score
                        self.save_high_score()
                    self.canvas.itemconfig(self.item_score, text=str(self.score))
                    self.canvas.itemconfig(self.item_score_shadow, text=str(self.score))

            # Remove off-screen pipes and spawn next pipe with speed-adapted spacing
            if len(self.pipes) > 0 and self.pipes[0]["x"] < -80:
                self.pipes.pop(0)
                last_x = self.pipes[-1]["x"]
                dynamic_spacing = PIPE_DISTANCE + (current_speed - BASE_SCROLL_SPEED) * 16.0
                self.spawn_pipe(last_x + dynamic_spacing)

            # Check collisions
            self.check_collisions()

        # State 3: GAME OVER (Bird falls to the ground)
        elif self.game_state == "GAMEOVER":
            if self.bird_y + 16 < GROUND_Y:
                self.bird_velocity += GRAVITY * time_factor
                self.bird_y += self.bird_velocity * time_factor
                self.bird_angle = max(-75.0, self.bird_angle - 4.0 * time_factor)
            else:
                self.bird_y = GROUND_Y - 16

    # --------------------------------------------------------------------------
    # COLLISION DETECTION
    # --------------------------------------------------------------------------
    def check_collisions(self):
        """Checks if bird hits ground, ceiling, or any pipes (forgiving hitbox)."""
        hit_w = 12
        hit_h = 9

        # 1. Ground collision
        if (self.bird_y + hit_h) >= GROUND_Y:
            self.bird_y = GROUND_Y - hit_h
            self.trigger_game_over()
            return

        # 2. Ceiling collision
        if self.bird_y - hit_h <= 0:
            self.bird_y = hit_h
            self.bird_velocity = 0.5

        # 3. Pipe collisions
        pipe_w = 66
        for pipe in self.pipes:
            px = pipe["x"]
            if (self.bird_x + hit_w > px) and (self.bird_x - hit_w < px + pipe_w):
                if (self.bird_y - hit_h < pipe["top_y"]) or (self.bird_y + hit_h > pipe["bottom_y"]):
                    self.trigger_game_over()
                    return

    def trigger_game_over(self):
        """Called when bird crashes."""
        if self.game_state != "GAMEOVER":
            self.game_state = "GAMEOVER"
            self.bird_velocity = 1.0
            if self.score > self.high_score:
                self.high_score = self.score
                self.save_high_score()
            SoundPlayer.play("hit")
            self.update_ui_state()

    # --------------------------------------------------------------------------
    # DISPLAY UPDATES & UI SYSTEM
    # --------------------------------------------------------------------------
    def update_canvas_positions(self):
        """Updates pipe coords and rotated bird sprite on the canvas."""
        # 1. Update Pipe positions
        for i, pipe_pair in enumerate(self.pipe_items):
            if i < len(self.pipes):
                p = self.pipes[i]
                self.canvas.coords(pipe_pair["top"], p["x"], p["top_y"])
                self.canvas.coords(pipe_pair["bottom"], p["x"], p["bottom_y"])
            else:
                self.canvas.coords(pipe_pair["top"], -200, -200)
                self.canvas.coords(pipe_pair["bottom"], -200, -200)

        # 2. Update bird position and rotated sprite
        bird_sprite = self.get_rotated_bird(self.current_bird, self.bird_frame_idx, self.bird_angle)
        self.canvas.coords(self.item_bird, int(self.bird_x), int(self.bird_y))
        self.canvas.itemconfig(self.item_bird, image=bird_sprite)

    def update_ui_state(self):
        """Manages display state of banners, buttons, score, and medals."""
        if self.game_state == "START":
            self.canvas.itemconfig(self.item_ui_start, state="normal")
            self.canvas.itemconfig(self.item_pill_bird_bg, state="normal")
            self.canvas.itemconfig(self.item_pill_bird_txt, text=f"BIRD: < {BIRD_NAMES[self.current_bird]} >", state="normal")
            self.canvas.itemconfig(self.item_pill_theme_bg, state="normal")
            self.canvas.itemconfig(self.item_pill_theme_txt, text=f"THEME: < {THEME_NAMES[self.current_theme]} >", state="normal")
            self.canvas.itemconfig(self.item_pill_hint, state="normal")

            self.canvas.itemconfig(self.item_score, state="hidden")
            self.canvas.itemconfig(self.item_score_shadow, state="hidden")
            self.set_game_over_group("hidden")

        elif self.game_state == "PLAYING":
            self.canvas.itemconfig(self.item_ui_start, state="hidden")
            self.canvas.itemconfig(self.item_pill_bird_bg, state="hidden")
            self.canvas.itemconfig(self.item_pill_bird_txt, state="hidden")
            self.canvas.itemconfig(self.item_pill_theme_bg, state="hidden")
            self.canvas.itemconfig(self.item_pill_theme_txt, state="hidden")
            self.canvas.itemconfig(self.item_pill_hint, state="hidden")

            self.canvas.itemconfig(self.item_score, text=str(self.score), state="normal")
            self.canvas.itemconfig(self.item_score_shadow, text=str(self.score), state="normal")
            self.set_game_over_group("hidden")

        elif self.game_state == "GAMEOVER":
            self.canvas.itemconfig(self.item_ui_start, state="hidden")
            self.canvas.itemconfig(self.item_pill_bird_bg, state="hidden")
            self.canvas.itemconfig(self.item_pill_bird_txt, state="hidden")
            self.canvas.itemconfig(self.item_pill_theme_bg, state="hidden")
            self.canvas.itemconfig(self.item_pill_theme_txt, state="hidden")
            self.canvas.itemconfig(self.item_pill_hint, state="hidden")

            self.canvas.itemconfig(self.item_score, state="hidden")
            self.canvas.itemconfig(self.item_score_shadow, state="hidden")

            # Update score card
            self.canvas.itemconfig(self.item_card_val_score, text=str(self.score))
            self.canvas.itemconfig(self.item_card_val_best, text=str(self.high_score))
            self.set_game_over_group("normal")

            # Instant Medal logic
            if self.score >= 10:
                medal_key = "platinum"
            elif self.score >= 6:
                medal_key = "gold"
            elif self.score >= 3:
                medal_key = "silver"
            else:
                medal_key = "bronze"

            self.canvas.itemconfig(self.item_card_medal, image=self.img_medals[medal_key], state="normal")

    def set_game_over_group(self, state):
        """Helper to toggle all Game Over items on/off."""
        items = [
            self.item_ui_gameover,
            self.item_card_bg,
            self.item_card_medal,
            self.item_card_lbl_score,
            self.item_card_val_score,
            self.item_card_lbl_best,
            self.item_card_val_best,
            self.item_btn_rect,
            self.item_btn_text,
            self.item_restart_hint
        ]
        for itm in items:
            self.canvas.itemconfig(itm, state=state)


# Alias for backward compatibility
FlappyBirdGame = FlapTheBirdGame


# ==============================================================================
# 5. GAME LAUNCHER
# ==============================================================================

def main():
    if sys.platform == "win32":
        try:
            # Request 1ms timer precision from Windows kernel for ultra-smooth 120-140 FPS
            ctypes.windll.winmm.timeBeginPeriod(1)
        except Exception:
            pass
    root = tk.Tk()
    app = FlapTheBirdGame(root)
    root.mainloop()


if __name__ == "__main__":
    main()
