import arcade
import arcade.gui
import paho.mqtt.client as mqtt
import json
import random
import threading
import time


###############
# JSON FUNCTION
###############

def load_leaderboard():
    """Carica la classifica dal file JSON"""
    with open("leaderboard.json", "r") as f:
        return json.load(f)


def save_leaderboard(leaderboard):
    """Salva la classifica nel file JSON"""
    with open("leaderboard.json", "w") as f:
        json.dump(leaderboard, f, indent=2)

def add_record(player_name, time_seconds):
    """Aggiungi un record per un giocatore"""
    leaderboard = load_leaderboard()

    # Aggiungi nuovo record
    leaderboard.append({
        "name": player_name,
        "time": round(time_seconds, 2)
    })

    # Ordina per tempo (crescente = più veloce prima)
    leaderboard.sort(key=lambda x: x["time"])

    save_leaderboard(leaderboard)
    return leaderboard

def get_top_players(n=10):
    """Ottieni i top N giocatori più veloci"""
    leaderboard = load_leaderboard()
    return leaderboard[:n]

def format_time(seconds):
    """Formatta il tempo in mm:ss.ms"""
    minutes = int(seconds // 60)
    secs = seconds % 60
    return f"{minutes:02d}:{secs:05.2f}"


####################
# SETTINGS LABIRINTO
####################

MAZE_SIZE = 57
exit_pos = [int(MAZE_SIZE / 2), int(MAZE_SIZE / 2)]
positions = {"player1": [1, 1], "player2": [MAZE_SIZE - 2, MAZE_SIZE - 2]}


#######################
# GENERAZIONE LABIRINTO
#######################

def genera_labirinto_simmetrico(size, difficult=0.5):
    """
    Genera labirinto simmetrico 4-quadranti
    Player 1 (1,1) e Player 2 (N-2,N-2) avranno SEMPRE stessa distanza dall'uscita
    """
    assert size % 2 == 1, "Size deve essere dispari per simmetria"

    # Dimensione quadrante (es. size=31 -> quadrante=15)
    quad_size = size // 2 + 1  # 16 per size=31

    # 1. Genera solo il QUADRANTE SUPERIORE SINISTRO
    quad = [[1 for _ in range(quad_size)] for _ in range(quad_size)]

    # Parametro di difficoltà
    dead_end_prob = difficult
    dead_end_temperature = 1

    # DFS solo nel quadrante
    stack = [(1, 1)]
    quad[1][1] = 0

    directions = [(0, 2), (2, 0), (0, -2), (-2, 0)]

    while stack:
        x, y = stack[-1]
        random.shuffle(directions)
        found = False

        for dx, dy in directions:
            nx, ny = x + dx, y + dy
            if 0 < nx < quad_size - 1 and 0 < ny < quad_size - 1:
                if quad[ny][nx] == 1:
                    found = True

                    # Aggiungo un dead end prima che tolga il muro, per evitare loop
                    if random.random() < (dead_end_prob * dead_end_temperature):
                        dead_end_temperature -= 0.1 * random.random()
                        break

                    quad[ny][nx] = 0
                    quad[y + dy // 2][x + dx // 2] = 0
                    stack.append((nx, ny))
                    break

        if not found:
            stack.pop()

    # Genera il labirinto a grandezza originale
    grid = [[1 for _ in range(size)] for _ in range(size)]

    for qy in range(quad_size):
        for qx in range(quad_size):
            grid[qy][qx] = quad[qy][qx]
            grid[qy][size - 1 - qx] = quad[qy][qx]
            grid[size - 1 - qy][qx] = quad[qy][qx]
            grid[size - 1 - qy][size - 1 - qx] = quad[qy][qx]

    # 3. Assicura celle chiave percorribili
    center = size // 2

    # 4. Collega i quadranti al centro (se necessario)
    for i in range(center - 2, center + 3):
        for j in range(center - 2, center + 3):
            if 0 <= i < size and 0 <= j < size:
                grid[i][j] = 0

    return grid


#####################
# GUI MINIMALE SERVER
#####################

class ServerDashboard(arcade.Window):
    def __init__(self):
        super().__init__(1300, 500, "🎮 Maze Server Dashboard")
        arcade.set_background_color(arcade.color.MIDNIGHT_BLUE)

        # Texture labirinto
        self.wall_texture = arcade.load_texture("./assets/wall.png")
        self.floor_texture = arcade.load_texture("./assets/floor.png")

        # UI Manager
        self.manager = arcade.gui.UIManager(self)
        self.manager.enable()

        # Stato
        self.needs_update = False
        self.pending_winner = None
        self.players_connected = 0
        self.player_names = {}
        self.winner = None
        self.game_started = False
        self.maze = None

        # Area labirinto vs GUI
        self.maze_area_width = 800
        self.gui_area_x = self.maze_area_width

        # SpriteList per il labirinto
        self.maze_sprite_list = None

        # Genera labirinto
        self.maze = genera_labirinto_simmetrico(MAZE_SIZE)

        # Costruisci sprite subito
        self.build_maze_sprites()

        # Timer di gioco
        self.game_start_time = None

        # Leaderboard
        self.leaderboard = get_top_players(20)

        # MQTT Client
        self.client = mqtt.Client(callback_api_version=mqtt.CallbackAPIVersion.VERSION2)
        self.client.on_connect = self.on_mqtt_connect
        self.client.on_message = self.on_mqtt_message
        self.client.connect("localhost", 1883, 60)
        threading.Thread(target=self.client.loop_forever, daemon=True).start()

        # Build UI
        self.draw_ui()
        self.draw_leaderboard()

        print(f"🚀 Server Dashboard avviato! Labirinto {MAZE_SIZE}x{MAZE_SIZE}")

    def build_maze_sprites(self):
        """Costruisci il labirinto come sprite (una volta sola)"""
        if not self.maze:
            return

        print("🔨 Costruzione sprite labirinto server...")
        self.maze_sprite_list = arcade.SpriteList()

        cell_size = 6
        offset_x = (self.width - MAZE_SIZE * cell_size - 40)
        offset_y = (self.height - MAZE_SIZE * cell_size) // 2

        for y in range(MAZE_SIZE):
            for x in range(MAZE_SIZE):
                center_x = offset_x + x * cell_size + cell_size // 2
                center_y = offset_y + y * cell_size + cell_size // 2

                if self.maze[y][x] != 0:
                    sprite = arcade.Sprite("./assets/wall.png",
                                           scale=cell_size / self.wall_texture.width)
                else:
                    sprite = arcade.Sprite("./assets/floor.png",
                                           scale=cell_size / self.floor_texture.width)

                sprite.center_x = center_x
                sprite.center_y = center_y
                self.maze_sprite_list.append(sprite)

        print("✅ Sprite labirinto server costruiti!")

    def on_mqtt_connect(self, client, userdata, flags, rc, properties):
        print("✅ Server Dashboard connesso a MQTT")
        client.subscribe("maze/player1/move")
        client.subscribe("maze/player2/move")
        client.subscribe("maze/player1/join")
        client.subscribe("maze/player2/join")

    def on_mqtt_message(self, client, userdata, msg):
        try:
            data = json.loads(msg.payload)

            if "join" in msg.topic:
                player_name = data.get("name", "Unknown")

                if player_name not in self.player_names.values():
                    player_id = "player1" if "player1" in msg.topic else "player2"
                    print(player_id)
                    self.player_names[player_id] = player_name
                    self.players_connected = len(self.player_names)

                    self.needs_update = True

                    print(f"👤 {player_name} connesso! ({self.players_connected}/2)")

            elif "move" in msg.topic:
                if not self.game_started:
                    return

                player_id = "player1" if "player1" in msg.topic else "player2"
                new_pos = data["pos"]

                positions[player_id] = new_pos
                client.publish(f"maze/{player_id}/pos", json.dumps(new_pos))

                # CHECK VITTORIA
                if ((abs(new_pos[0] - exit_pos[0]) in [-1, 0, 1]) and
                        (abs(new_pos[1] - exit_pos[1]) in [-1, 0, 1])):
                    # Stop timer
                    elapsed_time = time.time() - self.game_start_time
                    winner_name = self.player_names[player_id]

                    # Aggiungo al file leaderboard
                    self.leaderboard = add_record(winner_name, elapsed_time)

                    self.winner = player_id

                    self.pending_winner = (player_id, winner_name, elapsed_time)
                    self.needs_update = True

                    client.publish("maze/winner", json.dumps({"winner": player_id}))
                    print(f"🏆 {player_id.upper()} HA VINTO!")

        except Exception as e:
            print(f"❌ Errore MQTT: {e}")

    def draw_ui(self):
        # Layout principale
        hbox = arcade.gui.UIBoxLayout(align="center")

        # Titolo
        title = arcade.gui.UILabel(
            text="🎮 Maze Server Dashboard",
            font_size=28,
            text_color=arcade.color.WHITE)
        hbox.add(title)

        # Info labirinto
        lbl_maze = arcade.gui.UILabel(
            text=f"Labirinto: {MAZE_SIZE}x{MAZE_SIZE}",
            font_size=16,
            text_color=arcade.color.LIGHT_GRAY)
        hbox.add(lbl_maze)
        hbox.add(arcade.gui.UISpace(height=40))

        # Label contatore giocatori
        self.lbl_players = arcade.gui.UILabel(
            text="Giocatori connessi: 0/2",
            font_size=22,
            text_color=arcade.color.LIGHT_BLUE)
        hbox.add(self.lbl_players)

        # Lista nomi giocatori
        self.lbl_names = arcade.gui.UILabel(
            text="In attesa di giocatori...",
            font_size=16,
            text_color=arcade.color.LIGHT_GRAY)
        hbox.add(self.lbl_names)
        hbox.add(arcade.gui.UISpace(height=40))

        # Bottone START
        self.btn_start = arcade.gui.UIFlatButton(
            text="🚀 START GAME",
            width=250,
            height=70)
        self.btn_start.on_click = self.on_start_click
        hbox.add(self.btn_start)
        hbox.add(arcade.gui.UISpace(height=40))

        # Bottone RESET
        self.btn_reset = arcade.gui.UIFlatButton(
            text="🔄 RESET GAME",
            width=250,
            height=50)
        self.btn_reset.on_click = self.on_reset_click
        hbox.add(self.btn_reset)
        hbox.add(arcade.gui.UISpace(height=40))

        # Status label
        self.lbl_status = arcade.gui.UILabel(
            text="⏳ Attendi 2 giocatori per iniziare",
            font_size=14,
            text_color=arcade.color.YELLOW)
        hbox.add(self.lbl_status)
        hbox.add(arcade.gui.UISpace(height=40))

        # Anchor layout
        anchor = self.manager.add(arcade.gui.UIAnchorLayout(size_hint=(1, 1)))
        anchor.add(child=hbox, anchor_x="center_x", anchor_y="center_y", align_x=50)

    def draw_leaderboard(self):
        """Disegna la leaderboard a sinistra"""
        # Se esiste già, rimuovila prima
        if hasattr(self, 'leaderboard_anchor'):
            self.manager.remove(self.leaderboard_anchor)

        self.leaderboard = get_top_players(20)
        hbox = arcade.gui.UIBoxLayout(align="center")

        title = arcade.gui.UILabel(
            text="Top Players",
            font_size=20,
            text_color=arcade.color.WHITE)
        hbox.add(title)
        hbox.add(arcade.gui.UISpace(height=20))

        for i, record in enumerate(self.leaderboard, 1):
            text_line = f"{i}. {record['name']}: {format_time(record['time'])}"
            sample = arcade.gui.UILabel(
                text=text_line,
                font_size=12,
                text_color=arcade.color.WHITE)
            hbox.add(sample)

        # Salva il riferimento per poterlo rimuovere dopo
        self.leaderboard_anchor = self.manager.add(arcade.gui.UIAnchorLayout(size_hint=(1, 1)))
        self.leaderboard_anchor.add(child=hbox, anchor_x="left", anchor_y="center_y", align_x=50)

    def update_labels(self):
        """Aggiorna le label con i dati correnti"""
        self.lbl_players.text = f"Giocatori connessi: {self.players_connected}/2"

        if self.player_names:
            names_str = "\n".join([f"- {name}" for name in self.player_names.values()])
            self.lbl_names.text = names_str
        else:
            self.lbl_names.text = "In attesa di giocatori..."

        if self.players_connected >= 2 and not self.game_started:
            self.lbl_status.text = "✅ Pronti! Clicca START GAME"
            self.lbl_status.text_color = arcade.color.LIME
        elif not self.game_started:
            self.lbl_status.text = "⏳ Attendi 2 giocatori per iniziare"
            self.lbl_status.text_color = arcade.color.YELLOW

    def on_start_click(self, event):
        if self.players_connected >= 1 and not self.game_started:
            print("🚀 Generazione labirinto...")

            # Invia configurazione
            config = {
                "size": MAZE_SIZE,
                "start_p1": [1, 1],
                "start_p2": [MAZE_SIZE - 2, MAZE_SIZE - 2],
                "exit": exit_pos,
                "maze": self.maze,
                "game_ready": True
            }

            # Avvia timer
            self.game_start_time = time.time()

            self.client.publish("maze/config", json.dumps(config), retain=False)
            self.game_started = True

            self.lbl_status.text = "🎮 GIOCO AVVIATO!"
            self.lbl_status.text_color = arcade.color.GREEN
            print("✅ GIOCO INIZIATO!")

        elif self.game_started:
            self.lbl_status.text = "⚠️ Gioco già avviato!"
            self.lbl_status.text_color = arcade.color.ORANGE
        else:
            self.lbl_status.text = "⚠️ Aspetta almeno 2 giocatori!"
            self.lbl_status.text_color = arcade.color.RED

    def on_reset_click(self, event):
        """Reset server per nuova partita"""
        print("🔄 Reset server...")

        # Reset stato
        self.winner = None
        self.game_started = False
        self.players_connected = 0
        self.player_names = {}

        # Reset Labirinto
        self.maze = genera_labirinto_simmetrico(MAZE_SIZE)

        # Ricostruisci sprite
        self.build_maze_sprites()

        self.update_labels()
        self.draw_leaderboard()

        self.client.publish("maze/config", json.dumps({"reset_game": True}), retain=False)

    def on_draw(self):
        self.clear()

        # Disegna sprite labirinto
        self.maze_sprite_list.draw()
        self.manager.draw()

    def on_update(self, delta_time):
        self.manager.on_update(delta_time)

        if self.needs_update:
            self.update_labels()

            if self.pending_winner:
                player_id, winner_name, elapsed_time = self.pending_winner
                self.lbl_status.text = f"🏆 {winner_name} ha vinto in {format_time(elapsed_time)}!"
                self.lbl_status.text_color = arcade.color.GOLD

                # Aggiorna leaderboard dopo vittoria
                self.draw_leaderboard()
                self.pending_winner = None

            self.needs_update = False


if __name__ == "__main__":
    window = ServerDashboard()
    arcade.run()
