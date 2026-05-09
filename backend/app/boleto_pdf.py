"""
Geração de PDFs de boletos e listas de trabalhadores — épico #21.

Estes PDFs são VISUAIS apenas (mockup pra demo). A linha digitável e o código
de barras são placeholders — a integração bancária real (geração de boleto
registrado via API do Itaú/Bradesco) fica pra épico separado.

Layout do boleto: estilo Itaú 341-7 (FICHA DE COMPENSAÇÃO) + cabeçalho BSS
com info de amparo/competência/quantidade.

Layout da lista: simples — cabeçalho BSS + dados do boleto + lista nome-CPF-tipo.
"""

from __future__ import annotations

import io
from datetime import datetime
from pathlib import Path
from typing import Any

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm, mm
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas
from reportlab.platypus import (
    Image, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle,
)

from .database import get_pg_connection


# Caminho absoluto pro logo (independente de cwd):
_LOGO_PATH = Path(__file__).resolve().parent.parent / "frontend" / "img" / "bss_logo.png"
_LOGO_PATH_STR = str(_LOGO_PATH) if _LOGO_PATH.exists() else None


# Dados fixos do cedente (GNB / BSS):
CEDENTE_NOME = "BENEFICIO SOCIAL SINDICAL"
CEDENTE_CNPJ = "36.239.947/0001-05"
BANCO_NOME = "Itaú S.A."
BANCO_CODIGO = "341-7"
AGENCIA = "7690"
TELEFONE_BSS = "0800 580 3816"
EMAIL_BSS = "FINANCEIRO@BSSINDICAL.COM.BR"
EMAIL_INFORME = "INFORME@BSSINDICAL.COM.BR"

# Cores BSS (azul corporativo do logo):
COR_AZUL_BSS = colors.HexColor("#1E3A8A")
COR_AZUL_CLARO = colors.HexColor("#DBEAFE")


# =============================================================================
# Helpers de formatação
# =============================================================================

def _fmt_cnpj(cnpj: str | None) -> str:
    if not cnpj:
        return ""
    d = "".join(c for c in cnpj if c.isdigit())
    if len(d) == 14:
        return f"{d[0:2]}.{d[2:5]}.{d[5:8]}/{d[8:12]}-{d[12:14]}"
    return cnpj


def _fmt_cpf(cpf: str | None) -> str:
    if not cpf:
        return ""
    d = "".join(c for c in cpf if c.isdigit())
    if len(d) == 11:
        return f"{d[0:3]}.{d[3:6]}.{d[6:9]}-{d[9:11]}"
    return cpf


def _fmt_data(d: Any) -> str:
    if not d:
        return ""
    if isinstance(d, datetime):
        return d.strftime("%d/%m/%Y")
    if hasattr(d, "strftime"):
        return d.strftime("%d/%m/%Y")
    return str(d)


def _fmt_datahora(d: Any) -> str:
    if not d:
        return ""
    if isinstance(d, datetime):
        return d.strftime("%d/%m/%Y %H:%M")
    if hasattr(d, "strftime"):
        return d.strftime("%d/%m/%Y %H:%M")
    return str(d)


def _fmt_valor(v: Any) -> str:
    if v is None:
        return ""
    try:
        x = float(v)
    except (TypeError, ValueError):
        return str(v)
    return f"{x:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


_MESES_PT = {
    1: "Janeiro", 2: "Fevereiro", 3: "Março", 4: "Abril",
    5: "Maio", 6: "Junho", 7: "Julho", 8: "Agosto",
    9: "Setembro", 10: "Outubro", 11: "Novembro", 12: "Dezembro",
}


def _mes_pt(d) -> str:
    if not d:
        return ""
    return f"{_MESES_PT.get(d.month, '')}/{d.year}"


def _competencia_pt(mes_amparo) -> str:
    """mes_amparo (date) → mês/ano da competência (= amparo - 1 mês) em pt-BR."""
    if not mes_amparo:
        return ""
    m = mes_amparo.month - 1 or 12
    a = mes_amparo.year if mes_amparo.month > 1 else mes_amparo.year - 1
    return f"{_MESES_PT.get(m, '')}/{a}"


