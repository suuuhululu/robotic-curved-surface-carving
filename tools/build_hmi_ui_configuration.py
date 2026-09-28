#!/usr/bin/env python3
"""2026-09-27 HMI 실제 화면 구성도 최종본을 만든다.

기존 9/25 draw.io 원본의 화면 구조를 보존하면서 최신 HMI의 오류 안내,
실행 차단, 알람 수명주기, 공정/품질 판정 분리를 반영한다. PDF는 같은
좌표의 기존 검증 렌더 위에 변경 영역을 다시 그려 Notion 업로드용으로 만든다.
"""

from __future__ import annotations

import argparse
import html
import subprocess
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont
from reportlab.lib.pagesizes import landscape
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas


PAGE_W, PAGE_H = 1600, 1000
PDF_W, PDF_H = 864, 540
GREEN = "#087f62"
DARK = "#173f35"
MUTED = "#6f8579"
PALE = "#f2f7f1"
AMBER = "#fff6e5"
AMBER_TEXT = "#8a5b20"
RED = "#b75d4b"
REGULAR = "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"
BOLD = "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc"


def graph_root(diagram: ET.Element) -> ET.Element:
    return diagram.find("./mxGraphModel/root")


def cell(diagram: ET.Element, cell_id: str) -> ET.Element:
    found = graph_root(diagram).find(f"mxCell[@id='{cell_id}']")
    if found is None:
        raise KeyError(f"{diagram.get('name')} cell {cell_id}")
    return found


def update(diagram: ET.Element, cell_id: str, value: str, geometry=None) -> None:
    target = cell(diagram, cell_id)
    target.set("value", value)
    if geometry:
        geo = target.find("mxGeometry")
        for key, val in geometry.items():
            geo.set(key, str(val))


def add_cell(diagram: ET.Element, cell_id: str, value: str, x, y, w, h, style: str) -> None:
    target = ET.SubElement(
        graph_root(diagram),
        "mxCell",
        {"id": cell_id, "value": value, "style": style, "vertex": "1", "parent": "1"},
    )
    ET.SubElement(
        target,
        "mxGeometry",
        {"x": str(x), "y": str(y), "width": str(w), "height": str(h), "as": "geometry"},
    )


