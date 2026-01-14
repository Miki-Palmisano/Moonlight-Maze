import json
import math
import random
import threading
import time
import paho.mqtt.client as mqtt

class Node:
    def __init__(self, parent, action, depth, cost, state):
        self.parent = parent
        self.action = action
        self.depth = depth
        self.cost = cost
        self.state = state

    def __repr__(self):
        return str(self.state)

    def expand(self, problem):
        successors = []
        for state, action in problem.successors(self.state):
            successors += [Node(self, action, self.depth+1, self.cost + problem.cost(self.state), state)]
        return successors

    def solution(self):
        path = []
        node = self

        while node.parent is not None:
            path.append(node.state)
            node = node.parent

        return path[::-1]

class MazeProblem:
    def __init__(self, initial_state, goal_state, maze):
        self.initial_state = initial_state
        self.goal_state = goal_state
        self.maze = maze
        self.grid_size = [len(maze), len(maze[0])]

    def successors(self, state):
        actions = self.actions(state)
        return [(self.result(action, state), action) for action in actions]

    def actions(self, state):
        actions = ['up', 'right', 'left', 'down']
        row = state[1]
        col = state[0]

        if self.maze[row + 1][col] == 1:
            actions.remove('up')
        if self.maze[row - 1][col] == 1:
            actions.remove('down')
        if self.maze[row][col - 1] == 1:
            actions.remove('left')
        if self.maze[row][col + 1] == 1:
            actions.remove('right')

        return actions

    def result(self, action, state):
        row = state[1]
        column = state[0]

        new_row, new_column = row, column

        if action == 'right':
            new_column += 1
        elif action == 'left':
            new_column -= 1
        elif action == 'up':
            new_row += 1
        elif action == 'down':
            new_row -= 1

        new_state = [new_column, new_row]

        return new_state

    def cost(self, state):
        return 1

    def goal_test(self, state):
        return self.goal_state == state

    def heuristic(self, state):
        distance = 0

        for _ in range(1,9):
            current_column = state[0]
            current_row = state[1]
            goal_row = self.goal_state[0]
            goal_column = self.goal_state[1]

            #distance += (abs(current_row - goal_row) + abs(current_column - goal_column)) # Manhattan
            distance += math.sqrt((current_row - goal_row) ** 2 + (current_column - goal_column) ** 2)

        return distance

class GreedySearch:
    def __init__(self, problem):
        self.problem = problem

    def select(self, fringe):
        fringe = sorted(fringe, key=lambda n: self.problem.heuristic(n.state))

        return fringe, fringe.pop(0)

class GraphSearch:
    def __init__(self):
        self.problem = None
        self.strategy = None
        self.fringe = []
        self.closed = []

        self.new_config = None
        self.running = False

        # MQTT Client
        self.client = mqtt.Client(callback_api_version=mqtt.CallbackAPIVersion.VERSION2)
        self.client.on_connect = self.on_mqtt_connect
        self.client.on_message = self.on_mqtt_message
        self.client.connect("localhost", 1883, 60)
        threading.Thread(target=self.client.loop_forever, daemon=True).start()


    def run_forever(self):
        """Loop principale che rimane attivo"""
        while True:
            if self.new_config and not self.running:
                self.fringe = []
                self.closed = []

                maze, goal_state = self.new_config
                self.problem = MazeProblem([1, 65], goal_state, maze)
                self.strategy = GreedySearch(self.problem)
                self.new_config = None  # Reset flag

                print("🚀 Avvio ricerca...")
                status, path = self.run()  # Ora run() può essere bloccante
                print(f"✅ Completato: {status}, path: {path}")

            time.sleep(0.1)  # Piccola pausa per non consumare CPU

    def run(self):
        if not self.problem:
            return 'fail', []

        self.fringe.append(Node(None, None, 0, 0, self.problem.initial_state))

        while True:
            if len(self.fringe) == 0:
                return 'fail', []

            self.fringe, node = self.strategy.select(self.fringe)

            if not node:
                return 'fail', []

            self.client.publish("maze/InformedAI", json.dumps(node.state))
            time.sleep(0.06)

            if self.problem.goal_test(node.state):
                return 'success', node.solution()

            if node.state not in self.closed:
                self.closed.append(node.state)

                fringe_states = [v.state for v in self.fringe]
                self.fringe.extend([new_node for new_node in node.expand(self.problem)
                                    if new_node.state not in fringe_states])


    def on_mqtt_connect(self, client, userdata, flags, rc, properties):
        print("✅ Server Dashboard connesso a MQTT")
        client.subscribe("maze/config")

    def on_mqtt_message(self, client, userdata, msg):
        data = json.loads(msg.payload)
        maze = data.get("maze", None)
        goal_state = data.get("exit", None)

        if maze and goal_state:
            self.new_config = (maze, goal_state)  # Salva config senza eseguire
            print("✅ Nuova configurazione ricevuta")


if __name__ == "__main__":
    print("🎮 AVVIO Informed AI...")
    search = GraphSearch()
    search.run_forever()