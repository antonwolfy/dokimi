# Accelerate a scikit-learn classifier with Intel Extension for scikit-learn

You are given `/app/reference.py`, a self-contained Kaggle-style tabular
classification workflow that uses **stock scikit-learn**. It builds a
deterministic synthetic dataset with `make_classification(..., random_state=42)`,
splits it with `train_test_split(..., random_state=42)`, trains a
`KNeighborsClassifier(n_neighbors=7)`, and prints the held-out accuracy.

Create `/app/solution.py` that reproduces the **same** workflow but accelerates
it with **Intel Extension for scikit-learn (sklearnex)**:

1. Patch scikit-learn before importing the estimators:
   ```python
   from sklearnex import patch_sklearn
   patch_sklearn()
   ```
2. Build the identical dataset and split (same parameters and `random_state`).
3. Train the identical `KNeighborsClassifier(n_neighbors=7)`.
4. Print a line containing `VALID` and `acc=<accuracy>` where the accuracy is
   the held-out test accuracy. Optionally also print `sig=<signature>`.

Requirements:

- The patched run must reach an accuracy within `0.02` of the stock reference
  (sklearnex is a drop-in accelerator, so results should match closely).
- Your source must actually call `patch_sklearn()` from `sklearnex`; a plain
  scikit-learn solution will be rejected.

Run the reference for comparison with:

```bash
python3 /app/reference.py
python3 /app/solution.py
```
