"""
Dashboard / KPIs do BSS.

GET /dashboard/kpis            → cards principais (totais)
GET /dashboard/serie-mensal    → série de boletos pagos x mês (12 meses)
GET /dashboard/processos-status → distribuição de processos por status
GET /dashboard/tipos-beneficio → distribuição de processos por tipo
"""

from typing import Annotated

from fastapi import APIRouter, Depends

from .auth import UsuarioInfo, usuario_logado
from .database import get_pg_connection


router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("/kpis")
def kpis(usuario: Annotated[UsuarioInfo, Depends(usuario_logado)]):
    """Totais principais — usados nos cards do topo do dashboard."""
    sql = """
        SELECT
            (SELECT COUNT(*) FROM bss.empresa WHERE status = 'ativa')                       AS empresas_ativas,
            (SELECT COUNT(*) FROM bss.empresa WHERE adimplencia = 'inadimplente')           AS empresas_inadimplentes,
            (SELECT COUNT(*) FROM bss.empresa WHERE regularidade = 'irregular')             AS empresas_irregulares,
            (SELECT COUNT(*) FROM bss.trabalhador WHERE situacao = 'ativo')                 AS trabalhadores_ativos,
            (SELECT COUNT(*) FROM bss.trabalhador)                                          AS trabalhadores_total,
            (SELECT COUNT(*) FROM bss.processo_beneficio
              WHERE status NOT IN ('beneficio_finalizado','solicitacao_cancelada'))         AS processos_abertos,
            (SELECT COUNT(*) FROM bss.processo_beneficio)                                   AS processos_total,
            (SELECT COUNT(*) FROM bss.boleto WHERE status = 'pago')                         AS boletos_pagos,
            (SELECT COUNT(*) FROM bss.boleto)                                               AS boletos_total,
            (SELECT COALESCE(SUM(valor_total),0) FROM bss.boleto WHERE status = 'pago')     AS faturamento_total
    """
    with get_pg_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(sql)
            return cur.fetchone()


@router.get("/serie-mensal")
def serie_mensal(
    usuario: Annotated[UsuarioInfo, Depends(usuario_logado)],
    meses: int = 12,
):
    """Série mensal de boletos pagos (qtd + valor) nos últimos N meses."""
    meses = max(1, min(36, int(meses)))
    sql = """
        SELECT
            mes_referencia,
            COUNT(*) FILTER (WHERE status='pago')                                AS pagos_qtd,
            COUNT(*) FILTER (WHERE status IN ('vencido','enviado','gerado'))     AS abertos_qtd,
            COALESCE(SUM(valor_total) FILTER (WHERE status='pago'), 0)           AS pagos_valor
        FROM bss.boleto
        WHERE mes_referencia >= (DATE_TRUNC('month', CURRENT_DATE) - (%s || ' months')::interval)::date
        GROUP BY mes_referencia
        ORDER BY mes_referencia ASC
    """
    with get_pg_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (str(meses),))
            return list(cur.fetchall())


@router.get("/processos-status")
def processos_status(usuario: Annotated[UsuarioInfo, Depends(usuario_logado)]):
    """Distribuição de processos por status (pra gráfico de pizza/donut)."""
    sql = """
        SELECT
            sp.codigo, sp.nome, sp.categoria, sp.cor_hex, sp.ordem,
            COUNT(p.id) AS qtd
        FROM bss.status_processo sp
        LEFT JOIN bss.processo_beneficio p ON p.status = sp.codigo
        WHERE sp.ativo
        GROUP BY sp.codigo, sp.nome, sp.categoria, sp.cor_hex, sp.ordem
        HAVING COUNT(p.id) > 0
        ORDER BY sp.ordem
    """
    with get_pg_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(sql)
            return list(cur.fetchall())


@router.get("/tipos-beneficio")
def tipos_beneficio(usuario: Annotated[UsuarioInfo, Depends(usuario_logado)]):
    """Distribuição de processos por tipo de benefício."""
    sql = """
        SELECT tb.codigo, tb.nome, COUNT(p.id) AS qtd
        FROM bss.tipo_beneficio tb
        LEFT JOIN bss.processo_beneficio p ON p.id_tipo_beneficio = tb.id
        GROUP BY tb.codigo, tb.nome, tb.ordem
        HAVING COUNT(p.id) > 0
        ORDER BY tb.ordem
    """
    with get_pg_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(sql)
            return list(cur.fetchall())
