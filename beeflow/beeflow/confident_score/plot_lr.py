import matplotlib.pyplot as plt
from sklearn.metrics import roc_curve, auc

y_prob = model.predict_proba(X_val)[:, 1]

fpr, tpr, thresholds = roc_curve(y_val, y_prob)
roc_auc = auc(fpr, tpr)

J = tpr - fpr
best_idx = np.argmax(J)
best_threshold = thresholds[best_idx]

plt.figure(figsize=(7, 6))

plt.plot(
    fpr,
    tpr,
    label=f"Logistic Regression ROC (AUC = {roc_auc:.4f})",
)

plt.plot(
    [0, 1],
    [0, 1],
    linestyle="--",
    color="gray",
    label="Random baseline",
)

plt.scatter(
    fpr[best_idx],
    tpr[best_idx],
    color="red",
    zorder=3,
    label=(
        f"Youden's J threshold = {best_threshold:.4f}\n"
        f"J = {J[best_idx]:.4f}, "
        f"FPR = {fpr[best_idx]:.4f}, "
        f"Recall = {tpr[best_idx]:.4f}"
    ),
)

plt.xlabel("False Positive Rate")
plt.ylabel("Recall / True Positive Rate")
plt.title("ROC Curve - Logistic Regression")
plt.legend(loc="lower right")
plt.grid(alpha=0.3)
plt.tight_layout()

plt.savefig("confident_score/logistic_regression_roc_youden.png", dpi=200)
plt.show()