def _status_label(s: str | None) -> str:
    """Mapping DB → UI."""
    if not s:
        return ""
    if s == "gerado":
        return "Aberto"
    return s.capitalize()


# =============================================================================
# Carrega dados do boleto (1 query consolidada)
# =============================================================================

def _carregar_boleto(id_boleto: int) -> dict[str, Any] | None:
    sql = """
        SELECT b.id, b.nosso_numero, b.numero_boleto, b.banco,
               b.mes_referencia, b.data_emissao, b.data_vencimento,
               b.valor_total, b.qtd_trabalhadores, b.qtd_dependentes,
               b.status, b.tipo,
               e.razao_social AS empresa, e.cnpj AS empresa_cnpj,
               s.razao_social AS sindicato,
               p.nome         AS parametro_nome
          FROM bss.boleto b
          LEFT JOIN bss.empresa  e ON e.id = b.id_empresa
          LEFT JOIN bss.sindicato s ON s.id = b.id_sindicato
          LEFT JOIN bss.parametros_boleto p
                 ON p.id_sindicato = s.id AND p.ativo
         WHERE b.id = %s
    """
    with get_pg_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (id_boleto,))
            return cur.fetchone()


def _carregar_itens(id_boleto: int) -> list[dict[str, Any]]:
    sql = """
        SELECT bi.id_trabalhador, bi.taxa_aplicada, bi.eh_dependente,
               t.nome_completo, t.cpf, t.titularidade
          FROM bss.boleto_item bi
          JOIN bss.trabalhador t ON t.id = bi.id_trabalhador
         WHERE bi.id_boleto = %s
         ORDER BY bi.eh_dependente, t.nome_completo
    """
    with get_pg_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (id_boleto,))
            return cur.fetchall()


# =============================================================================
# PDF da Lista de Trabalhadores
# =============================================================================

def gerar_pdf_lista(id_boleto: int) -> bytes | None:
    """Lista de trabalhadores vinculados ao boleto."""
    b = _carregar_boleto(id_boleto)
    if not b:
        return None
    itens = _carregar_itens(id_boleto)

    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=A4,
        leftMargin=2*cm, rightMargin=2*cm,
        topMargin=2*cm, bottomMargin=2*cm,
        title=f"Lista do Boleto {b['nosso_numero']}",
        author="BSS - Benefício Social Sindical",
    )
    styles = getSampleStyleSheet()
    titulo_st = ParagraphStyle("titulo", parent=styles["Heading1"],
                               textColor=COR_AZUL_BSS, fontSize=14,
                               spaceAfter=12)
    label_st = ParagraphStyle("label", parent=styles["BodyText"],
                              fontSize=10, leading=14)
    item_st = ParagraphStyle("item", parent=styles["BodyText"],
                             fontSize=10, leading=16)

    elems: list[Any] = []

    # Logo:
    if _LOGO_PATH_STR:
        try:
            img = Image(_LOGO_PATH_STR, width=4*cm, height=4*cm, kind='proportional')
            elems.append(img)
        except Exception:
            elems.append(Paragraph(
                f'<b><font color="#1E3A8A" size="16">BENEFÍCIO</font></b> '
                f'<font color="#1E3A8A" size="14">SOCIAL SINDICAL</font>',
                styles["Normal"]))
    else:
        elems.append(Paragraph(
            f'<b><font color="#1E3A8A" size="16">BENEFÍCIO</font></b> '
            f'<font color="#1E3A8A" size="14">SOCIAL SINDICAL</font>',
            styles["Normal"]))
    elems.append(Spacer(1, 8*mm))

    elems.append(Paragraph("LISTA DE TRABALHADORES / DEPENDENTES VINCULADOS AO BOLETO",
                            titulo_st))
    elems.append(Spacer(1, 4*mm))

    elems.append(Paragraph(f"<b>Empresa:</b> {b['empresa'] or ''}", label_st))
    elems.append(Paragraph(f"<b>CNPJ/MF:</b> {_fmt_cnpj(b['empresa_cnpj'])}", label_st))
    elems.append(Paragraph(f"<b>Nº de documento:</b> {b['nosso_numero'] or ''}", label_st))
    elems.append(Paragraph(f"<b>Emissão:</b> {_fmt_datahora(b['data_emissao'])}", label_st))
    elems.append(Paragraph(f"<b>Vencimento:</b> {_fmt_data(b['data_vencimento'])}", label_st))
    elems.append(Paragraph(f"<b>Valor:</b> R$ {_fmt_valor(b['valor_total'])}", label_st))
    elems.append(Paragraph(f"<b>Status:</b> {_status_label(b['status'])}", label_st))
    elems.append(Spacer(1, 6*mm))

    elems.append(Paragraph(
        "<b>Informamos que os seguintes Trabalhadores / Dependentes estão "
        "relacionados neste boleto:</b>", label_st))
    elems.append(Spacer(1, 4*mm))

    for it in itens:
        tipo = "DEPENDENTE" if it["eh_dependente"] else "TRABALHADOR"
        nome = (it["nome_completo"] or "").strip()
        cpf = _fmt_cpf(it["cpf"])
        elems.append(Paragraph(f"{nome} - {cpf} - {tipo}", item_st))

    if not itens:
        elems.append(Paragraph("<i>Sem trabalhadores/dependentes vinculados.</i>", item_st))

    doc.build(elems)
    return buf.getvalue()


