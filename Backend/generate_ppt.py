# -*- coding: utf-8 -*-
"""
웹프로그래밍 조별 과제 - 서비스 기획문서 PPT 자동 생성 스크립트 (총 20장)
주제: 알약이가 (e-Drug Care) - 식약처 3대 OpenAPI 통합 스마트 의약품 식별 및 복약 안전 플랫폼
포함 내용:
  1. 문제정의 (기존 유사 서비스 한계와 차별성)
  2. SWOT 분석 (강점/약점/기회/위협 및 교차전략)
  3. STP 전략 (Segmentation, Targeting, Positioning)
  4. Persona (실제 사용자 2명 구체적 설정)
  5. Lean Canvas (9개 항목 비즈니스 모델 캔버스 + 상세 분석)
  6. Storyboard (화면 흐름도 및 MVP 5대 핵심 화면 와이어프레임·기능 명세)
  7. 2차 과제(Frontend + Django Backend) 구현 아키텍처 및 로드맵
"""

import shutil
from pathlib import Path
from pptx import Presentation
from pptx.util import Inches, Pt
from pptx.dml.color import RGBColor
from pptx.enum.text import PP_ALIGN, MSO_ANCHOR
from pptx.enum.shapes import MSO_SHAPE

# 컬러 팔레트 정의
C_NAVY = RGBColor(15, 23, 42)       # #0F172A 진네이비
C_BLUE = RGBColor(37, 99, 235)      # #2563EB 메인 블루
C_BLUE_DARK = RGBColor(29, 78, 216) # #1D4ED8 다크 블루
C_BLUE_LIGHT = RGBColor(239, 246, 255)  # #EFF6FF 연블루 배경
C_TEAL = RGBColor(13, 148, 136)     # #0D9488 틸 그린
C_TEAL_LIGHT = RGBColor(240, 253, 250)  # #F0FDFA 연틸 배경
C_PURPLE = RGBColor(124, 58, 237)   # #7C3AED 퍼플
C_PURPLE_LIGHT = RGBColor(245, 243, 255)
C_AMBER = RGBColor(217, 119, 6)     # #D97706 앰버
C_AMBER_LIGHT = RGBColor(255, 251, 235)
C_RED = RGBColor(220, 38, 38)       # #DC2626 레드
C_RED_LIGHT = RGBColor(254, 242, 242)
C_BG = RGBColor(248, 250, 252)      # #F8FAFC 슬라이드 배경
C_WHITE = RGBColor(255, 255, 255)
C_BORDER = RGBColor(203, 213, 225)  # #CBD5E1 테두리
C_TEXT = RGBColor(30, 41, 59)       # #1E293B 본문 다크
C_MUTED = RGBColor(100, 116, 139)   # #64748B 보조 텍스트

FONT_NAME = "맑은 고딕"


def set_slide_bg(slide, color=C_BG):
    background = slide.background
    fill = background.fill
    fill.solid()
    fill.fore_color.rgb = color


def add_box(slide, left, top, width, height, bg_color=C_WHITE, border_color=C_BORDER, shape_type=MSO_SHAPE.ROUNDED_RECTANGLE, border_pt=1):
    shape = slide.shapes.add_shape(shape_type, Inches(left), Inches(top), Inches(width), Inches(height))
    shape.fill.solid()
    shape.fill.fore_color.rgb = bg_color
    if border_color:
        shape.line.color.rgb = border_color
        shape.line.width = Pt(border_pt)
    else:
        shape.line.fill.background()
    if shape_type == MSO_SHAPE.ROUNDED_RECTANGLE and hasattr(shape, "adjustments") and len(shape.adjustments) > 0:
        shape.adjustments[0] = 0.04
    return shape


def add_text(slide, left, top, width, height, text, font_size=12, bold=False, color=C_TEXT, align=PP_ALIGN.LEFT, valign=MSO_ANCHOR.TOP):
    tb = slide.shapes.add_textbox(Inches(left), Inches(top), Inches(width), Inches(height))
    tf = tb.text_frame
    tf.word_wrap = True
    tf.vertical_anchor = valign
    tf.margin_left = Inches(0.05)
    tf.margin_right = Inches(0.05)
    tf.margin_top = Inches(0.03)
    tf.margin_bottom = Inches(0.03)

    lines = str(text).split("\n")
    for idx, line in enumerate(lines):
        p = tf.paragraphs[0] if idx == 0 else tf.add_paragraph()
        p.text = line
        p.alignment = align
        p.font.name = FONT_NAME
        p.font.size = Pt(font_size)
        p.font.bold = bold
        p.font.color.rgb = color
        p.space_after = Pt(4)
    return tb


def add_header(slide, section_badge, title, subtitle, slide_no, total_slides=20):
    set_slide_bg(slide, C_BG)
    # 상단 네이비 바
    top_bar = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(0), Inches(0), Inches(13.333), Inches(0.12))
    top_bar.fill.solid()
    top_bar.fill.fore_color.rgb = C_BLUE
    top_bar.line.fill.background()

    # 섹션 배지
    badge = add_box(slide, 0.6, 0.32, 2.5, 0.34, bg_color=C_BLUE_LIGHT, border_color=C_BLUE)
    add_text(slide, 0.6, 0.32, 2.5, 0.34, section_badge, font_size=10, bold=True, color=C_BLUE, align=PP_ALIGN.CENTER, valign=MSO_ANCHOR.MIDDLE)

    # 우측 상단 서비스 로고 & 슬라이드 번호
    add_text(slide, 9.5, 0.32, 3.2, 0.34, f"💊 알약이가 (e-Drug Care)  |  {slide_no:02d} / {total_slides:02d}", font_size=10, bold=True, color=C_MUTED, align=PP_ALIGN.RIGHT, valign=MSO_ANCHOR.MIDDLE)

    # 메인 타이틀 & 서브타이틀
    add_text(slide, 0.6, 0.72, 12.1, 0.48, title, font_size=22, bold=True, color=C_NAVY)
    add_text(slide, 0.6, 1.18, 12.1, 0.35, subtitle, font_size=12, bold=False, color=C_MUTED)

    # 구분선
    line = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(0.6), Inches(1.55), Inches(12.133), Inches(0.02))
    line.fill.solid()
    line.fill.fore_color.rgb = C_BORDER
    line.line.fill.background()


def add_card_with_header(slide, left, top, width, height, header_title, body_lines, header_bg=C_BLUE, card_bg=C_WHITE, body_size=11):
    # 전체 카드
    add_box(slide, left, top, width, height, bg_color=card_bg, border_color=C_BORDER)
    # 상단 헤더 영역
    h_box = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(left), Inches(top), Inches(width), Inches(0.46))
    h_box.fill.solid()
    h_box.fill.fore_color.rgb = header_bg
    h_box.line.fill.background()
    if hasattr(h_box, "adjustments") and len(h_box.adjustments) > 0:
        h_box.adjustments[0] = 0.08
    add_text(slide, left + 0.12, top, width - 0.24, 0.46, header_title, font_size=12, bold=True, color=C_WHITE, valign=MSO_ANCHOR.MIDDLE)

    # 본문 텍스트
    body_text = "\n".join(body_lines) if isinstance(body_lines, list) else str(body_lines)
    add_text(slide, left + 0.15, top + 0.55, width - 0.3, height - 0.65, body_text, font_size=body_size, color=C_TEXT)


