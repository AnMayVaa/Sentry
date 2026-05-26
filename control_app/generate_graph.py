import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import os

# Ensure Thai fonts render correctly on Windows
plt.rcParams['font.family'] = 'Tahoma'

DATA_DIR = 'data'
WINDOW_FRAMES = 150 # 5 seconds at 30Hz

def load_data(file, find_peak=False):
    path = os.path.join(DATA_DIR, file)
    if not os.path.exists(path): return None
    df = pd.read_csv(path)
    sub_cols = [c for c in df.columns if c.startswith('sub_')]
    data = df[sub_cols].values
    
    if len(data) < WINDOW_FRAMES: return data
    if find_peak:
        max_var = -1
        best_start = 0
        for i in range(len(data) - WINDOW_FRAMES):
            window = data[i:i+WINDOW_FRAMES]
            # Calculate rate of change to find the most violent impact
            mad = np.mean(np.abs(np.diff(window, axis=0)))
            if mad > max_var:
                max_var = mad
                best_start = i
        # Center the peak so the impact happens around 1.5 - 2 seconds in
        best_start = max(0, best_start - 45)
        return data[best_start:best_start+WINDOW_FRAMES]
    else:
        mid = len(data) // 2
        start = max(0, mid - WINDOW_FRAMES // 2)
        return data[start:start+WINDOW_FRAMES]

static_data = load_data('static.csv')
walking_data = load_data('walking.csv')
falling_data = load_data('falling.csv', find_peak=True)

plt.style.use('dark_background')
fig, (ax1, ax2, ax3) = plt.subplots(3, 1, figsize=(12, 10))

time_axis = np.arange(WINDOW_FRAMES) / 30.0 # Time in seconds

def plot_panel(ax, data, title):
    if data is None: return
    # Plot 5 distinct subcarriers to show the multipath variation
    colors = ['#00FFFF', '#FF00FF', '#FFFF00', '#00FF00', '#FF3333']
    for i, c in zip([5, 15, 25, 35, 45], colors):
        ax.plot(time_axis, data[:, i], color=c, alpha=0.9, linewidth=2.0)
    
    ax.set_title(title, color='white', fontsize=14, fontweight='bold', pad=15)
    ax.set_ylabel('CSI Amplitude', color='white', fontsize=12)
    ax.set_ylim(0, 50)
    ax.grid(True, color='#333333', linestyle='--')
    ax.tick_params(colors='white')

plot_panel(ax1, static_data, "1. Empty Room (Static) - Stable CSI Signal / ห้องว่าง (ไม่มีการเคลื่อนไหว)")
plot_panel(ax2, walking_data, "2. Walking - Continuous Fluctuation / คนเดิน (มีการเคลื่อนไหวต่อเนื่อง)")

if falling_data is not None:
    colors = ['#00FFFF', '#FF00FF', '#FFFF00', '#00FF00', '#FF3333']
    for i, c in zip([5, 15, 25, 35, 45], colors):
        ax3.plot(time_axis, falling_data[:, i], color=c, alpha=0.9, linewidth=2.0)
    
    ax3.set_title("3. Falling - Sudden Spike followed by Stillness / คนล้ม (เกิด Spike รุนแรงแล้วนิ่งสนิท)", color='white', fontsize=14, fontweight='bold', pad=15)
    ax3.set_xlabel('Time (Seconds)', color='white', fontsize=12)
    ax3.set_ylabel('CSI Amplitude', color='white', fontsize=12)
    
    # Calculate dynamic max for the falling data to place annotations nicely
    max_amp = np.max(falling_data[:, [5, 15, 25, 35, 45]])
    ax3.set_ylim(0, max(50, max_amp + 10))
    ax3.grid(True, color='#333333', linestyle='--')
    ax3.tick_params(colors='white')
    
    # Find the peak frame for annotation
    window_diff = np.mean(np.abs(np.diff(falling_data, axis=0)), axis=1)
    peak_frame = np.argmax(window_diff)
    peak_time = peak_frame / 30.0
    
    # Annotate Spike
    ax3.annotate("Massive Spike\n(Impact / ล้มกระแทก)", 
                xy=(peak_time, max_amp - 5), 
                xytext=(max(0.1, peak_time - 1.5), max_amp),
                arrowprops=dict(facecolor='#FF3333', shrink=0.05, width=2, headwidth=8),
                color='#FF3333', fontsize=12, fontweight='bold', bbox=dict(boxstyle="round,pad=0.3", fc="black", ec="#FF3333", lw=1))
                
    # Annotate Stillness
    still_time = peak_time + 1.5
    ax3.annotate("Stillness\n(Lying on ground / นอนนิ่ง)", 
                xy=(still_time, 20), 
                xytext=(still_time - 0.5, max_amp - 10),
                arrowprops=dict(facecolor='#00FFFF', shrink=0.05, width=2, headwidth=8),
                color='#00FFFF', fontsize=12, fontweight='bold', bbox=dict(boxstyle="round,pad=0.3", fc="black", ec="#00FFFF", lw=1))

plt.tight_layout()
# Save to the conversation artifact directory so the user can easily see and download it
out_path = os.path.join("C:\\Users\\ADMIN\\.gemini\\antigravity\\brain\\cf930a51-2fbe-4483-8fb5-8e7819635bf3", "CSI_Signal_Signatures.png")
plt.savefig(out_path, dpi=300, facecolor='#000000', edgecolor='none')
print(f"Graph saved to {out_path}")
