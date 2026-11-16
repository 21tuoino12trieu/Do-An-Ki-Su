# Confident Scoring

# Confident Scoring Design (RAG)

## 1. Objective

Xác định mức độ tự tin của truy vấn dựa trên:

- `embedding_similarity_score`
- `rerank_score`

## 2. Pipeline

```text
Query -> Retrieve -> Rerank -> Feature -> Confident Decision -> Answer/Fallback
```

## 3. Data Schema

```json
{
  "query": "...",
  "embedding_similarity_score": 0.82,
  "rerank_score": 0.67,
  "label": true
}
```

## 4. Feature Extraction

```text
max_embedding_score
avg_top3_embedding
max_rerank_score
rerank_gap
```

## 5. Phase 1 - Rule-based (Priority)

### 5.1 Approach

- Phân tích histogram (đúng vs sai)
- Chọn threshold bằng ROC/F1

### 5.2 Rule Baseline

```python
if rerank_score < 0.5:
    return False
if embedding_score < 0.7:
    return False
return True
```

### 5.3 Rule Nâng cao

```python
if max_rerank_score < 0.55:
    return False
if rerank_gap < 0.05:
    return False
if max_embedding_score < 0.72:
    return False
return True
```

### 5.4 Confidence

```python
confidence = 0.6 * rerank + 0.4 * embedding
```

## 6. Phase 2 - Classifier (Optional)

### 6.1 Model

- Logistic Regression
- XGBoost

### 6.2 Input

```python
[max_embedding_score, avg_top3_embedding, max_rerank_score, rerank_gap]
```

### 6.3 Decision

```python
if P(relevant) < 0.6:
    return False
```

## 7. Integration

```text
Retriever -> Reranker -> FeatureExtractor -> ConfidenceScorer
```

## 8. Monitoring

- Precision (ưu tiên)
- Recall
- False Positive Rate
