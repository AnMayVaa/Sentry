import networkx as nx
import matplotlib.pyplot as plt
import matplotlib.animation as animation
import numpy as np
import random

# Use dark theme for "Hacker/Cyber" presentation look
plt.style.use('dark_background')
plt.rcParams['font.family'] = 'Tahoma' # Support Thai if needed

# Setup Graph
num_nodes = 20
seed = 42 # Fixed seed for consistent beautiful layout
G = nx.random_geometric_graph(num_nodes, radius=0.4, seed=seed)
pos = nx.get_node_attributes(G, 'pos')

# Node 0 is the Central Gateway (Receiver)
gateway_node = 0
# Node 15 is the one that will detect the fall (Deep in the network)
fall_node = 15

# Find the shortest path (Mycelium Path) based on distance (energy efficiency)
try:
    shortest_path = nx.shortest_path(G, source=fall_node, target=gateway_node, weight='weight')
except nx.NetworkXNoPath:
    # Force a path if disconnected
    G.add_edge(fall_node, gateway_node)
    shortest_path = [fall_node, gateway_node]

# Convert path into a list of edges for animation
path_edges = list(zip(shortest_path, shortest_path[1:]))

# Setup the Plot
fig, ax = plt.subplots(figsize=(10, 8))
fig.canvas.manager.set_window_title('Sentry: Mycelium Network Simulator')

def update(frame):
    ax.clear()
    
    # Titles and Status
    ax.set_title("Sentry: Mycelium Mesh Network Simulation", fontsize=18, fontweight='bold', color='white', pad=20)
    
    status_text = "Status: Monitoring / เฝ้าระวังปกติ"
    status_color = "#00FFFF" # Cyan
    
    # Phase logic
    # Frames 0-20: Idle
    # Frames 20-40: Fall Detected at Node 15
    # Frames 40-100: Routing signal to Gateway
    
    is_fall = frame >= 20
    is_routing = frame >= 40
    
    if is_fall and not is_routing:
        status_text = f"Status: FALL DETECTED at Node {fall_node}!"
        status_color = "#FF3333" # Red
    elif is_routing:
        status_text = "Status: Routing via lowest-energy path..."
        status_color = "#FFFF00" # Yellow
        if frame > 80:
            status_text = "Status: Alert delivered to Gateway -> LINE API Triggered!"
            status_color = "#33FF57" # Green
            
    ax.text(0.5, -0.05, status_text, ha='center', fontsize=14, color=status_color, fontweight='bold', transform=ax.transAxes)

    # 1. Draw all edges (Dim)
    nx.draw_networkx_edges(G, pos, ax=ax, edge_color='#333333', width=1.0)
    
    # 2. Draw routing path (Animated)
    if is_routing:
        # Calculate how many edges of the path to illuminate based on frame
        route_progress = min(len(path_edges), int((frame - 40) / (40 / max(1, len(path_edges)))))
        current_edges = path_edges[:route_progress]
        if current_edges:
            nx.draw_networkx_edges(G, pos, ax=ax, edgelist=current_edges, edge_color='#FFFF00', width=4.0)

    # 3. Draw Nodes
    node_colors = []
    node_sizes = []
    
    for node in G.nodes():
        if node == gateway_node:
            node_colors.append('#33FF57') # Green Gateway
            node_sizes.append(600)
        elif node == fall_node and is_fall:
            # Pulse the red node
            pulse = 600 + 200 * np.sin((frame - 20) * 0.5) if not is_routing else 600
            node_colors.append('#FF3333') # Red Fall
            node_sizes.append(pulse)
        elif is_routing and node in shortest_path[:max(1, int((frame-40)/(40/len(shortest_path))))]:
            node_colors.append('#FFFF00') # Yellow Routing Nodes
            node_sizes.append(400)
        else:
            node_colors.append('#00FFFF') # Cyan Normal
            node_sizes.append(200)
            
    nx.draw_networkx_nodes(G, pos, ax=ax, node_color=node_colors, node_size=node_sizes, edgecolors='white', linewidths=1.5)
    
    # 4. Draw Labels
    labels = {gateway_node: "Gateway"}
    if is_fall:
        labels[fall_node] = "FALL!"
    nx.draw_networkx_labels(G, pos, labels=labels, ax=ax, font_size=10, font_weight='bold', font_color='black')
    
    ax.axis('off')
    ax.set_facecolor('black')

# Create Animation (100 frames, loops indefinitely)
ani = animation.FuncAnimation(fig, update, frames=120, interval=50, repeat=True)

print("Starting Mycelium Simulator... Close the window to stop.")
plt.show()
