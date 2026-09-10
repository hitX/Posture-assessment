from __future__ import annotations

import re

SEX_LABELS = {
    "男": "Male",
    "女": "Female",
    "未说明": "Unspecified",
}

MODULE_LABELS = {
    "用户信息": "User Profiles",
    "体态检测": "Posture Assessment",
    "步态检测": "Gait Assessment",
    "骨盆检测": "Pelvis Assessment",
    "脊柱评估": "Spine Assessment",
    "关节活动度": "Joint Range of Motion",
    "足底检测": "Foot Pressure Assessment",
}

STATUS_LABELS = {
    "待检测": "Waiting",
    "采集中": "Capturing",
    "待复核": "Pending Review",
    "分析中": "Analyzing",
    "需重拍": "Recapture Required",
    "已完成": "Completed",
    "失败": "Failed",
    "已采集": "Captured",
    "已替代": "Superseded",
    "原始数据已清理": "Raw Data Cleaned",
}

LEVEL_LABELS = {
    "实验性/待验证": "Experimental / Pending Validation",
    "置信度不足": "Insufficient Confidence",
    "仅显示实测值": "Measured Value Only",
    "需人工复核": "Manual Review Required",
}

DIRECTION_LABELS = {
    "居中": "Centered",
    "左": "Left",
    "右": "Right",
    "左高": "Left Higher",
    "右高": "Right Higher",
    "左移": "Shifted Left",
    "右移": "Shifted Right",
    "左侧高": "Left Side Higher",
    "右侧高": "Right Side Higher",
    "胸段": "Thoracic",
    "腰段": "Lumbar",
}

METRIC_LABELS = {
    "头部侧倾": "Head Tilt",
    "双肩高度差": "Shoulder Height Difference",
    "肩线角": "Shoulder Line Angle",
    "骨盆高低差": "Pelvis Height Difference",
    "骨盆冠状倾斜": "Pelvic Coronal Tilt",
    "骨盆侧移": "Pelvis Shift",
    "躯干侧移": "Trunk Shift",
    "膝中心距离": "Knee Center Distance",
    "踝中心距离": "Ankle Center Distance",
    "左下肢内外翻角": "Left Leg Alignment Angle",
    "右下肢内外翻角": "Right Leg Alignment Angle",
    "脊柱中线侧偏": "Spinal Midline Deviation",
    "肩胛表面不对称": "Scapular Surface Asymmetry",
    "头前伸距离": "Forward Head Distance",
    "躯干前倾": "Trunk Lean",
    "膝过伸": "Knee Hyperextension",
    "骨盆矢状倾斜": "Pelvic Sagittal Tilt",
    "胸椎体表曲率": "Thoracic Surface Curvature",
    "腰椎体表曲率": "Lumbar Surface Curvature",
    "最大躯干表面旋转": "Maximum Trunk Surface Rotation",
    "左右背部高度差": "Back Height Difference",
    "最大差异所在节段": "Segment with Maximum Difference",
    "髋中心高低差": "Hip Center Height Difference",
    "髋轴冠状倾斜代理角": "Hip Axis Coronal Tilt Proxy",
    "骨盆中心支撑基底侧移": "Pelvis Center Support-Base Shift",
    "模型骨盆前后倾代理角": "Model Pelvis Pitch Proxy",
    "模型骨盆水平旋转代理角": "Model Pelvis Yaw Proxy",
    "背面髋臀区体表对称差代理值": "Posterior Hip/Gluteal Surface Symmetry Proxy",
}


def display_sex(value: str) -> str:
    return SEX_LABELS.get(value, value)


def display_module(value: str) -> str:
    return MODULE_LABELS.get(value, value)


def display_status(value: str) -> str:
    return STATUS_LABELS.get(value, value)


def display_level(value: str) -> str:
    text = str(value or "").strip()
    experimental_suffix = "（实验性/待验证）"
    text = re.sub(r"(?:（实验性/待验证）|\(Experimental / Pending Validation\))+", "", text).strip()
    for repeated_base in ("参考范围内", "轻度关注", "建议进一步评估"):
        text = re.sub(f"(?:{re.escape(repeated_base)})+", repeated_base, text)
    if text:
        translated_base = {
            "参考范围内": "Within Reference Range",
            "轻度关注": "Mild Attention",
            "建议进一步评估": "Further Evaluation Recommended",
        }.get(text, LEVEL_LABELS.get(text, text))
        if text in {"参考范围内", "轻度关注", "建议进一步评估"}:
            return f"{translated_base} (Experimental / Pending Validation)"
        return translated_base
    return LEVEL_LABELS.get(text, text)


def display_direction(value: str | None) -> str | None:
    if value is None:
        return None
    return DIRECTION_LABELS.get(value, value)


def display_metric(value: str) -> str:
    proxy_suffix = "（代理值）"
    if value.endswith(proxy_suffix):
        return f"{METRIC_LABELS.get(value[:-len(proxy_suffix)], value[:-len(proxy_suffix)])} (Proxy)"
    return METRIC_LABELS.get(value, value)


def display_review_reason(value: str) -> str:
    text = str(value or "")
    replacements = {
        "跨姿势差异": "Cross-pose difference",
        "超过": "exceeds",
        "需要人工复核": "Manual review required",
        "髋中心高低差": "Hip center height difference",
    }
    for source, target in replacements.items():
        text = text.replace(source, target)
    return text.replace("，", ", ")


def display_disclaimer(value: str) -> str:
    text = str(value or "").strip()
    if "不作为医学诊断" in text:
        return "For posture screening support only; not a medical diagnosis."
    if "非诊断性体态筛查" in text:
        return (
            "For non-diagnostic posture screening only. Pelvic angles are SDK model "
            "or surface proxies and are not clinical ASIS-PSIS measurements."
        )
    return text
