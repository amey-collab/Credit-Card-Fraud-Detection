"""
utils.py - Shared utilities for data processing, feature engineering, and reporting.
"""
import pandas as pd
import numpy as np
from sklearn.preprocessing import LabelEncoder, MinMaxScaler
from imblearn.over_sampling import SMOTE
from imblearn.under_sampling import RandomUnderSampler
import joblib
import os

DATASET_PATH = os.path.join(os.path.dirname(__file__), "dataset.csv")
MODEL_PATH   = os.path.join(os.path.dirname(__file__), "model.pkl")
META_PATH    = os.path.join(os.path.dirname(__file__), "model_meta.pkl")

# ── Column roles ──────────────────────────────────────────────────────────────
NUMERIC_COLS      = ["amount", "transaction_hour", "device_trust_score",
                     "velocity_last_24h", "cardholder_age"]
CATEGORICAL_COLS  = ["merchant_category"]
BINARY_COLS       = ["foreign_transaction", "location_mismatch"]
TARGET_COL        = "is_fraud"
ID_COL            = "transaction_id"

FEATURE_COLS = NUMERIC_COLS + CATEGORICAL_COLS + BINARY_COLS


def load_dataset(path=None):
    """Load CSV or Excel dataset and return a DataFrame."""
    path = path or DATASET_PATH
    ext = os.path.splitext(path)[1].lower()
    if ext in (".xlsx", ".xls"):
        df = pd.read_excel(path)
    else:
        df = pd.read_csv(path)
    return df


def preprocess(df: pd.DataFrame):
    """
    Clean, encode, and scale the dataframe.
    Returns (X, y, encoders, scaler, feature_names).
    """
    df = df.copy()

    # Drop ID column if present
    if ID_COL in df.columns:
        df.drop(columns=[ID_COL], inplace=True)

    # Fill missing values
    for col in df.select_dtypes(include="number").columns:
        df[col].fillna(df[col].median(), inplace=True)
    for col in df.select_dtypes(include="object").columns:
        df[col].fillna(df[col].mode()[0], inplace=True)

    # Encode categoricals
    encoders = {}
    for col in CATEGORICAL_COLS:
        if col in df.columns:
            le = LabelEncoder()
            df[col] = le.fit_transform(df[col].astype(str))
            encoders[col] = le

    # Build feature matrix
    available_features = [c for c in FEATURE_COLS if c in df.columns]
    X = df[available_features].copy()

    # Scale numeric columns
    scaler = MinMaxScaler()
    num_cols = [c for c in NUMERIC_COLS if c in X.columns]
    X[num_cols] = scaler.fit_transform(X[num_cols])

    y = df[TARGET_COL].values if TARGET_COL in df.columns else None
    return X, y, encoders, scaler, available_features


def balance_dataset(X, y, strategy="smote"):
    """Apply SMOTE or undersampling to handle class imbalance."""
    if strategy == "smote":
        sampler = SMOTE(random_state=42)
    else:
        sampler = RandomUnderSampler(random_state=42)
    X_res, y_res = sampler.fit_resample(X, y)
    return X_res, y_res


def save_model(model, meta: dict):
    joblib.dump(model, MODEL_PATH)
    joblib.dump(meta, META_PATH)


def load_model():
    if not os.path.exists(MODEL_PATH):
        return None, None
    model = joblib.load(MODEL_PATH)
    meta  = joblib.load(META_PATH)
    return model, meta


def risk_level(prob: float) -> str:
    if prob >= 0.75:
        return "High"
    elif prob >= 0.40:
        return "Medium"
    return "Low"


def explain_prediction(input_dict: dict, prob: float) -> list:
    """Rule-based explanation for a prediction."""
    reasons = []
    if input_dict.get("amount", 0) > 800:
        reasons.append("Unusually high transaction amount")
    hour = input_dict.get("transaction_hour", 12)
    if hour < 5 or hour > 22:
        reasons.append("Transaction at unusual hour")
    if input_dict.get("foreign_transaction", 0) == 1:
        reasons.append("Foreign / cross-border transaction")
    if input_dict.get("location_mismatch", 0) == 1:
        reasons.append("Location mismatch detected")
    if input_dict.get("velocity_last_24h", 0) >= 5:
        reasons.append("High transaction velocity in last 24 hours")
    if input_dict.get("device_trust_score", 100) < 30:
        reasons.append("Low device trust score (new or suspicious device)")
    if not reasons:
        if prob > 0.5:
            reasons.append("Model pattern match — statistical anomaly detected")
        else:
            reasons.append("No strong fraud indicators found")
    return reasons