# =============================================================================
# PDF do Boleto (mockup estilo Itaú 341-7)
# =============================================================================

def _desenhar_cabecalho_bss(c: canvas.Canvas, b: dict[str, Any], y_topo: float):
    """Desenha o bloco superior do boleto: logo + dados do empregador + amparo."""
    largura, _ = A4
    x0 = 2*cm
    x_end = largura - 2*cm

    # ===== Logo à esquerda + Info à direita =====
    if _LOGO_PATH_STR:
        # 4cm de largura, mantendo proporção da imagem original:
        c.drawImage(_LOGO_PATH_STR, x0, y_topo - 50, width=4*cm, height=50,
                    preserveAspectRatio=True, mask='auto', anchor='nw')
    else:
        c.setFillColor(COR_AZUL_BSS)
        c.setFont("Helvetica-Bold", 18)
        c.drawString(x0, y_topo - 14, "BENEFÍCIO")
        c.setFont("Helvetica", 14)
        c.drawString(x0, y_topo - 30, "SOCIAL SINDICAL")

    c.setFillColor(colors.black)
    c.setFont("Helvetica-Bold", 9)
    c.drawRightString(x_end, y_topo - 14, "INFORMAÇÕES OU DÚVIDAS")
    c.setFont("Helvetica", 9)
    c.drawRightString(x_end, y_topo - 26, TELEFONE_BSS)
    c.drawRightString(x_end, y_topo - 38, EMAIL_BSS)

    # ===== Box "Empregador / CNPJ / Data Emissão" =====
    y = y_topo - 56
    box_h = 36
    c.setStrokeColor(COR_AZUL_BSS)
    c.setLineWidth(0.5)
    c.rect(x0, y - box_h, x_end - x0, box_h, fill=0)

    # 2 linhas dentro do box: linha 1 = Empregador; linha 2 = CNPJ + Data Emissão
    y_lin1 = y - 14
    y_lin2 = y - 28
    c.setFillColor(colors.black)
    c.setFont("Helvetica-Bold", 9)
    c.drawString(x0 + 5, y_lin1, "Empregador:")
    c.setFont("Helvetica", 9)
    c.drawString(x0 + 65, y_lin1, b.get("empresa") or "")

    c.setFont("Helvetica-Bold", 9)
    c.drawString(x0 + 5, y_lin2, "CNPJ / CPF:")
    c.setFont("Helvetica", 9)
    c.drawString(x0 + 65, y_lin2, _fmt_cnpj(b.get("empresa_cnpj")))
    c.setFont("Helvetica-Bold", 9)
    c.drawRightString(x_end - 130, y_lin2, "Data Emissão:")
    c.setFont("Helvetica", 9)
    c.drawRightString(x_end - 5, y_lin2, _fmt_datahora(b.get("data_emissao")))

    # ===== Faixa azul "Este boleto destina-se ao pagamento..." =====
    y2 = y - box_h
    faixa_h = 16
    c.setFillColor(COR_AZUL_BSS)
    c.rect(x0, y2 - faixa_h, x_end - x0, faixa_h, fill=1, stroke=0)
    c.setFillColor(colors.white)
    c.setFont("Helvetica-Bold", 9)
    c.drawCentredString(largura/2, y2 - 11,
                        "Este boleto destina-se ao pagamento do "
                        "Benefício Social Sindical de seus trabalhadores")

    # ===== Box info amparo (3 linhas, cada uma com label esq + valor dir) =====
    qtd_total = (b.get("qtd_trabalhadores") or 0) + (b.get("qtd_dependentes") or 0)
    y3 = y2 - faixa_h
    bloco_h = 60   # 3 linhas × 20pt cada
    c.setFillColor(colors.black)
    c.setStrokeColor(COR_AZUL_BSS)
    c.rect(x0, y3 - bloco_h, x_end - x0, bloco_h, fill=0)

    # Cada linha com 4 elementos: [label_esq] [valor_esq] [label_dir] [valor_dir]
    # Posições X (em pontos absolutos):
    x_label_esq = x0 + 5
    x_valor_esq = x0 + 200    # esquerda larga (labels longos: "Período de amparo desta contribuição:")
    x_label_dir = x0 + 320
    x_valor_dir = x_end - 5

    linhas_amparo = [
        ("Período de amparo:",                  _mes_pt(b.get("mes_referencia")),
         "Vencimento:",                          _fmt_data(b.get("data_vencimento"))),
        ("Trabalhadores / Dependentes amparados:", f"{qtd_total} Ativos",
         "Segmento:",                            b.get("parametro_nome") or ""),
        ("Competência:",                         _competencia_pt(b.get("mes_referencia")),
         "",                                      ""),
    ]
    for i, (lbl_e, val_e, lbl_d, val_d) in enumerate(linhas_amparo):
        y_lin = y3 - 14 - i*18  # 18pt entre linhas
        c.setFont("Helvetica-Bold", 9)
        c.drawString(x_label_esq, y_lin, lbl_e)
        c.setFont("Helvetica", 9)
        c.drawString(x_valor_esq, y_lin, val_e)
        if lbl_d:
            c.setFont("Helvetica-Bold", 9)
            c.drawString(x_label_dir, y_lin, lbl_d)
            c.setFont("Helvetica", 9)
            c.drawRightString(x_valor_dir, y_lin, val_d)

    return y3 - bloco_h  # base do bloco superior


