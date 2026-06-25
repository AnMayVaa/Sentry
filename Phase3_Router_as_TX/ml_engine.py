import pandas as pd
import numpy as np
import joblib
import os
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import train_test_split
from sklearn.metrics import classification_report, accuracy_score

# Configuration
WINDOW_SIZE = 45 # 1.5 seconds at 30Hz
STEP_SIZE = 15   # 0.5 second overlap
DATA_DIR = "data"

def extract_features(window_df):
    """
    Extract statistical features from a window of CSI data.
    Input: DataFrame of shape (WINDOW_SIZE, 52) containing only subcarrier amplitudes.
    Output: 1D numpy array of features.
    """
    # Convert to numpy array for faster operations
    data = window_df.values
    
    # Feature 1: Standard deviation of each subcarrier over time
    std_devs = np.std(data, axis=0)
    
    # Feature 2: Peak-to-peak (max - min) of each subcarrier over time
    ptp = np.ptp(data, axis=0)
    
    # Feature 3: Mean absolute difference between consecutive frames (rate of change)
    diffs = np.diff(data, axis=0)
    mad = np.mean(np.abs(diffs), axis=0)
    
    # Aggregate features across all 52 subcarriers
    features = [
        np.mean(std_devs),
        np.max(std_devs),
        np.mean(ptp),
        np.max(ptp),
        np.mean(mad),
        np.max(mad)
    ]
    return np.array(features)

def extract_features_np(data):
    """
    Same as extract_features but takes a numpy array directly (no pandas).
    This avoids DataFrame creation overhead in the real-time hot path.
    Input: numpy array of shape (WINDOW_SIZE, 52)
    Output: 1D numpy array of features.
    """
    std_devs = np.std(data, axis=0)
    ptp = np.ptp(data, axis=0)
    diffs = np.diff(data, axis=0)
    mad = np.mean(np.abs(diffs), axis=0)
    
    return np.array([
        np.mean(std_devs),
        np.max(std_devs),
        np.mean(ptp),
        np.max(ptp),
        np.mean(mad),
        np.max(mad)
    ])

def create_dataset(file_path, label, is_fall=False):
    """
    Reads a CSV and extracts features using a sliding window.
    If is_fall=True, it filters the data to ONLY keep the top 15% highest-variance 
    windows to avoid labeling static/walking parts of the fall recording as 'Fall'.
    """
    if not os.path.exists(file_path):
        print(f"Warning: {file_path} not found.")
        return [], []
        
    df = pd.read_csv(file_path)
    # Drop timestamp and rssi columns, keep only sub_1 to sub_52
    sub_cols = [col for col in df.columns if col.startswith('sub_')]
    df = df[sub_cols]
    
    X = []
    y = []
    
    for start in range(0, len(df) - WINDOW_SIZE, STEP_SIZE):
        window = df.iloc[start:start+WINDOW_SIZE]
        features = extract_features(window)
        X.append(features)
        y.append(label)
        
    if is_fall and len(X) > 0:
        # Sort by Mean MAD (Rate of Change) which is features[4]
        X_sorted = sorted(X, key=lambda x: x[4], reverse=True)
        # Keep top 15% (the actual fall impacts)
        keep_count = max(1, int(len(X) * 0.15))
        X = X_sorted[:keep_count]
        y = [label] * keep_count
        
    return X, y

def main():
    print("Loading datasets...")
    # Labels: 0 = Static, 1 = Walking, 2 = Fall
    X_static, y_static = create_dataset(os.path.join(DATA_DIR, "static.csv"), 0)
    X_walking, y_walking = create_dataset(os.path.join(DATA_DIR, "walking.csv"), 1)
    X_falling, y_falling = create_dataset(os.path.join(DATA_DIR, "falling.csv"), 2, is_fall=True)
    
    X = X_static + X_walking + X_falling
    y = y_static + y_walking + y_falling
    
    if len(X) == 0:
        print("Error: No data found. Make sure static.csv, walking.csv, and falling.csv exist in the data/ folder.")
        return
        
    X = np.array(X)
    y = np.array(y)
    
    print(f"Dataset created: {len(X)} samples.")
    print("Training Random Forest model...")
    
    # Split into train and test sets
    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)
    
    # Train model
    clf = RandomForestClassifier(n_estimators=100, random_state=42, max_depth=10)
    clf.fit(X_train, y_train)
    
    # Evaluate
    y_pred = clf.predict(X_test)
    print("\nModel Evaluation:")
    print(f"Accuracy: {accuracy_score(y_test, y_pred) * 100:.2f}%")
    
    # Names for the report
    target_names = []
    if 0 in y: target_names.append("Static")
    if 1 in y: target_names.append("Walking")
    if 2 in y: target_names.append("Falling")
    
    if len(np.unique(y_test)) == len(target_names):
        print(classification_report(y_test, y_pred, target_names=target_names))
    else:
        # If test set is missing a class, default report
        print(classification_report(y_test, y_pred))
    
    # Save model
    model_path = "fall_detection_model.pkl"
    joblib.dump(clf, model_path)
    print(f"\nSuccess! Model saved to {model_path}")
    print("You can now update the main app to load this model.")

if __name__ == "__main__":
    main()
