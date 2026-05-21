"""
AutoML Service — no-code machine learning model training and inference.

Supported task types:
  - classification: binary or multi-class (churn, fraud detection, etc.)
  - regression: continuous target prediction (sales, revenue, etc.)
  - clustering: unsupervised customer segmentation

Pipeline:
  1. Load dataset and validate target column
  2. Preprocessing: median imputation, one-hot encoding, StandardScaler
  3. Model selection: train multiple candidates, pick best by 5-fold CV
  4. Persist model via joblib to ./models/{job_id}.pkl
  5. Return structured result with feature importances, metrics, sample predictions
"""

import os
import uuid
import logging
from datetime import datetime
from typing import List, Dict, Any, Optional

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

MODELS_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "models")
os.makedirs(MODELS_DIR, exist_ok=True)


class AutoMLService:
    """Train and serve sklearn-based ML models without code."""

    # ── Training ─────────────────────────────────────────────────

    def train(
        self,
        df: pd.DataFrame,
        target_column: str,
        task_type: str,
        job_id: str,
    ) -> Dict[str, Any]:
        """Train the best model for the given task and return structured result."""
        if target_column not in df.columns:
            raise ValueError(f"Target column '{target_column}' not found")

        task_type = task_type.lower()
        if task_type not in ("classification", "regression", "clustering"):
            raise ValueError(f"task_type must be classification | regression | clustering")

        # Validate minimum sample count
        MIN_SAMPLES = 5
        if len(df) < MIN_SAMPLES:
            raise ValueError(
                f"Dataset has only {len(df)} rows. AutoML requires at least {MIN_SAMPLES} rows to train reliably."
            )

        # Prepare features and target
        feature_df = df.drop(columns=[target_column]).copy()
        if task_type != "clustering":
            y = df[target_column].copy()
        else:
            y = None

        # ── Preprocessing: sanitize feature_df before sklearn pipeline ──
        from sklearn.preprocessing import LabelEncoder as _LE

        # Drop datetime columns (cannot be used directly)
        date_cols = feature_df.select_dtypes(include=["datetime64"]).columns.tolist()
        if date_cols:
            feature_df = feature_df.drop(columns=date_cols)

        # Drop all-null columns, fill remaining NaN with 0
        feature_df = feature_df.dropna(axis=1, how="all").fillna(0)

        # Encode categorical feature columns with LabelEncoder
        for col in feature_df.select_dtypes(include=["object", "category"]).columns:
            le = _LE()
            feature_df[col] = le.fit_transform(feature_df[col].astype(str))

        if feature_df.shape[1] == 0:
            raise ValueError("No usable numeric/categorical features found after preprocessing.")

        # Encode target column if categorical (classification only)
        if y is not None and (y.dtype == object or str(y.dtype) == "category"):
            le = _LE()
            y = pd.Series(le.fit_transform(y.astype(str)), name=target_column)

        X, feature_names = self._preprocess(feature_df)

        if task_type == "classification":
            return self._train_classification(X, y, feature_names, job_id)
        elif task_type == "regression":
            return self._train_regression(X, y, feature_names, job_id)
        else:
            return self._train_clustering(X, feature_names, job_id)

    # ── Preprocessing ────────────────────────────────────────────

    def _preprocess(self, df: pd.DataFrame):
        """Build a sklearn Pipeline for numeric + categorical features."""
        from sklearn.pipeline import Pipeline
        from sklearn.compose import ColumnTransformer
        from sklearn.preprocessing import StandardScaler, OneHotEncoder
        from sklearn.impute import SimpleImputer

        numeric_cols = df.select_dtypes(include=[np.number]).columns.tolist()
        categorical_cols = df.select_dtypes(include=["object", "category"]).columns.tolist()

        # Limit categorical cardinality to avoid memory explosion
        categorical_cols = [c for c in categorical_cols if df[c].nunique() <= 50]

        transformers = []
        if numeric_cols:
            num_pipe = Pipeline([
                ("imputer", SimpleImputer(strategy="median")),
                ("scaler", StandardScaler()),
            ])
            transformers.append(("num", num_pipe, numeric_cols))
        if categorical_cols:
            cat_pipe = Pipeline([
                ("imputer", SimpleImputer(strategy="constant", fill_value="missing")),
                ("encoder", OneHotEncoder(handle_unknown="ignore", sparse_output=False)),
            ])
            transformers.append(("cat", cat_pipe, categorical_cols))

        if not transformers:
            raise ValueError("No usable features found in the dataset")

        preprocessor = ColumnTransformer(transformers=transformers, remainder="drop")
        X = preprocessor.fit_transform(df)

        # Build feature name list for importance mapping
        names = list(numeric_cols)
        if categorical_cols:
            enc = preprocessor.named_transformers_["cat"]["encoder"]
            names += list(enc.get_feature_names_out(categorical_cols))

        return X, names

    # ── Classification ───────────────────────────────────────────

    def _train_classification(self, X, y, feature_names: List[str], job_id: str) -> Dict[str, Any]:
        from sklearn.ensemble import RandomForestClassifier, GradientBoostingClassifier
        from sklearn.linear_model import LogisticRegression
        from sklearn.model_selection import cross_val_score
        from sklearn.metrics import confusion_matrix
        import joblib

        # Encode string targets
        from sklearn.preprocessing import LabelEncoder
        le = LabelEncoder()
        y_enc = le.fit_transform(y.fillna("missing").astype(str))

        candidates = [
            ("RandomForest", RandomForestClassifier(n_estimators=100, random_state=42, n_jobs=-1)),
            ("GradientBoosting", GradientBoostingClassifier(n_estimators=100, random_state=42)),
            ("LogisticRegression", LogisticRegression(max_iter=500, random_state=42)),
        ]

        cv_folds = max(2, min(5, len(y_enc)))
        best_name, best_model, best_score = None, None, -1.0
        for name, model in candidates:
            try:
                scores = cross_val_score(model, X, y_enc, cv=cv_folds, scoring="f1_weighted", n_jobs=-1)
                score = float(scores.mean())
                logger.info(f"AutoML [{name}] CV f1={score:.3f}")
                if score > best_score:
                    best_score = score
                    best_model = model
                    best_name = name
            except Exception as e:
                logger.warning(f"AutoML candidate {name} failed: {e}")

        if best_model is None:
            raise RuntimeError("All classification candidates failed")

        best_model.fit(X, y_enc)

        # Feature importance
        importance = {}
        if hasattr(best_model, "feature_importances_"):
            fi = best_model.feature_importances_
            for name, imp in zip(feature_names[:len(fi)], fi):
                importance[name] = round(float(imp), 4)
            importance = dict(sorted(importance.items(), key=lambda x: x[1], reverse=True)[:20])

        # Confusion matrix
        y_pred = best_model.predict(X)
        cm = confusion_matrix(y_enc, y_pred).tolist()

        # Sample predictions
        sample = [{
            "prediction": le.inverse_transform([int(p)])[0],
            "index": int(i),
        } for i, p in enumerate(y_pred[:10])]

        # Persist
        model_path = os.path.join(MODELS_DIR, f"{job_id}.pkl")
        joblib.dump({"model": best_model, "label_encoder": le, "task_type": "classification"}, model_path)

        return {
            "best_model": best_name,
            "cv_score": round(best_score, 4),
            "metric_name": "F1 (weighted)",
            "feature_importance": importance,
            "confusion_matrix": cm,
            "class_labels": list(le.classes_),
            "sample_predictions": sample,
            "model_path": model_path,
        }

    # ── Regression ───────────────────────────────────────────────

    def _train_regression(self, X, y, feature_names: List[str], job_id: str) -> Dict[str, Any]:
        from sklearn.ensemble import RandomForestRegressor, GradientBoostingRegressor
        from sklearn.linear_model import LinearRegression
        from sklearn.model_selection import cross_val_score
        from sklearn.metrics import mean_absolute_error, mean_squared_error
        import joblib

        y_num = pd.to_numeric(y, errors="coerce").fillna(y.median() if hasattr(y, "median") else 0)

        candidates = [
            ("RandomForest", RandomForestRegressor(n_estimators=100, random_state=42, n_jobs=-1)),
            ("GradientBoosting", GradientBoostingRegressor(n_estimators=100, random_state=42)),
            ("LinearRegression", LinearRegression()),
        ]

        cv_folds = max(2, min(5, len(y_num)))
        best_name, best_model, best_score = None, None, float("inf")
        for name, model in candidates:
            try:
                scores = cross_val_score(model, X, y_num, cv=cv_folds, scoring="neg_mean_absolute_error", n_jobs=-1)
                score = float(-scores.mean())  # MAE (lower = better)
                logger.info(f"AutoML [{name}] CV MAE={score:.3f}")
                if score < best_score:
                    best_score = score
                    best_model = model
                    best_name = name
            except Exception as e:
                logger.warning(f"AutoML candidate {name} failed: {e}")

        if best_model is None:
            raise RuntimeError("All regression candidates failed")

        best_model.fit(X, y_num)
        y_pred = best_model.predict(X)
        mae = float(mean_absolute_error(y_num, y_pred))
        rmse = float(np.sqrt(mean_squared_error(y_num, y_pred)))

        importance = {}
        if hasattr(best_model, "feature_importances_"):
            fi = best_model.feature_importances_
            for name, imp in zip(feature_names[:len(fi)], fi):
                importance[name] = round(float(imp), 4)
            importance = dict(sorted(importance.items(), key=lambda x: x[1], reverse=True)[:20])

        sample = [{"actual": float(a), "predicted": float(p)} for a, p in zip(y_num[:10], y_pred[:10])]

        model_path = os.path.join(MODELS_DIR, f"{job_id}.pkl")
        joblib.dump({"model": best_model, "task_type": "regression"}, model_path)

        return {
            "best_model": best_name,
            "cv_score": round(mae, 4),
            "metric_name": "MAE (lower is better)",
            "metrics": {"MAE": round(mae, 4), "RMSE": round(rmse, 4)},
            "feature_importance": importance,
            "sample_predictions": sample,
            "model_path": model_path,
        }

    # ── Clustering ───────────────────────────────────────────────

    def _train_clustering(self, X, feature_names: List[str], job_id: str) -> Dict[str, Any]:
        from sklearn.cluster import KMeans
        from sklearn.metrics import silhouette_score
        import joblib

        # Auto-select k using elbow heuristic (2–8 clusters)
        max_k = min(8, X.shape[0] // 10 + 2)
        best_k, best_score = 3, -1.0
        for k in range(2, max_k + 1):
            try:
                km = KMeans(n_clusters=k, random_state=42, n_init=10)
                labels = km.fit_predict(X)
                if len(set(labels)) > 1:
                    sil = float(silhouette_score(X, labels))
                    if sil > best_score:
                        best_score = sil
                        best_k = k
            except Exception:
                pass

        km = KMeans(n_clusters=best_k, random_state=42, n_init=10)
        labels = km.fit_predict(X)
        cluster_sizes = {int(c): int((labels == c).sum()) for c in range(best_k)}

        model_path = os.path.join(MODELS_DIR, f"{job_id}.pkl")
        joblib.dump({"model": km, "task_type": "clustering"}, model_path)

        return {
            "best_model": f"KMeans (k={best_k})",
            "cv_score": round(best_score, 4),
            "metric_name": "Silhouette Score",
            "n_clusters": best_k,
            "cluster_sizes": cluster_sizes,
            "model_path": model_path,
        }

    # ── Inference ────────────────────────────────────────────────

    def predict(self, model_path: str, records: List[Dict]) -> List[Dict]:
        """Load a trained model and run inference on new records."""
        import joblib

        if not os.path.exists(model_path):
            raise FileNotFoundError(f"Model file not found: {model_path}")

        artifact = joblib.load(model_path)
        model = artifact["model"]
        task_type = artifact.get("task_type", "classification")

        df = pd.DataFrame(records)
        # Simple numeric-only preprocessing for inference
        numeric_cols = df.select_dtypes(include=[np.number]).columns.tolist()
        X = df[numeric_cols].fillna(0).values if numeric_cols else np.zeros((len(df), 1))

        preds = model.predict(X)

        results = []
        for i, (record, pred) in enumerate(zip(records, preds)):
            entry = {"index": i, "prediction": None}
            if task_type == "classification":
                le = artifact.get("label_encoder")
                entry["prediction"] = le.inverse_transform([int(pred)])[0] if le else str(pred)
                if hasattr(model, "predict_proba"):
                    try:
                        proba = model.predict_proba(X[i:i+1])[0]
                        entry["confidence"] = round(float(max(proba)), 3)
                    except Exception:
                        pass
            elif task_type == "regression":
                entry["prediction"] = round(float(pred), 4)
            else:
                entry["cluster"] = int(pred)
            results.append(entry)

        return results


# ── Singleton ─────────────────────────────────────────────────────
automl_service = AutoMLService()