def _row_2cols(c: canvas.Canvas, x0: float, x_mid: float, x_end: float,
               y: float, h: float,
               label1: str, val1: str, label2: str, val2: str,
               linha_meio: bool = True):
    """Desenha 2 células lado-a-lado (label no topo, valor maior embaixo).
    Padrão Itaú: label 6pt, valor 9pt, padding interno generoso pra não 'trepar'.
    """
    c.setLineWidth(0.3)
    c.rect(x0, y, x_end - x0, h, fill=0)
    if linha_meio:
        c.line(x_mid, y, x_mid, y + h)
    # Labels (topo da célula):
    c.setFont("Helvetica", 6)
    c.drawString(x0 + 3, y + h - 7, label1)
    if label2:
        c.drawString(x_mid + 3, y + h - 7, label2)
    # Valores (centro da célula):
    c.setFont("Helvetica", 9)
    c.drawString(x0 + 3, y + 5, str(val1) if val1 is not None else "")
    if label2:
        c.drawString(x_mid + 3, y + 5, str(val2) if val2 is not None else "")


def _row_4cols(c: canvas.Canvas, xs: list[float], y: float, h: float,
               vals: list[tuple[str, str]]):
    """Desenha 4 células lado-a-lado. xs tem 5 elementos (4 colunas)."""
    c.setLineWidth(0.3)
    c.rect(xs[0], y, xs[4] - xs[0], h, fill=0)
    for i in range(1, 4):
        c.line(xs[i], y, xs[i], y + h)
    c.setFont("Helvetica", 6)
    for i, (label, _) in enumerate(vals):
        c.drawString(xs[i] + 3, y + h - 7, label)
    c.setFont("Helvetica", 9)
    for i, (_, val) in enumerate(vals):
        c.drawString(xs[i] + 3, y + 5, str(val) if val is not None else "")


