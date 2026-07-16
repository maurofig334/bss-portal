"""
AUTOCADASTRO — porta de entrada dos usuários externos. PROTÓTIPO PARA TESTES.

Fluxo (ver docs/AUTOCADASTRO.md):

    CNPJ digitado
     ├── EXISTE na base → "prossiga para cadastrar novo usuário"
     │                  → pede nome/telefone/senha
     └── NÃO existe     → consulta RFB → dados read-only → pede e-mail
                        ├── e-mail já é contato → vincula a nova empresa a ele
                        └── e-mail novo         → cria Empresa + Contato
     └──> TODO contato novo é aprovado por um ANALISTA INTERNO
     └──> vai pra tela de login

⚠️ ESTES ENDPOINTS SÃO PÚBLICOS — sem autenticação, por definição: é a porta de
entrada de quem ainda não tem conta. Consequências que PRECISAM ser tratadas
antes de produção:
  - rate limit / captcha (hoje qualquer um cria registro em loop)
  - a consulta de CNPJ revela se uma empresa é cliente da BSS (enumeração)
  - o cadastro dispara consulta à RFB — custo/limite do provedor

⚠️ RFB via BrasilAPI: gratuita, sem chave, sem SLA. Boa pra teste; a escolha do
provedor definitivo (BrasilAPI x ReceitaWS x Serpro) é decisão em aberto.
"""

from __future__ import annotations

import hashlib
import json
import re
import urllib.error
import urllib.request
from typing import Any

import bcrypt
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field, field_validator

from .database import get_pg_connection


router = APIRouter(prefix="/autocadastro", tags=["autocadastro"])

# Versão do texto do termo. Se o texto mudar, MUDE a versão — os aceites
# antigos referenciam a redação que a pessoa realmente viu.
TERMO_VERSAO = "2026-07-v1"
TERMO_TEXTO = (
    "Ao prosseguir com este cadastro, estou ciente da minha responsabilidade "
    "civil e criminal quanto à exatidão dos dados e quanto à segurança dos "
    "dados que irei incluir, considerando ser a principal finalidade o "
    "atendimento ao preconizado pela CCT - Convenção Coletiva de Trabalho, no "
    "tocante às contribuições mensais das empresas e a concessão de benefícios "
    "de CCT aos seus trabalhadores"
)
TERMO_HASH = hashlib.sha256(TERMO_TEXTO.encode()).hexdigest()

BRASILAPI = "https://brasilapi.com.br/api/cnpj/v1/{cnpj}"


def _so_digitos(s: str | None) -> str:
    return re.sub(r"\D", "", s or "")


def _valida_cnpj(cnpj: str) -> bool:
    """Validação de CNPJ com dígito verificador (não só o tamanho)."""
    c = _so_digitos(cnpj)
    if len(c) != 14 or c == c[0] * 14:
        return False
    for tam, pesos in ((12, [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]),
                       (13, [6, 5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2])):
        soma = sum(int(c[i]) * pesos[i] for i in range(tam))
        resto = soma % 11
        dv = 0 if resto < 2 else 11 - resto
        if int(c[tam]) != dv:
            return False
    return True


def _consultar_rfb(cnpj: str) -> dict[str, Any] | None:
    """
    Consulta a Receita via BrasilAPI. Devolve None se falhar — o cadastro NÃO
    pode morrer porque um serviço de terceiro está fora do ar.
    """
    try:
        req = urllib.request.Request(
            BRASILAPI.format(cnpj=cnpj),
            headers={"User-Agent": "BSS/autocadastro"},
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read().decode())
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, ValueError):
        return None


def _ip(request: Request) -> str | None:
    fwd = request.headers.get("x-forwarded-for")
    if fwd:
        return fwd.split(",")[0].strip()
    return request.client.host if request.client else None


# ---------------------------------------------------------------------------
# 1. Consulta de CNPJ — decide o ramo do fluxo
# ---------------------------------------------------------------------------

