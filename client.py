import arcade
import arcade.gui
import paho.mqtt.client as mqtt
import threading
import json
import time


class MidnightMaze(arcade.Window):
    def __init__(self):
        super().__init__(width=1024, height=768, title="🔴 Moonlight Maze - Player 1", fullscreen=False, resizable=True)

        # TEXTURE LABIRINTO
        self.wall_texture = arcade.load_texture("./assets/wall.png")
        self.floor_texture = arcade.load_texture("./assets/floor.png")

        arcade.set_background_color(arcade.color.MIDNIGHT_BLUE)

        # UI MANAGER
        self.manager = arcade.gui.UIManager(self)
        self.manager.enable()

        # STATO SCHERMATA: "join" | "waiting" | "game" | "game_over"
        self.state = "join"

        # STATO GIOCO
        self.reset_state()

        # Move Command
        self.keys_pressed = {}
        self.move_cooldown = 0.06  # ms tra movimenti
        self.time_since_last_move = 0

        # Join Page
        self.player_name = ""
        self.name_input = None

        # COSTRUZIONE UI JOIN PAGE (UNA SOLA VOLTA)
        self.draw_join_ui()
        self.draw_reset_button()

        # Reset
        self.pending_reset = False
        self.pending_maze_build = False

        # SpriteList per il labirinto (disegna tutto in una volta)
        self.maze_sprite_list = None

        # MQTT
        self.client = mqtt.Client(callback_api_version=mqtt.CallbackAPIVersion.VERSION2)
        self.client.on_connect = self.on_mqtt_connect
        self.client.on_message = self.on_mqtt_message
        self.client.connect("localhost", 1883, 60)
        threading.Thread(target=self.client.loop_forever, daemon=True).start()

        print("🚀 Midnight Maze Arcade - Player 1 pronto!")

    def reset_state(self):
        self.griglia = None
        self.pos_player1 = None
        self.pos_player2 = None
        self.pos_informed_ai = [1,65]
        self.exit_pos = None
        self.maze_size = None
        self.cell_size = None
        self.game_ready = False
        self.winner = None
        self.maze_sprite_list = None

    # ---------- MQTT ----------

    def on_mqtt_connect(self, client, userdata, flags, rc, properties):
        print("Player 1 Arcade connesso!")
        self.client.subscribe("maze/config")
        self.client.subscribe("maze/player2/pos")
        self.client.subscribe("maze/winner")
        self.client.subscribe("maze/InformedAI")

    def on_mqtt_message(self, client, userdata, msg):
        try:
            data = json.loads(msg.payload)

            if msg.topic == "maze/config":
                if data.get("reset_game", False):
                    self.pending_reset = True
                    return

                self.maze_size = data.get("size", self.maze_size)
                self.griglia = data.get("maze", self.griglia)
                self.pos_player1 = data.get("start_p1", self.pos_player1)
                self.pos_player2 = data.get("start_p2", self.pos_player2)
                self.exit_pos = data.get("exit", self.exit_pos)
                self.game_ready = data.get("game_ready", False)

                if self.maze_size is not None:
                    self.cell_size = self.height // self.maze_size
                    print(f"🎮 Labirinto {self.maze_size}x{self.maze_size} caricato!")

                if self.game_ready:
                    self.state = "game"
                    self.pending_maze_build = True

            elif "player2/pos" in msg.topic:
                self.pos_player2 = data

            elif "InformedAI" in msg.topic:
                self.pos_informed_ai = data

            elif "winner" in msg.topic:
                self.winner = data["winner"]
                self.state = "game_over"
                print(f"{self.winner.upper()} HA VINTO!")

        except Exception as e:
            print(f"MQTT errore: {e}")

    # ---------- UI JOIN PAGE ----------

    def draw_join_ui(self):
        """Costruisce i widget della join page una sola volta."""
        self.vbox = arcade.gui.UIBoxLayout()

        title = arcade.gui.UILabel(
            text="Moonlight Maze",
            font_size=68,
            font_name=("Courier New", "Consolas", "monospace"),
            text_color=arcade.color.CYAN
        )
        self.vbox.add(title)
        self.vbox.add(arcade.gui.UISpace(height=120))

        instructions = arcade.gui.UILabel(
            text="Inserisci il tuo nome:",
            font_size=24,
            text_color=arcade.color.WHITE,
            font_name=("Courier New", "Consolas", "monospace")
        )
        self.vbox.add(instructions)

        self.name_input = arcade.gui.UIInputText(
            width=300,
            height=50,
            font_size=24,
            font_name=("Courier New", "Consolas", "monospace")
        )
        self.vbox.add(self.name_input)
        self.vbox.add(arcade.gui.UISpace(height=50))

        play_btn = arcade.gui.UIFlatButton(
            text="INIZIA GIOCO",
            width=200,
            height=60,
            font_name=("Courier New", "Consolas", "monospace")
        )
        play_btn.on_click = self.on_play_click
        self.vbox.add(play_btn)

        self.join_anchor = self.manager.add(arcade.gui.UIAnchorLayout(size_hint=(1, 1)))
        self.join_anchor.add(child=self.vbox, anchor_x="center_x", anchor_y="center_y")

    def draw_reset_button(self):
        """Bottone RESET in alto a destra (sempre visibile)"""
        self.btn_reset = arcade.gui.UIFlatButton(
            text="🔄 RESET GAME",
            width=150,
            height=50,
            font_name=("Courier New", "Consolas", "monospace")
        )
        self.btn_reset.on_click = self.on_reset_click

        # Aggiungi in alto a destra
        anchor = self.manager.add(arcade.gui.UIAnchorLayout(size_hint=(1, 1)))
        anchor.add(
            child=self.btn_reset,
            anchor_x="right",
            anchor_y="top",
            align_x=-20,  # 20px dal bordo destro
            align_y=-20  # 20px dal bordo alto
        )

    def on_reset_click(self, event):
        """Reset completo del client"""
        print("🔄 Reset client...")

        # Reset stato
        self.state = "join"
        self.reset_state()
        self.keys_pressed = {}

        self.name_input.text = ""
        self.player_name = ""

        # Mostra di nuovo la join GUI
        self.manager.enable()
        self.join_anchor.visible = True

        print("✅ Client resettato - torna alla schermata join")

    def on_play_click(self, event):
        self.player_name = self.name_input.text
        if self.player_name != "":
            print(f"👤 Giocatore: {self.player_name}")
            self.state = "waiting"

            # Nascondi la join GUI
            self.join_anchor.visible = False

            # Notifica al server che il player è pronto (topic a tua scelta)
            self.client.publish(
                "maze/player1/join",
                json.dumps({"name": self.player_name}))

    # ---------- DRAW ----------

    def build_maze(self):
        """Costruisci il labirinto come sprite (una volta sola)"""
        if self.griglia is None or self.maze_size is None:
            return

        self.maze_sprite_list = arcade.SpriteList()

        offset_x = (self.width - self.maze_size * self.cell_size) // 2
        offset_y = (self.height - self.maze_size * self.cell_size) // 2

        for y in range(self.maze_size):
            for x in range(self.maze_size):
                center_x = offset_x + x * self.cell_size + self.cell_size // 2
                center_y = offset_y + y * self.cell_size + self.cell_size // 2

                if self.griglia[y][x] != 0:
                    sprite = arcade.Sprite("./assets/wall.png", scale=self.cell_size / self.wall_texture.width)
                else:
                    sprite = arcade.Sprite("./assets/floor.png", scale=self.cell_size / self.floor_texture.width)

                sprite.center_x = center_x
                sprite.center_y = center_y
                self.maze_sprite_list.append(sprite)

    def on_draw(self):
        self.clear()
        arcade.set_background_color(arcade.color.MIDNIGHT_BLUE)

        # SCHERMATA JOIN
        if self.state == "join":
            self.manager.draw()
            return

        # SCHERMATA ATTESA CONFIG
        if self.state == "waiting" or not self.game_ready:
            self.manager.draw()
            arcade.Text(
                "In attesa del server...", self.width // 2,
                self.height // 2 - 140, arcade.color.WHITE,
                24, anchor_x="center").draw()
            return

        # SCHERMATA GAME OVER
        if self.state == "game_over":
            self.manager.disable()
            if self.winner:
                arcade.Text(
                    f"🏆 {self.winner.upper()} HA VINTO!",
                    self.width // 2, self.height - 50, arcade.color.BLACK,
                    32, anchor_x="center").draw()

        # GIOCO ATTIVO
        if (self.pos_player1 is None or self.pos_player2 is None
                or self.griglia is None):
            arcade.Text("Caricamento dati giocatore...",
                        self.width // 2, self.height // 2,
                        arcade.color.WHITE,24, anchor_x="center").draw()
            return

        self.maze_sprite_list.draw()

        offset_x = (self.width - self.maze_size * self.cell_size) // 2
        offset_y = (self.height - self.maze_size * self.cell_size) // 2

        # USCITA
        self.draw_circle(
            player=self.exit_pos, color=arcade.color.GOLD,
            size=self.cell_size * 1.5, offset_x=offset_x, offset_y=offset_y)

        # PLAYER 1
        self.draw_circle(
            player=self.pos_player1, color=arcade.color.CRIMSON,
            size=self.cell_size // 2, offset_x=offset_x, offset_y=offset_y)

        # PLAYER 2
        self.draw_circle(
            player=self.pos_player2, color=arcade.color.GREEN,
            size=self.cell_size // 2, offset_x=offset_x, offset_y=offset_y)

        # INFORMED AI
        self.draw_circle(
            player=self.pos_informed_ai, color=arcade.color.GREEN,
            size=self.cell_size // 2, offset_x=offset_x, offset_y=offset_y)

        arcade.Text(
            "Moonlight Maze",20,
            self.height - 40, arcade.color.WHITE,
            24, anchor_x="left",
            font_name="Arial").draw()
        self.manager.disable()

    # ---------- INPUT & LOGICA ----------

    def draw_circle(self, player, size, color, offset_x, offset_y):
        px = offset_x + player[0] * self.cell_size + self.cell_size // 2
        py = offset_y + player[1] * self.cell_size + self.cell_size // 2
        arcade.draw_circle_filled(px, py, size, color)
        arcade.draw_circle_outline(px, py, size, arcade.color.BLACK, 3)

    def on_key_press(self, key, modifiers):
        if self.state != "game":
            return
        self.keys_pressed[key] = True

    def on_key_release(self, key, modifiers):
        if self.state != "game":
            return
        self.keys_pressed.pop(key, None)

    def is_valid_move_local(self, new_pos):
        if not self.griglia:
            return False

        x, y = int(new_pos[0]), int(new_pos[1])

        if not (0 <= x < self.maze_size and 0 <= y < self.maze_size):
            return False

        return self.griglia[y][x] == 0

    def on_update(self, delta_time):

        self.manager.on_update(delta_time)

        if self.pending_reset:
            self.on_reset_click(None)
            self.pending_reset = False
            return

        if self.pending_maze_build:
            self.build_maze()
            self.pending_maze_build = False

        if self.state != "game":
            return

        # Accumula tempo
        self.time_since_last_move += delta_time

        if self.time_since_last_move >= self.move_cooldown:
            if self.game_ready and not self.winner and self.keys_pressed:
                new_pos = self.pos_player1[:]
                moved = False

                if arcade.key.S in self.keys_pressed:
                    new_pos[1] -= 1
                    moved = True
                if arcade.key.W in self.keys_pressed:
                    new_pos[1] += 1
                    moved = True
                if arcade.key.A in self.keys_pressed:
                    new_pos[0] -= 1
                    moved = True
                if arcade.key.D in self.keys_pressed:
                    new_pos[0] += 1
                    moved = True

                if moved and self.is_valid_move_local(new_pos):

                    self.pos_player1 = new_pos
                    self.client.publish(
                        "maze/player1/move",
                        json.dumps({"name": "player1", "pos": new_pos}))
                # Reset timer
                self.time_since_last_move = 0


if __name__ == "__main__":
    print("🎮 AVVIO Midnight Maze ARCADE...")
    window = MidnightMaze()
    arcade.run()
