import pandas as pd
import numpy as np
import json
import matplotlib.pyplot as plt
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import train_test_split
from sklearn.metrics import roc_curve, auc
from sklearn.preprocessing import StandardScaler
from sklearn.pipeline import Pipeline
from sklearn.metrics import precision_recall_curve

with open("confident_score/confident_scoring_dataset.relaxed.json", "r", encoding ="utf-8") as f:
    data = json.load(f)

needed_items = [
    "retrieve_max_score",
    "rerank_max_score",
    "avg_top3_embedding",
    "rerank_gap",
    "label"
]

filtered_data = [
    {k: item[k] for k in needed_items if k in item}
    for item in data if int(item["rerank_count"]) >= 2
]

df = pd.DataFrame(filtered_data)
df["label"] = df["label"].map({True: 1, False: 0})
print(df)
feature_columns = ["retrieve_max_score", "rerank_max_score", "avg_top3_embedding", "rerank_gap"]

X = df[feature_columns]
y = df["label"]

X_train, X_val, y_train, y_val = train_test_split(X, y, test_size=0.2, random_state= 42, stratify=y, shuffle=True)

model = Pipeline([
    ("scaler", StandardScaler()),
    ("clf", LogisticRegression(random_state=42, max_iter=1000, class_weight="balanced"))
])

model.fit(X_train, y_train)

y_prob = model.predict_proba(X_val)[:,1]

fpr, tpr, thresholds = roc_curve(y_val, y_prob)
roc_auc = auc(fpr, tpr)

# Youden's J
# J = tpr - fpr
# best_idx = np.argmax(J)


best_threshold = thresholds[best_idx]

print("ROC-AUC: ",roc_auc)
print("Best threshold:", best_threshold)
 
tp = fp = fn = tn = 0
for label, prob in zip(y_val, y_prob):
    predict = prob >= best_threshold

    if label == 1 and predict:
        tp += 1
    elif label == 0 and predict:
        fp += 1
    elif label == 0 and not predict:
        tn += 1
    else:
        fn += 1

precision = tp/(tp+fp)
recall = tp/(tp+fn)
fpr_metric = fp/(fp+tn)
f1 = 2*precision*recall/(precision+recall)

print(f"tp: {tp}, fp: {fp}, tn: {tn}, fn: {fn}, fallback rate: {(fn+tn)/len(y_val)}")
print("precision: ", precision)
print("recall: ", recall)
print("fpr: ", fpr_metric)
print("f1: ",f1)

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
    # label=(
    #     f"Youden's J threshold = {best_threshold:.4f}\n"
    #     f"J = {J[best_idx]:.4f}, "
    #     f"FPR = {fpr[best_idx]:.4f}, "
    #     f"Recall = {tpr[best_idx]:.4f}"
    # ),
)

plt.xlabel("False Positive Rate")
plt.ylabel("Recall")
plt.title("ROC Curve - Logistic Regression")
plt.legend(loc="lower right")
plt.grid(alpha=0.3)
plt.tight_layout()

plt.savefig("confident_score/logistic_regression_roc_youden.png", dpi=200)
plt.show()