def edit_drawio(source: Path, output: Path) -> None:
    tree = ET.parse(source)
    root = tree.getroot()
    diagrams = root.findall("diagram")
    if len(diagrams) != 6:
        raise ValueError(f"6개 화면 필요: {len(diagrams)}")
    root.set("modified", "2026-09-27T19:30:00+09:00")
    root.set("agent", "Codex · code-aligned HMI final")

    # 01 준비·측정: Action 결과와 오류 조치를 함께 읽는다.
    d = diagrams[0]
    update(d, "41", "오류 시 코드·단계·운영자 조치를 함께 표시합니다.")
    update(d, "50", "코드 NONE · 치명/미확인 오류는 현장 확인 전 자동 재시도 금지")
    update(d, "83", "오류가 발생하면 코드와 조치가 준비 결과 바로 아래 표시됩니다. 실패·UNKNOWN이면 경로 생성으로 진행하지 않습니다.")
    update(d, "85", "준비 성공 조건 · 오류 코드/조치 · 8점과 최종 성공 구분 · 정지 접수/완료를 함께 확인합니다.")

    # 02 입력·미리보기·실행: 실제 적용 설정과 모든 시작 차단 사유를 표시한다.
    d = diagrams[1]
    update(d, "72", "차단 4건")
    rows = {
        "73": ("경로 검증", {"y": 592}),
        "74": ("미생성", {"y": 592}),
        "75": ("접촉 / 깊이", {"y": 618}),
        "76": ("fixed_depth · 0.50 mm", {"y": 618}),
        "77": ("동작 속도", {"y": 644}),
        "78": ("CUT 5 mm/s · APPROACH 20 mm/s", {"y": 644}),
        "79": ("정지 / 동일성", {"y": 670}),
        "80": ("2초 · path/profile SHA", {"y": 670}),
        "81": ("☐ 도안 위치와 경로를 확인했습니다.", {"y": 702}),
        "82": ("☐ 드릴 수동 ON 확인 · 센서 아님", {"y": 728}),
        "83": ("→  시작 요청", {"y": 812}),
    }
    for cell_id, (value, geo) in rows.items():
        update(d, cell_id, value, geo)
    add_cell(
        d,
        "final-blockers",
        "시작 차단 사유 · 경로 없음 · 미리보기 미확인 · 드릴 확인 필요 · 최신 상태 미확인",
        960,
        758,
        190,
        46,
        "rounded=1;whiteSpace=wrap;html=1;fillColor=#fff6e5;strokeColor=#e9be78;fontColor=#8a5b20;fontSize=9;align=left;verticalAlign=middle;spacingLeft=8;spacingRight=6;",
    )
    update(d, "93", "오른쪽 아래 실행 준비는 적용 깊이·속도·정지 제한·경로/설정 해시와 모든 시작 차단 사유를 읽기 전용으로 표시합니다.")
    update(d, "95", "차단 사유가 0건이어도 공정 제어가 PRECHECK를 다시 수행합니다. 체크는 센서나 실제 전원 제어를 대신하지 않습니다.")
    update(d, "97", "미리보기/실행 동일성 · 적용 설정 · 차단 사유 · 운영자 확인 · 공정 PRECHECK 재검사를 확인합니다.")

    # 03 공정 관제: 실패 코드를 메시지와 분리하고 REAL/SIM 관측 문구를 구분한다.
    d = diagrams[2]
    add_cell(
        d,
        "final-process-error",
        "오류 코드 NONE · 오류 시 단계·코드·조치 표시 / UNKNOWN은 현장 확인 전 새 모션 금지",
        318,
        642,
        508,
        26,
        "rounded=1;whiteSpace=wrap;html=1;fillColor=#fff6e5;strokeColor=#e9be78;fontColor=#8a5b20;fontSize=9;align=left;verticalAlign=middle;spacingLeft=8;",
    )
    update(d, "68", "선택/장착 도구  고정 드릴/미확인     확인 출처  UNKNOWN     정지 상태  NONE     경로 ID·버전·SHA  —")
    update(d, "69", "SIMULATION은 모의 관측 · REAL은 최신 수신 품질/시각 확인 · 미확인 값을 정상으로 간주하지 않음")
    update(d, "81", "현재 공정 카드는 상태·메시지·오류 코드·운영자 조치·조각 진행률과 5단계 위치를 함께 보여줍니다.")
    update(d, "85", "공정 이벤트는 단계 전환과 알람 발생/해제를 시간순으로 보존합니다. 현재 상태와 함께 대조합니다.")
    update(d, "89", "공정 상태/이벤트 분리 · 오류 코드/조치 · 진행률 범위 · REAL 최신성 · 정지 접수/완료를 확인합니다.")

    # 04 실행 이력: 공정 성공과 품질 PASS를 분리한다.
    d = diagrams[3]
    update(d, "37", "공정 결과")
    update(d, "40", "품질 판정 / 상세")
    update(d, "46", "PASS · 상세  ›")
    update(d, "52", "미검사 · 상세  ›")
    update(d, "58", "HOLD · 상세  ›")
    update(d, "65", "공정 결과: 성공 · 공정이 정상 완료되었습니다.<br>오류 코드: NONE · 품질 판정: PASS<br>경로 9ef20d1a · v2")
    update(d, "78", "목록은 실행 ID·경로와 공정 결과를 보관하고, 품질 PASS/HOLD/REJECT/미검사는 별도 열로 표시합니다.")
    update(d, "82", "모달 상단에서 공정 결과·오류 코드·운영자 조치·품질 판정과 경로 ID·버전을 다시 대조합니다.")
    update(d, "88", "공정 결과와 품질 판정 분리 · 오류 코드/조치 · 경로 동일성 · 검사 근거를 확인합니다.")

    # 05 알람: 활성/해제와 조치를 함께 표시한다.
    d = diagrams[4]
    update(d, "34", "활성 2 / 전체 3")
    update(d, "36", "STOP_UNCONFIRMED   [활성]")
    update(d, "37", "정지 완료 미확인<br>조치: 실제 로봇·도구 상태 확인 전 새 모션 금지")
    update(d, "41", "PROFILE_MISMATCH   [해제]")
    update(d, "42", "동일 경로·프로파일 PRECHECK 재통과<br>해제 결과와 시각을 보존")
    update(d, "46", "COMMUNICATION_LOST   [활성]")
    update(d, "47", "최신 상태 확정 불가<br>조치: 자동 재시도 금지, 통신·정지 상태 현장 확인")
    update(d, "54", "알람 메뉴는 실패·불명 상태와 운영자 조치를 확인하는 화면입니다. 활성 알람을 먼저 표시합니다.")
    update(d, "56", "각 행은 활성/해제, 심각도·단계·코드·메시지·조치·발생 시각과 해제 근거로 구성됩니다.")
    update(d, "58", "ALARM_CLEARED는 이력을 삭제하지 않고 동일 경로·프로파일·단계·코드의 기존 알람을 해제로 전환합니다.")
    update(d, "62", "문서와 시험은 감지 조건·차단·조치·해제 조건을 오류 ID와 연결합니다. UNKNOWN은 자동 해제하지 않습니다.")
    update(d, "64", "활성/해제 수명주기 · 오류 코드별 조치 · 해제 근거 · 자동 재시도 금지를 확인합니다.")

    # 06 설정: 실행에 실제 적용되는 읽기 전용 프로파일 요약을 표시한다.
    d = diagrams[5]
    setting_rows = {
        "34": "작업대상",
        "35": "양초 · Ø68.5 × H150 mm",
        "36": "작업 영역",
        "37": "상·하단 10 mm 제외 · V 10~140 mm",
        "38": "도구 / 제어기 TCP",
        "39": "engraving_drill / GripperDA_v1",
        "40": "장착 정책",
        "41": "철사 고정 · 그리퍼 열기 금지",
        "42": "경로 기준",
        "43": "드릴 끝 · c2_base · m / quaternion xyzw",
        "44": "스냅샷 ID / SHA-256",
        "45": "434d189f… / 7483935b…",
        "46": "실행 모드 / 접촉",
        "47": "SIMULATION · fixed_depth",
        "48": "깊이 / CUT 속도",
        "49": "0.50 mm / 5 mm/s · 읽기 전용",
        "50": "정지 확인 / J6 여유",
        "51": "2.0 s / 0.0° · 현장 검증 별도",
        "52": "현장 확정 상태",
        "53": "후보값 · 실기 승인/품질 검증 아님",
    }
    for cell_id, value in setting_rows.items():
        update(d, cell_id, value)
    update(d, "54", "현재 스냅샷과 실행 설정을 읽기 전용으로 확인합니다. 값 표시가 실기 승인이나 안전 검증 완료를 뜻하지 않습니다.")
    update(d, "74", "왼쪽은 현재 프로파일의 작업영역·도구·좌표계와 실행 모드·접촉·깊이·속도·정지/J6 설정을 읽는 영역입니다.")
    update(d, "76", "스냅샷 ID와 SHA-256을 경로·미리보기·실행 기록의 동일성 근거로 연결합니다.")
    update(d, "82", "REAL 연결에서도 설정은 읽기 전용이며, 후보값·현장 확정·실기 검증 상태를 구분해 표시합니다.")
    update(d, "84", "설정 출처·단위·해시 · 후보/승인/검증 구분 · REAL/SIM 모드 · robot_adapter 책임을 확인합니다.")

    label_style = "rounded=1;whiteSpace=wrap;html=1;fillColor=#e8f5ef;strokeColor=#b6d7c7;fontColor=#087f62;fontStyle=1;fontSize=9;align=center;verticalAlign=middle;"
    for index, diagram in enumerate(diagrams, 1):
        add_cell(diagram, f"final-revision-{index}", "최종 개정 · 2026-09-27 · PR #93", 1240, 72, 310, 26, label_style)

    output.parent.mkdir(parents=True, exist_ok=True)
    ET.indent(tree, space="  ")
    tree.write(output, encoding="utf-8", xml_declaration=True)


