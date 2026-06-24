import pandas as pd
import numpy as np
import os
from train_model import extract_features

DATA_DIR = 'data'
WINDOW_SIZE = 45
STEP_SIZE = 15

def get_stats(f):
    path = os.path.join(DATA_DIR, f)
    if not os.path.exists(path): return None
    df = pd.read_csv(path)
    sub_cols = [c for c in df.columns if c.startswith('sub_')]
    df = df[sub_cols]
    
    features_list = []
    for start in range(0, len(df) - WINDOW_SIZE, STEP_SIZE):
        window = df.iloc[start:start+WINDOW_SIZE]
        feat = extract_features(window)
        # feat[0] = mean_std, feat[1] = max_std, feat[4] = mean_mad, feat[5] = max_mad
        features_list.append(feat)
    
    features_list = np.array(features_list)
    if len(features_list) == 0: return None
    
    print(f"\n--- {f} ---")
    print(f"Mean STD across windows: {np.mean(features_list[:, 0]):.2f} (Max: {np.max(features_list[:, 0]):.2f})")
    print(f"Mean MAD across windows: {np.mean(features_list[:, 4]):.2f} (Max: {np.max(features_list[:, 4]):.2f})")
    return features_list

get_stats('static.csv')
get_stats('walking.csv')
get_stats('falling.csv')