def build_presentation():
    prs = Presentation()
    prs.slide_width = Inches(13.333)
    prs.slide_height = Inches(7.5)
    blank_layout = prs.slide_layouts[6]

    # =========================================================================
    # Slide 01: 표지 (Cover)
    # =========================================================================
    s1 = prs.slides.add_slide(blank_layout)
    set_slide_bg(s1, C_NAVY)

    # 배경 포인트 도형
    deco1 = s1.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(8.6), Inches(0.8), Inches(4.2), Inches(5.9))
    deco1.fill.solid()
    deco1.fill.fore_color.rgb = RGBColor(30, 41, 59)
    deco1.line.color.rgb = C_BLUE
    deco1.line.width = Pt(1.5)

    add_box(s1, 0.8, 1.0, 3.6, 0.42, bg_color=C_BLUE, border_color=None)
    add_text(s1, 0.8, 1.0, 3.6, 0.42, "2026 웹프로그래밍 1차 서비스 기획서", font_size=12, bold=True, color=C_WHITE, align=PP_ALIGN.CENTER, valign=MSO_ANCHOR.MIDDLE)

    add_text(s1, 0.8, 1.75, 7.5, 1.2, "알약이가 (e-Drug Care)", font_size=40, bold=True, color=C_WHITE)
    add_text(s1, 0.8, 2.75, 7.5, 0.9, "식약처 3대 OpenAPI 통합 스마트 의약품 식별 및\n개인 맞춤형 복약 안전 웹 플랫폼 기획", font_size=18, bold=True, color=RGBColor(147, 197, 253))

    add_text(
        s1, 0.8, 3.85, 7.4, 1.3,
        "• 정체 모를 알약의 외형(모양·색상·각인) 기반 0.1초 스마트 낱알 식별\n"
        "• 식약처 [낱알식별] + [제품허가] + [e약은요] 3대 공공데이터 실시간 교차 매칭\n"
        "• 내 약통(복약 수첩) 기반 주성분 중복 복용 경고 및 병용금기 안전 리포트\n"
        "• 2차 과제 연계: Python Django + SQLite3 + PC·모바일 반응형 웹 완벽 구현",
        font_size=13, color=RGBColor(226, 232, 240)
    )

    # 제출 정보 박스
    add_box(s1, 0.8, 5.55, 7.4, 1.15, bg_color=RGBColor(30, 41, 59), border_color=RGBColor(71, 85, 105))
    add_text(
        s1, 1.0, 5.68, 7.0, 0.95,
        "과목명 : 웹프로그래밍 (실습 및 프로젝트)     |     제출기한 : 2026. 10. 31(토)\n"
        "제출자 : [조장이름] (조장)                  |     조원명단 : [조원1, 조원2, 조원3]\n"
        "기술스택 : HTML5 / CSS3 / Vanilla JS + Python Django 6.1 + SQLite3 + 식약처 OpenAPI 3종",
        font_size=11, bold=True, color=C_WHITE
    )

    # 우측 3대 OpenAPI 카드 요약
    add_text(s1, 8.9, 1.1, 3.6, 0.4, "🔗 핵심 연동 공공데이터 (OpenAPI)", font_size=14, bold=True, color=C_WHITE)
    apis = [
        ("API 1. 의약품 낱알식별 정보", "MdcinGrnIdntfcInfoService03\n• 실물 이미지, 모양, 색상, 앞/뒤 각인, 크기", C_TEAL),
        ("API 2. 의약품 제품 허가정보", "DrugPrdtPrmsnInfoService08\n• 전문/일반 구분, 영문/한글 주성분, 유효기간", C_PURPLE),
        ("API 3. 의약품개요정보 (e약은요)", "DrbEasyDrugInfoService\n• 환자 눈높이 효능·복용법·주의사항·병용금기", C_BLUE),
    ]
    for i, (t, desc, col) in enumerate(apis):
        y = 1.65 + i * 1.6
        add_box(s1, 8.9, y, 3.6, 1.38, bg_color=RGBColor(15, 23, 42), border_color=col, border_pt=1.5)
        add_text(s1, 9.05, y + 0.1, 3.3, 0.35, t, font_size=12, bold=True, color=C_WHITE)
        add_text(s1, 9.05, y + 0.48, 3.3, 0.8, desc, font_size=10, color=RGBColor(203, 213, 225))

    # =========================================================================
    # Slide 02: 목차 및 기획 개요 (Table of Contents)
    # =========================================================================
    s2 = prs.slides.add_slide(blank_layout)
    add_header(s2, "OVERVIEW & INDEX", "목차 및 서비스 기획 개요", "실제 구현 가능한 웹서비스 기획부터 2차 과제(Frontend + Django Backend) 구현까지의 전체 설계", 2)

    toc_items = [
        ("01", "문제 정의 (Problem Definition)", "일상 속 복약 문제 진단, 기존 의약품 검색 서비스의 한계 분석 및 본 서비스만의 3대 핵심 차별성", "Slides 03 - 05", C_BLUE),
        ("02", "SWOT 분석 (SWOT Analysis)", "조의 개발 역량 및 서비스 강점·약점(S/W)과 시장·사용자·공공데이터 환경의 기회·위협(O/T) 및 교차전략", "Slides 06 - 07", C_TEAL),
        ("03", "STP 전략 (Segmentation · Targeting · Positioning)", "의약품 정보 탐색 시장 세분화, 핵심 타겟 고객층 선정 및 직관성·전문성 기반 포지셔닝 맵", "Slides 08 - 09", C_PURPLE),
        ("04", "페르소나 (User Persona)", "구체적인 실제 타겟 사용자 2명(자취 대학생 김민지, 다제복용 부모님 케어 직장인 박성호) 심층 정의", "Slides 10 - 11", C_AMBER),
        ("05", "린 캔버스 (Lean Canvas 9 Blocks)", "문제·해결책·가치제안·고객군·채널·핵심지표·비용구조·수익원·경쟁우위 9개 블록 비즈니스 모델 설계", "Slides 12 - 13", C_BLUE_DARK),
        ("06", "스토리보드 및 아키텍처 (Storyboard & MVP)", "전체 유저 플로우 및 MVP 5대 핵심 화면(통합검색·낱알식별·허가조회·상세모달·내 약통) 상세 설계", "Slides 14 - 20", C_RED),
    ]
    for idx, (num, title, desc, pages, col) in enumerate(toc_items):
        row = idx // 2
        col_idx = idx % 2
        x = 0.6 + col_idx * 6.15
        y = 1.85 + row * 1.75
        add_box(s2, x, y, 5.95, 1.55, bg_color=C_WHITE, border_color=C_BORDER)
        num_box = add_box(s2, x + 0.18, y + 0.22, 0.75, 0.75, bg_color=col, border_color=None)
        add_text(s2, x + 0.18, y + 0.22, 0.75, 0.75, num, font_size=18, bold=True, color=C_WHITE, align=PP_ALIGN.CENTER, valign=MSO_ANCHOR.MIDDLE)
        add_text(s2, x + 1.08, y + 0.18, 3.6, 0.35, title, font_size=14, bold=True, color=C_NAVY)
        add_text(s2, x + 4.6, y + 0.2, 1.2, 0.3, pages, font_size=10, bold=True, color=col, align=PP_ALIGN.RIGHT)
        add_text(s2, x + 1.08, y + 0.58, 4.7, 0.85, desc, font_size=10.5, color=C_MUTED)

    # =========================================================================
    # Slide 03: ① 문제정의 (1/3) - 어떤 문제를 해결하는 서비스인가?
    # =========================================================================
    s3 = prs.slides.add_slide(blank_layout)
    add_header(s3, "01. 문제 정의 (1/3)", "왜 새로운 의약품 웹서비스가 필요한가?", "가정 내 상비약·처방약 복용 과정에서 누구나 겪는 3가지 심각한 정보 비대칭과 안전 문제", 3)

    problems = [
        (
            "문제 1. 정체불명 '알약(낱알)' 방치 및 오남용",
            C_RED,
            [
                "• 약봉지나 외부 상자를 버린 뒤 약통에 남은 알약은",
                "  이름을 알 수 없어 '무슨 약인지' 식별 불가능",
                "• 알약 표면에는 'TYLENOL', 'YH', '80' 같은 영문/숫자",
                "  각인과 모양·색상만 존재함",
                "• 일반 포털에 '하얀색 길쭉한 알약'으로 검색해도",
                "  부정확한 블로그/지식인 글만 노출되어 오복용 위험 초래",
                "",
                "▶ 니즈: 약 이름을 몰라도 외형(모양·색상·각인)만으로",
                "   정확한 의약품을 즉시 식별할 수 있는 도구 필요"
            ]
        ),
        (
            "문제 2. 파편화된 공공데이터와 어려운 의학 용어",
            C_BLUE,
            [
                "• 식약처 'e약은요'는 설명이 쉽지만 등재 품목이 약 4,700여",
                "  개(일반약 위주)에 불과해 전문 처방약 검색 시 누락 빈번",
                "• 반면 '의약품 제품허가(42,000건)' 및 '낱알식별(25,000건)'은",
                "  방대하지만 전문 약학 용어로만 표기되어 일반인 이해 곤란",
                "• 소비자가 약 하나의 외형+성분+쉬운 복용법을 보려면",
                "  서로 다른 3개의 사이트/API를 각각 찾아다녀야 함",
                "",
                "▶ 니즈: 3대 식약처 데이터를 품목코드 기준으로 하나로",
                "   병합해 '쉬운 복약안내 + 전문 스펙'을 동시에 제공해야 함"
            ]
        ),
        (
            "문제 3. 다제 복용 시 '주성분 중복' 및 병용금기 간과",
            C_AMBER,
            [
                "• 감기약(판콜 등)과 해열진통제(타이레놀)를 동시에 복용할 때",
                "  두 약 모두 '아세트아미노펜'이 함유된 줄 모르고 과량 복용",
                "• 서로 다른 상품명을 가진 약이라도 동일한 주성분(Active",
                "  Ingredient)을 포함한 경우가 매우 흔함",
                "• 기존 단순 검색 사이트는 단발성 1회 조회에 그쳐,",
                "  '내가 지금 먹는 약들의 조합'이 안전한지 알려주지 못함",
                "",
                "▶ 니즈: 복용 중인 약을 '내 약통'에 담아두면 주성분 중복과",
                "   병용 주의사항을 자동 브리핑해주는 안전 관리 기능 필요"
            ]
        ),
    ]

    for i, (p_title, col, lines) in enumerate(problems):
        add_card_with_header(s3, 0.6 + i * 4.12, 1.8, 3.9, 4.35, p_title, lines, header_bg=col, body_size=10.8)

    add_box(s3, 0.6, 6.32, 12.133, 0.78, bg_color=C_NAVY, border_color=None)
    add_text(
        s3, 0.8, 6.32, 11.7, 0.78,
        "💡 핵심 문제정의 요약 : \"소비자는 (1) 이름 모를 알약을 식별하기 어렵고, (2) 흩어진 전문 허가정보와 쉬운 복약정보를 한 번에 볼 수 없으며, (3) 여러 약 복용 시 주성분 중복 위험에 노출되어 있다.\"",
        font_size=12, bold=True, color=C_WHITE, valign=MSO_ANCHOR.MIDDLE
    )

    # =========================================================================
    # Slide 04: ① 문제정의 (2/3) - 기존 유사 서비스의 한계와 비교 분석
    # =========================================================================
    s4 = prs.slides.add_slide(blank_layout)
    add_header(s4, "01. 문제 정의 (2/3)", "기존 유사 서비스의 한계점 및 비교 분석", "기존 의약품 포털 및 공공 서비스가 해결하지 못한 사용자 경험(UX) 및 데이터 단절 문제", 4)

    # 비교 표 생성
    rows, cols = 6, 5
    table_shape = s4.shapes.add_table(rows, cols, Inches(0.6), Inches(1.8), Inches(12.133), Inches(3.8))
    table = table_shape.table
    widths = [2.1, 2.3, 2.3, 2.3, 3.133]
    for idx, w in enumerate(widths):
        table.columns[idx].width = Inches(w)

    headers = ["비교 항목", "네이버 지식백과 / 포털", "약학정보원 / 의약품안전나라", "기존 단순 e약은요 검색기", "💊 알약이가 (본 기획 서비스)"]
    matrix = [
        ["데이터 범위", "인기 약품 위주 단편 정보\n(광고성 블로그 혼재)", "허가/전문 정보 방대하나\n메뉴가 복잡하고 파편화됨", "e약은요 단일 API만 사용\n(전문의약품·외형정보 부재)", "식약처 3대 OpenAPI 통합 연동\n(e약은요+낱알식별+제품허가)"],
        ["이름 모를 낱알 식별", "불가능 (정확한 약 이름\n입력 필수)", "가능하나 화면이 복잡하고\n모바일 조작성이 크게 떨어짐", "불가능 (낱알식별 API 미연동)", "모양·색상·각인 원클릭 비주얼 필터\n(Django SQLite 캐시로 0.1초 탐색)"],
        ["정보 이해도 & 깊이", "요약은 있으나 출처 불명확", "전문 약학 용어 위주\n(일반인 이해하기 어려움)", "설명은 쉬우나 주성분 영문명,\n유효기간, EDI 코드 등 누락", "3-Tab 상세 모달로 쉬운 복약법과\n전문 허가스펙을 한 화면에 제공"],
        ["개인 복약 관리 &\n중복 성분 체크", "지원 안 함 (단순 일회성 검색)", "지원 안 함", "지원 안 함", "'내 약통' DB 저장 및 주성분 중복·\n병용금기 자동 안전 리포트 제공"],
        ["PC / 모바일 사용성", "포털 UI에 종속됨", "PC 중심 레거시 테이블 UI\n(모바일 가독성 저하)", "단순 텍스트/카드 나열 수준", "PC 와이드 뷰 + 모바일 하단 탭바 &\n바텀시트 모달 완벽 반응형 지원"],
    ]

    for c_idx, h_text in enumerate(headers):
        cell = table.cell(0, c_idx)
        cell.fill.solid()
        cell.fill.fore_color.rgb = C_BLUE if c_idx == 4 else C_NAVY
        cell.vertical_anchor = MSO_ANCHOR.MIDDLE
        p = cell.text_frame.paragraphs[0]
        p.text = h_text
        p.font.name = FONT_NAME
        p.font.size = Pt(11)
        p.font.bold = True
        p.font.color.rgb = C_WHITE
        p.alignment = PP_ALIGN.CENTER

    for r_idx, row_data in enumerate(matrix):
        for c_idx, val in enumerate(row_data):
            cell = table.cell(r_idx + 1, c_idx)
            cell.fill.solid()
            if c_idx == 0:
                cell.fill.fore_color.rgb = RGBColor(241, 245, 249)
            elif c_idx == 4:
                cell.fill.fore_color.rgb = C_BLUE_LIGHT
            else:
                cell.fill.fore_color.rgb = C_WHITE
            cell.vertical_anchor = MSO_ANCHOR.MIDDLE
            p = cell.text_frame.paragraphs[0]
            p.text = val
            p.font.name = FONT_NAME
            p.font.size = Pt(10)
            p.font.bold = (c_idx == 0 or c_idx == 4)
            p.font.color.rgb = C_BLUE_DARK if c_idx == 4 else C_TEXT
            p.alignment = PP_ALIGN.CENTER if c_idx == 0 else PP_ALIGN.LEFT

    # 하단 시사점 카드
    add_box(s4, 0.6, 5.82, 12.133, 1.25, bg_color=C_WHITE, border_color=C_BLUE, border_pt=1.5)
    add_text(
        s4, 0.85, 5.92, 11.6, 1.05,
        "📌 기존 서비스 한계 극복의 핵심 논리\n"
        "• 기존 학생/토이 프로젝트들은 단일 OpenAPI(e약은요 1개)만 호출해 단순 출력하는 데 그쳐 실제 활용 가치가 낮았습니다.\n"
        "• 본 조는 식약처의 서로 다른 3개 API를 품목기준코드(ITEM_SEQ)로 조인(Join)하고, 공공 API가 지원하지 않는 '외형 단독 고속 필터링'을 Django DB 캐싱으로 해결했습니다.",
        font_size=11, bold=False, color=C_TEXT
    )

    # =========================================================================
    # Slide 05: ① 문제정의 (3/3) - 본 서비스의 3대 핵심 차별성
    # =========================================================================
    s5 = prs.slides.add_slide(blank_layout)
    add_header(s5, "01. 문제 정의 (3/3)", "알약이가(e-Drug Care)의 3대 핵심 차별성", "단순 OpenAPI 조회를 넘어 백엔드 엔지니어링(Django)과 사용자 경험(UX)을 결합한 독창적 가치", 5)

    diffs = [
        (
            "차별성 1. 식약처 3대 OpenAPI 실시간 하이브리드 병합 엔진",
            C_BLUE,
            "• 단일 검색어로 3개 API를 병렬(ThreadPool) 호출 후 ITEM_SEQ 기준 자동 병합\n"
            "• [e약은요] 환자용 복약법 + [낱알식별] 실물 사진·크기·각인 + [제품허가] 주성분·유효기간·전문/일반 구분을 단일 카드와 3-Tab 모달로 통합 제공\n"
            "• 어느 한 API에 데이터가 없더라도 다른 API 데이터로 상호 보완(Fallback)하여 검색 누락 제로화"
        ),
        (
            "차별성 2. 공공API 한계를 극복한 'Django SQLite 외형 인덱싱 낱알 식별기'",
            C_TEAL,
            "• [기술적 문제 해결] 식약처 낱알식별 API는 약 이름 없이 모양·색상 파라미터만으로는 서버단 필터링을 지원하지 않는 치명적 한계 보유\n"
            "• [본 조의 해결책] Django 백엔드 SQLite DB(PillCache 모델)에 낱알 외형 데이터를 자동 인덱싱하여, 약 이름을 전혀 몰라도 모양+색상+각인 조합만으로 0.1초 내 즉시 식별 구현"
        ),
        (
            "차별성 3. '내 약통(My Pillbox)' 주성분 중복 감지 & 복약 안전 리포트",
            C_PURPLE,
            "• 사용자가 복용 중인 약들을 '내 약통(Django SavedDrug 모델)'에 담으면 주성분(ITEM_INGR_NAME)을 자동 파싱하여 교차 검증\n"
            "• 동일 주성분(예: Acetaminophen 등)이 2개 이상의 약에 중복 포함될 경우 즉시 시각적 경고 배너 및 병용금기 브리핑 제공"
        ),
    ]

    for i, (d_title, col, d_desc) in enumerate(diffs):
        y = 1.82 + i * 1.75
        add_box(s5, 0.6, y, 12.133, 1.55, bg_color=C_WHITE, border_color=col, border_pt=1.5)
        badge_b = add_box(s5, 0.8, y + 0.2, 11.7, 0.38, bg_color=col, border_color=None)
        add_text(s5, 0.95, y + 0.2, 11.4, 0.38, d_title, font_size=13, bold=True, color=C_WHITE, valign=MSO_ANCHOR.MIDDLE)
        add_text(s5, 0.85, y + 0.68, 11.6, 0.8, d_desc, font_size=11, color=C_TEXT)

    # =========================================================================
    # Slide 06: ② SWOT 분석 (1/2) - 내·외부 환경 분석 매트릭스
    # =========================================================================
    s6 = prs.slides.add_slide(blank_layout)
    add_header(s6, "02. SWOT 분석 (1/2)", "조의 역량·서비스 관점 및 시장 환경 SWOT 분석", "내부 역량(Strengths·Weaknesses)과 외부 시장·사용자 환경(Opportunities·Threats) 다각도 진단", 6)

    swot_data = [
        (
            "S - Strengths (강점 : 조의 역량 및 서비스 관점)",
            C_BLUE, C_BLUE_LIGHT,
            [
                "• 식약처 3대 핵심 OpenAPI 통합 연동 및 정규화 파이프라인 구축 완료",
                "• Python Django 백엔드 + SQLite 캐싱을 결합해 공공API의 응답 속도와 외형 검색 한계를 동시에 해결한 기술적 완성도",
                "• PC 와이드 레이아웃과 모바일 하단 네비게이션을 동시 지원하는 완성도 높은 반응형 프론트엔드 구현 역량",
                "• 비전공자·고령자도 직관적으로 쓸 수 있는 컬러칩·도형 기반 UI/UX"
            ]
        ),
        (
            "W - Weaknesses (약점 : 조의 역량 및 서비스 관점)",
            C_AMBER, C_AMBER_LIGHT,
            [
                "• 대학생 프로젝트 특성상 초기 마케팅 예산 및 브랜드 인지도 부족",
                "• 식약처 공공데이터 API의 일일 트래픽 제한 및 간헐적 응답 지연에 대한 의존성 존재 (로컬 DB 캐싱으로 완화 필요)",
                "• 카메라 촬영을 통한 AI 이미지 딥러닝 자동 인식 대신 사용자가 모양·색상·각인을 직접 선택해야 하는 반자동 식별 방식"
            ]
        ),
        (
            "O - Opportunities (기회 : 시장·사용자·경쟁환경)",
            C_TEAL, C_TEAL_LIGHT,
            [
                "• 셀프 메디케이션(Self-Medication) 확산 및 가정 내 상비약·영양제 다제 복용 인구의 급격한 증가",
                "• 정부의 공공데이터 개방 확대 기조 및 디지털 헬스케어·복약 안전 서비스에 대한 사회적 관심 증대",
                "• 기존 약학 포털들의 모바일 UX 노후화로 인해 직관적이고 빠른 모바일 웹 의약품 검색 도구에 대한 틈새 수요(Niche Market) 존재"
            ]
        ),
        (
            "T - Threats (위협 : 시장·사용자·경쟁환경)",
            C_RED, C_RED_LIGHT,
            [
                "• 대형 헬스케어 앱(굿닥, 나만의닥터 등) 및 대형 포털의 의약품 검색 기능 고도화 가능성",
                "• 의약품 정보 제공 시 법적 의료행위(진단·처방) 오해 소지를 방지해야 하는 의료법/약사법 규제 환경",
                "• 공공데이터 포털(data.go.kr) 게이트웨이 점검 시 실시간 조회 장애 발생 가능성"
            ]
        ),
    ]

    for idx, (title, col, light_col, bullets) in enumerate(swot_data):
        r = idx // 2
        c = idx % 2
        x = 0.6 + c * 6.15
        y = 1.8 + r * 2.65
        add_card_with_header(s6, x, y, 5.95, 2.48, title, bullets, header_bg=col, card_bg=light_col, body_size=10.5)

    # =========================================================================
    # Slide 07: ② SWOT 분석 (2/2) - SWOT 교차 전략 (SO / WO / ST / WT)
    # =========================================================================
    s7 = prs.slides.add_slide(blank_layout)
    add_header(s7, "02. SWOT 분석 (2/2)", "SWOT 교차 분석 기반 핵심 실행 전략", "강점은 극대화하고 약점·위협은 기술적·기획적 설계로 보완하는 4대 실행 전략", 7)

    strategies = [
        (
            "SO 전략 (강점 × 기회) : 시장 선점 및 특화 가치 극대화",
            C_BLUE,
            [
                "• [3-in-1 통합 뷰로 셀프 메디케이션 수요 흡수]",
                "  다제 복용 증가 트렌드(O)에 맞춰 3대 OpenAPI 통합 검색 및",
                "  '내 약통 주성분 중복 체크' 기능(S)을 전면에 내세워 차별화",
                "• [모바일 퍼스트 반응형 웹 제공]",
                "  별도 앱 설치 없이 스마트폰 브라우저에서 즉시 알약을 식별하고",
                "  복약지도를 확인하는 모바일 웹 접근성 극대화"
            ]
        ),
        (
            "WO 전략 (약점보완 × 기회) : 기술적 캐싱 및 UX 고도화",
            C_TEAL,
            [
                "• [Django SQLite 로컬 캐싱으로 공공API 한계 극복]",
                "  공공API 속도 및 트래픽 한계(W)를 극복하기 위해 다빈도 의약품 및",
                "  낱알식별 데이터를 Django DB에 인덱싱하여 0.1초 고속 검색 구현",
                "• [초직관적 비주얼 필터 UI로 카메라 AI 부재 보완]",
                "  실제 색상 컬러칩(16색)과 모양 아이콘, 각인 입력창을 결합해",
                "  누구나 3번의 터치만으로 알약을 찾을 수 있도록 설계"
            ]
        ),
        (
            "ST 전략 (강점 × 위협대응) : 공신력 확보 및 법적 안전장치",
            C_PURPLE,
            [
                "• [100% 식약처 공식 데이터 출처 명시로 신뢰성 확보]",
                "  모든 검색 카드와 상세 모달에 식약처 3대 API 출처 배지와",
                "  품목기준코드(ITEM_SEQ)·허가일자를 투명하게 표기",
                "• [의료법 준수 안내 가이드라인 적용]",
                "  본 서비스는 의학적 진단을 대체하지 않으며 약사·의사 상담을",
                "  보조하는 공공데이터 안내 서비스임을 명확히 고지"
            ]
        ),
        (
            "WT 전략 (약점보완 × 위협대응) : 하이브리드 폴백 아키텍처",
            C_AMBER,
            [
                "• [Django 서버 + 클라이언트 Direct API 이중화 폴백 설계]",
                "  특정 API 응답 지연 시 나머지 API 및 로컬 캐시 DB 데이터로",
                "  서비스가 중단 없이 작동하는 무중단 폴백(Fallback) 구조 구현",
                "• [MVP 핵심 기능 집중을 통한 2차 과제 완벽 구현]",
                "  과도한 외부 유료 API를 배제하고 검증된 식약처 OpenAPI 3종과",
                "  Django 표준 스택에 집중하여 100% 작동 가능한 결과물 완성"
            ]
        ),
    ]

    for idx, (title, col, bullets) in enumerate(strategies):
        r = idx // 2
        c = idx % 2
        x = 0.6 + c * 6.15
        y = 1.8 + r * 2.65
        add_card_with_header(s7, x, y, 5.95, 2.48, title, bullets, header_bg=col, card_bg=C_WHITE, body_size=10.5)

    # =========================================================================
    # Slide 08: ③ STP 전략 (1/2) - Segmentation & Targeting
    # =========================================================================
    s8 = prs.slides.add_slide(blank_layout)
    add_header(s8, "03. STP 전략 (1/2)", "시장 세분화(Segmentation) 및 타겟 고객 선정(Targeting)", "의약품 정보 탐색 행동 패턴에 따른 시장 세분화 및 핵심 타겟 그룹 정의", 8)

    # 좌측: Segmentation
    add_card_with_header(
        s8, 0.6, 1.8, 5.8, 5.2,
        "1. 시장 세분화 (Market Segmentation)",
        [
            "① 복약 및 건강관리 상황 기준 세분화",
            "   • 그룹 A : 가정 내 상비약·일반의약품 위주 간헐적 복용층 (1인 가구·대학생)",
            "   • 그룹 B : 만성질환 처방약·다제 복용자 및 그 가족 케어층 (3040 직장인·주부)",
            "   • 그룹 C : 전문 의학/약학 학술 스펙 및 보험코드가 필요한 관련 전공 학생/종사자",
            "",
            "② 정보 탐색 니즈(Needs) 기준 세분화",
            "   • 외형 탐색형 : 약봉지를 분실해 알약의 모양·색상·각인으로 정체를 찾고자 함",
            "   • 증상·안심 탐색형 : 두통·소화불량 등 증상에 맞는 약과 쉬운 주의사항을 원함",
            "   • 복합 안전 관리형 : 여러 약을 함께 먹을 때 주성분 중복·상호작용을 체크하고 싶음",
            "",
            "③ 디지털 기기 활용 환경 기준",
            "   • 모바일 즉시 검색형 (약국 방문 전/가정 내 약통 앞에서 스마트폰으로 검색)",
            "   • PC 심층 비교형 (성분·허가정보·외형을 넓은 화면에서 꼼꼼히 대조)"
        ],
        header_bg=C_NAVY, body_size=10.5
    )

    # 우측: Targeting
    add_card_with_header(
        s8, 6.7, 1.8, 6.033, 5.2,
        "2. 타겟 고객 선정 (Target Audience)",
        [
            "🎯 1차 핵심 타겟 (Primary Target)",
            "   [상비약 오남용이 걱정되는 2030 1인 가구 대학생 및 사회초년생]",
            "   • 특징 : 집에 먹다 남은 처방약·상비약이 섞여 있으나 정확한 정보를 모름",
            "   • 핵심 페인포인트 : 약봉지를 버려 무슨 약인지 모르고, 진통제·감기약 교차",
            "     복용 시 성분이 겹치는지 모바일로 빠르게 확인하고 싶음",
            "",
            "🎯 2차 핵심 타겟 (Secondary Target)",
            "   [다제 복용 부모님·가족의 약을 챙기는 3040 케어기버(Caregiver)]",
            "   • 특징 : 부모님이 드시는 여러 전문의약품의 효능·부작용·보관법을",
            "     어려운 약학 용어 대신 쉬운 말로 확인하고 약통에 기록해 관리하고 싶음",
            "",
            "🎯 3차 확장 타겟 (Sub Target)",
            "   [의약품 허가 스펙·주성분·보험코드(EDI)를 빠르게 조회하려는 보건·약학 실습생]"
        ],
        header_bg=C_BLUE, body_size=10.5
    )

    # =========================================================================
    # Slide 09: ③ STP 전략 (2/2) - Positioning 전략
    # =========================================================================
    s9 = prs.slides.add_slide(blank_layout)
    add_header(s9, "03. STP 전략 (2/2)", "포지셔닝(Positioning) 맵 및 차별화 전략", "기존 서비스의 빈틈인 '높은 전문 데이터 신뢰성 + 누구나 이해하기 쉬운 직관적 UX' 영역 선점", 9)

    # 좌측 포지셔닝 맵 시각화 박스
    add_box(s9, 0.6, 1.8, 6.4, 5.2, bg_color=C_WHITE, border_color=C_BORDER)
    add_text(s9, 0.8, 1.95, 6.0, 0.35, "📊 의약품 정보 서비스 포지셔닝 맵 (Positioning Map)", font_size=13, bold=True, color=C_NAVY)

    # 십자 축 그리기
    v_axis = s9.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(3.8), Inches(2.5), Inches(0.03), Inches(4.1))
    v_axis.fill.solid()
    v_axis.fill.fore_color.rgb = C_MUTED
    v_axis.line.fill.background()

    h_axis = s9.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(1.0), Inches(4.55), Inches(5.6), Inches(0.03))
    h_axis.fill.solid()
    h_axis.fill.fore_color.rgb = C_MUTED
    h_axis.line.fill.background()

    add_text(s9, 2.8, 2.22, 2.0, 0.3, "▲ 데이터 깊이·전문성 높음\n(낱알식별+허가성분+복약정보)", font_size=9, bold=True, color=C_NAVY, align=PP_ALIGN.CENTER)
    add_text(s9, 2.8, 6.62, 2.0, 0.3, "▼ 단편적·요약 정보 위주", font_size=9, bold=True, color=C_MUTED, align=PP_ALIGN.CENTER)
    add_text(s9, 0.7, 4.35, 1.3, 0.4, "◀ 전문가 중심\n어려운 UI/용어", font_size=9, bold=True, color=C_MUTED, align=PP_ALIGN.LEFT)
    add_text(s9, 5.5, 4.35, 1.4, 0.4, "직관적 UX ▶\n모바일·쉬운 설명", font_size=9, bold=True, color=C_BLUE, align=PP_ALIGN.RIGHT)

    # 경쟁사 버블
    b1 = add_box(s9, 1.25, 2.85, 2.2, 0.9, bg_color=RGBColor(241, 245, 249), border_color=C_MUTED)
    add_text(s9, 1.25, 2.85, 2.2, 0.9, "의약품안전나라 / 약학정보원\n(정보는 방대하나 UI 복잡)", font_size=9.5, bold=True, color=C_TEXT, align=PP_ALIGN.CENTER, valign=MSO_ANCHOR.MIDDLE)

    b2 = add_box(s9, 1.35, 5.2, 2.0, 0.85, bg_color=RGBColor(241, 245, 249), border_color=C_MUTED)
    add_text(s9, 1.35, 5.2, 2.0, 0.85, "포털 블로그 / 커뮤니티\n(정확도·신뢰성 낮음)", font_size=9.5, bold=True, color=C_MUTED, align=PP_ALIGN.CENTER, valign=MSO_ANCHOR.MIDDLE)

    b3 = add_box(s9, 4.2, 5.15, 2.2, 0.9, bg_color=C_TEAL_LIGHT, border_color=C_TEAL)
    add_text(s9, 4.2, 5.15, 2.2, 0.9, "단순 e약은요 조회 웹\n(쉬우나 전문약·낱알식별 불가)", font_size=9.5, bold=True, color=C_TEAL, align=PP_ALIGN.CENTER, valign=MSO_ANCHOR.MIDDLE)

    # 우리 서비스 강조 버블 (1사분면)
    b_our = add_box(s9, 4.05, 2.7, 2.65, 1.35, bg_color=C_BLUE, border_color=C_NAVY, border_pt=2)
    add_text(s9, 4.05, 2.7, 2.65, 1.35, "💊 알약이가 (e-Drug Care)\n[식약처 3대 API 통합 +\n비주얼 낱알식별 + 내 약통]", font_size=11, bold=True, color=C_WHITE, align=PP_ALIGN.CENTER, valign=MSO_ANCHOR.MIDDLE)

    # 우측 포지셔닝 전략 설명
    add_card_with_header(
        s9, 7.25, 1.8, 5.48, 5.2,
        "🎯 핵심 포지셔닝 선언문 (Positioning Statement)",
        [
            "\"알약이가(e-Drug Care)는 약의 정체나 안전한 복용법이 궁금한",
            "일반 사용자들에게, 식약처 3대 공식 데이터를 하나로 결합하여",
            "가장 쉽고 빠르게 알약 식별부터 성분 중복 점검까지 해결해주는",
            "내 손안의 스마트 복약 안전 파트너입니다.\"",
            "",
            "1. [Easy & Deep] 쉬운 설명과 전문 스펙의 완벽한 공존",
            "   • 기본 화면은 비전공자 눈높이의 쉬운 복약 가이드(e약은요)를",
            "     제공하면서, 탭 전환만으로 주성분·허가코드·실측크기를 제공",
            "",
            "2. [Visual First] 텍스트 입력 없이도 찾는 비주얼 낱알 탐색",
            "   • 알약 모양·색상 컬러칩 선택만으로 즉시 식별 결과 도출",
            "",
            "3. [Actionable Care] 일회성 검색을 넘어선 '내 약통' 안전 관리",
            "   • 복용 약 저장 및 주성분 중복 자동 경고로 실질적 복약 사고 예방"
        ],
        header_bg=C_BLUE_DARK, body_size=10.5
    )

    # =========================================================================
    # Slide 10: ④ Persona (1/2) - 페르소나 1 (자취 대학생 김민지)
    # =========================================================================
    s10 = prs.slides.add_slide(blank_layout)
    add_header(s10, "04. 페르소나 (1/2)", "대표 사용자 페르소나 #1 : 자취 3년차 대학생 김민지", "상비약·처방약 낱알 식별과 진통제·감기약 중복 복용 여부가 궁금한 20대 1인 가구 사용자", 10)

    # 좌측 프로필 카드
    add_box(s10, 0.6, 1.8, 3.8, 5.2, bg_color=C_WHITE, border_color=C_BLUE, border_pt=1.5)
    avatar1 = add_box(s10, 1.6, 2.05, 1.8, 1.3, bg_color=C_BLUE_LIGHT, border_color=C_BLUE)
    add_text(s10, 1.6, 2.05, 1.8, 1.3, "👩‍🎓\nPersona #1", font_size=20, bold=True, color=C_BLUE, align=PP_ALIGN.CENTER, valign=MSO_ANCHOR.MIDDLE)
    add_text(s10, 0.8, 3.5, 3.4, 0.4, "김민지 (23세, 대학교 3학년)", font_size=15, bold=True, color=C_NAVY, align=PP_ALIGN.CENTER)
    add_text(
        s10, 0.85, 4.0, 3.3, 2.8,
        "• 거주 형태 : 학교 앞 원룸 1인 자취\n"
        "• 주 사용 기기 : 스마트폰(iOS) & 노트북\n"
        "• 복약 습관 : 두통약, 소화제, 생리통약,\n"
        "  예전에 처방받은 감기약을 한 약통에\n"
        "  모아서 보관함\n"
        "• 한줄 인용구 :\n"
        "  \"약봉지를 버려서 이 노란 알약이 뭔지\n"
        "   모르겠어요. 타이레놀이랑 같이 먹어도\n"
        "   성분이 안 겹치는지 바로 알고 싶어요!\"",
        font_size=10.5, color=C_TEXT
    )

    # 우측 상세 분석 카드 3개
    add_card_with_header(
        s10, 4.65, 1.8, 8.08, 1.62,
        "📌 현재 처한 상황 (Context & Scenario)",
        [
            "• 시험기간에 심한 두통과 몸살 기운이 와서 서랍 속 약통을 열었지만, 낱알 포장만 남은 분홍색·하얀색 알약이 무슨 약인지 기억나지 않음",
            "• 집에 있는 종합감기약과 진통제를 같이 먹으려는데, 뉴스에서 본 '아세트아미노펜 과다복용 간 독성' 기사가 떠올라 불안해짐"
        ],
        header_bg=C_NAVY, body_size=10.5
    )

    add_card_with_header(
        s10, 4.65, 3.58, 3.92, 3.42,
        "😣 겪고 있는 문제점 (Pain Points)",
        [
            "1. 알약 표면에 영문 각인('TYLENOL', 'DW')만 적혀",
            "   있어 일반 포털 검색으로는 약 이름을 찾기 힘듦",
            "2. 기존 약학 사이트는 모바일 화면이 너무 작고",
            "   전문 용어가 많아 읽다가 포기하게 됨",
            "3. 감기약과 진통제의 주성분이 겹치는지 일일이",
            "   성분표를 영어로 대조해보기가 번거로움"
        ],
        header_bg=C_RED, body_size=10.5
    )

    add_card_with_header(
        s10, 8.81, 3.58, 3.92, 3.42,
        "✨ 알약이가(e-Drug Care)를 통한 해결 (Needs & Gain)",
        [
            "1. [스마트 낱알 식별기]에서 '장방형 + 하양 + 각인'",
            "   선택만으로 3초 만에 정확한 알약 사진과 이름 확인",
            "2. [내 약통 담기] 기능으로 복용할 약 2개를 담자마자",
            "   '주성분(Acetaminophen) 중복 주의' 알림을 받아",
            "   안전하게 복용량 조절 성공",
            "3. 자주 먹는 상비약을 모바일에 저장해 언제든 열람"
        ],
        header_bg=C_BLUE, body_size=10.5
    )

    # =========================================================================
    # Slide 11: ④ Persona (2/2) - 페르소나 2 (부모님 약 챙기는 직장인 박성호)
    # =========================================================================
    s11 = prs.slides.add_slide(blank_layout)
    add_header(s11, "04. 페르소나 (2/2)", "대표 사용자 페르소나 #2 : 다제복용 부모님 케어 직장인 박성호", "전문의약품 허가정보와 어르신 눈높이 복약 안내·보관법을 함께 관리하려는 30대 사용자", 11)

    add_box(s11, 0.6, 1.8, 3.8, 5.2, bg_color=C_WHITE, border_color=C_TEAL, border_pt=1.5)
    avatar2 = add_box(s11, 1.6, 2.05, 1.8, 1.3, bg_color=C_TEAL_LIGHT, border_color=C_TEAL)
    add_text(s11, 1.6, 2.05, 1.8, 1.3, "👨‍💼\nPersona #2", font_size=20, bold=True, color=C_TEAL, align=PP_ALIGN.CENTER, valign=MSO_ANCHOR.MIDDLE)
    add_text(s11, 0.8, 3.5, 3.4, 0.4, "박성호 (34세, IT기업 직장인)", font_size=15, bold=True, color=C_NAVY, align=PP_ALIGN.CENTER)
    add_text(
        s11, 0.85, 4.0, 3.3, 2.8,
        "• 가족 상황 : 고혈압·고지혈증·위장약을\n"
        "  복용하시는 60대 부모님과 주말마다 왕래\n"
        "• 주 사용 기기 : 사무실 데스크톱 PC &\n"
        "  갤럭시 스마트폰\n"
        "• 한줄 인용구 :\n"
        "  \"부모님이 병원에서 받아오신 전문의약품이\n"
        "   5가지가 넘는데, 각 약의 정확한 성분과\n"
        "   피해야 할 음식·부작용을 한눈에 정리해\n"
        "   드리고 싶어요.\"",
        font_size=10.5, color=C_TEXT
    )

    add_card_with_header(
        s11, 4.65, 1.8, 8.08, 1.62,
        "📌 현재 처한 상황 (Context & Scenario)",
        [
            "• 부모님이 내과와 정형외과 두 곳에서 처방받은 약들을 드시는데, 어떤 약이 혈압약이고 어떤 약이 소염진통제인지 헷갈려 하심",
            "• 일반 'e약은요' 검색만으로는 부모님이 드시는 전문의약품(예: 노바스크, 리피토 등)이 검색되지 않는 경우가 많아 통합 조회가 필요함"
        ],
        header_bg=C_NAVY, body_size=10.5
    )

    add_card_with_header(
        s11, 4.65, 3.58, 3.92, 3.42,
        "😣 겪고 있는 문제점 (Pain Points)",
        [
            "1. 'e약은요'에는 일반의약품 위주로만 나와 있어",
            "   부모님이 처방받은 전문의약품 정보가 자주 누락됨",
            "2. 반대로 식약처 허가정보만 보면 효능·용법 문서가",
            "   어려운 전문 한자어/의학용어로 되어 있어 부모님께",
            "   설명해 드리기가 어려움",
            "3. 아침·저녁 복용 시간대별로 약을 기록해 둘 곳 부재"
        ],
        header_bg=C_AMBER, body_size=10.5
    )

    add_card_with_header(
        s11, 8.81, 3.58, 3.92, 3.42,
        "✨ 알약이가(e-Drug Care)를 통한 해결 (Needs & Gain)",
        [
            "1. [통합 스마트 검색]과 [허가·성분 전문조회]를 통해",
            "   e약은요에 없는 전문의약품도 식약처 허가 API 및",
            "   낱알식별 API와 결합해 빠짐없이 조회",
            "2. 부모님 약들을 [내 약통]에 '아침 식후 / 저녁 식후'",
            "   메모와 함께 등록하여 복약 스케줄과 주의사항을",
            "   체계적으로 관리"
        ],
        header_bg=C_TEAL, body_size=10.5
    )

    # =========================================================================
    # Slide 12: ⑤ Lean Canvas (1/2) - 9개 블록 비즈니스 모델 캔버스
    # =========================================================================
    s12 = prs.slides.add_slide(blank_layout)
    add_header(s12, "05. 린 캔버스 (1/2)", "Lean Canvas 비즈니스 모델 (9개 핵심 블록)", "기획한 서비스의 문제·해결책·가치제안·고객군·채널·수익원·비용구조·핵심지표·경쟁우위 구조화", 12)

    # 상단 5열 그리드 (높이 3.65) + 하단 2열 그리드 (높이 1.45)
    top_y = 1.78
    top_h = 3.62
    half_h = 1.77
    col_w = 2.426

    # 1. 문제 (Problem)
    add_card_with_header(
        s12, 0.6, top_y, col_w, top_h,
        "① 문제 (Problem)",
        [
            "1. 약봉지 분실 시 낱알의",
            "   정체를 알 수 없음",
            "2. e약은요(쉬운설명)와",
            "   허가/낱알정보(전문스펙)",
            "   데이터가 파편화됨",
            "3. 다제 복용 시 주성분",
            "   중복 및 병용금기 인지",
            "   어려움",
            "",
            "[기존 대안]",
            "• 포털 검색, 약학정보원"
        ],
        header_bg=C_RED, body_size=9.5
    )

    # 2. 해결책 (Solution) & 8. 핵심지표 (Key Metrics)
    add_card_with_header(
        s12, 0.6 + col_w, top_y, col_w, half_h,
        "④ 해결책 (Solution)",
        [
            "• 식약처 3대 API 통합검색",
            "• 모양·색상·각인 기반",
            "  비주얼 낱알 식별기",
            "• 내 약통 & 주성분 중복",
            "  자동 경고 리포트"
        ],
        header_bg=C_BLUE, body_size=9.5
    )
    add_card_with_header(
        s12, 0.6 + col_w, top_y + half_h + 0.08, col_w, half_h,
        "⑧ 핵심지표 (Key Metrics)",
        [
            "• 일/월간 검색 건수(SearchLog)",
            "• 낱알식별 매칭 성공률",
            "• 내 약통(SavedDrug) 등록 수",
            "• 중복성분 경고 확인 전환율",
            "• 재방문율(Retention)"
        ],
        header_bg=C_TEAL, body_size=9.5
    )

    # 3. 고유 가치제안 (UVP)
    add_card_with_header(
        s12, 0.6 + col_w * 2, top_y, col_w, top_h,
        "③ 고유 가치제안 (UVP)",
        [
            "\"이름 모를 알약 한 알부터",
            "내 약통 속 중복 성분까지,",
            "식약처 3대 공공데이터로",
            "3초 만에 해결하는 스마트",
            "복약 안전 웹 플랫폼\"",
            "",
            "[핵심 제공 가치]",
            "• 3-in-1 무누락 통합 정보",
            "• 약 이름 몰라도 찾는 외형검색",
            "• 주성분 중복 자동 브리핑",
            "• 앱 설치 없는 반응형 웹"
        ],
        header_bg=C_NAVY, card_bg=C_BLUE_LIGHT, body_size=9.5
    )

    # 4. 경쟁우위 (Unfair Advantage) & 5. 채널 (Channels)
    add_card_with_header(
        s12, 0.6 + col_w * 3, top_y, col_w, half_h,
        "⑨ 경쟁우위 (Advantage)",
        [
            "• ITEM_SEQ 기반 3대 식약처",
            "  API 실시간 병합 알고리즘",
            "• 공공API 한계를 해결한",
            "  Django SQLite 낱알 캐싱",
            "• 직관적 3-Tab 상세 모달 UX"
        ],
        header_bg=C_PURPLE, body_size=9.5
    )
    add_card_with_header(
        s12, 0.6 + col_w * 3, top_y + half_h + 0.08, col_w, half_h,
        "⑤ 채널 (Channels)",
        [
            "• PC/모바일 반응형 웹 배포",
            "• 대학교 에브리타임·자취생",
            "  커뮤니티 바이럴 확산",
            "• 검색엔진(SEO) 키워드 유입",
            "• 약국 복약지도 QR코드 연계"
        ],
        header_bg=C_AMBER, body_size=9.5
    )

    # 5. 고객군 (Customer Segments)
    add_card_with_header(
        s12, 0.6 + col_w * 4, top_y, col_w, top_h,
        "② 고객군 (Segments)",
        [
            "[핵심 타겟 고객]",
            "• 상비약·처방약을 보관하는",
            "  2030 1인 가구·대학생",
            "• 다제 복용 부모님 약을",
            "  관리하는 3040 케어기버",
            "",
            "[얼리어답터]",
            "• 셀프 메디케이션에 관심이",
            "  높고 모바일로 약 성분과",
            "  부작용을 꼼꼼히 확인하는",
            "  디지털 네이티브 세대"
        ],
        header_bg=C_BLUE_DARK, body_size=9.5
    )

    # 하단: 7. 비용구조 (Cost Structure) & 6. 수익원 (Revenue Streams)
    bot_y = 5.52
    bot_h = 1.55
    add_card_with_header(
        s12, 0.6, bot_y, 6.0, bot_h,
        "⑦ 비용 구조 (Cost Structure)",
        [
            "• 데이터 수집 비용 : 0원 (식약처 공공데이터포털 OpenAPI 3종 무료 활용)",
            "• 서버 및 DB 인프라 비용 : 초기 무료 클라우드 호스팅(PythonAnywhere / Render) 및 SQLite3 활용으로 최소 비용 운영",
            "• 개발 및 유지보수 : 조원 자체 프론트엔드/Django 백엔드 개발 및 공공API 스키마 모니터링"
        ],
        header_bg=C_NAVY, body_size=9.8
    )

    add_card_with_header(
        s12, 6.733, bot_y, 6.0, bot_h,
        "⑥ 수익원 (Revenue Streams - 확장 비즈니스 모델)",
        [
            "• B2C 프리미엄 구독 (Freemium) : 가족 복약 알림(카카오톡 알림톡 연동) 및 무제한 가족 약통 공유 서비스",
            "• 제휴 커머스 & 헬스케어 광고 : 복용 중인 약과 궁합이 맞는 건강기능식품·영양제 맞춤형 추천 제휴 수수료",
            "• B2B 약국/클리닉 위젯 제공 : 지역 약국 모바일 복약안내 페이지 SaaS 연동 모델"
        ],
        header_bg=C_TEAL, body_size=9.8
    )

    # =========================================================================
    # Slide 13: ⑤ Lean Canvas (2/2) - 비즈니스 선순환 구조 및 핵심 지표(KPI) 설계
    # =========================================================================
    s13 = prs.slides.add_slide(blank_layout)
    add_header(s13, "05. 린 캔버스 (2/2)", "비즈니스 선순환 구조 및 핵심성과지표(KPI) 설계", "공공데이터 무료 활용을 통한 저비용 고효율 구조와 데이터 축적에 따른 서비스 고도화 선순환", 13)

    flow_cards = [
        ("STEP 1. 유입 (Acquisition)", "이름 모를 알약 식별 또는\n증상·약 이름 검색으로\n모바일/PC 웹 유입", C_BLUE),
        ("STEP 2. 활성화 (Activation)", "3대 OpenAPI 통합 결과로\n외형·효능·성분을 한 번에\n해결하는 '아하 모먼트' 경험", C_TEAL),
        ("STEP 3. 유지 (Retention)", "복용 중인 약을 '내 약통'에\n등록하고 주성분 중복·병용\n안전 리포트를 수시 점검", C_PURPLE),
        ("STEP 4. 데이터 축적 & 수익화", "검색어 통계(SearchLog) 및\n낱알 캐시 DB 축적 → 맞춤형\n영양제/복약알림 수익 모델 확장", C_AMBER),
    ]
    for i, (st_title, st_desc, col) in enumerate(flow_cards):
        x = 0.6 + i * 3.1
        add_box(s13, x, 1.85, 2.85, 2.1, bg_color=C_WHITE, border_color=col, border_pt=2)
        add_box(s13, x, 1.85, 2.85, 0.45, bg_color=col, border_color=None)
        add_text(s13, x, 1.85, 2.85, 0.45, st_title, font_size=11.5, bold=True, color=C_WHITE, align=PP_ALIGN.CENTER, valign=MSO_ANCHOR.MIDDLE)
        add_text(s13, x + 0.15, 2.45, 2.55, 1.35, st_desc, font_size=11, bold=True, color=C_TEXT, align=PP_ALIGN.CENTER, valign=MSO_ANCHOR.MIDDLE)
        if i < 3:
            add_text(s13, x + 2.85, 2.65, 0.25, 0.5, "▶", font_size=16, bold=True, color=C_MUTED, align=PP_ALIGN.CENTER)

    add_card_with_header(
        s13, 0.6, 4.25, 12.133, 2.8,
        "📊 2차 과제(Django 백엔드 구현)와 직결되는 핵심지표(Key Metrics) 측정 설계",
        [
            "1. 검색 로그 분석 지표 (Django SearchLog 모델 연동)",
            "   • 사용자가 가장 많이 찾는 의약품 키워드 및 검색 유형(통합검색 vs 낱알식별 vs 허가조회)을 DB에 자동 집계하여 인기 검색어 제공",
            "2. 낱알 외형 식별 캐시 적중률 (Django PillCache 모델 연동)",
            "   • 식약처 낱알식별 API 호출 시마다 SQLite DB에 외형 정보를 자동 축적하여, 검색이 누적될수록 응답 속도가 기하급수적으로 향상되는 구조",
            "3. 내 약통 활성도 및 중복 성분 검출 건수 (Django SavedDrug 모델 연동)",
            "   • 사용자당 평균 등록 의약품 수 및 '주성분 중복 경고'를 통해 잠재적 오남용을 예방한 건수를 핵심 안전 지표로 측정"
        ],
        header_bg=C_NAVY, body_size=10.8
    )

    # =========================================================================
    # Slide 14: ⑥ Storyboard (1/6) - 전체 서비스 IA 및 화면 이동 흐름도
    # =========================================================================
    s14 = prs.slides.add_slide(blank_layout)
    add_header(s14, "06. 스토리보드 (1/6)", "전체 서비스 정보구조도(IA) 및 화면 이동 흐름(User Flow)", "MVP 핵심 기능을 중심으로 직관적인 4대 탭 네비게이션과 3-Tab 통합 상세 모달로 이어지는 화면 흐름", 14)

    # 상단 진입점
    add_box(s14, 4.4, 1.8, 4.5, 0.7, bg_color=C_NAVY, border_color=None)
    add_text(s14, 4.4, 1.8, 4.5, 0.7, "🏠 메인 웹 애플리케이션 진입 (PC 상단 GNB / 모바일 하단 탭바)\nDjango Backend 상태 체크 (/api/status/) & 대표 상비약 초기 브리핑", font_size=10.5, bold=True, color=C_WHITE, align=PP_ALIGN.CENTER, valign=MSO_ANCHOR.MIDDLE)

    # 4개 메인 탭 화면 박스
    tabs_ia = [
        ("화면 #1 [탭 1]\n🔍 통합 스마트 검색", "• 약 이름 / 증상·효능 / 제약사 선택\n• 추천 키워드 해시태그 원클릭\n• 식약처 3대 API 실시간 병렬 호출\n• 3대 API 매칭 건수 요약 배너\n• 통합 의약품 카드 그리드 출력", C_BLUE),
        ("화면 #2 [탭 2]\n💊 스마트 낱알 식별기", "• 각인 문자(앞/뒤) 입력\n• 알약 모양(10종 도형칩) 선택\n• 알약 색상(16종 컬러칩) 선택\n• 제형(정제/캡슐) & 분할선 선택\n• 외형 일치 알약 카드 리스트 출력", C_TEAL),
        ("화면 #3 [탭 3]\n📋 허가·성분 전문조회", "• 전체 / 일반의약품 / 전문의약품 필터\n• 품목명 검색 (DrugPrdtPrmsnInfo)\n• 영문/한글 주성분명 및 약효분류\n• 품목허가일·보험코드(EDI) 표시\n• 전문 의약품 스펙 카드 출력", C_PURPLE),
        ("화면 #5 [탭 4]\n🧰 내 약통 & 안전리포트", "• 저장된 복용 의약품 목록 조회\n• 주성분(Active Ingredient) 교차분석\n• 중복 성분 발견 시 적색 경고 배너\n• 복용 시간대(아침/저녁) 메모 관리\n• 약통 품목 원클릭 추가/삭제", C_AMBER),
    ]
    for i, (t_head, t_body, col) in enumerate(tabs_ia):
        x = 0.6 + i * 3.1
        add_card_with_header(s14, x, 2.75, 2.85, 2.65, t_head, t_body, header_bg=col, body_size=9.8)

    # 하단 공통 모달 연결 박스
    add_box(s14, 0.6, 5.65, 12.133, 1.4, bg_color=C_BLUE_LIGHT, border_color=C_BLUE, border_pt=2)
    add_text(
        s14, 0.85, 5.75, 11.6, 1.2,
        "🔗 화면 #4 [공통 상세 모달 팝업] 3-in-1 통합 상세 정보 뷰 (/api/drug-detail/ 연동)\n"
        "• 어느 탭에서든 의약품 카드를 클릭하면 모달 팝업이 열리며, 해당 약품의 품목기준코드(ITEM_SEQ)로 3대 API 상세 데이터를 실시간 보강 조회\n"
        "• 모달 내부 3대 서브탭 : [서브탭 1: 📖 쉬운 복약가이드(e약은요)] ↔ [서브탭 2: 🔎 낱알 외형·식별 스펙] ↔ [서브탭 3: 🧪 성분·허가 상세 스펙]\n"
        "• 모달 상단 [+ 내 약통에 추가하기] 버튼 클릭 시 복용 시간대 메모 입력 후 [화면 #5 내 약통] DB에 즉시 저장 및 중복 성분 재계산!",
        font_size=10.5, bold=True, color=C_NAVY
    )

    # =========================================================================
    # Slide 15: ⑥ Storyboard (2/6) - 화면 #1: 메인 & 3대 API 통합 스마트 검색
    # =========================================================================
    s15 = prs.slides.add_slide(blank_layout)
    add_header(s15, "06. 스토리보드 (2/6)", "Storyboard #1 : 메인 대시보드 & 3-in-1 통합 스마트 검색 화면", "단 한 번의 검색으로 식약처 3대 OpenAPI(e약은요·낱알식별·제품허가) 결과를 병합하여 보여주는 메인 화면", 15)

    # 좌측 UI 와이어프레임 목업 (0.6 ~ 8.1)
    add_box(s15, 0.6, 1.75, 7.6, 5.3, bg_color=C_WHITE, border_color=C_NAVY, border_pt=1.5)
    # 브라우저 상단바
    add_box(s15, 0.6, 1.75, 7.6, 0.42, bg_color=C_NAVY, border_color=None, shape_type=MSO_SHAPE.RECTANGLE)
    add_text(s15, 0.75, 1.75, 7.3, 0.42, "💊 알약이가 e-Drug Care   [🟢 Django+SQLite]     [🔍통합검색] [💊낱알식별] [📋허가조회] [🧰내 약통(2)]", font_size=9.5, bold=True, color=C_WHITE, valign=MSO_ANCHOR.MIDDLE)

    # 히어로 검색 영역 목업
    add_box(s15, 0.85, 2.3, 7.1, 1.45, bg_color=C_BLUE_LIGHT, border_color=C_BLUE)
    add_text(s15, 1.05, 2.38, 6.7, 0.35, "궁금한 약 이름이나 증상을 검색해보세요 (3-in-1 Hybrid Search)", font_size=11, bold=True, color=C_NAVY)
    # 검색바 목업
    add_box(s15, 1.05, 2.78, 6.7, 0.45, bg_color=C_WHITE, border_color=C_BLUE, border_pt=1.5)
    add_text(s15, 1.15, 2.78, 6.5, 0.45, "[약 이름(품목명) ▼]  |  타이레놀                                              [ 통합 검색 ]", font_size=10, bold=True, color=C_BLUE_DARK, valign=MSO_ANCHOR.MIDDLE)
    add_text(s15, 1.05, 3.32, 6.7, 0.3, "추천 검색 :  [#타이레놀]  [#게보린]  [#아스피린]  [#베아제]  [🩺증상:두통]  [🩺증상:소화불량]", font_size=8.8, bold=True, color=C_TEAL)

    # 통계 배너 목업
    add_box(s15, 0.85, 3.88, 7.1, 0.44, bg_color=RGBColor(241, 245, 249), border_color=C_BORDER)
    add_text(s15, 0.95, 3.88, 6.9, 0.44, "📊 통합 매칭 결과: 14건   |   e약은요: 8건   |   낱알식별 외형: 4건   |   제품허가정보: 7건", font_size=9.5, bold=True, color=C_NAVY, align=PP_ALIGN.CENTER, valign=MSO_ANCHOR.MIDDLE)

    # 결과 카드 3개 목업
    for c_i in range(3):
        cx = 0.85 + c_i * 2.42
        add_box(s15, cx, 4.45, 2.26, 2.4, bg_color=C_WHITE, border_color=C_BORDER)
        add_box(s15, cx + 0.1, 4.55, 2.06, 0.8, bg_color=RGBColor(241, 245, 249), border_color=None)
        add_text(s15, cx + 0.1, 4.55, 2.06, 0.8, "[일반] [e약은요·낱알·허가]\n💊 실물 알약 이미지", font_size=8.5, bold=True, color=C_BLUE, align=PP_ALIGN.CENTER, valign=MSO_ANCHOR.MIDDLE)
        add_text(
            s15, cx + 0.1, 5.42, 2.06, 1.35,
            f"한국존슨앤드존슨 · #20210{c_i}\n타이레놀정500mg\n[장방형] [하양] [각인:TYLENOL]\n감기로 인한 발열 및 동통...\n[상세보기 →]  [+ 내 약통 담기]",
            font_size=8.2, color=C_TEXT
        )

    # 우측 기능 명세
    add_card_with_header(
        s15, 8.4, 1.75, 4.333, 5.3,
        "📋 화면 #1 주요 기능 및 동작 명세",
        [
            "1. 다중 검색 조건 지원",
            "   • 품목명(약 이름), 증상·효능(두통, 기침 등),",
            "     제약사명 3가지 모드로 선택 검색 가능",
            "   • 원클릭 추천 키워드 및 증상 태그 제공",
            "",
            "2. 백엔드 3대 API 병렬 교차 매칭",
            "   • GET /api/unified-search/ 호출",
            "   • Django ThreadPoolExecutor로 식약처 3대",
            "     API를 동시 호출 후 ITEM_SEQ 기준 병합",
            "",
            "3. 통합 매칭 현황 대시보드 바",
            "   • 각 API별 조회 건수와 최종 병합된 고유",
            "     의약품 건수를 투명하게 시각화",
            "",
            "4. 화면 간 이동 흐름 (Navigation)",
            "   • 카드 본문 클릭 → [화면 #4 상세 모달] 오픈",
            "   • [+ 내 약통 담기] 클릭 → 복용시간 입력 후",
            "     [화면 #5 내 약통]에 즉시 저장"
        ],
        header_bg=C_BLUE, body_size=10
    )

    # =========================================================================
    # Slide 16: ⑥ Storyboard (3/6) - 화면 #2: 스마트 낱알 식별기 화면
    # =========================================================================
    s16 = prs.slides.add_slide(blank_layout)
    add_header(s16, "06. 스토리보드 (3/6)", "Storyboard #2 : 스마트 낱알 식별기 (Visual Pill Identifier)", "약 이름을 몰라도 알약의 각인·모양·색상·제형·분할선을 선택해 정체를 찾는 핵심 특화 화면", 16)

    # 좌측 와이어프레임 목업
    add_box(s16, 0.6, 1.75, 7.6, 5.3, bg_color=C_WHITE, border_color=C_TEAL, border_pt=1.5)
    add_box(s16, 0.6, 1.75, 7.6, 0.42, bg_color=C_TEAL, border_color=None, shape_type=MSO_SHAPE.RECTANGLE)
    add_text(s16, 0.75, 1.75, 7.3, 0.42, "💊 스마트 낱알 식별기 (MdcinGrnIdntfcInfoService03 + Django SQLite PillCache)", font_size=10, bold=True, color=C_WHITE, valign=MSO_ANCHOR.MIDDLE)

    # 필터 영역 목업
    add_box(s16, 0.85, 2.3, 7.1, 2.65, bg_color=C_TEAL_LIGHT, border_color=C_TEAL)
    add_text(
        s16, 1.0, 2.38, 6.8, 2.5,
        "🔤 알약 각인 문자 입력 : [ TYLENOL / YH / 80 ...      ]   🏷️ 보조 키워드 : [ 선택 입력          ]\n"
        "1. 모양 선택 : [전체] [⚪원형] [🥚타원형] [💊장방형(선택됨)] [🛑팔각형] [⬢육각형] [🔺삼각형]\n"
        "2. 색상 선택 : [전체] [⚪하양(선택됨)] [🟡노랑] [🟠주황] [🩷분홍] [🔴빨강] [🟢초록] [🔵파랑] ...\n"
        "3. 제형 구분 : [전체] [정제(알약)] [경질캡슐] [연질캡슐]   |   4. 분할선 : [전체] [없음] [(-)형] [(+)형]\n"
        "┌──────────────────────────────────────────────────────────────┐\n"
        "│              🔎 선택한 외형 조건으로 알약 식별하기 (0.1초 탐색)              │\n"
        "└──────────────────────────────────────────────────────────────┘",
        font_size=9.3, bold=True, color=C_NAVY
    )

    # 하단 식별 결과 카드 목업
    for c_i in range(2):
        cx = 0.85 + c_i * 3.6
        add_box(s16, cx, 5.1, 3.45, 1.75, bg_color=C_WHITE, border_color=C_BORDER)
        add_text(
            s16, cx + 0.15, 5.2, 3.15, 1.55,
            f"📷 [실물 고화질 낱알 사진]   [전문의약품 / 낱알식별]\n"
            f"품목명 : 타이레놀8시간이알서방정 (#202200{c_i})\n"
            f"외형칩 : [장방형]  [하양]  [앞각인: TYLENOL]  [뒤각인: ER]\n"
            f"크기 : 장축 19.1mm × 단축 8.1mm × 두께 6.1mm",
            font_size=9, color=C_TEXT
        )

    # 우측 명세
    add_card_with_header(
        s16, 8.4, 1.75, 4.333, 5.3,
        "📋 화면 #2 주요 기능 및 기술적 특징",
        [
            "1. 시각적 다중 필터 인터페이스",
            "   • 각인 문자(앞/뒤), 알약 모양(10종),",
            "     색상 컬러칩(16종), 제형(4종), 분할선(4종)",
            "     조합 검색 지원 및 [필터 초기화] 제공",
            "",
            "2. 공공API 한계를 해결한 백엔드 로직",
            "   • GET /api/grain-search/ 엔드포인트",
            "   • 식약처 낱알식별 API는 약 이름 없이",
            "     모양/색상만으로는 검색이 불가한 한계 존재",
            "   • 이를 해결하기 위해 Django PillCache 모델에",
            "     다빈도 의약품 외형 정보를 인덱싱하여",
            "     약 이름을 몰라도 외형만으로 즉시 매칭!",
            "",
            "3. 실물 이미지 폴백 그래픽 제공",
            "   • 만약 공공데이터에 이미지가 없는 품목도",
            "     각인 문자와 모양/색상 배지를 그래픽으로",
            "     시각화하여 식별 편의성 보장"
        ],
        header_bg=C_TEAL, body_size=10
    )

    # =========================================================================
    # Slide 17: ⑥ Storyboard (4/6) - 화면 #3: 의약품 제품 허가·성분 전문 조회
    # =========================================================================
    s17 = prs.slides.add_slide(blank_layout)
    add_header(s17, "06. 스토리보드 (4/6)", "Storyboard #3 : 의약품 제품 허가·주성분 전문 조회 화면", "전문의약품·일반의약품 구분 필터링 및 주성분(영문/한글)·유효기간·보험코드(EDI) 전문 스펙 조회", 17)

    # 좌측 와이어프레임 목업
    add_box(s17, 0.6, 1.75, 7.6, 5.3, bg_color=C_WHITE, border_color=C_PURPLE, border_pt=1.5)
    add_box(s17, 0.6, 1.75, 7.6, 0.42, bg_color=C_PURPLE, border_color=None, shape_type=MSO_SHAPE.RECTANGLE)
    add_text(s17, 0.75, 1.75, 7.3, 0.42, "📋 식약처 의약품 제품 허가·성분 전문 조회 (DrugPrdtPrmsnInfoService08)", font_size=10, bold=True, color=C_WHITE, valign=MSO_ANCHOR.MIDDLE)

    add_box(s17, 0.85, 2.3, 7.1, 1.15, bg_color=C_PURPLE_LIGHT, border_color=C_PURPLE)
    add_text(s17, 1.0, 2.4, 6.8, 0.35, "전문의약품·일반의약품 구분 및 주성분·약효분류·허가일자 공식 스펙 조회", font_size=10.5, bold=True, color=C_NAVY)
    add_box(s17, 1.0, 2.82, 6.8, 0.45, bg_color=C_WHITE, border_color=C_PURPLE)
    add_text(s17, 1.1, 2.82, 6.6, 0.45, "[전문의약품 ▼]  |  아모디핀 / 리피토 / 아스피린                        [ 허가정보 조회 ]", font_size=9.8, bold=True, color=C_PURPLE, valign=MSO_ANCHOR.MIDDLE)

    add_text(s17, 0.85, 3.58, 7.1, 0.3, "식약처 허가 DB 총 42,704건 중 조건 일치 상위 품목 표시", font_size=9.5, bold=True, color=C_PURPLE, align=PP_ALIGN.CENTER)

    for c_i in range(2):
        cx = 0.85 + c_i * 3.6
        add_box(s17, cx, 3.95, 3.45, 2.9, bg_color=C_WHITE, border_color=C_BORDER)
        add_box(s17, cx + 0.12, 4.08, 3.2, 0.38, bg_color=C_PURPLE_LIGHT, border_color=None)
        add_text(s17, cx + 0.18, 4.08, 3.1, 0.38, "[전문의약품]  [✔ 허가정보 API]  정상 품목", font_size=9, bold=True, color=C_PURPLE, valign=MSO_ANCHOR.MIDDLE)
        add_text(
            s17, cx + 0.15, 4.55, 3.15, 2.2,
            f"품목명 : 아모디핀정5밀리그램 (#2004018{c_i})\n"
            f"영문명 : Amodipin Tab. 5mg\n"
            f"제조사 : 한미약품(주)\n"
            f"약효분류 : [02140] 혈압강하제\n"
            f"주성분 : Amlodipine Camsylate (암로디핀)\n"
            f"품목허가일 : 2004-05-29  |  EDI : 643501710\n"
            f"[상세 허가스펙·첨부문서 보기 →]  [+ 내 약통]",
            font_size=9, color=C_TEXT
        )

    add_card_with_header(
        s17, 8.4, 1.75, 4.333, 5.3,
        "📋 화면 #3 주요 기능 및 동작 명세",
        [
            "1. 전문의약품 vs 일반의약품 필터링",
            "   • e약은요 API만으로는 조회가 불가능했던",
            "     42,700여 건의 식약처 전체 허가 의약품",
            "     (전문의약품 포함)을 빠짐없이 검색 지원",
            "",
            "2. 주성분(Active Ingredient) 투명 공개",
            "   • 영문/한글 주성분명(ITEM_INGR_NAME)과",
            "     성분 개수, 식약처 약효분류 번호(예: [02140]",
            "     혈압강하제, [01140] 해열진통소염제) 제공",
            "",
            "3. 허가 상세 API 2단계 연동",
            "   • 목록 조회(getDrugPrdtPrmsnInq08) 후",
            "     카드 클릭 시 상세 조회(getDrugPrdtPrmsnDtlInq08)",
            "     API를 호출하여 유효기간(VALID_TERM),",
            "     저장방법(STORAGE_METHOD), 원료분량,",
            "     표준바코드까지 완벽하게 브리핑"
        ],
        header_bg=C_PURPLE, body_size=10
    )

    # =========================================================================
    # Slide 18: ⑥ Storyboard (5/6) - 화면 #4: 3-Tab 통합 상세 모달 팝업
    # =========================================================================
    s18 = prs.slides.add_slide(blank_layout)
    add_header(s18, "06. 스토리보드 (5/6)", "Storyboard #4 : 3-in-1 통합 상세 모달 팝업 화면", "하나의 모달 안에서 [쉬운 복약가이드] · [낱알 외형스펙] · [성분·허가 상세] 3대 탭을 전환하며 열람", 18)

    # 좌측 모달 와이어프레임
    add_box(s18, 0.6, 1.75, 7.6, 5.3, bg_color=RGBColor(226, 232, 240), border_color=C_NAVY, border_pt=1.5)
    modal_box = add_box(s18, 0.95, 1.95, 6.9, 4.9, bg_color=C_WHITE, border_color=C_BLUE, border_pt=2)

    # 모달 상단 헤더
    add_box(s18, 1.15, 2.12, 1.8, 1.15, bg_color=RGBColor(241, 245, 249), border_color=C_BORDER)
    add_text(s18, 1.15, 2.12, 1.8, 1.15, "💊 고화질 낱알\n실물 이미지\n(앞/뒤 표시)", font_size=9, bold=True, color=C_BLUE, align=PP_ALIGN.CENTER, valign=MSO_ANCHOR.MIDDLE)

    add_text(
        s18, 3.1, 2.1, 4.5, 1.2,
        "[일반의약품]  [✔ e약은요 API]  [✔ 낱알식별 API]  [✔ 허가정보 API]      [✕]\n"
        "타이레놀정500밀리그람 (아세트아미노펜)\n"
        "제조사: 한국존슨앤드존슨  |  품목기준코드: 202106092\n"
        "[ 🧰 내 약통에 추가하기 (복용시간대·메모 등록) ]",
        font_size=9.2, bold=True, color=C_NAVY
    )

    # 모달 내부 3대 서브탭 바
    add_box(s18, 1.15, 3.4, 6.5, 0.42, bg_color=RGBColor(241, 245, 249), border_color=C_BORDER)
    add_box(s18, 1.2, 3.44, 2.15, 0.34, bg_color=C_BLUE, border_color=None)
    add_text(s18, 1.2, 3.44, 2.15, 0.34, "📖 쉬운 복약가이드", font_size=9, bold=True, color=C_WHITE, align=PP_ALIGN.CENTER, valign=MSO_ANCHOR.MIDDLE)
    add_text(s18, 3.4, 3.44, 2.1, 0.34, "🔎 낱알 외형·식별 정보", font_size=9, bold=True, color=C_TEXT, align=PP_ALIGN.CENTER, valign=MSO_ANCHOR.MIDDLE)
    add_text(s18, 5.5, 3.44, 2.1, 0.34, "🧪 성분·허가 전문 스펙", font_size=9, bold=True, color=C_TEXT, align=PP_ALIGN.CENTER, valign=MSO_ANCHOR.MIDDLE)

    # 모달 본문 3열 프리뷰 (각 서브탭 핵심 내용 요약)
    sub_previews = [
        ("서브탭 1: e약은요", "• 📌 효능·효과 (감기 발열, 두통)\n• 📌 용법·용량 (1회 1~2정)\n• 🚨 복용 전 필수 경고(적색)\n• 💊 병용주의 약·음식\n• 📦 가정 내 보관법", C_BLUE_LIGHT),
        ("서브탭 2: 낱알 외형", "• 성상: 흰색의 장방형 필름코팅정\n• 모양/색상: 장방형 / 하양\n• 앞/뒤 각인: TYLENOL / 500\n• 분할선: 없음\n• 크기: 17.5 × 7.0 × 5.6 mm", C_TEAL_LIGHT),
        ("서브탭 3: 허가·성분", "• 주성분: Acetaminophen 500mg\n• 약효분류: 해열·진통·소염제\n• 유효기간: 제조일로부터 36개월\n• 저장방법: 기밀용기, 실온보관\n• 표준바코드 & EDI 코드", C_PURPLE_LIGHT),
    ]
    for idx, (st, sb, bgc) in enumerate(sub_previews):
        sx = 1.15 + idx * 2.2
        add_box(s18, sx, 3.92, 2.1, 2.75, bg_color=bgc, border_color=C_BORDER)
        add_text(s18, sx + 0.08, 4.0, 1.94, 0.3, st, font_size=9.5, bold=True, color=C_NAVY)
        add_text(s18, sx + 0.08, 4.32, 1.94, 2.3, sb, font_size=8.5, color=C_TEXT)

    # 우측 설명
    add_card_with_header(
        s18, 8.4, 1.75, 4.333, 5.3,
        "📋 화면 #4 주요 기능 및 UX 설계 포인트",
        [
            "1. 실시간 3대 API 상세 교차 보강",
            "   • 카드 클릭 시 GET /api/drug-detail/ 호출",
            "   • e약은요 + 낱알식별 + 허가목록 + 허가상세",
            "     (getDrugPrdtPrmsnDtlInq08) 4개 오퍼레이션을",
            "     동시 조회하여 빈틈없는 상세 정보 완성",
            "",
            "2. 정보 과부하를 막는 3-Tab 구조",
            "   • 한 화면에 너무 긴 텍스트를 나열하는 대신,",
            "     사용자의 관심사에 따라 [쉬운 복약법],",
            "     [알약 외형 치수], [주성분·허가 스펙]을",
            "     탭으로 깔끔하게 분리",
            "",
            "3. 경고 정보 시각적 하이라이팅",
            "   • 복용 전 필수 경고(atpnWarnQesitm)는",
            "     적색 박스(#FEF2F2)로 최상단에 강조 배치",
            "   • 모바일에서는 화면 하단에서 올라오는",
            "     바텀시트(Bottom-Sheet) 모달로 동작"
        ],
        header_bg=C_NAVY, body_size=10
    )

    # =========================================================================
    # Slide 19: ⑥ Storyboard (6/6) - 화면 #5: 내 약통 & PC/모바일 반응형 설계
    # =========================================================================
    s19 = prs.slides.add_slide(blank_layout)
    add_header(s19, "06. 스토리보드 (6/6)", "Storyboard #5 : 내 약통(복약 수첩) & 모바일 반응형 화면 설계", "Django SQLite DB(SavedDrug) 연동 복약 관리, 주성분 중복 경고 리포트 및 모바일 최적화 UI", 19)

    # 좌측: 내 약통 화면 목업
    add_box(s19, 0.6, 1.75, 5.2, 5.3, bg_color=C_WHITE, border_color=C_AMBER, border_pt=1.5)
    add_box(s19, 0.6, 1.75, 5.2, 0.42, bg_color=C_AMBER, border_color=None, shape_type=MSO_SHAPE.RECTANGLE)
    add_text(s19, 0.75, 1.75, 4.9, 0.42, "🧰 화면 #5 : 내 약통 & 주성분 중복·병용 안전 리포트", font_size=10, bold=True, color=C_WHITE, valign=MSO_ANCHOR.MIDDLE)

    # 경고 배너 목업
    add_box(s19, 0.8, 2.3, 4.8, 1.35, bg_color=C_RED_LIGHT, border_color=C_RED, border_pt=1.5)
    add_text(
        s19, 0.92, 2.38, 4.56, 1.2,
        "🚨 주성분 중복 복용 주의 : [Acetaminophen (아세트아미노펜)]\n"
        "현재 내 약통에 담긴 '타이레놀정500mg', '판콜에이내복액'에 동일한\n"
        "주성분이 포함되어 있습니다! 과량 복용 위험이 있으니 주의하세요.",
        font_size=9.2, bold=True, color=C_RED
    )

    # 저장된 약 카드 2개
    for idx, (dn, dt, ing) in enumerate([
        ("타이레놀정500밀리그람", "🕒 아침·저녁 식후 30분 (두통 시)", "주성분: Acetaminophen"),
        ("판콜에이내복액", "🕒 취침 전 복용 (초기 감기)", "주성분: Acetaminophen / Caffeine...")
    ]):
        cy = 3.82 + idx * 1.5
        add_box(s19, 0.8, cy, 4.8, 1.35, bg_color=RGBColor(248, 250, 252), border_color=C_BORDER)
        add_text(
            s19, 0.95, cy + 0.1, 4.5, 1.15,
            f"💊 {dn}   [약통에서 삭제]\n"
            f"   {ing}\n"
            f"   복용 메모 : {dt}",
            font_size=9.5, bold=True, color=C_TEXT
        )

    # 중앙: 모바일 뷰포트 목업 (375px 스마트폰 프레임)
    add_box(s19, 6.05, 1.75, 2.8, 5.3, bg_color=C_NAVY, border_color=C_NAVY, border_pt=2)
    add_box(s19, 6.18, 2.0, 2.54, 4.45, bg_color=C_BG, border_color=None, shape_type=MSO_SHAPE.RECTANGLE)
    add_text(s19, 6.18, 1.77, 2.54, 0.22, "📱 Mobile Responsive (375px)", font_size=8.5, bold=True, color=C_WHITE, align=PP_ALIGN.CENTER)
    add_text(
        s19, 6.26, 2.08, 2.38, 3.8,
        "💊 알약이가 e-Drug Care\n"
        "───────────────────\n"
        "[약 이름 ▼]\n"
        "[ 검색어 입력...              ]\n"
        "[         통합 검색         ]\n"
        "───────────────────\n"
        "┌─────────────────┐\n"
        "│ 📷 실물 알약 사진    │\n"
        "│ 타이레놀정 500mg     │\n"
        "│ [장방형][하양][TYLENOL]│\n"
        "│ [+ 내 약통 담기]     │\n"
        "└─────────────────┘",
        font_size=8.5, bold=True, color=C_TEXT
    )
    # 모바일 하단 네비게이션 바
    add_box(s19, 6.18, 6.45, 2.54, 0.48, bg_color=C_WHITE, border_color=C_BORDER, shape_type=MSO_SHAPE.RECTANGLE)
    add_text(s19, 6.18, 6.45, 2.54, 0.48, "🔍검색   💊식별   📋허가   🧰약통", font_size=8.5, bold=True, color=C_BLUE, align=PP_ALIGN.CENTER, valign=MSO_ANCHOR.MIDDLE)

    # 우측 명세
    add_card_with_header(
        s19, 9.1, 1.75, 3.633, 5.3,
        "📋 내 약통 & 반응형 동작 명세",
        [
            "1. Django SavedDrug CRUD 연동",
            "   • POST / GET / DELETE /api/pillbox/",
            "   • 복용 중인 약품 등록, 복용 시간대",
            "     메모 저장 및 삭제 지원",
            "",
            "2. 주성분 중복 자동 검출 알고리즘",
            "   • 약통에 담긴 모든 약품의 주성분",
            "     (ITEM_INGR_NAME)을 파싱하여",
            "     2개 이상 겹치는 성분이 있으면",
            "     상단에 즉시 경고 배너 렌더링",
            "",
            "3. PC · 모바일 완벽 반응형 UI",
            "   • PC (>900px) : 상단 GNB 탭 +",
            "     다단 그리드 카드 레이아웃",
            "   • Mobile (≤900px) : 엄지손가락",
            "     조작에 최적화된 하단 고정 탭바",
            "     (Bottom Nav) & 바텀시트 모달"
        ],
        header_bg=C_NAVY, body_size=9.8
    )

    # =========================================================================
    # Slide 20: 2차 과제 구현 아키텍처 & 결론 (Django + OpenAPI 3종)
    # =========================================================================
    s20 = prs.slides.add_slide(blank_layout)
    add_header(s20, "07. 2차 과제 구현 아키텍처", "2차 과제(Frontend + Django Backend) 시스템 아키텍처 및 결론", "기획을 넘어 실제 작동하는 Python Django 6.1 + SQLite3 + 식약처 3대 OpenAPI 프로토타입 구현 완료", 20)

    # 3단 아키텍처 다이어그램
    arch_cols = [
        (
            "1. Client Layer (PC & Mobile Web)",
            C_BLUE,
            [
                "• HTML5 시맨틱 마크업 (index.html)",
                "• CSS3 반응형 그리드 & 모바일 하단 네비게이션 (style.css)",
                "• Vanilla JS 비동기 컨트롤러 (app.js)",
                "  - 4대 메인 탭 & 3-Tab 상세 모달",
                "  - 16색 컬러칩 & 도형 낱알 필터 UI",
                "  - Django API 우선 연동 + 정적 호스팅(GitHub Pages) 자동 폴백 지원"
            ]
        ),
        (
            "2. Backend & DB Layer (Python Django)",
            C_NAVY,
            [
                "• Python Django 6.1 프레임워크",
                "  - config/ (settings.py, urls.py)",
                "  - drugs/ (models.py, views.py, services.py)",
                "• ThreadPoolExecutor 병렬 API 엔진",
                "  - 3대 식약처 API 동시 호출 및 ITEM_SEQ 기준 정규화·병합",
                "• SQLite3 데이터베이스 (db.sqlite3)",
                "  - PillCache : 낱알 외형 고속 인덱싱",
                "  - SavedDrug : 내 약통 & 중복성분 분석",
                "  - SearchLog : 실시간 인기 검색어 집계"
            ]
        ),
        (
            "3. External Data Layer (식약처 OpenAPI)",
            C_TEAL,
            [
                "• [API 1] 의약품 낱알식별 정보",
                "  MdcinGrnIdntfcInfoService03",
                "  (외형, 모양, 색상, 앞/뒤 각인, 치수)",
                "",
                "• [API 2] 의약품 제품 허가정보",
                "  DrugPrdtPrmsnInfoService08",
                "  (전문/일반 구분, 주성분, 유효기간)",
                "",
                "• [API 3] 의약품개요정보 (e약은요)",
                "  DrbEasyDrugInfoService",
                "  (효능, 용법, 경고, 병용금기, 부작용)"
            ]
        ),
    ]

    for i, (a_title, col, a_lines) in enumerate(arch_cols):
        x = 0.6 + i * 4.12
        add_card_with_header(s20, x, 1.8, 3.9, 3.85, a_title, a_lines, header_bg=col, body_size=10)

    # 하단 평가기준 부합 요약 배너
    add_box(s20, 0.6, 5.82, 12.133, 1.25, bg_color=C_NAVY, border_color=C_BLUE, border_pt=1.5)
    add_text(
        s20, 0.85, 5.9, 11.6, 1.1,
        "✅ 평가 기준 5대 항목 완벽 충족 및 구현 완료\n"
        "• [문제정의·차별성] 3대 API 통합 & 외형 캐싱 식별  |  [타겟·사용자이해] STP & 2인의 구체적 페르소나  |  [비즈니스구조] Lean Canvas 9블록\n"
        "• [스토리보드 완성도] MVP 5대 화면 상세 와이어프레임  |  [2차 과제 구현 가능성] 실제 작동하는 Django 백엔드 + 반응형 프론트엔드 구축 완료",
        font_size=11, bold=True, color=C_WHITE
    )

    # 파일 저장 (프로젝트 루트 기본 저장 + 존재하는 보조 경로에만 안전 복사)
    filename = "웹프로그래밍_알약이가(e-DrugCare)_[조장이름]_[조원명단].pptx"
    project_root = Path(__file__).resolve().parent.parent
    primary_path = project_root / filename
    prs.save(str(primary_path))
    saved_paths = [str(primary_path)]

    optional_dirs = [
        Path.home() / "Desktop",
        Path.home() / "Desktop" / "project",
    ]
    for opt_dir in optional_dirs:
        if opt_dir.is_dir():
            dest = opt_dir / filename
            if dest.resolve() != primary_path.resolve():
                shutil.copyfile(str(primary_path), str(dest))
                saved_paths.append(str(dest))
    print("Saved PPTX to:", saved_paths)


if __name__ == "__main__":
    build_presentation()
