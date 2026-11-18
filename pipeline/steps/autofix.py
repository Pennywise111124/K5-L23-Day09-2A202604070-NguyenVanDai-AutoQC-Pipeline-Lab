"""BƯỚC 2/4 — Sửa tự động những lỗi bắt buộc mà máy sửa được AN TOÀN.   ★★

Test:  pytest tests/test_autofix.py -q

`fix(ds, issues, cfg) -> list[dict]`: duyệt `issues` (chỉ lỗi severity ERROR), sửa thẳng vào thư mục `ds`,
và trả về danh sách thay đổi; mỗi phần tử có khoá: image, line, action, before, after
(đây chính là file `03_fixes.csv` — bằng chứng pipeline đã làm gì, người có thể kiểm lại).

| code lỗi                                       | cách sửa                                    | action           |
|------------------------------------------------|---------------------------------------------|------------------|
| BAD_FORMAT, BAD_CLASS_ID, BOX_ZERO, DUP_BOX    | xoá dòng đó khỏi file nhãn                  | "drop_line"      |
| BOX_OUT_OF_IMAGE                               | cắt box về trong [0,1] (giữ nguyên lớp)     | "clip_box"       |
| MISSING_LABEL_FILE                             | KHÔNG sửa file (máy không thể bịa nhãn): ghi 1 dòng fix, before="(không có file)", after="chuyển người gán" | "needs_label" |
| BAD_CLASS_NAME                                 | ghi lại `names` trong data.yaml đúng `cfg["classes"]` | "rename_classes" |
| DUP_IMAGE_*, LEAK_TEST, CORRUPT_IMAGE, BAD_SIZE| xoá ảnh + nhãn khỏi `ds`                    | "remove_image"   |

Bẫy cần nghĩ tới (có test cho từng cái)
- Một file có NHIỀU dòng lỗi: số dòng trong `issues` là số dòng GỐC. Nếu xoá từng dòng một thì số dòng lệch.
  Gom theo file, rồi ghi lại MỘT lần.
- Sau khi cắt, box có thể không còn diện tích (nằm hẳn ngoài ảnh): lúc đó xoá dòng thay vì ghi box rỗng.
- Một dòng có 2 lỗi (vd. BOX_OUT_OF_IMAGE + DUP_BOX): xoá dòng thắng, chỉ ghi 1 fix `drop_line`, không ghi thêm `clip_box`. Dòng trống ở giữa file vẫn đếm vào số dòng gốc.
- Ảnh vừa bị xoá (DUP_IMAGE_*...) mà còn issue dòng của chính nó: bỏ qua êm, không được báo lỗi/chết.
- Không động tới lỗi WARN (cảnh báo là việc của người). Không sửa file ở `data/raw/` — chỉ sửa `ds`.
- Chạy lần 2 trên dữ liệu đã sửa phải không làm gì thêm (idempotent) — NGOẠI LỆ duy nhất: `needs_label` được ghi lại mỗi lần còn lỗi `MISSING_LABEL_FILE` (vì ảnh vẫn chưa có nhãn).

- `needs_label` KHÔNG tạo file nhãn rỗng (rỗng = "ảnh nền", khác với "chưa gán"). `review_queue` sẽ đẩy ảnh này lên đầu hàng đợi cho người.

Gợi ý: `yaml.safe_load / safe_dump`.
"""
from collections import defaultdict

import yaml

from ..common import ERROR, parse_yolo_line

REMOVE = {"DUP_IMAGE_EXACT", "DUP_IMAGE_NEAR", "LEAK_TEST", "CORRUPT_IMAGE", "BAD_SIZE"}
DROP = {"BAD_FORMAT", "BAD_CLASS_ID", "BOX_ZERO", "DUP_BOX"}
LINE_CODES = DROP | {"BOX_OUT_OF_IMAGE"}


def _row(image, line, action, before, after):
    return dict(image=image, line=line, action=action, before=before, after=after)


def _clip(ln):
    """Cắt box về [0,1]; trả None nếu không parse được hoặc không còn diện tích."""
    try:
        c, x, y, w, h = parse_yolo_line(ln)
    except (ValueError, OverflowError):
        return None
    x1, x2 = max(0.0, x - w / 2), min(1.0, x + w / 2)
    y1, y2 = max(0.0, y - h / 2), min(1.0, y + h / 2)
    nw, nh = x2 - x1, y2 - y1
    if nw <= 0 or nh <= 0:
        return None
    return f"{c} {(x1 + x2) / 2:.6f} {(y1 + y2) / 2:.6f} {nw:.6f} {nh:.6f}"


def fix(ds, issues, cfg):
    errs = [i for i in issues if i.severity == ERROR]
    fixes = []

    # 1) data.yaml: ghi lại names đúng cfg["classes"] (một lần dù có nhiều issue)
    if any(i.code == "BAD_CLASS_NAME" for i in errs):
        data = {}
        if ds.yaml_path.exists():
            data = yaml.safe_load(ds.yaml_path.read_text(encoding="utf-8")) or {}
        new_names = dict(enumerate(cfg["classes"]))
        fixes.append(_row("data.yaml", "", "rename_classes", str(ds.yaml_names()), str(new_names)))
        data["names"] = new_names
        ds.yaml_path.write_text(yaml.safe_dump(data, allow_unicode=True), encoding="utf-8")

    # 2) xoá ảnh (+ nhãn)
    removed = set()
    for stem in sorted({i.image for i in errs if i.code in REMOVE}):
        removed.add(stem)
        ip = ds.image_path(stem)
        if ip is None:
            continue
        code = next(i.code for i in errs if i.image == stem and i.code in REMOVE)
        ip.unlink()
        if ds.label_path(stem).exists():
            ds.label_path(stem).unlink()
        fixes.append(_row(stem, "", "remove_image", code, "đã xoá ảnh + nhãn"))

    # 3) thiếu file nhãn: máy không bịa nhãn
    for stem in sorted({i.image for i in errs if i.code == "MISSING_LABEL_FILE"} - removed):
        fixes.append(_row(stem, "", "needs_label", "(không có file)", "chuyển người gán"))

    # 4) lỗi theo dòng: gom theo file, dùng số dòng GỐC, ghi một lần
    per = defaultdict(lambda: defaultdict(set))
    for i in errs:
        if i.line is not None and i.code in LINE_CODES:
            per[i.image][i.line].add(i.code)
    for stem in sorted(per):
        lp = ds.label_path(stem)
        if stem in removed or not lp.exists():
            continue
        out = []
        for no, ln in enumerate(lp.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
            codes = per[stem].get(no)
            if not codes:
                out.append(ln)
            elif codes & DROP:
                fixes.append(_row(stem, no, "drop_line", ln, ""))
            else:                                     # chỉ còn BOX_OUT_OF_IMAGE
                new = _clip(ln)
                if new is None:
                    fixes.append(_row(stem, no, "drop_line", ln, ""))
                else:
                    out.append(new)
                    fixes.append(_row(stem, no, "clip_box", ln, new))
        lp.write_text("".join(l + "\n" for l in out), encoding="utf-8")
    return fixes