@router.get("/cnpj/{cnpj}")
def consultar_cnpj(cnpj: str):
    """
    Existe na base? Se sim, o cadastrante vira mais um gestor. Se não, busca a
    Receita e a empresa nasce junto.
    """
    c = _so_digitos(cnpj)
    if not _valida_cnpj(c):
        raise HTTPException(400, "CNPJ inválido")

    with get_pg_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT e.id, e.cnpj, e.razao_social, e.cidade, e.uf, e.status,
                       (SELECT COUNT(*) FROM bss.usuario_empresa ue
                         WHERE ue.id_empresa = e.id AND ue.ativo) AS gestores
                  FROM bss.empresa e
                 WHERE e.cnpj = %s
                 ORDER BY e.id
                 LIMIT 1
                """,
                (c,),
            )
            emp = cur.fetchone()

    if emp:
        return {
            "existe": True,
            "empresa": emp,
            "mensagem": "Este CNPJ já existe. Prossiga para cadastrar novo "
                        "usuário para administrar este CNPJ!",
        }

    rfb = _consultar_rfb(c)
    if not rfb:
        raise HTTPException(
            503,
            "Não foi possível consultar a Receita Federal agora. "
            "Tente novamente em alguns instantes.",
        )
    return {
        "existe": False,
        "empresa": None,
        "rfb": {
            "cnpj": c,
            "razao_social": rfb.get("razao_social"),
            "nome_fantasia": rfb.get("nome_fantasia"),
            "situacao_cadastral": rfb.get("descricao_situacao_cadastral"),
            "data_situacao_cadastral": rfb.get("data_situacao_cadastral"),
            "cnae_principal": str(rfb.get("cnae_fiscal") or ""),
            "cnae_descricao": rfb.get("cnae_fiscal_descricao"),
            "logradouro": f"{rfb.get('descricao_tipo_de_logradouro') or ''} {rfb.get('logradouro') or ''}".strip(),
            "numero": rfb.get("numero"),
            "complemento": rfb.get("complemento"),
            "bairro": rfb.get("bairro"),
            "cidade": rfb.get("municipio"),
            "uf": rfb.get("uf"),
            "cep": _so_digitos(rfb.get("cep")),
            "telefone": rfb.get("ddd_telefone_1"),
            "email": (rfb.get("email") or "").lower() or None,
        },
        "mensagem": "Empresa não cadastrada. Os dados abaixo vieram da Receita "
                    "Federal e não podem ser editados.",
    }


# ---------------------------------------------------------------------------
# 2. Gravação
# ---------------------------------------------------------------------------

# Validação de e-mail própria. NÃO usar pydantic.EmailStr: ele exige o pacote
# `email-validator`, que não está nas dependências — e o import estoura só na
# hora de montar o schema, derrubando a aplicação INTEIRA no boot
# (ImportError: email-validator is not installed). O projeto tem 10
# dependências, todas com propósito claro; não vale uma nova por causa de uma
# anotação de tipo.
RE_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]{2,}$")


class CadastroIn(BaseModel):
    cnpj: str
    email: str
    nome: str | None = Field(None, max_length=120)
    telefone: str | None = Field(None, max_length=20)
    senha: str | None = Field(None, min_length=8)
    aceite: bool

    @field_validator("email")
    @classmethod
    def _valida_email(cls, v: str) -> str:
        v = (v or "").strip().lower()
        if not RE_EMAIL.match(v):
            raise ValueError("e-mail inválido")
        return v


@router.post("")
def cadastrar(dados: CadastroIn, request: Request):
    """
    Cria (ou reaproveita) a empresa e o contato, e registra a solicitação de
    acesso — que fica PENDENTE até um analista interno aprovar.

    Idempotência: `uq_solic_pendente_por_par` (migration 17) impede dois pedidos
    pendentes pro mesmo par usuário×empresa. É a trava contra o duplo clique
    que encheu o legado de 94 e-mails duplicados.
    """
    if not dados.aceite:
        raise HTTPException(400, "É necessário aceitar o termo de responsabilidade")

    cnpj = _so_digitos(dados.cnpj)
    if not _valida_cnpj(cnpj):
        raise HTTPException(400, "CNPJ inválido")
    email = dados.email.lower().strip()
    ip = _ip(request)

    with get_pg_connection() as conn:
        with conn.cursor() as cur:
            # ---- Empresa: existe ou nasce da RFB --------------------------
            cur.execute("SELECT id FROM bss.empresa WHERE cnpj = %s ORDER BY id LIMIT 1", (cnpj,))
            row = cur.fetchone()
            if row:
                id_empresa = row["id"]
                preexistente = True
            else:
                rfb = _consultar_rfb(cnpj)
                if not rfb:
                    raise HTTPException(503, "Não foi possível consultar a Receita Federal agora.")
                cur.execute(
                    """
                    INSERT INTO bss.empresa (
                        cnpj, razao_social, nome_fantasia,
                        logradouro, numero, complemento, bairro, cidade, uf, cep,
                        telefone, email,
                        situacao_cadastral, data_situacao_cadastral,
                        cnae_principal, cnae_descricao, rfb_consultado_em,
                        tipo_cadastro, status_cadastro, status
                    )
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,NOW(),
                            'auto','pendente','ativa')
                    RETURNING id
                    """,
                    (
                        cnpj,
                        (rfb.get("razao_social") or "")[:255],
                        (rfb.get("nome_fantasia") or None),
                        f"{rfb.get('descricao_tipo_de_logradouro') or ''} {rfb.get('logradouro') or ''}".strip()[:150] or None,
                        (str(rfb.get("numero") or "") or None),
                        (rfb.get("complemento") or None),
                        (rfb.get("bairro") or None),
                        (rfb.get("municipio") or None),
                        (rfb.get("uf") or None),
                        _so_digitos(rfb.get("cep"))[:8] or None,
                        (rfb.get("ddd_telefone_1") or None),
                        ((rfb.get("email") or "").lower() or None),
                        (rfb.get("descricao_situacao_cadastral") or None),
                        (rfb.get("data_situacao_cadastral") or None),
                        (str(rfb.get("cnae_fiscal") or "") or None),
                        (rfb.get("cnae_fiscal_descricao") or None),
                    ),
                )
                id_empresa = cur.fetchone()["id"]
                preexistente = False

            # ---- Contato: existe ou nasce --------------------------------
            cur.execute("SELECT id, nome FROM bss_users WHERE email = %s", (email,))
            row = cur.fetchone()
            if row:
                id_usuario = row["id"]
                contato_novo = False
            else:
                if not dados.nome or not dados.senha:
                    raise HTTPException(400, "Nome e senha são obrigatórios para um novo usuário")
                senha_hash = bcrypt.hashpw(dados.senha.encode(), bcrypt.gensalt()).decode()
                cur.execute(
                    """
                    INSERT INTO bss_users (
                        email, nome, senha_hash, telefone, perfil, ativo,
                        tipo_cadastro, preferencias_notificacao
                    )
                    VALUES (%s,%s,%s,%s,'empresa', FALSE, 'auto',
                            '{"financeiro":true,"beneficio":true,"atualizacao":true,"boleto":true}'::jsonb)
                    RETURNING id
                    """,
                    (email, dados.nome.strip()[:120], senha_hash,
                     (dados.telefone or None)),
                )
                # ativo=FALSE: TODO contato novo espera aprovação de analista.
                id_usuario = cur.fetchone()["id"]
                contato_novo = True

            # ---- Aceite do termo (auditoria jurídica) ---------------------
            cur.execute(
                """
                INSERT INTO bss.aceite_termo
                    (id_usuario, id_empresa, versao, texto_hash, ip, user_agent)
                VALUES (%s,%s,%s,%s,%s,%s)
                """,
                (id_usuario, id_empresa, TERMO_VERSAO, TERMO_HASH, ip,
                 request.headers.get("user-agent")),
            )

            # ---- Solicitação de acesso (a fila do analista) ---------------
            try:
                cur.execute(
                    """
                    INSERT INTO bss.solicitacao_acesso
                        (id_usuario, id_empresa, origem, empresa_preexistente,
                         status, ip_origem)
                    VALUES (%s,%s,'autocadastro',%s,'pendente',%s)
                    RETURNING id
                    """,
                    (id_usuario, id_empresa, preexistente, ip),
                )
                id_solic = cur.fetchone()["id"]
                duplicada = False
            except Exception:
                # uq_solic_pendente_por_par: já existe pedido pendente pro par.
                # É o duplo clique — respondemos como sucesso, sem criar outra.
                conn.rollback()
                id_solic = None
                duplicada = True

            if not duplicada:
                conn.commit()

    return {
        "ok": True,
        "id_solicitacao": id_solic,
        "contato_novo": contato_novo,
        "empresa_preexistente": preexistente,
        "duplicada": duplicada,
        "mensagem": "Cadastro recebido. Seu acesso será liberado após análise "
                    "da nossa equipe — você receberá um aviso por e-mail.",
    }
