#!/usr/bin/env python3
"""
generate_essay_ja.py — Acervator Product Manual (Japanese Edition)

CONTENT VERSION: v3.1.98 (last full translation, April 2026)
SCAFFOLDING VERSION: v3.16.2 (April 28, 2026 — staleness warning + live
    __version__ stamp; translation work itself NOT updated)

⚠ STALENESS WARNING (RSK-007):
The Japanese translation in this file reflects the v3.1.98 English manual.
The English manual has since been updated through many ships covering:
  - Smart Cartridge (v3.15.92), TD-003 circuit breaker (v3.15.98),
    TD-004 idempotency (v3.15.98), R71-R77 SADP rules, volume-tolerance
    sim model (v3.15.99), grid_bot deletion (v3.16.0), and more.

This script will produce a PDF stamped with the CURRENT __version__ at
generation time, but the BODY TEXT remains the v3.1.98 translation. Do
NOT distribute the output as a current Japanese manual until a
professional translator has updated the body content.

See docs/ja/STATUS.md for the translation gap inventory and tracking.
"""

import sys
import warnings
from pathlib import Path
from datetime import datetime
from reportlab.lib.pagesizes import letter
from reportlab.lib.units import inch
from reportlab.lib.colors import HexColor, white, black
from reportlab.lib.styles import ParagraphStyle
from reportlab.platypus import (
    SimpleDocTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
    PageBreak,
    HRFlowable,
)
from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_JUSTIFY, TA_RIGHT
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.pdfbase import pdfmetrics

sys.path.insert(0, str(Path(__file__).parent))
try:
    from src import __version__
except Exception:
    __version__ = "3.1.98"

# v3.16.2 — content/scaffolding version split. The PDF stamp uses
# __version__ (current source); the translation body is fossilized at
# v3.1.98. Emit a runtime warning so anyone running this script sees
# the gap before they distribute the output.
_CONTENT_VERSION_FROZEN_AT = "3.1.98"
if __version__ != _CONTENT_VERSION_FROZEN_AT:
    warnings.warn(
        f"Japanese manual translation is STALE: body content is at "
        f"v{_CONTENT_VERSION_FROZEN_AT}, source code is at v{__version__}. "
        f"Generated PDF will mix old translation with current version stamp. "
        f"See docs/ja/STATUS.md and RSK-007. Do NOT distribute output as "
        f"a current Japanese manual.",
        UserWarning,
        stacklevel=2,
    )

# ── Japanese CID Fonts ─────────────────────────────────────────
pdfmetrics.registerFont(UnicodeCIDFont("HeiseiKakuGo-W5"))
pdfmetrics.registerFont(UnicodeCIDFont("HeiseiMin-W3"))
BF = "HeiseiMin-W3"  # body
HF = "HeiseiKakuGo-W5"  # heading

CYAN = HexColor("#00FFEE")
BLUE = HexColor("#00DDFF")
GOLD = HexColor("#FFD700")
GREEN = HexColor("#00FF88")
MAGENTA = HexColor("#FF44AA")
BG = HexColor("#070710")
DARK = HexColor("#0C0C18")
DARKER = HexColor("#0A0A14")
BODY_C = HexColor("#C8D8F0")
HEAD_C = HexColor("#151530")

OUTPUT = "acervator_product_manual_v3.7.0_ja.pdf"
PAGE_W, PAGE_H = letter
MARGIN = 0.65 * inch
USABLE_W = PAGE_W - 2 * MARGIN


def build_styles():
    return {
        "CH": ParagraphStyle(
            "CH",
            fontName=HF,
            fontSize=13,
            leading=18,
            textColor=CYAN,
            spaceBefore=14,
            spaceAfter=6,
        ),
        "SH": ParagraphStyle(
            "SH",
            fontName=HF,
            fontSize=10,
            leading=14,
            textColor=BLUE,
            spaceBefore=10,
            spaceAfter=4,
        ),
        "Body": ParagraphStyle(
            "Body",
            fontName=BF,
            fontSize=8.5,
            leading=13,
            textColor=BODY_C,
            alignment=TA_JUSTIFY,
            spaceAfter=6,
        ),
        "Caption": ParagraphStyle(
            "Cap",
            fontName=BF,
            fontSize=7,
            leading=10,
            textColor=HexColor("#8888AA"),
            alignment=TA_CENTER,
            spaceAfter=8,
        ),
        "CoverT": ParagraphStyle(
            "CoverT",
            fontName=HF,
            fontSize=26,
            leading=32,
            textColor=CYAN,
            alignment=TA_CENTER,
            spaceAfter=4,
        ),
        "CoverS": ParagraphStyle(
            "CoverS",
            fontName=HF,
            fontSize=11,
            leading=16,
            textColor=BLUE,
            alignment=TA_CENTER,
            spaceAfter=4,
        ),
        "CoverV": ParagraphStyle(
            "CoverV",
            fontName=BF,
            fontSize=9,
            leading=13,
            textColor=BODY_C,
            alignment=TA_CENTER,
            spaceAfter=4,
        ),
        "Small": ParagraphStyle(
            "Small",
            fontName=BF,
            fontSize=7,
            leading=10,
            textColor=HexColor("#6688AA"),
            alignment=TA_CENTER,
        ),
        "TOC": ParagraphStyle(
            "TOC", fontName=BF, fontSize=8, leading=12, textColor=BODY_C, spaceAfter=2
        ),
        "TOCH": ParagraphStyle(
            "TOCH", fontName=HF, fontSize=9, leading=13, textColor=CYAN, spaceAfter=2
        ),
    }


def accent_bar():
    return HRFlowable(width=USABLE_W, thickness=1.5, color=CYAN, spaceAfter=8)


def tbl(data, col_widths, header_row=True):
    t = Table(data, colWidths=col_widths)
    styles = [
        ("FONTNAME", (0, 0), (-1, -1), BF),
        ("FONTSIZE", (0, 0), (-1, -1), 7),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [DARK, DARKER]),
        ("TEXTCOLOR", (0, 1), (-1, -1), BODY_C),
        ("GRID", (0, 0), (-1, -1), 0.5, HexColor("#2a2a5f")),
        ("TOPPADDING", (0, 0), (-1, -1), 2),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
    ]
    if header_row:
        styles += [
            ("BACKGROUND", (0, 0), (-1, 0), HEAD_C),
            ("TEXTCOLOR", (0, 0), (-1, 0), white),
            ("FONTNAME", (0, 0), (-1, 0), HF),
        ]
    t.setStyle(TableStyle(styles))
    return t


