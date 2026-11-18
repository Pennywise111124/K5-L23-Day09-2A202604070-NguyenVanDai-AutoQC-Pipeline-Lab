# Báo cáo Day 09 — Nguyễn Văn Đại, 2A202604070

## 1. Kết luận trước
Pipeline kết luận **Hold**. Lô thô có 224 ảnh; bước nhận dữ liệu loại 22 ảnh, còn 202 ảnh vào QC và 202 ảnh trong bản xuất `clean_v1` (bản NHÁP, chưa phát hành). Không còn lỗi bắt buộc, nhưng 38/202 ảnh (18,8%) còn cảnh báo chưa được người duyệt, vượt ngưỡng 10% của cổng. Nguyên nhân chính: hàng đợi 125 ảnh lớn hơn ngân sách duyệt 80 ảnh, nên 45 ảnh không ai xem.

## 2. Lỗi và phân việc
Số liệu là số dòng báo cáo trong `02_error_list_v1`. Mã ở cửa vào lấy mẫu số 224 ảnh thô; mã QC lấy mẫu số 202 ảnh.

| Mã lỗi | Số dòng | Ai sửa | Vì sao |
|---|---:|---|---|
| DUP_IMAGE_EXACT / DUP_IMAGE_NEAR | 8 / 4 | Máy | Trùng ảnh: loại ở cửa vào (md5, phash ≤ 10). |
| LEAK_TEST | 5 | Máy | Ảnh trùng tập test: loại để điểm đo cuối không bị thổi phồng. |
| CORRUPT_IMAGE / BAD_SIZE | 2 / 3 | Máy | Ảnh hỏng hoặc cạnh ngắn < 250 px: loại. |
| BAD_FORMAT, BAD_CLASS_ID, BOX_ZERO, DUP_BOX | 3, 6, 4, 7 | Máy | Lỗi cú pháp rõ ràng: `drop_line`. |
| BOX_OUT_OF_IMAGE | 8 | Máy | Cắt box về trong ảnh (`clip_box`), xoá dòng nếu hết diện tích. |
| BAD_CLASS_NAME | 2 | Máy | Ghi lại `names` trong data.yaml đúng thứ tự của dự án. |
| CLASS_RARE | 4 | Máy (gián tiếp) | Biến mất ở v2 vì các dòng có id lớp sai (BAD_CLASS_ID) đã bị xoá. |
| MISSING_LABEL_FILE | 6 | Người | Máy không được bịa nhãn: chuyển người gán (`needs_label`). |
| POSSIBLE_MISSING / WRONG_CLASS / LOOSE_BOX / FALSE_POS | 53 / 18 / 28 / 29 | Người | Lỗi ngữ nghĩa, model chỉ nghi ngờ nên phải qua mắt người. |
| BOX_TINY, BOX_HUGE, EMPTY_LABEL | 6, 3, 12 | Người | Cảnh báo theo quy tắc, cần xem ý nghĩa. |

Hàng đợi `05_review_queue.csv` xếp theo tổng trọng số cảnh báo của mỗi ảnh. `NEEDS_LABEL` có trọng số 10 nên cả 6 ảnh thiếu nhãn đứng đầu (đều nằm trong 80 ảnh được duyệt), kế đến là `WRONG_CLASS` (3), `MISSING` và `FALSE_POS` (2). Ngân sách duyệt là 80/125 ảnh. So `04_error_list_v2` với `07_error_list_v3`, người duyệt xử lý được `POSSIBLE_MISSING` 53→13, `WRONG_CLASS` 18→3, `LOOSE_BOX` 28→20, `FALSE_POS` 24→21, nên `FALSE_POS` và `LOOSE_BOX` là hai nhóm còn nhiều nhất.

## 3. Calibration (2 ngưỡng)

| Tham số | Khởi đầu | Đã chọn | Precision / Recall (trước → sau) | Lý do (đánh đổi) |
|---|---|---|---|---|
| `duplicates.phash_dist` | 2 | 10 | `DUP_IMAGE_NEAR`: P 1,00 → 1,00; R 0,50 → 0,67 | Xoá nhầm ảnh tốt là lỗi đắt nên ưu tiên precision. Giá trị 4–14 cùng cho P 1,00 và R 0,67; chọn 10 nằm giữa vùng ổn định, xa mức 20 (recall của `DUP_IMAGE_EXACT` tụt còn 0,33). Mức 16 cho R 0,83 nhưng chỉ hơn đúng 1/6 ca và sát mức tụt. |
| `second_opinion.conf` | 0,25 | 0,6 | `MISSING`: P 0,50 → 0,57, R 1,00 → 1,00; `WRONG_CLASS`: P 0,56 → 0,62, R 0,83 → 0,83; `LOOSE_BOX`: P 0,29 → 0,20, R 0,40 → 0,20 | Cảnh báo dành cho người nên giữ recall: 0,6 là mức cao nhất mà `MISSING` chưa mất recall (0,7 tụt còn 0,88). Chấp nhận mất recall của `LOOSE_BOX` vì đó là cảnh báo có trọng số thấp nhất trong nhóm `second_opinion`. |

**Chỗ calibration có thể đánh lừa.**