def _desenhar_ficha_compensacao(c: canvas.Canvas, b: dict[str, Any], y_topo: float):
    """Desenha o canhoto do banco (estilo Itaú 341-7) — visual mockup."""
    largura, _ = A4
    nosso = b.get("nosso_numero") or ""
    valor_str = _fmt_valor(b.get("valor_total"))
    venc_str = _fmt_data(b.get("data_vencimento"))
    emi_str = _fmt_data(b.get("data_emissao"))
    sacado = (b.get("empresa") or "") + " - " + _fmt_cnpj(b.get("empresa_cnpj"))

    # Linha digitável (mockup):
    digital = (
        f"34191.09206 50787.{nosso[:6].rjust(6,'0')} 09925.030000 2 "
        f"14430000{int(float(b.get('valor_total') or 0)*100):010d}"
    )

    cell_h = 22  # altura padrão das células (suficiente pra label 6pt + valor 9pt)
    x0 = 2*cm
    x_end = largura - 2*cm
    # Para fichas com 4 colunas: cedente | doc | venc | valor
    xs4 = [x0, x0 + (x_end-x0)*0.40, x0 + (x_end-x0)*0.62,
           x0 + (x_end-x0)*0.80, x_end]
    x_mid = x0 + (x_end-x0)*0.55  # divisor pra layout 2 colunas

    # ===== Banner Itaú + linha digitável =====
    y = y_topo
    c.setStrokeColor(colors.black)
    c.setLineWidth(1)
    c.line(x0, y, x_end, y)
    c.setFont("Helvetica-Bold", 14)
    c.drawString(x0, y - 14, "Itaú")
    c.setFont("Helvetica", 9)
    c.drawString(x0 + 1.4*cm, y - 14, f"Banco {BANCO_NOME}")
    c.setFont("Helvetica-Bold", 14)
    c.drawString(x0 + 4.5*cm, y - 14, BANCO_CODIGO)
    c.setFont("Helvetica-Bold", 10)
    c.drawString(x0 + 6.2*cm, y - 14, digital)
    c.line(x0, y - 18, x_end, y - 18)

    # ===== Recibo do sacado (4 linhas estilo 2-col) =====
    y -= 18
    rows1 = [
        ("Cedente", CEDENTE_NOME,                "CPF/CNPJ",            CEDENTE_CNPJ),
        ("Sacado",  sacado,                      "Nº do Documento",     nosso),
        ("Espécie", "R$",                        "(=) Valor",           valor_str),
        ("Agência", AGENCIA,                     "Vencimento",          venc_str),
    ]
    for l1, v1, l2, v2 in rows1:
        y -= cell_h
        _row_2cols(c, x0, x_mid, x_end, y, cell_h, l1, v1, l2, v2)

    # ===== Banner repetido (ficha de compensação) =====
    y -= 16
    c.setLineWidth(1)
    c.line(x0, y, x_end, y)
    c.setFont("Helvetica-Bold", 14)
    c.drawString(x0, y - 14, "Itaú")
    c.setFont("Helvetica-Bold", 14)
    c.drawString(x0 + 4.5*cm, y - 14, BANCO_CODIGO)
    c.setFont("Helvetica-Bold", 10)
    c.drawString(x0 + 6.2*cm, y - 14, digital)
    c.line(x0, y - 18, x_end, y - 18)
    y -= 18

    # ===== Linhas principais da ficha =====
    rows2 = [
        ("Local de pagamento",   "PAGÁVEL EM QUALQUER BANCO",  "Vencimento",                venc_str),
        ("Cedente",              CEDENTE_NOME,                  "Agência / Código cedente",  AGENCIA),
        ("Data documento",       emi_str,                        "Nº do Documento",           nosso),
        ("Espécie",              "REAL",                         "(=) Valor do Documento",    valor_str),
    ]
    for l1, v1, l2, v2 in rows2:
        y -= cell_h
        _row_2cols(c, x0, x_mid, x_end, y, cell_h, l1, v1, l2, v2)

    # ===== Bloco de instruções (texto livre) =====
    bloco_h = 70
    y -= bloco_h
    c.setLineWidth(0.3)
    c.rect(x0, y, x_end - x0, bloco_h, fill=0)
    c.setFont("Helvetica", 6)
    c.drawString(x0 + 3, y + bloco_h - 7, "Instruções (Texto de responsabilidade do cedente)")
    c.setFont("Helvetica", 8)
    instr = [
        "Este documento refere-se à contribuição do Benefício Social Sindical, previsto em",
        "acordo ou Convenção Coletiva de Trabalho, firmado entre Sindicatos de Trabalhadores",
        f"e de Empresas. Em caso de dúvidas, ligue {TELEFONE_BSS} ou envie e-mail para",
        f"{EMAIL_BSS.lower()}. Após o vencimento, acréscimo de multa 10% e juros 0%.",
    ]
    for i, line in enumerate(instr):
        c.drawString(x0 + 5, y + bloco_h - 18 - i*11, line)

    # ===== Sacado (linha final) =====
    y -= cell_h
    c.setLineWidth(0.3)
    c.rect(x0, y, x_end - x0, cell_h, fill=0)
    c.setFont("Helvetica", 6)
    c.drawString(x0 + 3, y + cell_h - 7, "Sacado")
    c.setFont("Helvetica", 9)
    c.drawString(x0 + 3, y + 5, sacado)

    # ===== Código de barras placeholder + selo =====
    y -= 35
    c.setFillColor(colors.black)
    bar_x = x0
    for i, ch in enumerate(digital.replace(" ", "").replace(".", "")[:30]):
        h = 28 if int(ch) % 2 == 0 else 18
        c.rect(bar_x + i*5, y, 2.5, h, fill=1, stroke=0)
    c.setFont("Helvetica", 6)
    c.drawRightString(x_end, y + 8, "Autenticação mecânica - FICHA DE COMPENSAÇÃO")


