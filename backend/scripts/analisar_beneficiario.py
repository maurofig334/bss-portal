"""
Descobre, nos dados reais, em que tipos o beneficiário é OUTRA pessoa.

Uso (do diretório backend/):
    venv/bin/python -m scripts.analisar_beneficiario

A REGRA (definida pela BSS em 17/07/2026)
------------------------------------------
    "Beneficiário é quem recebe uma indenização e que NÃO seja o próprio
     trabalhador. Ex.: num acidente grave o trabalhador pode estar
     incapacitado para receber o dinheiro; no falecimento é óbvio que vai
     para a viúva ou o filho. Beneficiário é alguém que recebe o benefício
     no lugar do trabalhador."

POR QUE MEDIR EM VEZ DE DEDUZIR
-------------------------------
Pela regra, dava pra deduzir "FALECIMENTO sempre tem, CONSULTA MÉDICA nunca
tem" e montar o formulário assim. Mas a tela do analista no legado mostra dois
processos de NATALIDADE lado a lado: num, o beneficiário é o próprio
trabalhador; no outro, é outra pessoa. Ou seja, a regra pode não ser "por
tipo", e sim "por caso".

Deduzir regra de negócio a partir de dois exemplos foi exatamente o erro do
protocolo — uma fórmula plausível, validada em 2 casos, que teria sobrescrito
19 mil números históricos. Aqui os 19 mil processos JÁ têm a resposta gravada:
basta comparar beneficiario_cpf com o CPF do trabalhador.

O resultado decide o formulário:
  - tipo em que beneficiário NUNCA difere → não mostrar o bloco;
  - tipo em que SEMPRE difere            → bloco obrigatório;
  - tipo em que ÀS VEZES difere          → bloco opcional, revelado por uma
                                            pergunta ("outra pessoa vai
                                            receber?") — e aí a regra não cabe
                                            em tipo_beneficio_campo.

NÃO GRAVA NADA.
"""

from app.database import get_pg_connection


def main() -> None:
    with get_pg_connection() as conn, conn.cursor() as cur:

        cur.execute(
            """
            SELECT
                tb.nome                                              AS tipo,
                count(*)                                             AS processos,
                count(*) FILTER (WHERE p.beneficiario_cpf IS NULL
                                    OR p.beneficiario_cpf = '')      AS sem_benef,
                count(*) FILTER (WHERE p.beneficiario_cpf IS NOT NULL
                                   AND p.beneficiario_cpf <> ''
                                   AND p.beneficiario_cpf = t.cpf)   AS benef_eh_o_trab,
                count(*) FILTER (WHERE p.beneficiario_cpf IS NOT NULL
                                   AND p.beneficiario_cpf <> ''
                                   AND t.cpf IS NOT NULL
                                   AND p.beneficiario_cpf <> t.cpf)  AS benef_outra_pessoa
              FROM bss.processo_beneficio p
              JOIN bss.tipo_beneficio tb ON tb.id = p.id_tipo_beneficio
              LEFT JOIN bss.trabalhador t ON t.id = p.id_trabalhador
             GROUP BY tb.nome, tb.ordem
             ORDER BY tb.ordem
            """
        )
        linhas = cur.fetchall()

        cab = (f"{'tipo':<24} {'proc':>6} {'sem benef':>10} "
               f"{'benef=trab':>11} {'benef=OUTRO':>12}  veredito")
        print("\n" + cab)
        print("-" * len(cab))

        for r in linhas:
            outro = r["benef_outra_pessoa"]
            igual = r["benef_eh_o_trab"]
            preenchidos = outro + igual

            if preenchidos == 0:
                veredito = "SEM bloco"
            elif outro == 0:
                veredito = "SEM bloco (nunca difere)"
            elif igual == 0:
                veredito = "bloco OBRIGATORIO"
            else:
                pct = 100.0 * outro / preenchidos
                veredito = f"bloco OPCIONAL ({pct:.0f}% difere)"

            print(f"{r['tipo'][:24]:<24} {r['processos']:>6} {r['sem_benef']:>10} "
                  f"{igual:>11} {outro:>12}  {veredito}")

        print("\n  sem benef   = beneficiario_cpf vazio → ninguém no lugar do trabalhador")
        print("  benef=trab  = preenchido, mas com o CPF do próprio trabalhador")
        print("  benef=OUTRO = preenchido com CPF de outra pessoa → é o caso real de uso")

        # 'benef=trab' alto é sintoma de formulário que obriga a preencher: o
        # usuário repete o trabalhador só pra conseguir salvar. Isso é ruído,
        # não informação — e é argumento pra NÃO obrigar no BSS.
        cur.execute(
            """
            SELECT
                count(*) FILTER (WHERE p.beneficiario_cpf = t.cpf) AS repetido,
                count(*) FILTER (WHERE p.beneficiario_cpf IS NOT NULL
                                   AND p.beneficiario_cpf <> '')   AS preenchido
              FROM bss.processo_beneficio p
              LEFT JOIN bss.trabalhador t ON t.id = p.id_trabalhador
            """
        )
        r = cur.fetchone()
        if r["preenchido"]:
            pct = 100.0 * r["repetido"] / r["preenchido"]
            print(f"\n  Beneficiário repetindo o trabalhador: "
                  f"{r['repetido']:,} de {r['preenchido']:,} ({pct:.1f}%)")
            if pct > 30:
                print("  ⚠ Muita repetição. Cheira a campo obrigatório sendo preenchido")
                print("    só pra deixar salvar — o formulário está pedindo dado que o")
                print("    caso não tem. No BSS, não obrigar.")

        # Grau de parentesco confirma a regra por outro caminho: se a maioria
        # for viúva/filho, o bloco é mesmo pra "no lugar do trabalhador".
        cur.execute(
            """
            SELECT COALESCE(NULLIF(TRIM(beneficiario_grau_parentesco), ''), '(vazio)') AS grau,
                   count(*) AS qtd
              FROM bss.processo_beneficio
             GROUP BY 1
             ORDER BY 2 DESC
             LIMIT 12
            """
        )
        print("\n=== Grau de parentesco do beneficiário ".ljust(60, "="))
        for r in cur.fetchall():
            print(f"  {r['grau'][:34]:<34} {r['qtd']:>7}")

    print()


if __name__ == "__main__":
    main()