def font(size: int, bold=False):
    return ImageFont.truetype(BOLD if bold else REGULAR, size=size)


def rgb(value: str):
    value = value.lstrip("#")
    return tuple(int(value[i : i + 2], 16) for i in (0, 2, 4))


def wrap(draw: ImageDraw.ImageDraw, text: str, fnt, max_width: int):
    lines = []
    for raw in text.replace("<br>", "\n").splitlines() or [""]:
        words = raw.split(" ")
        current = ""
        for word in words:
            candidate = word if not current else f"{current} {word}"
            if draw.textbbox((0, 0), candidate, font=fnt)[2] <= max_width:
                current = candidate
            else:
                if current:
                    lines.append(current)
                current = word
        lines.append(current)
    return lines


def paint(img: Image.Image, x, y, w, h, text, *, size=10, fill="#ffffff", color=DARK,
          bold=False, border=None, align="left", pad=7, radius=0):
    scale = img.width / PAGE_W
    box = tuple(round(v * scale) for v in (x, y, x + w, y + h))
    draw = ImageDraw.Draw(img)
    kwargs = {"fill": rgb(fill)}
    if border:
        kwargs.update(outline=rgb(border), width=max(1, round(scale)))
    if radius:
        draw.rounded_rectangle(box, radius=round(radius * scale), **kwargs)
    else:
        draw.rectangle(box, **kwargs)
    fnt = font(max(8, round(size * scale)), bold)
    max_width = max(1, box[2] - box[0] - round(pad * 2 * scale))
    lines = wrap(draw, text, fnt, max_width)
    spacing = max(2, round(2 * scale))
    bboxes = [draw.textbbox((0, 0), line, font=fnt) for line in lines]
    heights = [b[3] - b[1] for b in bboxes]
    total = sum(heights) + spacing * max(0, len(lines) - 1)
    ty = box[1] + max(round(4 * scale), (box[3] - box[1] - total) // 2)
    for line, bbox, lh in zip(lines, bboxes, heights):
        tw = bbox[2] - bbox[0]
        if align == "center":
            tx = box[0] + (box[2] - box[0] - tw) // 2
        elif align == "right":
            tx = box[2] - round(pad * scale) - tw
        else:
            tx = box[0] + round(pad * scale)
        draw.text((tx, ty), line, font=fnt, fill=rgb(color))
        ty += lh + spacing


def final_label(img):
    paint(img, 1240, 72, 310, 26, "최종 개정 · 2026-09-27 · PR #93", size=9,
          fill="#e8f5ef", color=GREEN, bold=True, border="#b6d7c7", align="center", radius=5)


def render_pdf(source_pdf: Path, output_pdf: Path, preview_dir: Path) -> None:
    preview_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="hmi-ui-final-") as tmp:
        prefix = Path(tmp) / "page"
        subprocess.run(["pdftoppm", "-png", "-r", "180", str(source_pdf), str(prefix)], check=True)
        pages = [Image.open(path).convert("RGB") for path in sorted(Path(tmp).glob("page-*.png"))]
        if len(pages) != 6:
            raise ValueError(f"PDF 6페이지 필요: {len(pages)}")

        # 01 준비·측정
        p = pages[0]
        paint(p, 816, 378, 334, 48, "오류 시 코드·단계·운영자 조치를 함께 표시합니다.", size=10)
        paint(p, 816, 468, 334, 40, "코드 NONE · 치명/미확인 오류는 현장 확인 전 자동 재시도 금지",
              size=8, fill=PALE, color=GREEN, border="#c7dccf", radius=5)
        paint(p, 1280, 590, 278, 80, "오류 코드와 조치가 준비 결과 바로 아래 표시됩니다. 실패·UNKNOWN이면 경로 생성으로 진행하지 않습니다.", size=10)
        paint(p, 1232, 854, 326, 82, "준비 성공 조건 · 오류 코드/조치 · 8점과 최종 성공 구분 · 정지 접수/완료를 함께 확인합니다.", size=9, fill=AMBER, color=AMBER_TEXT, border="#ebc987", radius=5)
        final_label(p)

        # 02 실행 준비 패널을 최신 코드 기준으로 다시 그린다.
        p = pages[1]
        paint(p, 948, 548, 214, 306, "", fill="#ffffff")
        paint(p, 960, 554, 120, 28, "실행 준비", size=14, bold=True)
        paint(p, 1088, 556, 64, 24, "차단 4건", size=8, fill=AMBER, color=AMBER_TEXT, border="#ebc987", align="center", radius=4)
        pairs = [
            ("경로 검증", "미생성"),
            ("접촉 / 깊이", "fixed_depth · 0.50 mm"),
            ("동작 속도", "CUT 5 · 접근 20 mm/s"),
            ("정지 / 동일성", "2초 · path/profile SHA"),
        ]
        y = 590
        for left, right in pairs:
            paint(p, 956, y, 82, 24, left, size=8, color=MUTED)
            paint(p, 1038, y, 118, 24, right, size=8, align="right")
            y += 27
        paint(p, 956, 702, 200, 24, "☐ 도안 위치와 경로를 확인했습니다.", size=8)
        paint(p, 956, 727, 200, 24, "☐ 드릴 수동 ON 확인 · 센서 아님", size=8)
        paint(p, 956, 756, 200, 50, "시작 차단 사유<br>경로 없음 · 미리보기/드릴/최신 상태 미확인",
              size=8, fill=AMBER, color=AMBER_TEXT, border="#ebc987", radius=5)
        paint(p, 956, 812, 200, 34, "→  시작 요청", size=10, fill="#92cbb8", color="#ffffff", bold=True, align="center", radius=4)
        paint(p, 1280, 492, 278, 86, "실행 준비에는 깊이·속도·정지 제한·경로/설정 해시와 모든 시작 차단 사유를 읽기 전용으로 표시합니다.", size=9)
        paint(p, 1280, 590, 278, 86, "차단이 0건이어도 공정 제어가 PRECHECK를 다시 수행합니다. 체크는 센서나 전원 제어가 아닙니다.", size=9)
        paint(p, 1232, 854, 326, 82, "미리보기/실행 동일성 · 적용 설정 · 차단 사유 · 운영자 확인 · PRECHECK 재검사를 확인합니다.", size=9, fill=AMBER, color=AMBER_TEXT, border="#ebc987", radius=5)
        final_label(p)

        # 03 공정 관제
        p = pages[2]
        paint(p, 314, 640, 516, 30, "오류 코드 NONE · 오류 시 단계·코드·조치 표시 / UNKNOWN은 현장 확인 전 새 모션 금지",
              size=8, fill=AMBER, color=AMBER_TEXT, border="#ebc987", radius=4)
        paint(p, 228, 770, 606, 42, "선택/장착 도구  고정 드릴/미확인   ·   확인 출처 UNKNOWN   ·   정지 NONE   ·   경로 ID·버전·SHA —", size=8)
        paint(p, 228, 805, 606, 30, "SIMULATION은 모의 관측 · REAL은 최신 수신 품질/시각 확인 · 미확인 값을 정상으로 간주하지 않음", size=8, fill=PALE, color=GREEN)
        paint(p, 1280, 296, 278, 78, "현재 공정 카드는 상태·메시지·오류 코드·조치·조각 진행률과 5단계 위치를 함께 보여줍니다.", size=9)
        paint(p, 1280, 492, 278, 78, "공정 이벤트는 단계 전환과 알람 발생/해제를 보존하며 현재 상태와 대조합니다.", size=9)
        paint(p, 1232, 854, 326, 82, "공정 상태/이벤트 분리 · 오류 코드/조치 · REAL 최신성 · 정지 접수/완료를 확인합니다.", size=9, fill=AMBER, color=AMBER_TEXT, border="#ebc987", radius=5)
        final_label(p)

        # 04 실행 이력
        p = pages[3]
        paint(p, 556, 328, 132, 38, "공정 결과", size=9, fill="#f4f7f2", bold=True, align="center")
        paint(p, 1002, 328, 156, 38, "품질 판정 / 상세", size=9, fill="#f4f7f2", bold=True, align="center")
        for y, value in [(365, "PASS · 상세  ›"), (435, "미검사 · 상세  ›"), (505, "HOLD · 상세  ›")]:
            paint(p, 1002, y, 156, 60, value, size=9, align="center")
        paint(p, 470, 332, 466, 74, "공정 결과: 성공 · 공정이 정상 완료되었습니다.<br>오류 코드: NONE · 품질 판정: PASS<br>경로 9ef20d1a · v2", size=9, fill=PALE, color=GREEN)
        paint(p, 1280, 198, 278, 86, "실행 ID·경로와 공정 결과를 보관하고 품질 PASS/HOLD/REJECT/미검사를 별도 열로 표시합니다.", size=9)
        paint(p, 1280, 394, 278, 86, "모달에서 공정 결과·오류 코드·조치·품질 판정과 경로 ID·버전을 다시 대조합니다.", size=9)
        paint(p, 1232, 854, 326, 82, "공정 결과와 품질 판정 분리 · 오류 코드/조치 · 경로 동일성 · 검사 근거를 확인합니다.", size=9, fill=AMBER, color=AMBER_TEXT, border="#ebc987", radius=5)
        final_label(p)

        # 05 알람 목록 전체를 최신 수명주기 표현으로 다시 그린다.
        p = pages[4]
        paint(p, 224, 320, 934, 360, "", fill="#ffffff")
        paint(p, 1084, 274, 74, 30, "활성 2 / 전체 3", size=8, fill=PALE, color=GREEN, align="center", radius=4)
        alarms = [
            (338, "STOP_UNCONFIRMED", "활성", "정지 완료 미확인", "실제 로봇·도구 상태 확인 전 새 모션 금지", "14:20:31", True),
            (446, "PROFILE_MISMATCH", "해제", "동일 경로·프로파일 PRECHECK 재통과", "해제 결과와 시각 보존", "13:43:02", False),
            (554, "COMMUNICATION_LOST", "활성", "최신 상태 확정 불가", "자동 재시도 금지, 통신·정지 상태 현장 확인", "11:12:44", True),
        ]
        for y, code, state, msg, action, stamp, active_state in alarms:
            paint(p, 232, y, 45, 78, "△", size=15, fill="#fffaf4", color=RED if active_state else MUTED, border="#ead8c7", align="center", radius=8)
            paint(p, 288, y, 550, 28, f"{code}   [{state}]", size=10, color=RED if active_state else GREEN, bold=True)
            paint(p, 288, y + 28, 690, 50, f"{msg}<br>조치: {action}", size=8, color=DARK)
            paint(p, 1032, y + 18, 116, 32, stamp, size=8, color=MUTED, align="right")
        paint(p, 1280, 198, 278, 80, "알람은 실패·불명 상태와 운영자 조치를 확인하는 화면이며 활성 알람을 먼저 표시합니다.", size=9)
        paint(p, 1280, 296, 278, 80, "각 행은 활성/해제, 단계·심각도·코드·메시지·조치·해제 근거로 구성됩니다.", size=9)
        paint(p, 1280, 394, 278, 80, "ALARM_CLEARED는 이력을 삭제하지 않고 동일 범위의 기존 알람을 해제로 전환합니다.", size=9)
        paint(p, 1280, 590, 278, 80, "UNKNOWN은 자동 해제하지 않습니다. 감지·차단·조치·해제 조건을 오류 ID와 연결합니다.", size=9)
        paint(p, 1232, 854, 326, 82, "활성/해제 수명주기 · 오류 코드별 조치 · 해제 근거 · 자동 재시도 금지를 확인합니다.", size=9, fill=AMBER, color=AMBER_TEXT, border="#ebc987", radius=5)
        final_label(p)

        # 06 설정 정보
        p = pages[5]
        paint(p, 224, 320, 438, 500, "", fill="#ffffff")
        rows = [
            ("작업대상", "양초 · Ø68.5 × H150 mm"),
            ("작업 영역", "상·하단 10 mm 제외 · V 10~140 mm"),
            ("도구 / 제어기 TCP", "engraving_drill / GripperDA_v1"),
            ("장착 정책", "철사 고정 · 그리퍼 열기 금지"),
            ("경로 기준", "드릴 끝 · c2_base · m/quaternion"),
            ("스냅샷 ID / SHA", "434d189f… / 7483935b…"),
            ("실행 모드 / 접촉", "SIMULATION · fixed_depth"),
            ("깊이 / CUT 속도", "0.50 mm / 5 mm/s · 읽기 전용"),
            ("정지 확인 / J6", "2.0 s / 0.0° · 현장 검증 별도"),
            ("현장 확정 상태", "후보값 · 실기 승인/품질 검증 아님"),
        ]
        y = 326
        for label, value in rows:
            paint(p, 230, y, 146, 34, label, size=8, color=MUTED)
            paint(p, 378, y, 276, 34, value, size=8)
            y += 36
        paint(p, 230, 704, 424, 82, "현재 스냅샷과 실행 설정을 읽기 전용으로 확인합니다.<br>값 표시가 실기 승인이나 안전 검증 완료를 뜻하지 않습니다.", size=8, fill=PALE, color=GREEN, border="#c7dccf", radius=5)
        paint(p, 1280, 198, 278, 86, "현재 프로파일의 작업영역·도구·좌표계와 접촉·깊이·속도·정지/J6 설정을 읽습니다.", size=9)
        paint(p, 1280, 296, 278, 86, "스냅샷 ID와 SHA-256을 경로·미리보기·실행 기록의 동일성 근거로 연결합니다.", size=9)
        paint(p, 1280, 590, 278, 86, "REAL에서도 설정은 읽기 전용이며 후보값·현장 확정·실기 검증 상태를 구분합니다.", size=9)
        paint(p, 1232, 854, 326, 82, "설정 출처·단위·해시 · 후보/승인/검증 구분 · REAL/SIM · robot_adapter 책임을 확인합니다.", size=9, fill=AMBER, color=AMBER_TEXT, border="#ebc987", radius=5)
        final_label(p)

        for index, page in enumerate(pages, 1):
            page.save(preview_dir / f"HMI_UI_FINAL_page_{index}.png", optimize=True)

        output_pdf.parent.mkdir(parents=True, exist_ok=True)
        pdf = canvas.Canvas(str(output_pdf), pagesize=landscape((PDF_H, PDF_W)))
        pdf.setTitle("C-2 HMI UI Configuration Final 2026-09-27")
        pdf.setAuthor("C-2 Team")
        pdf.setSubject("Code-aligned HMI wireframe with exception and safety states")
        for page in pages:
            pdf.drawImage(ImageReader(page), 0, 0, width=PDF_W, height=PDF_H)
            pdf.showPage()
        pdf.save()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-drawio", type=Path, required=True)
    parser.add_argument("--source-pdf", type=Path, required=True)
    parser.add_argument("--output-drawio", type=Path, required=True)
    parser.add_argument("--output-pdf", type=Path, required=True)
    parser.add_argument("--preview-dir", type=Path, required=True)
    args = parser.parse_args()
    edit_drawio(args.source_drawio, args.output_drawio)
    render_pdf(args.source_pdf, args.output_pdf, args.preview_dir)


if __name__ == "__main__":
    main()
