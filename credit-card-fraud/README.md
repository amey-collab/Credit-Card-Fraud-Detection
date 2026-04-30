# 🛡️ FraudShield — Credit Card Fraud Detection System

A full-stack ML-powered web application for detecting credit card fraud in real time.

Built with Flask, scikit-learn, XGBoost, Chart.js, and a glassmorphism UI.

---

## 🚀 Quick Start

```bash
cd credit-card-fraud
pip install -r requirements.txt
python app.py
```

Open [http://localhost:5000](http://localhost:5000)

The model trains automatically on first launch using `dataset.csv`.  
Default admin login: **admin / admin123**

---

## ✨ Features

### ML & Data
- Multi-model training: Logistic Regression, Decision Tree, Random Forest, Gradient Boosting, XGBoost
- SMOTE / undersampling for class imbalance
- Auto-selects best model by F1 score
- Feature importance, confusion matrix, ROC-AUC comparison
- Upload your own CSV / XLSX dataset

### Dashboard (Admin)
- KPI cards with animated counters
- 6 interactive charts: Fraud vs Legit donut, Fraud by Hour, Merchant, Age Group, Amount Distribution, Model Comparison
- Confusion matrix visualization
- Feature importance chart
- Transaction table with search
- Real-time transaction simulation feed
- CSV and PDF export

### Prediction
- Single transaction prediction with fraud probability, risk level, and explainable reasons
- Batch prediction — upload CSV, download results
- Prediction history panel

### User System
- Signup / Login with hashed passwords
- Role-based access: **admin** vs **user**
- Admin panel: manage users, promote/demote, delete, view activity stats
- Login rate limiting (5 attempts → 5 min lockout)

### Alerts
- High-risk fraud alerts log
- Filter by foreign transaction / location mismatch
- Search and clear (admin only)

---

## 📁 Project Structure

```
credit-card-fraud/
├── app.py                  # Flask app + all routes
├── train.py                # ML training pipeline
├── utils.py                # Preprocessing & helpers
├── dataset.csv             # Training dataset
├── requirements.txt
├── templates/
│   ├── login.html
│   ├── signup.html
│   ├── dashboard.html
│   ├── predict.html
│   ├── alerts.html
│   └── admin.html
└── static/
    ├── css/style.css
    └── js/
        ├── dashboard.js
        └── predict.js
```

---

## 📊 Dataset Columns

| Column | Description |
|---|---|
| transaction_id | Unique ID |
| amount | Transaction amount ($) |
| transaction_hour | Hour of day (0–23) |
| merchant_category | Merchant type |
| foreign_transaction | 1 = foreign |
| location_mismatch | 1 = mismatch |
| device_trust_score | Device trust (0–100) |
| velocity_last_24h | Transactions in last 24h |
| cardholder_age | Cardholder age |
| is_fraud | 1 = fraud (target label) |

---

## 🔧 Retrain Manually

```bash
python train.py
```

---