def gerar_pdf_boleto(id_boleto: int) -> bytes | None:
    """Gera o PDF visual do boleto (mockup Itaú 341-7)."""
    b = _carregar_boleto(id_boleto)
    if not b:
        return None

    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    c.setTitle(f"Boleto {b['nosso_numero']}")
    c.setAuthor("BSS - Benefício Social Sindical")

    largura, altura = A4

    # Página 1: cabeçalho + ficha de compensação
    y_topo = altura - 2*cm
    base = _desenhar_cabecalho_bss(c, b, y_topo)
    _desenhar_ficha_compensacao(c, b, base - 8)

    # Página 2: cabeçalho repetido + nota de responsabilidade
    c.showPage()
    y_topo = altura - 2*cm
    _desenhar_cabecalho_bss(c, b, y_topo)
    c.setFont("Helvetica-Bold", 11)
    c.drawCentredString(largura/2, altura/2 + 1*cm,
                        "FICA DE RESPONSABILIDADE DA EMPRESA ENVIAR PARA O EMAIL")
    c.drawCentredString(largura/2, altura/2,
                        f"{EMAIL_INFORME} A RELAÇÃO DOS TRABALHADORES")
    c.drawCentredString(largura/2, altura/2 - 1*cm,
                        "AMPARADOS PARA A COMPETÊNCIA DO MÊS CONTRIBUÍDO.")

    c.save()
    return buf.getvalue()