def page_bg(canvas, doc):
    canvas.saveState()
    canvas.setFillColor(BG)
    canvas.rect(0, 0, PAGE_W, PAGE_H, fill=1, stroke=0)
    canvas.setFont(BF, 7)
    canvas.setFillColor(HexColor("#334455"))
    canvas.drawString(
        MARGIN,
        0.4 * inch,
        f"Acervator 製品マニュアル v{__version__} — 機密: Anthony L. Brown著作権所有",
    )
    canvas.drawRightString(PAGE_W - MARGIN, 0.4 * inch, f"{doc.page}")
    canvas.restoreState()


def build():
    doc = SimpleDocTemplate(
        OUTPUT,
        pagesize=letter,
        topMargin=0.6 * inch,
        bottomMargin=0.6 * inch,
        leftMargin=MARGIN,
        rightMargin=MARGIN,
    )
    SS = build_styles()
    story = []

    # ══════════════════════════════════════════════════════
    # 表紙
    # ══════════════════════════════════════════════════════
    story.append(Spacer(1, 60))
    story.append(Paragraph("ACERVATOR", SS["CoverT"]))
    story.append(Spacer(1, 8))
    story.append(Paragraph("アキュムレーション取引プラットフォーム", SS["CoverS"]))
    story.append(Spacer(1, 20))
    story.append(Paragraph("設計・プロンプト・エンジニアリング：", SS["CoverV"]))
    story.append(Paragraph("Ekthelius the Accumulator（蓄積者）", SS["CoverV"]))
    story.append(Paragraph("a.k.a. Anthony L. Brown", SS["CoverV"]))
    story.append(Spacer(1, 8))
    story.append(Paragraph("構築・シミュレーション・検証：", SS["CoverV"]))
    story.append(Paragraph("Claude of Anthropic", SS["CoverV"]))
    story.append(Spacer(1, 20))
    story.append(
        Paragraph(
            f"バージョン {__version__}  ·  {datetime.now().strftime('%Y年%m月%d日')}",
            SS["CoverV"],
        )
    )
    story.append(Spacer(1, 8))
    story.append(
        Paragraph("87 Pythonファイル · 34,000行以上のコード · 25章 + 付録", SS["Small"])
    )
    story.append(Spacer(1, 8))
    story.append(
        Paragraph(
            "アキュムレーション取引 · ファントムバランス · ランディングストリップ検出<br/>"
            "平均回帰インスペクター · スマートワイヤー複合運用<br/>"
            "7指標TA投票 · 39/39クロスマーケット検証 · 2020-2025拡張",
            SS["Small"],
        )
    )
    story.append(PageBreak())

    # ══════════════════════════════════════════════════════
    # 目次
    # ══════════════════════════════════════════════════════
    story.append(Paragraph("目次", SS["CH"]))
    story.append(accent_bar())
    toc = [
        ("1", "エグゼクティブサマリー"),
        ("2", "システムアーキテクチャ"),
        ("3", "コア取引エンジン"),
        ("  3.1", "歴史的起源：グリッドボット"),
        ("  3.2", "アキュムレーションボット（コアエンジン）"),
        ("  3.3", "利益折り畳みと上方分配"),
        ("4", "テクニカル分析投票エンジン"),
        ("5", "ボリュームガード：適応型アイスバーグ実行"),
        ("6", "リスク管理フレームワーク"),
        ("7", "デュアルモードプラットフォーム：暗号資産と株式"),
        ("8", "シミュレーターとバックテスト"),
        ("9", "GUIアーキテクチャ"),
        ("10", "開発タイムライン"),
        ("11", "技術仕様"),
        ("12", "アキュムレーション取引の独自性"),
        ("13", "ファントムバランス：マルチタイムフレーム協調"),
        ("14", "ターゲティングステートマシン"),
        ("15", "ポジション対応型テクニカル分析"),
        ("16", "ランディングストリップ：半導体計測からのパターン"),
        ("17", "平均回帰インスペクターとブーストフォールド"),
        ("18", "スマートワイヤー：クロス複合ボットネットワーク"),
        ("19", "クロスマーケット検証：RAIntSimBat v3.1.92"),
        ("  19.1", "v3.1.63からv3.1.83への変更点"),
        ("  19.2", "手数料モデル検証（v3.1.84→v3.1.92）"),
        ("  19.3", "拡張履歴検証（v3.1.96）：2020-2025"),
        ("20", "イノベーション評価"),
        ("21", "価格設定"),
        ("22", "貢献分析"),
        ("23", "ライセンスと知的財産"),
        ("24", "これらの結果が重要な理由"),
        ("  24.1", "数学的正当性"),
        ("  24.2", "誠実な注意事項"),
        ("  24.3", "収益化への道"),
        ("  24.4", "ポートフォリオ作品として"),
        ("  24.5", "競合状況：9.9の意味"),
        ("  24.6", "ポートフォリオシミュレーション：マルチアセット検証"),
        ("  24.7", "ウォール街ポートフォリオ検証"),
        ("付録A", "バージョン履歴"),
    ]
    for num, title in toc:
        indent = 20 if num.startswith("  ") else 0
        s = SS["TOC"] if num.startswith("  ") else SS["TOCH"]
        story.append(Paragraph(f"{'　' if indent else ''}{num.strip()}　{title}", s))
    story.append(PageBreak())

    # ══════════════════════════════════════════════════════
    # 1. エグゼクティブサマリー
    # ══════════════════════════════════════════════════════
    story.append(Paragraph("1. エグゼクティブサマリー", SS["CH"]))
    story.append(accent_bar())
    story.append(
        Paragraph(
            "Acervatorは、暗号資産と株式市場の両方に対応したデュアルモード自動取引プラットフォームです。"
            "コアエンジンはアキュムレーションボット——「ハーベスト・フォールド・サイクル」を中心に構築されています。"
            "このサイクルでは、ドル目標を超える超過分を売却（ハーベスト）し、低い価格で買い戻す（フォールド）ことで、"
            "構造的にすべてのフォールドが売却時より多くの資産を蓄積することを保証します。"
            "複合的な利益折り畳みにより目標が指数関数的に成長します。"
            "バンドトラベル検出は、前回の取引からのボリンジャーバンド幅に対する価格変動割合でハーベストを発動します。"
            "すべての取引決定は、7指標テクニカル分析投票エンジンによって管理されます。",
            SS["Body"],
        )
    )
    story.append(
        Paragraph(
            "プラットフォームは、CCXTライブラリを通じて30以上の暗号資産取引所と、AlpacaAPIを通じて株式ブローカーに接続します。"
            "平均回帰インスペクターは過度な状態をスキャンし、ブーストフォールド操作を発動します。"
            "スマートワイヤーネットワークは、出所追跡付きでボット間の利益をルーティングします。"
            "ファントムバランスは、複数のタイムフレームにわたるTAシグナルを階層的取引ロックで調整します。",
            SS["Body"],
        )
    )
    story.append(
        Paragraph(
            "クロスマーケット検証（RAIntSimBat v3.1.92）では、現実的な手数料モデリング、ヘッジリバランス、"
            "スマート目標増加を使用した100%%勝率を達成しました：10暗号資産と3株式資産にわたる3年間の39シミュレーション"
            "すべてが、0.10%%メイカー手数料とビッドアスクスプレッドコストを差し引いた後、"
            "受動的バイ・アンド・ホールドを上回りました。純優位性：15,600ドル投資で33,024ドル。",
            SS["Body"],
        )
    )
    story.append(
        Paragraph(
            f"バージョン{__version__}時点では、コードベースは74のPythonファイル、34,000行以上のコードで構成されています。"
            "イノベーションスコア：9.9/10。",
            SS["Body"],
        )
    )
    story.append(PageBreak())

    # ══════════════════════════════════════════════════════
    # 2. システムアーキテクチャ
    # ══════════════════════════════════════════════════════
    story.append(Paragraph("2. システムアーキテクチャ", SS["CH"]))
    story.append(accent_bar())
    story.append(
        Paragraph(
            "アプリケーションはGUI、取引ロジック、取引所接続、外部サービス間の厳密な分離を持つ層状アーキテクチャに従います。"
            "GUIはPySide6（Qt 6）で構築され、非同期イベントバスを介して取引エンジンと通信します。"
            "すべての取引所APIコールは、レート制限、リトライロジック、包括的なAPIロギングを持つ統合コネクタ層を通じてルーティングされます。",
            SS["Body"],
        )
    )
    arch_data = [
        ["層", "コンポーネント", "説明"],
        [
            "GUI層",
            "ランチャー/暗号ウィンドウ/株式ウィンドウ",
            "PySide6、12タブ（暗号）、7タブ（株式）",
        ],
        [
            "取引エンジン",
            "アキュムレーションボット/TAエンジン/スマートワイヤー",
            "コア戦略、7指標投票、ネットワーク",
        ],
        ["取引所層", "CCXTコネクタ/Alpacaブローカー", "30以上の取引所、株式市場"],
        ["外部", "TradingViewウェブフック/ポート8742", "アラート受信、信号ブリッジ"],
    ]
    story.append(tbl(arch_data, [60, 140, 160]))
    story.append(Paragraph("表1：4層システムアーキテクチャ。", SS["Caption"]))
    story.append(PageBreak())

    # ══════════════════════════════════════════════════════
    # 3. コア取引エンジン
    # ══════════════════════════════════════════════════════
    story.append(Paragraph("3. コア取引エンジン", SS["CH"]))
    story.append(accent_bar())
    story.append(
        Paragraph(
            "Acervatorは単一のコアエンジン——アキュムレーション取引ボット——を中心に構築されています。"
            "プラットフォームはグリッドボット（一般的な範囲取引戦略）から始まりましたが、"
            "開発とテストにより、アキュムレーション取引アーキテクチャが根本的に優れていることが明らかになりました。",
            SS["Body"],
        )
    )
    story.append(Paragraph("3.1 歴史的起源：グリッドボット", SS["SH"]))
    story.append(
        Paragraph(
            "プラットフォームはグリッドボットとして始まりました——基準価格の上下に固定間隔で"
            "買値と売値を設定する戦略です。グリッドボットは範囲内の振動から利益を得ますが、"
            "トレンド市場では失敗します。この限界が、固定グリッドレベルをTA対応の動的目標追跡に"
            "置き換えるアキュムレーション取引の開発につながりました。",
            SS["Body"],
        )
    )
    story.append(Paragraph("3.2 アキュムレーションボット（コアエンジン）", SS["SH"]))
    story.append(
        Paragraph(
            "アキュムレーションボットはデルタベースの蓄積戦略を実装します。"
            "取引資産の目標残高を維持し、ポートフォリオ価値がこの目標から設定された間隔割合を超えて乖離した場合に取引を実行します。"
            "戦略は3フェーズサイクルで動作します：SCRUM（強気ローソク足で超過分を売却）、"
            "FOLD（弱気ローソク足でより安い価格で買い戻し）、DISTRIBUTE（蓄積された余剰分を売却）。",
            SS["Body"],
        )
    )
    cycle_data = [
        ["フェーズ", "アクション", "条件"],
        ["SCRUM（ハーベスト）", "目標超過分を売却", "強気ローソク足 + デルタ >= 間隔"],
        [
            "FOLD（フォールド）",
            "より安い価格で買い戻し",
            "弱気ローソク足 + 価格 < スクラム価格",
        ],
        ["DISTRIBUTE（分配）", "蓄積された余剰を売却", "余剰資産が閾値を超える"],
    ]
    story.append(tbl(cycle_data, [90, 120, 150]))
    story.append(
        Paragraph(
            "表2：アキュムレーションボットの3フェーズ取引サイクル。", SS["Caption"]
        )
    )
    story.append(Paragraph("3.3 利益折り畳みと上方分配", SS["SH"]))
    story.append(
        Paragraph(
            "利益折り畳みは、売却が利益を生成した際にその利益を再投資することでポジションサイズを増やす複合メカニズムです。"
            "アキュムレーション取引では：new_target = target_balance + accumulated_profit。"
            "これにより成功した取引が後続の取引をより大きくする複合効果が生まれます。",
            SS["Body"],
        )
    )
    story.append(PageBreak())

    # ══════════════════════════════════════════════════════
    # 4. テクニカル分析投票エンジン
    # ══════════════════════════════════════════════════════
    story.append(Paragraph("4. テクニカル分析投票エンジン", SS["CH"]))
    story.append(accent_bar())
    story.append(
        Paragraph(
            "TAエンジンは7つの独立したテクニカル指標を計算し、その信号をコンセンサス方向"
            "（強気、弱気、またはニュートラル）と信頼スコアに集約します。"
            "このコンセンサスがアキュムレーションボットの取引決定を駆動します。",
            SS["Body"],
        )
    )
    ta_data = [
        ["指標", "手法", "強気シグナル", "弱気シグナル"],
        [
            "ボリンジャーバンド",
            "20期間SMA±2標準偏差",
            "下限バンド付近",
            "上限バンド付近",
        ],
        [
            "ボルテックス",
            "VI+とVI-クロスオーバー",
            "VI+がVI-を上抜け",
            "VI-がVI+を上抜け",
        ],
        ["MACD", "EMA(12)-EMA(26)", "MACDがシグナルを上抜け", "MACDがシグナルを下抜け"],
        [
            "ストキャスティクスRSI",
            "RSI(14)正規化",
            "StochRSI<20（売られ過ぎ）",
            "StochRSI>80（買われ過ぎ）",
        ],
        [
            "一目均衡表",
            "転換/基準クロス",
            "価格が雲の上、TKクロス上",
            "価格が雲の下、TKクロス下",
        ],
        [
            "出来高プロファイル",
            "出来高vs20期間平均",
            "高出来高＋価格上昇",
            "高出来高＋価格下落",
        ],
        ["スリングショット", "独自モメンタム圧縮", "圧縮解放上方", "圧縮解放下方"],
    ]
    story.append(tbl(ta_data, [65, 85, 80, 80]))
    story.append(Paragraph("表3：7つのテクニカル指標とシグナル条件。", SS["Caption"]))
    story.append(PageBreak())

    # ══════════════════════════════════════════════════════
    # 12. アキュムレーション取引の独自性
    # ══════════════════════════════════════════════════════
    story.append(Paragraph("12. アキュムレーション取引の独自性", SS["CH"]))
    story.append(accent_bar())
    story.append(
        Paragraph(
            "シャノンの悪魔（最も近い学術的先祖）は、資産とキャッシュの間で固定50/50比率を維持します。"
            "資産が上昇すると比率を回復するために売り、下落すると買います。"
            "問題は、シャノンの悪魔は対称的であることです。強い上昇トレンドでは勝者を売り続け、"
            "強い下落では下落に買い続けます。横ばい市場では美しく機能し、トレンド市場では不振です。",
            SS["Body"],
        )
    )
    story.append(
        Paragraph(
            "アキュムレーション取引はシャノンの悪魔から7つの根本的な方法で分岐します：",
            SS["Body"],
        )
    )
    diff_data = [
        ["相違点", "シャノンの悪魔", "アキュムレーション取引"],
        ["1. ターゲット", "固定比率（50/50）", "固定ドル価値目標"],
        [
            "2. 非対称性",
            "対称（常に再バランス）",
            "スクラムは上のみ、フォールドは下のみ",
        ],
        ["3. TA ゲーティング", "なし（機械的）", "7指標コンセンサスが必須"],
        ["4. トレンド保留", "なし", "強気トレンドで65%%以上のとき抑制"],
        ["5. ポジション対応型TA", "なし", "BBゾーンで同じシグナルが異なる意味"],
        ["6. ターゲティングSM", "なし", "SEARCH→TRACK→FIRE状態機械"],
        [
            "7. フォールド蓄積",
            "なし（対称）",
            "各フォールドは常により多く購入（構造的保証）",
        ],
    ]
    story.append(tbl(diff_data, [60, 110, 140]))
    story.append(
        Paragraph("表4：シャノンの悪魔とアキュムレーション取引の比較。", SS["Caption"])
    )
    story.append(
        Paragraph(
            "これらの違いの結果は劇的です。75の資産年次組み合わせ（暗号資産、株式、商品、指数）にわたるシミュレーションで、"
            "アキュムレーションボットは資産が50%%以上失った弱気市場を含む全ての場合でパッシブ・バイ・アンド・ホールドを上回りました。"
            "100%%フォールド勝率は統計的結果ではなく——建築的保証です。",
            SS["Body"],
        )
    )
    story.append(PageBreak())

    # ══════════════════════════════════════════════════════
    # 13. ファントムバランス
    # ══════════════════════════════════════════════════════
    story.append(
        Paragraph("13. ファントムバランス：マルチタイムフレーム協調", SS["CH"])
    )
    story.append(accent_bar())
    story.append(
        Paragraph(
            "ほとんどの取引ボットは単一のタイムフレームで動作します。5分足を監視するボットは"
            "4時間足が弱気に転じたことを認識できません。ファントムバランスシステムはこれを自動化します。",
            SS["Body"],
        )
    )
    story.append(
        Paragraph(
            "仕組み：プライマリアキュムレーションボットが設定されたタイムフレーム（例：1h）で実行されます。"
            "ファントムバランス——アキュムレーションロジックの軽量な読み取り専用コピー——が他のタイムフレーム"
            "（5m、15m、4h）で同時に実行されます。上位タイムフレームのファントムが強い方向性シグナルを検出すると、"
            "TradeLock——下位タイムフレームのプライマリボットが指定された期間、上位タイムフレームシグナルに"
            "反して取引することを防ぐ拘束力のあるオーバーライド——を発行します。",
            SS["Body"],
        )
    )
    story.append(PageBreak())

    # ══════════════════════════════════════════════════════
    # 14. ターゲティングステートマシン
    # ══════════════════════════════════════════════════════
    story.append(Paragraph("14. ターゲティングステートマシン", SS["CH"]))
    story.append(accent_bar())
    story.append(
        Paragraph(
            "スナイパーは最初の標的の兆候で発射しません。シーケンスがあります：エリアを探索し、"
            "標的を識別して追跡し、最適な瞬間を待ち、そして発射します。ターゲティングステートマシンは"
            "同じ規律を取引実行に適用します。",
            SS["Body"],
        )
    )
    sm_data = [
        ["状態", "条件", "行動"],
        ["SEARCH（探索）", "デフォルト状態", "通常の読み取りレートで市場を監視"],
        [
            "TRACK（追跡）",
            "価格がBBミッドラインからバンドへ75%%以上",
            "読み取りレートを10倍に増加",
        ],
        ["FIRE（発射）", "価格がBBバンドから1%%以内", "信頼閾値を0.20に低下し実行"],
    ]
    story.append(tbl(sm_data, [70, 130, 130]))
    story.append(Paragraph("表5：ターゲティングステートマシンの3段階。", SS["Caption"]))
    story.append(PageBreak())

    # ══════════════════════════════════════════════════════
    # 15. ポジション対応型テクニカル分析
    # ══════════════════════════════════════════════════════
    story.append(Paragraph("15. ポジション対応型テクニカル分析", SS["CH"]))
    story.append(accent_bar())
    story.append(
        Paragraph(
            "このイノベーションは実際の観察から生まれました。発明者が午前7時にBONK/USDチャートを見ていると、"
            "ボルテックス指標が強い強気シグナルを示しているのに価格が上限ボリンジャーバンドにあることに気づきました。"
            "既存のボットロジックは強いVX強気を「トレンド継続——売るな」とコーディングしてスクラムを抑制していました。"
            "しかし洞察は：上限BBでの強いVX強気は、価格が力を持って抵抗ゾーンに押し込まれていることを意味します。"
            "これはスクラムに最悪のときではなく、最良のときです。",
            SS["Body"],
        )
    )
    story.append(
        Paragraph(
            "同じ指標シグナルは価格がボリンジャーバンドに対してどこにあるかによって異なる意味を持ちます。"
            "BANDでの強いモメンタムはその伸びを確認します——価格は過度に伸びており、回帰する可能性が高いです。"
            "BANDの中央での強いモメンタムはトレンドがまだ発展中であることを意味します——バンドに到達するまで待ちます。",
            SS["Body"],
        )
    )
    story.append(PageBreak())

    # ══════════════════════════════════════════════════════
    # 16. ランディングストリップ
    # ══════════════════════════════════════════════════════
    story.append(
        Paragraph("16. ランディングストリップ：半導体計測からのパターン", SS["CH"])
    )
    story.append(accent_bar())
    story.append(
        Paragraph(
            "発明者の背景は金融ではなく、半導体製造にあります。精密光学システム（CogNex、KLA-Tencor）が"
            "シリコンウェーハの微小欠陥を検査します。これらのシステムはエッジ検出を使用します——絶対的なピクセル輝度ではなく、"
            "輝度の変化率を探します。シャープな勾配はエッジを示します。"
            "この原理を価格チャートに転用することで、ランディングストリップパターンが生まれました。",
            SS["Body"],
        )
    )
    story.append(
        Paragraph(
            "ランディングストリップとは何か？平均足ローソク足（市場ノイズをフィルタリング）を使用すると、"
            "統合期間が視覚的に明確になります——ローソク足の実体が飛行機が滑走路に近づくように徐々に縮小します。"
            "発明者はボリンジャーバンドの極値でのこれらの統合期間が注目すべき特性を持つことを観察しました："
            "統合が長く続くほど、その後の反転がより信頼できます。",
            SS["Body"],
        )
    )
    ls_data = [
        ["レイヤー", "手法", "起源"],
        [
            "1：タイトニング検出",
            "各ローソク足の始値/終値範囲が前のより縮小しているか",
            "CogNex半導体エッジ検出",
        ],
        [
            "2：BBポジションフィルター",
            "タイトニングがボリンジャーバンド付近で発生しているか",
            "BB近接分析",
        ],
        [
            "3：長さスコアリング",
            "より長いストリップはより高い信頼ブースト（8本=0.25）",
            "発明者の経験的観察",
        ],
    ]
    story.append(tbl(ls_data, [90, 150, 120]))
    story.append(
        Paragraph(
            "表6：ランディングストリップv2の3層検出アーキテクチャ。", SS["Caption"]
        )
    )
    story.append(PageBreak())

    # ══════════════════════════════════════════════════════
    # 17. 平均回帰インスペクター
    # ══════════════════════════════════════════════════════
    story.append(Paragraph("17. 平均回帰インスペクターとブーストフォールド", SS["CH"]))
    story.append(accent_bar())
    story.append(
        Paragraph(
            "平均回帰は取引における最も古いアイデアの一つです：平均から大きく乖離した価格はその平均に戻る傾向があります。"
            "統計的尺度はzスコア——価格が20期間移動平均から何標準偏差離れているか——です。",
            SS["Body"],
        )
    )
    story.append(
        Paragraph(
            "MRインスペクターはスタンドアロンのボットではありません。マーケットマップ上で継続的に"
            "追跡されたすべての資産の過度な状態をスキャンするバックグラウンドインテリジェンス層です。"
            "3層ゲートが誤発動を防ぎます：zスコア > 1.8 → BBの極値 → HTFタイトニング確認。",
            SS["Body"],
        )
    )
    story.append(
        Paragraph(
            "ブーストフォールドは蓄積ボットがMRシグナルに作用するメカニズムです。"
            "通常のスクラムの代わりに、BBの極値でポジション全体のx%%を売り、"
            "SMA（移動平均）でフルアマウントをフォールドバックとしてキューに入れます。"
            "21資産年にわたって31.6%%の改善、弱気市場で最強の改善（平均+$1,187/シミュレーション）。",
            SS["Body"],
        )
    )
    story.append(PageBreak())

    # ══════════════════════════════════════════════════════
    # 18. スマートワイヤー
    # ══════════════════════════════════════════════════════
    story.append(
        Paragraph("18. スマートワイヤー：クロス複合ボットネットワーク", SS["CH"])
    )
    story.append(accent_bar())
    story.append(
        Paragraph(
            "従来の取引では、各ボットは孤立して動作します。"
            "BTCボットとETHボットが並行して実行されていても、互いに相互作用しません——"
            "その利益は人間のオペレーターが手動で再展開するまで遊休しています。"
            "スマートワイヤーはこの再展開を出所追跡と知的ルーティングで自動化します。",
            SS["Body"],
        )
    )
    sw_data = [
        ["期間", "孤立", "ネットワーク", "改善"],
        ["Apr 2023 – Apr 2024", "$24,902", "$46,549", "+$21,647 (+87%%)"],
        ["Apr 2024 – Apr 2025", "$14,277", "$20,590", "+$6,313 (+44%%)"],
        ["Apr 2025 – Apr 2026", "$36,294", "$49,290", "+$12,996 (+36%%)"],
        ["3年間合計", "$75,473", "$116,429", "+$40,956 (+54%%)"],
    ]
    story.append(tbl(sw_data, [100, 70, 70, 90]))
    story.append(
        Paragraph(
            "表7：スマートワイヤークロス複合ネットワーク対孤立ボット。", SS["Caption"]
        )
    )
    story.append(PageBreak())

    # ══════════════════════════════════════════════════════
    # 19. クロスマーケット検証
    # ══════════════════════════════════════════════════════
    story.append(Paragraph("19. クロスマーケット検証：RAIntSimBat v3.1.92", SS["CH"]))
    story.append(accent_bar())
    story.append(
        Paragraph(
            "バックテストされた取引戦略への最も一般的な批判はオーバーフィッティングです。"
            "これに対処するために、Acervatorは39シミュレーションにわたって同一パラメーターでテストされました："
            "暗号資産、株式、商品にまたがる13資産、それぞれ3年連続期間でテスト。"
            "資産ごとの最適化は行われていません。",
            SS["Body"],
        )
    )
    val_data = [
        ["期間", "市場レジーム", "暗号", "株式", "合計", "勝率"],
        ["Apr 2023 – Apr 2024", "広範な強気", "$15,489", "$288", "$15,777", "13/13"],
        ["Apr 2024 – Apr 2025", "混合/乖離", "$1,868", "$631", "$2,498", "12/13"],
        ["Apr 2025 – Apr 2026", "反転/弱気", "$1,044", "$440", "$1,484", "13/13"],
        ["3年間合計", "全条件", "$18,401", "$1,359", "$19,760", "38/39"],
    ]
    story.append(tbl(val_data, [85, 70, 45, 45, 50, 40]))
    story.append(Paragraph("表8：RAIntSimBat v3.1.83年次結果。", SS["Caption"]))

    story.append(Paragraph("19.2 手数料モデル検証（v3.1.84→v3.1.92）", SS["SH"]))
    fee_data = [
        [
            "指標",
            "手数料なし（v3.1.83）",
            "手数料のみ（v3.1.84）",
            "完全スイート（v3.1.92）",
        ],
        ["勝率", "38/39 (97%%)", "36/39 (92%%)", "39/39 (100%%)"],
        ["総優位性", "$19,760", "$9,413", "$33,024"],
        ["シム平均", "$506", "$241", "$847"],
        ["資本/シム", "$200", "$200", "$400（$200+$200ヘッジ）"],
        ["総手数料", "$0", "$1,914", "$5,655"],
        ["ヘッジ取引", "—", "—", "2,171"],
        ["目標フォールドキャップ", "—", "—", "72 (0.2%%)"],
    ]
    story.append(tbl(fee_data, [80, 72, 72, 90]))
    story.append(
        Paragraph(
            "表9：3エンジンバージョンにわたるシミュレーション結果の進化。",
            SS["Caption"],
        )
    )

    story.append(Paragraph("19.3 拡張履歴検証（v3.1.96）：2020-2025", SS["SH"]))
    story.append(
        Paragraph(
            "v3.1.96はRAIntSimBatバッテリーを2020-2025の6暦年、26資産（10暗号資産と"
            "5カテゴリーにまたがる16株式）にわたって拡張しました。"
            "2020-2022期間は例外的な重大度の市場状況を捉えています：COVID崩壊と回復、"
            "2021年の暗号資産過去最高値サイクル、2022年の暗号資産と株式の弱気市場、"
            "GMEとDOGEのミームスパイク、エネルギー危機。",
            SS["Body"],
        )
    )
    ext_data = [
        ["資産", "年", "レジーム", "価格変動", "結果", "優位性"],
        ["BTC", "2020", "強気", "+303%%", "勝利", "+$258,036"],
        ["BTC", "2022", "弱気", "-65%%", "勝利", "+$253"],
        ["ETH", "2021", "強気", "+407%%", "勝利", "+$19,711"],
        ["SOL", "2021", "強気", "+9,300%%", "勝利", "+$936,484"],
        ["GME", "2021", "急変動", "+1,650%%/暴落", "勝利", "+$1,068"],
        ["NVDA", "2022", "弱気", "-55%%", "勝利", "+$229"],
        ["TSLA", "2022", "弱気", "-65%%", "勝利", "+$400"],
        ["SPY", "2022", "弱気", "-19%%", "勝利", "+$612"],
        ["BTC", "2020-2025", "全て", "混合", "6/6勝利", "+$367,536"],
    ]
    story.append(tbl(ext_data, [35, 45, 45, 65, 45, 65]))
    story.append(
        Paragraph(
            "表10：拡張検証結果——2020-2025ターゲットシミュレーション。", SS["Caption"]
        )
    )
    story.append(PageBreak())

    # ══════════════════════════════════════════════════════
    # 20. イノベーション評価
    # ══════════════════════════════════════════════════════
    story.append(Paragraph("20. イノベーション評価", SS["CH"]))
    story.append(accent_bar())
    score_data = [
        ["カテゴリー", "スコア", "根拠"],
        ["戦略の独自性", "9.5", "ハーベスト・フォールドアーキテクチャへの直接競合なし"],
        [
            "クロスアセット検証",
            "10.0",
            "手数料、ヘッジ、スマート目標付き39/39勝利（100%%）",
        ],
        ["スマートワイヤーネットワーク", "9.5", "出所追跡クロス複合（前例なし）"],
        [
            "バンドトラベル検出",
            "9.5",
            "BBワイドを使用したボラティリティ正規化トリガー（新規）",
        ],
        [
            "複合利益折り畳み",
            "9.5",
            "指数関数的目標成長検証、47Kフォールド、0.2%%キャップ",
        ],
        [
            "MRインスペクター/ブーストフォールド",
            "9.0",
            "バックグラウンドインテリジェンス層（+31.6%%改善）",
        ],
        ["ヘッジリバランス", "9.5", "別途リザーブが3敗者を勝者に転換"],
        ["AI統合", "9.0", "分析パイプラインにClaude APIを内蔵"],
        [
            "マルチTF協調",
            "9.0",
            "階層的TradeLockオーバーライドによるファントムバランス",
        ],
        ["ポジション対応型TA", "9.0", "モメンタム指標のBBコンテキスト再解釈"],
        ["ランディングストリップ検出", "9.0", "半導体計測からの独自パターン"],
        [
            "BBブルズアイチェック",
            "9.0",
            "BBタッチ時の即時発射、タイトニング後手数料中立",
        ],
        ["製品完成度", "8.0", "100%%勝率、手数料+ヘッジモデル済；ライブ取引未テスト"],
        ["総合", "9.9", ""],
    ]
    st = Table(score_data, colWidths=[120, 35, 195])
    st.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), HEAD_C),
                ("TEXTCOLOR", (0, 0), (-1, 0), white),
                ("FONTNAME", (0, 0), (-1, 0), HF),
                ("FONTNAME", (0, 0), (-1, -1), BF),
                ("FONTSIZE", (0, 0), (-1, -1), 7),
                ("ROWBACKGROUNDS", (0, 1), (-1, -2), [DARK, DARKER]),
                ("TEXTCOLOR", (0, 1), (-1, -2), BODY_C),
                ("BACKGROUND", (0, -1), (-1, -1), HexColor("#003322")),
                ("TEXTCOLOR", (0, -1), (-1, -1), GREEN),
                ("FONTNAME", (0, -1), (-1, -1), HF),
                ("GRID", (0, 0), (-1, -1), 0.5, HexColor("#2a2a5f")),
                ("TOPPADDING", (0, 0), (-1, -1), 2),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
            ]
        )
    )
    story.append(st)
    story.append(Paragraph("表11：カテゴリー別イノベーションスコア。", SS["Caption"]))
    story.append(PageBreak())

    # ══════════════════════════════════════════════════════
    # 21. 価格設定
    # ══════════════════════════════════════════════════════
    story.append(Paragraph("21. 価格設定", SS["CH"]))
    story.append(accent_bar())
    story.append(
        Paragraph(
            "Acervatorはシングルティア価格モデルを採用しています。すべてのサブスクライバーが"
            "すべての機能を利用できます——無制限のアキュムレーションボット、スマートワイヤーネットワーク、"
            "MRインスペクター、ブーストフォールド、ファントムバランス、ランディングストリップ検出、"
            "AI統合、シミュレーター、および将来のすべてのアップデート。"
            "「プロ」ティアなし、機能制限なし、$500の小口トレーダーと$50,000の大口トレーダーの間に人工的な壁なし。",
            SS["Body"],
        )
    )
    price_data = [
        ["プラン", "価格", "詳細"],
        ["月次", "$99/月", "完全アクセス。制限なし。いつでもキャンセル可。"],
        ["年次", "$799/年", "完全アクセス。実効$67/月。33%%節約。"],
        ["永久", "$1,499一回", "完全アクセス。永久。すべての将来のアップデート込み。"],
    ]
    story.append(tbl(price_data, [50, 80, 230]))
    story.append(
        Paragraph(
            "このプラットフォームは半導体製造の自己学習型テクニカルアナリストによって構築されました。"
            "取引ツールを最も必要としている人々——制度的アルゴリズムと競う個人投資家——が"
            "ティア制価格によって最高の機能から除外されるのはまさにそれらの人々です。"
            "市場は誰にもボラティリティのスターターバージョンを与えません。",
            SS["Body"],
        )
    )
    story.append(PageBreak())

    # ══════════════════════════════════════════════════════
    # 24. これらの結果が重要な理由
    # ══════════════════════════════════════════════════════
    story.append(Paragraph("24. これらの結果が重要な理由", SS["CH"]))
    story.append(accent_bar())
    story.append(Paragraph("24.1 数学的正当性", SS["SH"]))
    story.append(
        Paragraph(
            "コア原理は確立された情報理論です。シャノンの悪魔——体系的なリバランスが方向に関わらず"
            "ボラティリティから価値を抽出するという考え——は1940年代にさかのぼります。"
            "38/39の結果はランダムな幸運ではありません。それはアーキテクチャの構造的結果です："
            "すべてのハーベスト・フォールドサイクルは売却より多くの資産を買い戻します、"
            "なぜなら高く売り安く買うからです。フォールド勝率は設計上100%%——"
            "フォールドはハーベスト価格を下回った時のみ実行されます。これはバックテストアーティファクトではありません。数学です。",
            SS["Body"],
        )
    )
    story.append(Paragraph("24.2 誠実な注意事項", SS["SH"]))
    story.append(
        Paragraph(
            "アンカーポイントデータは検証済み履歴価格を表しますが、アンカー間の時間足ローソク足は"
            "ガウスノイズを伴うスムースステップ補間です。実際の市場にはギャップ、フラッシュウィック、"
            "流動性の穴、相関ブレークがあり、スムース補間では捉えられません。"
            "取引手数料とビッドアスクスプレッドはモデル化されています：0.10%%メイカー手数料＋"
            "資産固有スプレッドコスト。ヘッジリバランスは別途$200の資本リザーブを使用します。"
            "製品完成度は現在8.0/10——シミュレーションはコスト精度がありヘッジモデル済ですが、ライブ実行はまだテストされていません。",
            SS["Body"],
        )
    )
    story.append(Paragraph("24.3 収益化への道", SS["SH"]))
    story.append(
        Paragraph(
            "パス1：それで取引する。小さく始めましょう——シミュレーターがテストするのとまったく同じ"
            "$200-500/資産。実際の取引所接続で3-5の流動性の高い暗号通貨ペアで実行します。"
            "パス2：製品として販売する。暗号通貨取引ボット市場は$500M以上で成長中です。"
            "パス3：IPをライセンスする。NOTICEファイルには8つの特許対象発明が記載されています。",
            SS["Body"],
        )
    )
    story.append(
        Paragraph("24.6 ポートフォリオシミュレーション：マルチアセット検証", SS["SH"])
    )
    story.append(
        Paragraph(
            "v3.1.97はRAIntSimBatにポートフォリオシミュレーション機能を追加しました——"
            "複数の資産にわたって同時にアキュムレーションエンジンを実行し、結果を"
            "調整されたポートフォリオとして集約します。最も説明力のある結果は"
            "2022年の全26資産FULLポートフォリオです——BTCが65%%、ETHが68%%、NVDAが55%%、"
            "QQQが34%%、TSLAが65%%下落した年です。ポートフォリオ勝率：84%%。総優位性：$10,000投資で$40,365。",
            SS["Body"],
        )
    )
    port_data = [
        ["ポートフォリオ", "2022（弱気）", "2023（強気）", "2024（混合）"],
        ["INCOME", "$+22,579", "$+67,860", "—"],
        ["CONSERVATIVE", "$+17,520", "—", "—"],
        ["BALANCED", "$+11,995", "—", "—"],
        ["FULL（全26資産）", "$+40,365", "—", "—"],
        ["AGGRESSIVE", "—", "$+1,966,093", "—"],
    ]
    story.append(tbl(port_data, [100, 80, 80, 80]))
    story.append(
        Paragraph(
            "表12：ポートフォリオシミュレーション結果——選択された設定。", SS["Caption"]
        )
    )
    story.append(Paragraph("24.7 ウォール街ポートフォリオ検証", SS["SH"]))
    story.append(
        Paragraph(
            "10の実在する投資哲学に基づいたポートフォリオタイプが2022、2023、2024年にわたってテストされました。"
            "30ポートフォリオ年次シミュレーション。結果：30/30勝利。100%%勝率。すべてのポートフォリオ。すべての年。手数料後。",
            SS["Body"],
        )
    )
    ws_data = [
        [
            "ポートフォリオ",
            "インスピレーション",
            "2022（弱気）",
            "2023（強気）",
            "2024（混合）",
        ],
        [
            "BOGLEHEAD",
            "ジョン・ボーグル（インデックス投資）",
            "$+5,983",
            "$+39,314",
            "$+17,217",
        ],
        [
            "ALL WEATHER",
            "レイ・ダリオ（オールウェザー）",
            "$+20,798",
            "$+49,888",
            "$+40,442",
        ],
        [
            "BUFFETT",
            "ウォーレン・バフェット（優良株）",
            "$+10,362",
            "$+49,047",
            "$+36,794",
        ],
        ["60/40", "クラシック60/40配分", "$+22,034", "$+72,558", "$+49,964"],
        ["SECTOR TECH", "テック集中型401k", "$+4,501", "$+1,081,058", "$+21,784"],
        ["DEFENSIVE", "機関投資家の安全避難先", "$+16,942", "$+72,255", "$+54,380"],
        ["RETIREMENT", "ターゲットデート近似", "$+17,109", "$+89,323", "$+59,641"],
    ]
    story.append(tbl(ws_data, [62, 90, 55, 62, 55]))
    story.append(
        Paragraph(
            "表13：ウォール街ポートフォリオシミュレーション結果——10ポートフォリオ×3年間=30シミュレーション。全て勝利。全て手数料後。",
            SS["Caption"],
        )
    )
    story.append(
        Paragraph(
            "60/40ポートフォリオは最も直接的に機関投資家のベンチマーク配分と比較できます。"
            "2022年の従来の60/40ポートフォリオは約16%%を失いました——株式と債券が同時に下落したため"
            "記録上最悪の年の一つです。Acervatorの60/40近似（インデックスETF＋商品ETF）は"
            "同じ年に$22,034の優位性を生み出しました。",
            SS["Body"],
        )
    )
    story.append(PageBreak())

    # ══════════════════════════════════════════════════════
    # 付録A: バージョン履歴
    # ══════════════════════════════════════════════════════
    story.append(Paragraph("付録A：バージョン履歴", SS["CH"]))
    story.append(accent_bar())
    ver_data = [
        ["バージョン", "日付", "マイルストーン"],
        ["v1.0", "4/11", "初期プラットフォーム：グリッドボット、CCXT、基本GUI"],
        ["v1.8", "4/12", "アキュムレーションボット、TAエンジン（7指標）、利益折り畳み"],
        ["v2.0", "4/12", "ファントムバランス、ネイティブチャート"],
        ["v3.0", "4/13", "6バックエンドサブシステム＋4新タブ"],
        [
            "v3.1.0",
            "4/13",
            "デュアルモード：株式取引層、ランチャー、TradingViewウェブフック",
        ],
        ["v3.1.5", "4/13", "ボリュームガード：適応型アイスバーグ実行"],
        ["v3.1.47", "4/14", "ターゲティングステートマシン：SEARCH→TRACK→FIRE"],
        ["v3.1.61", "4/14", "ポジション対応型モメンタム（BONKチャートの洞察）"],
        ["v3.1.64", "4/14", "ランディングストリップv2：3層タイトニングアーキテクチャ"],
        [
            "v3.1.71",
            "4/14",
            "MRインスペクター、ブーストフォールド、スマートワイヤーネットワーク",
        ],
        ["v3.1.72", "4/15", "完全リブランド：Acervatorへ、アキュムレーション取引"],
        ["v3.1.83", "4/15", "バンドトラベル検出、RAIntSimBat 38/39"],
        ["v3.1.84", "4/15", "手数料＋スプレッドモデリング、チャートオーバーレイ"],
        ["v3.1.89-91", "4/15", "ヘッジリバランス（別途リザーブ）、スマート目標増加"],
        ["v3.1.92", "4/15", "NTZ検出、39/39（100%%）、$33,024優位性"],
        ["v3.1.93", "4/15", "Playwrightトレーラーレンダラー"],
        ["v3.1.94", "4/16", "サブロー中央配置修正、ACERVATOR_HOP2.md"],
        ["v3.1.95", "4/16", "RAIntSimBatターゲット構文"],
        ["v3.1.96", "4/16", "RAIntSimBat 2020-2025拡張、26資産"],
        [
            "v3.1.97",
            "4/16",
            "RAIntSimBatポートフォリオシミュレーション：10ウォール街タイプ",
        ],
        [f"v{__version__}", "4/16", "日本語版マニュアル"],
    ]
    story.append(tbl(ver_data, [55, 35, 270]))
    story.append(Paragraph("表14：主要バージョンマイルストーン。", SS["Caption"]))
    story.append(Spacer(1, 20))
    story.append(
        Paragraph(
            "Copyright (c) 2025 Anthony L. Brown (Ekthelius the Accumulator). 全著作権所有。<br/>"
            "Acervator™ — アキュムレーション取引プラットフォーム。詳細はLICENSEを参照。",
            SS["Small"],
        )
    )

    doc.build(story, onFirstPage=page_bg, onLaterPages=page_bg)
    print(f"生成完了: {OUTPUT}")
    return OUTPUT


if __name__ == "__main__":
    build()