1. Calib không có ca `LEAK_TEST` nào, trong khi raw có 5 ca với phash so với ảnh test lần lượt là 0, 6, 2, 0, 0. Ca `img_0101` (phash 6) chỉ bị bắt khi tăng ngưỡng; ở `phash_dist = 2` nó lọt vào tập train. Đối chiếu bằng mắt 7 cặp ảnh (2 cặp NEAR bị loại thêm do tăng ngưỡng và cả 5 cặp LEAK) đều là cùng một ảnh, không có cặp nào gộp nhầm.
2. Mỗi nhóm lỗi chỉ có 5–8 ca chèn nên precision và recall nhảy từng bước lớn (`LOOSE_BOX` có R 0,60 ở conf 0,1 nhưng 0,20 ở 0,6).
3. Kết luận của cổng phụ thuộc mạnh vào độ dài hàng đợi, không chỉ chất lượng cảnh báo. Thử trên bản sao cấu hình (`work/what_if.py`, không đụng bài nộp): conf 0,25 / 0,6 / 0,7 / 0,8 cho hàng đợi 143 / 125 / 118 / 102 ảnh, số ảnh còn cảnh báo 58 / 38 / 29 / 16, kết luận Hold / Hold / Hold / Release. Release ở 0,8 chỉ xuất hiện khi hàng đợi co lại, đồng thời recall `MISSING` rơi còn 0,75 (bỏ sót 2/8 lỗi chèn), nên tôi không chọn ngưỡng theo kết luận này.

## 4. Cửa chặn và điều pipeline KHÔNG bắt được

**(a) Gate chặn đúng.** Chạy `python -m pipeline.run --budget 0 --reports work/rep_nb --export-dir work/exp_nb`: kết luận **Rework** ("còn 6 lỗi bắt buộc, không được bỏ qua, kể cả ở ảnh đã duyệt"), mã thoát **20**, log ghi "KHÔNG xuất", và thư mục `work/exp_nb` không được tạo. Lý do: không có người duyệt nên 6 ảnh `MISSING_LABEL_FILE` vẫn chưa có nhãn.

**(b) Điểm mù** (bằng chứng từ `calibration_report.md` ở cấu hình đã chọn: `phash_dist` 10, `conf` 0,6).

- **Ảnh trùng bị biến đổi nhiều.** `DUP_IMAGE_NEAR` chỉ bắt 4/6 ca (R 0,67). Hai ca bị sót là các ca có mức biến đổi cao nhất trong `MANIFEST`: `calib_037` (mức 3, phash 16) và `calib_038` (mức 4, phash 18), đều vượt ngưỡng 10. Bốn ca còn lại có phash 0, 4, 2, 2. Hạ ngưỡng lên 16 chỉ lấy thêm `calib_037` và sát mức tụt, nên ảnh trùng bị biến đổi nhiều vẫn lọt vào dataset.
- **Box lỏng hoặc lệch.** `POSSIBLE_LOOSE_BOX` chỉ bắt 1/5 lỗi chèn (R 0,20), 4 ca lọt.
- **Nhầm lớp và báo động giả.** `POSSIBLE_WRONG_CLASS` bỏ sót 1/6 ca. `POSSIBLE_FALSE_POS` có precision chỉ 0,31 (5 ca thật, 11 báo động giả), tức người duyệt phải mở xem nhiều ảnh vô ích.

## 5. Train: raw vs clean (tùy chọn, chấm riêng)
Chưa chạy: thời gian dành cho phần lõi (4 module, calibrate, báo cáo), chưa chạy được notebook train trên Colab.

## 6. Quyết định và ghi chú AI

**(a) Quyết định cuối: Hold** (bản xuất `clean_v1` là bản nháp, chưa phát hành). Để thành Release cần giảm số ảnh còn cảnh báo chưa duyệt từ 38 xuống ≤ 20 (10% của 202 ảnh). Nếu người duyệt xử lý tiếp các ảnh kế tiếp trong hàng đợi, ước lượng cần khoảng 98 ảnh trở lên thay vì 80 (chỉ là ước lượng, vì ảnh vào hàng đợi do bước sửa tự động có thể đã hết cảnh báo). Hai nhóm precision thấp là `FALSE_POS` (0,31) và `LOOSE_BOX` (0,20); giảm báo động giả của chúng bằng cách chỉnh `fp_conf` và `iou_loose` là một hướng cải thiện cho lần sau, nhưng hai tham số này do đề cố định nên tôi không đụng vào. Không tăng `conf` chỉ để ép ra Release.

**(b) Dùng AI (Claude).**
- *Prompt chính:* nhờ Claude tóm tắt và hướng dẫn từng bước hoàn thiện.
- *Cách kiểm:* `pytest` 79 passed; chạy pipeline thật (Hold, mã thoát 10); thử `--budget 0` (Rework, mã 20); chạy 4 mức `conf` trên bản sao cấu hình; mở bằng mắt 7 cặp ảnh bị coi là trùng hoặc rò rỉ; tính lại phash của 6 cặp NEAR trong calib; chạy `scripts/check_submission.py`.

**(c) Ghi chú về công cụ kiểm tra.** Trên Windows, `scripts/check_submission.py` báo 2 lỗi giả về `pipeline\calibrate.py` (nhắc tới `MANIFEST` và `data/calib`) vì so đường dẫn bằng dấu `\` với danh sách file ghim dùng dấu `/`. Tôi không sửa script gốc; một bản sao có chuẩn hoá đường dẫn (`as_posix`) trong thư mục `work/` cho 0 lỗi, và `calibrate.py` của tôi không bị sửa so với bản đề.