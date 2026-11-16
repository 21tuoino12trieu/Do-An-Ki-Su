# Phase 1 Confident Scoring Workflow

## Mục tiêu

Phase 1 dùng rule-based scoring để quyết định một query RAG có đủ tin cậy để trả lời hay nên fallback.

Lỗi cần ưu tiên kiểm soát là:

```text
label=false nhưng hệ thống vẫn confident và trả lời
```

Đây là false positive. Với bài toán RAG, false positive thường nguy hiểm hơn false negative, vì fallback một câu đúng vẫn an toàn hơn trả lời sai một câu không đủ căn cứ.

## Dữ liệu đầu vào

Pipeline hiện dùng hai nguồn dữ liệu:

```text
confident_score/enterprise.xlsx
confident_score/log.json
```

`enterprise.xlsx` là nguồn label chính. Chỉ những dòng có label rõ ràng `True` hoặc `False` mới được dùng. Các dòng trống, `CÂN NHẮC`, hoặc giá trị không hợp lệ bị bỏ qua.

`log.json` là log compact từ Langfuse. Mỗi trace chỉ cần các observation:

```text
init_quiery_fn
vec_search
rerank
```

## Tạo dataset

Script:

```bash
python confident_score/create_data.py
```

Output mặc định:

```text
confident_score/confident_scoring_dataset.relaxed.json
```

Luồng xử lý:

```text
enterprise.xlsx
  -> lấy các câu có label True/False
  -> dùng câu hỏi làm key

log.json
  -> lấy origin_query từ init_quiery_fn
  -> index trace theo origin_query

enterprise labels
  -> map sang trace tương ứng trong log
  -> extract retrieve scores
  -> extract rerank scores
  -> build feature
  -> ghi dataset JSON
```

Dataset hiện dùng hướng relaxed:

```text
rerank_count >= 1
retrieve_scores không rỗng
```

Lý do không ép `rerank_count == 8`: nếu ép strict, dataset sạch hơn nhưng mất nhiều mẫu. Dataset relaxed phản ánh production tốt hơn và tăng số mẫu false để đánh giá threshold ổn định hơn.

Nếu cần tạo strict dataset để so sánh:

```bash
python confident_score/create_data.py \
  --expected-rerank-count 8 \
  --output confident_score/confident_scoring_dataset.strict.json
```

## Feature hiện tại

Dataset vẫn lưu nhiều feature để audit:

```text
retrieve_scores
retrieve_count
retrieve_top1_score
retrieve_top2_score
retrieve_gap_top1_top2
retrieve_avg_top3
retrieve_max_score
retrieve_min_score

rerank_scores
rerank_count
rerank_top1_score
rerank_top2_score
rerank_gap_top1_top2
rerank_avg_top3
rerank_max_score
rerank_min_score
```

Feature chính dùng cho Phase 1 rule:

```text
max_embedding_score
max_rerank_score
```

Trong đó:

```text
max_embedding_score = retrieve_max_score
max_rerank_score = rerank_max_score
```

`rerank_gap` hiện không được dùng làm hard rule. Lý do là histogram và threshold analysis cho thấy `rerank_gap` không tách tốt giữa `label=true` và `label=false`. Ngoài ra với relaxed dataset, nhiều trace có `rerank_count = 1`, khi đó gap không có ý nghĩa.

## Histogram

Script:

```bash
python confident_score/plot_histograms.py
```

Output:

```text
confident_score/histograms.svg
```

Histogram dùng để nhìn phân bố score giữa hai nhóm:

```text
label=true
label=false
```

Trục X là giá trị feature. Trục Y là share trong từng label group, không phải raw count.

Lý do dùng share: dataset bị lệch label, số mẫu true lớn hơn false nhiều. Nếu dùng raw count, nhóm true sẽ áp đảo biểu đồ và khó so sánh phân bố.

Histogram giúp trả lời:

```text
Feature nào có khả năng tách label=true và label=false?
Vùng overlap nằm ở đâu?
Threshold có nên đặt ở khoảng nào?
```

## Threshold Analysis

Script:

```bash
python confident_score/analyze_thresholds.py
```

Output:

```text
confident_score/threshold_analysis.relaxed.json
```

Rule đang phân tích:

```python
predict = (
    max_embedding_score >= threshold_embedding
    and max_rerank_score >= threshold_rerank
)
```

Nghĩa là hệ thống chỉ confident nếu cả retrieve và rerank đều đủ mạnh.

Với rule kết hợp 2 feature, script dùng 2D suffix sum để scan threshold nhanh hơn:

```text
TP/FP = lookup số mẫu trong vùng
max_embedding_score >= threshold_embedding
and max_rerank_score >= threshold_rerank
```

Nhờ vậy exact scan không cần lặp lại toàn bộ dataset cho từng cặp threshold.

## Lý thuyết metric

Confusion matrix:

```text
TP: label=true  và predict=true
FP: label=false và predict=true
TN: label=false và predict=false
FN: label=true  và predict=false
```

Các metric:

```text
precision = TP / (TP + FP)
recall    = TP / (TP + FN)
FPR       = FP / (FP + TN)
F1        = 2 * precision * recall / (precision + recall)
```

Với data lệch mạnh, không nên chốt threshold theo F1 hoặc accuracy. Nếu true nhiều hơn false, một rule pass gần như tất cả có thể đạt F1 cao nhưng FPR cũng rất cao. Điều đó không phù hợp với confident scoring.

Vì vậy tiêu chí hiện tại là:

```text
Trong tất cả threshold có FPR <= max_fpr,
chọn threshold có recall cao nhất.
```

Nói cách khác:

```text
Giới hạn số câu false bị pass.
Trong giới hạn đó, cố giữ lại nhiều câu true nhất.
```

## ROC Analysis

Script:

```bash
python confident_score/plot_roc.py
```

Output:

```text
confident_score/roc_curves.svg
```

ROC plot dùng trục X là false positive rate và trục Y là recall/TPR.

Với từng feature riêng lẻ, đường ROC được tạo bằng cách scan threshold:

```python
predict = feature_score >= threshold
```

Với rule kết hợp Phase 1, plot hiển thị các điểm grid search và frontier tốt nhất cho rule:

```python
predict = (
    max_embedding_score >= threshold_embedding
    and max_rerank_score >= threshold_rerank
)
```

Marker màu đỏ là threshold được chọn theo tiêu chí:

```text
maximize recall with FPR <= max_fpr
```

## Rule Phase 1 hiện tại

Theo dataset relaxed và `max_fpr = 0.1`, rule được recommend là:

```python
def is_confident(max_embedding_score: float, max_rerank_score: float) -> bool:
    return (
        max_embedding_score >= 0.6776017546653748
        and max_rerank_score >= 0.9962266683578491
    )
```

Metric trên dataset hiện tại:

```text
precision = 0.9707
recall    = 0.2708
fpr       = 0.0940

tp = 364
fp = 11
tn = 106
fn = 980
```

Đây là rule conservative. Nó giảm rủi ro trả lời sai, nhưng fallback nhiều câu đúng.

## Cách hiểu tradeoff

Rule conservative phù hợp cho Phase 1 vì:

```text
False positive thấp
Precision cao
Logic dễ giải thích
Dễ monitor trong production
```

Đổi lại:

```text
Recall thấp
Nhiều câu đúng sẽ fallback
```

Tradeoff này chấp nhận được nếu fallback an toàn hơn trả lời sai.

## Monitoring sau khi tích hợp

Khi đưa vào pipeline, nên log lại các field:

```text
origin_query
max_embedding_score
max_rerank_score
confidence_decision
fallback_or_answer
label/user feedback nếu có
```

Các metric cần theo dõi:

```text
precision
recall
false positive rate
false negative count
fallback rate
```

Khi có thêm dữ liệu mới, chạy lại:

```bash
python confident_score/create_data.py
python confident_score/plot_histograms.py
python confident_score/plot_roc.py
python confident_score/analyze_thresholds.py
```

Sau đó so sánh threshold mới với threshold hiện tại trước khi cập nhật rule.

## Khi nào chuyển sang Phase 2

Nếu Phase 1 rule quá conservative và recall thấp kéo dài, có thể chuyển sang classifier:

```text
Logistic Regression
XGBoost
```

Logistic Regression analysis script:

```bash
python confident_score/analyze_phase2_logistic.py
```

Output:

```text
confident_score/phase2_logistic_analysis.relaxed.json
```

Script này cần `scikit-learn` và dùng các feature:

```text
max_embedding_score
avg_top3_embedding
max_rerank_score
rerank_gap
```

Model output là `P(relevant)`. Sau đó threshold cho probability vẫn được chọn theo:

```text
maximize recall with FPR <= max_fpr
```

Nhưng classifier vẫn cần tối ưu theo mục tiêu:

```text
maximize recall under FPR target
```

Không nên tối ưu accuracy mặc định vì data lệch.
