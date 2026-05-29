#!/usr/bin/env bash
set -euo pipefail

cat > /app/solution.py <<'PY'
from sklearnex import patch_sklearn
patch_sklearn()

import numpy as np
from sklearn.datasets import make_classification
from sklearn.model_selection import train_test_split
from sklearn.neighbors import KNeighborsClassifier
from sklearn.metrics import accuracy_score


def build_dataset():
    X, y = make_classification(
        n_samples=4000,
        n_features=20,
        n_informative=12,
        n_redundant=4,
        n_classes=3,
        random_state=42,
    )
    return train_test_split(X, y, test_size=0.25, random_state=42)


def main():
    X_train, X_test, y_train, y_test = build_dataset()
    clf = KNeighborsClassifier(n_neighbors=7)
    clf.fit(X_train, y_train)
    pred = clf.predict(X_test).astype(np.int64)
    acc = accuracy_score(y_test, pred)
    sig = int(np.sum((pred + 1) * (np.arange(len(pred)) % 7 + 1)))
    print(f"VALID sklearnex acc={acc:.6f} sig={sig}")


if __name__ == "__main__":
    main()
PY

echo "solution written to /app/solution.py"
