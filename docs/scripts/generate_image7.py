import os
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt

os.makedirs(r"C:\Antigravity\CSI\docs", exist_ok=True)

plt.style.use('default')
plt.rcParams['font.family'] = 'sans-serif'

fig, axs = plt.subplots(3, 1, figsize=(10, 12), sharex=False)
fs = 30 # Approx 30 frames per second

# Function to extract only the 52 usable subcarriers
# Format: timestamp, rssi, csi0, csi1... csi51
def get_amps(csv_file):
    data = []
    with open(csv_file, 'r') as f:
        for line in f:
            parts = [p.strip() for p in line.split(',') if p.strip()]
            if len(parts) >= 54:
                # Assuming index 0 is time, index 1 is RSSI, index 2:54 are amplitudes
                try:
                    amps = [float(x) for x in parts[2:54]]
                    data.append(amps)
                except ValueError:
                    continue
    return np.array(data)

# 1. LOAD REAL DATA
static_data = get_amps(r'C:\Antigravity\CSI\control_app\data\static.csv')
walking_data = get_amps(r'C:\Antigravity\CSI\control_app\data\walking.csv')
falling_data = get_amps(r'C:\Antigravity\CSI\control_app\data\falling.csv')

# 2. Extract 6-second windows (180 frames at 30fps) to ensure we isolate just ONE fall sequence
# and cut out the user standing back up!
window_size = 6 * fs
static_window = static_data[:window_size] if len(static_data) > window_size else static_data
walking_window = walking_data[:window_size] if len(walking_data) > window_size else walking_data

# Falling: Find the actual fall impact (highest variance)
frame_variances = np.var(falling_data, axis=1)

# To find the cleanest fall, we just grab the absolute max variance spike
spike_idx = np.argmax(frame_variances)

# Take 2 seconds before the spike (walking) and 4 seconds after (stillness)
start_idx = max(0, spike_idx - (2 * fs))
end_idx = min(len(falling_data), spike_idx + (4 * fs))

# If the window is too small (e.g., spike is at the very end), pad it or shift it
falling_window = falling_data[start_idx:end_idx]
spike_relative_idx = spike_idx - start_idx
spike_time_sec = spike_relative_idx / fs

# 3. Plot Static
time_static = np.linspace(0, len(static_window)/fs, len(static_window))
axs[0].set_title('Situation 1: Static (Empty Room) - REAL DATA', fontsize=16, fontweight='bold', color='#2ca02c')
for i in range(52):
    axs[0].plot(time_static, static_window[:, i], alpha=0.4, linewidth=1)
axs[0].grid(True, alpha=0.3)
axs[0].set_ylabel('CSI Amplitude', fontsize=12)

# 4. Plot Walking
time_walking = np.linspace(0, len(walking_window)/fs, len(walking_window))
axs[1].set_title('Situation 2: Continuous Walking - REAL DATA', fontsize=16, fontweight='bold', color='#ff7f0e')
for i in range(52):
    axs[1].plot(time_walking, walking_window[:, i], alpha=0.4, linewidth=1)
axs[1].grid(True, alpha=0.3)
axs[1].set_ylabel('CSI Amplitude', fontsize=12)

# 5. Plot Falling
time_falling = np.linspace(0, len(falling_window)/fs, len(falling_window))
axs[2].set_title('Situation 3: Falling Sequence (Walking -> Impact -> Stillness) - REAL DATA', fontsize=16, fontweight='bold', color='#d62728', pad=15)

# Calculate dynamic y-limits to prevent text crushing
min_val = np.min(falling_window)
max_val = np.max(falling_window)
y_range = max_val - min_val
axs[2].set_ylim(min_val - (y_range * 0.1), max_val + (y_range * 0.4)) # Add 40% headroom for text

# Add background highlights (axvspan) for the 3 periods
t1 = max(0, spike_time_sec - 0.2)
t2 = min(6.0, spike_time_sec + 1.2)

axs[2].axvspan(0, t1, facecolor='#ffcc99', alpha=0.3, label='Walking')
axs[2].axvspan(t1, t2, facecolor='#ff9999', alpha=0.3, label='Impact')
axs[2].axvspan(t2, time_falling[-1], facecolor='#99ff99', alpha=0.3, label='Stillness')

for i in range(52):
    axs[2].plot(time_falling, falling_window[:, i], alpha=0.6, linewidth=1)

axs[2].axvline(x=spike_time_sec, color='red', linestyle='--', linewidth=2)

# Mark the 3 phases relative to the spike, using safe Y coordinates
text_y = max_val + (y_range * 0.15)
axs[2].text(t1 / 2, text_y, '1. Walking\n(Moderate Variance)', fontsize=12, ha='center', bbox=dict(facecolor='white', alpha=0.8, edgecolor='none'))
axs[2].text(spike_time_sec + 0.5, text_y, '2. IMPACT SPIKE', fontsize=12, ha='center', color='red', fontweight='bold', bbox=dict(facecolor='white', alpha=0.8, edgecolor='red'))
axs[2].text(t2 + (time_falling[-1] - t2) / 2, text_y, '3. Stillness\n(Low Variance)', fontsize=12, ha='center', bbox=dict(facecolor='white', alpha=0.8, edgecolor='none'))

axs[2].grid(True, alpha=0.3)
axs[2].set_ylabel('CSI Amplitude', fontsize=12)
axs[2].set_xlabel('Time (Seconds)', fontsize=14)

plt.tight_layout()
output_path = r'C:\Antigravity\CSI\docs\CSI_Signal_Signatures.png'
plt.savefig(output_path, dpi=300)
print(f"Saved REAL DATA plot to {output_path}")
