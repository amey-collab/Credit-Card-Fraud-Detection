"""
train.py - Train multiple ML models, compare, and save the best one.
Run standalone:  python train.py
"""
import warnings
warnings.filterwarnings("ignore")

import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.tree import DecisionTreeClassifier
from sklearn.ensemble import RandomForestClassifier, GradientBoostingClassifier
from sklearn.model_selection import train_test_split
from sklearn.metrics import (classification_report, roc_auc_score,
                             f1_score, recall_score, confusion_matrix)
from utils import load_dataset, preprocess, balance_dataset, save_model

try:
    from xgboost import XGBClassifier
    HAS_XGB = True
except ImportError:
    HAS_XGB = False


def get_models():
    models = {
        "Logistic Regression": LogisticRegression(max_iter=1000, random_state=42),
        "Decision Tree":       DecisionTreeClassifier(max_depth=8, random_state=42),
        "Random Forest":       RandomForestClassifier(n_estimators=100, random_state=42, n_jobs=-1),
        "Gradient Boosting":   GradientBoostingClassifier(n_estimators=100, random_state=42),
    }
    if HAS_XGB:
        models["XGBoost"] = XGBClassifier(n_estimators=100, use_label_encoder=False,
                                          eval_metric="logloss", random_state=42)
    return models


def train_all(balance_strategy="smote"):
    df = load_dataset()
    X, y, encoders, scaler, feature_names = preprocess(df)
    X_bal, y_bal = balance_dataset(X, y, strategy=balance_strategy)

    X_train, X_test, y_train, y_test = train_test_split(
        X_bal, y_bal, test_size=0.2, random_state=42, stratify=y_bal)

    results = {}
    best_name, best_model, best_score = None, None, -1

    for name, model in get_models().items():
        model.fit(X_train, y_train)
        y_pred  = model.predict(X_test)
        y_proba = model.predict_proba(X_test)[:, 1]

        f1  = f1_score(y_test, y_pred)
        rec = recall_score(y_test, y_pred)
        auc = roc_auc_score(y_test, y_proba)
        cm  = confusion_matrix(y_test, y_pred).tolist()

        results[name] = {
            "f1": round(f1, 4),
            "recall": round(rec, 4),
            "roc_auc": round(auc, 4),
            "confusion_matrix": cm,
            "report": classification_report(y_test, y_pred, output_dict=True)
        }
        print(f"[{name}]  F1={f1:.4f}  Recall={rec:.4f}  AUC={auc:.4f}")

        if f1 > best_score:
            best_score = f1
            best_name  = name
            best_model = model

    print(f"\n✅ Best model: {best_name} (F1={best_score:.4f})")

    # Feature importances
    importances = {}
    if hasattr(best_model, "feature_importances_"):
        importances = dict(zip(feature_names,
                               best_model.feature_importances_.tolist()))
    elif hasattr(best_model, "coef_"):
        importances = dict(zip(feature_names,
                               np.abs(best_model.coef_[0]).tolist()))

    meta = {
        "best_model_name": best_name,
        "results": results,
        "feature_names": feature_names,
        "encoders": encoders,
        "scaler": scaler,
        "importances": importances,
    }
    save_model(best_model, meta)
    print("💾 Model saved to model.pkl")
    return meta


if __name__ == "__main__":
    train_all()
