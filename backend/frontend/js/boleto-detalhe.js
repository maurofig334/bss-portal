/* Tela de detalhe do boleto — espelha o print do legado (task #30). */

const u = exigirLogin();
if (u) document.getElementById("usuario-info").textContent = `${u.nome} (${u.perfil})`;

const PERFIS_INTERNOS = ["admin", "interno"];
let _boleto = null;

function brl(n) { return Number(n || 0).toLocaleString("pt-BR", { style: "currency", currency: "BRL" }); }
function fmtData(d) { return d ? new Date(d).toLocaleDateString("pt-BR") : "—"; }
function fmtDataHora(d) {
  if (!d) return "—";
  return new Date(d).toLocaleString("pt-BR", { dateStyle: "short", timeStyle: "short" });
}
function fmtMesAno(d) {
  if (!d) return "—";
  const dt = new Date(d);
  const meses = ["JANEIRO","FEVEREIRO","MARÇO","ABRIL","MAIO","JUNHO","JULHO","AGOSTO","SETEMBRO","OUTUBRO","NOVEMBRO","DEZEMBRO"];
  return `${meses[dt.getUTCMonth()]} / ${dt.getUTCFullYear()}`;
}
function fmtMesAnoLong(d) {
  // "Abril/2026" (formato legado)
  if (!d) return "";
  const dt = new Date(d);
  const meses = ["Janeiro","Fevereiro","Março","Abril","Maio","Junho","Julho","Agosto","Setembro","Outubro","Novembro","Dezembro"];
  return `${meses[dt.getUTCMonth()]}/${dt.getUTCFullYear()}`;
}
function fmtCnpj(c) {
  if (!c) return "—";
  const d = String(c).replace(/\D/g, "");
  if (d.length === 14) return `${d.slice(0,2)}.${d.slice(2,5)}.${d.slice(5,8)}/${d.slice(8,12)}-${d.slice(12,14)}`;
  return c;
}
function fmtCpf(c) {
  if (!c) return "—";
  const d = String(c).replace(/\D/g, "");
  if (d.length === 11) return `${d.slice(0,3)}.${d.slice(3,6)}.${d.slice(6,9)}-${d.slice(9,11)}`;
  return c;
}

// Mapping DB → UI
const STATUS_LABEL = { gerado: "Aberto", pago: "Pago", vencido: "Vencido", cancelado: "Cancelado", pendente: "Pendente" };
const STATUS_COR   = {
  gerado: "bg-blue-100 text-blue-800",
  pago: "bg-emerald-100 text-emerald-800",
  vencido: "bg-rose-100 text-rose-800",
  pendente: "bg-amber-100 text-amber-800",
  cancelado: "bg-slate-200 text-slate-500 line-through",
};
function badgeStatus(s) {
  const label = STATUS_LABEL[s] || s || "—";
  const cor = STATUS_COR[s] || "bg-slate-100 text-slate-600";
  return `<span class="inline-block px-2 py-0.5 rounded-full text-xs ${cor}">${label}</span>`;
}

function par(label, valor, classCol = "md:col-span-6") {
  const v = (valor === null || valor === undefined || valor === "")
    ? '<span class="text-slate-400">—</span>'
    : valor;
  return `
    <div class="${classCol}">
      <div class="text-xs font-medium uppercase tracking-wider text-slate-500">${label}</div>
      <div class="mt-0.5 text-slate-800">${v}</div>
    </div>
  `;
}

function getIdFromUrl() {
  const u = new URL(window.location.href);
  return u.searchParams.get("id");
}

async function carregar() {
  const id = getIdFromUrl();
  if (!id) {
    document.getElementById("loading").classList.add("hidden");
    document.getElementById("erro").classList.remove("hidden");
    document.getElementById("erro").textContent = "ID do boleto não informado na URL.";
    return;
  }

  try {
    const b = await apiFetch(`/boletos/${id}/detalhe`);
    _boleto = b;
    render(b);
  } catch (e) {
    document.getElementById("loading").classList.add("hidden");
    document.getElementById("erro").classList.remove("hidden");
    document.getElementById("erro").textContent = `Erro: ${e.message}`;
  }
}

function render(b) {
  document.getElementById("loading").classList.add("hidden");
  document.getElementById("conteudo").classList.remove("hidden");

  // Título: "MAIO / 2026 - 57934846"
  document.getElementById("titulo").innerHTML = `
    ${fmtMesAno(b.mes_referencia)}
    <span class="text-slate-400 mx-2">·</span>
    <span class="font-mono text-base">${b.nosso_numero || b.numero_boleto || "—"}</span>
  `;

  // Bloco principal de informações
  const ativos = (b.qtd_trabalhadores || 0) + (b.qtd_dependentes || 0);
  const mes = new Date(b.mes_referencia);
  const grid = document.getElementById("grid-info");
  // Layout 2 colunas (mesmo que legado): label na esquerda, valor na direita
  // de cada par. Ordem espelha o print do legado.
  const boletoOrigemHtml = b.nosso_numero_origem
    ? `<a href="/app/boleto-detalhe.html?id=${b.id_boleto_substituido}" class="text-rose-600 hover:underline">${fmtMesAnoLong(b.mes_origem)} - Boleto ${b.nosso_numero_origem}</a>`
    : null;
  const boletoSubstHtml = b.nosso_numero_substituto
    ? `<a href="/app/boleto-detalhe.html?id=${b.id_substituto}" class="text-rose-600 hover:underline">Substituído por ${b.nosso_numero_substituto}</a>`
    : null;

  grid.innerHTML = [
    // Linha 1: Empresa | Responsável
    par("Empresa", `<a href="/app/empresas.html?busca=${encodeURIComponent(b.empresa_cnpj || '')}" class="text-rose-600 hover:underline font-medium">${b.empresa || '—'}</a>`),
    par("Responsável", null),
    // Linha 2: CNPJ | Tipo de Cobrança
    par("CNPJ da Empresa", b.empresa_cnpj ? `<span>${fmtCnpj(b.empresa_cnpj)}</span>` : null),
    par("Tipo de Cobrança", "Contribuição"),
    // Linha 3: Ano | Mês
    par("Ano", mes.getUTCFullYear()),
    par("Mês", mes.getUTCMonth() + 1),
    // Linha 4: Data Emissão | Data Vencimento
    par("Data de Emissão", fmtDataHora(b.data_emissao)),
    par("Data Vencimento", fmtData(b.data_vencimento)),
    // Linha 5: Ativos | Valor
    par("Ativos", `${ativos.toLocaleString("pt-BR")}`),
    par("Valor", `${brl(b.valor_total).replace('R$ ', '')}`),
    // Linha 6: Status | Data Pagamento
    par("Status", badgeStatus(b.status)),
    par("Data Pagamento", fmtData(b.data_pagamento)),
    // Linha 7: Tipo de Boleto | Observação
    par("Tipo de Boleto", b.tipo || null),
    par("Observação", null),
    // Linha 8: Regra | Banco
    par("Regra", b.parametro_nome || "—"),
    par("Banco", b.banco ? `<span class="font-mono">${b.banco}</span>` : null),
    // Linha 9: Boleto de origem | Importação OMIE
    par("Boleto de origem", boletoOrigemHtml),
    par("Importação OMIE", `<input type="checkbox" disabled class="w-4 h-4 align-middle">`),
    // Linha 10 (extra, fora do legado): substituído por / motivo de cancelamento
    boletoSubstHtml ? par("Substituído por", boletoSubstHtml, "md:col-span-12") : "",
    b.motivo_cancelamento ? par("Motivo do Cancelamento", b.motivo_cancelamento, "md:col-span-12") : "",
  ].join("");

  // Log
  document.getElementById("grid-log").innerHTML = [
    par("Data de Criação", fmtDataHora(b.criado_em)),
    par("Data de Modificação", fmtDataHora(b.atualizado_em)),
    par("Criado por (Portal)", null),
    par("Modificado por (Portal)", null),
  ].join("");

  // Trabalhadores — sanfona com sumário
  const qtdPessoas = b.itens.length;
  const somaTaxas = b.itens.reduce((acc, it) => acc + Number(it.taxa_aplicada || 0), 0);
  const totalLancamentos = b.itens.reduce((acc, it) => acc + Number(it.qtd_lancamentos || 1), 0);
  const temDuplicacao = b.itens.some(it => (it.qtd_lancamentos || 1) > 1);
  document.getElementById("qtd-itens").innerHTML =
    `<b>${qtdPessoas.toLocaleString("pt-BR")}</b> pessoa(s) · `
    + `total <b>${brl(somaTaxas)}</b>`
    + (temDuplicacao ? ` · <span class="text-amber-700">${totalLancamentos} lançamentos (com duplicações)</span>` : "")
    + ` <span class="ml-2 text-slate-400">▸ clique pra abrir</span>`;
  const tbody = document.getElementById("tbody-itens");
  if (qtdPessoas === 0) {
    tbody.innerHTML = `<tr><td colspan="6" class="px-3 py-6 text-center text-slate-400">Sem trabalhadores/dependentes vinculados</td></tr>`;
  } else {
    tbody.innerHTML = b.itens.map(it => {
      const dupBadge = (it.qtd_lancamentos || 1) > 1
        ? `<span class="ml-2 px-1.5 py-0.5 bg-amber-100 text-amber-800 rounded text-xs">${it.qtd_lancamentos}×</span>`
        : "";
      return `
      <tr class="border-t border-slate-100 hover:bg-slate-50">
        <td class="px-3 py-2">
          <a href="/app/trabalhadores.html?busca=${encodeURIComponent(it.cpf)}" class="text-indigo-700 hover:underline">${it.nome_completo || "—"}</a>${dupBadge}
        </td>
        <td class="px-3 py-2 font-mono text-xs">${fmtCpf(it.cpf)}</td>
        <td class="px-3 py-2 text-center">
          <span class="inline-block px-2 py-0.5 rounded text-xs ${it.eh_dependente ? "bg-purple-100 text-purple-800" : "bg-slate-100 text-slate-700"}">
            ${it.eh_dependente ? "Dependente" : "Titular"}
          </span>
        </td>
        <td class="px-3 py-2 text-center text-xs">${(it.situacao || "—").toUpperCase()}</td>
        <td class="px-3 py-2 text-right font-mono">${brl(it.taxa_aplicada)}</td>
        <td class="px-3 py-2 text-center text-xs text-slate-500">${fmtData(it.data_admissao)}</td>
      </tr>
    `;}).join("");
  }

  // Botões de ação conforme status:
  const btnPdf      = document.getElementById("btn-pdf");
  const btnLista    = document.getElementById("btn-lista");
  const btnReemitir = document.getElementById("btn-reemitir");
  const btnCancelar = document.getElementById("btn-cancelar");

  if (b.status === "gerado" || b.status === "pendente") {
    btnPdf.classList.remove("hidden");
    btnLista.classList.remove("hidden");
  } else if (b.status === "vencido") {
    btnLista.classList.remove("hidden");
    btnReemitir.classList.remove("hidden");
  }
  // Cancelar só pra admin/interno e se ainda for vivo:
  if (PERFIS_INTERNOS.includes(u.perfil) && !["cancelado","pago"].includes(b.status)) {
    btnCancelar.classList.remove("hidden");
  }
}

async function abrirPdf() {
  try { await apiAbrirPdf(`/boletos/${_boleto.id}/pdf`); }
  catch (e) { alert(`Erro: ${e.message}`); }
}
async function abrirLista() {
  try { await apiAbrirPdf(`/boletos/${_boleto.id}/lista-pdf`); }
  catch (e) { alert(`Erro: ${e.message}`); }
}
async function reemitir() {
  if (!confirm("Reemitir este boleto?\n\nO atual será CANCELADO e um novo será emitido com nova data de vencimento.")) return;
  try {
    const r = await apiFetch(`/boletos/${_boleto.id}/reemitir`, { method: "POST" });
    alert(`Boleto reemitido. Novo nº ${r.nosso_numero}, vencimento ${fmtData(r.data_vencimento)}`);
    window.location.href = `/app/boleto-detalhe.html?id=${r.id_boleto_novo}`;
  } catch (e) {
    alert(`Erro: ${e.message}`);
  }
}
async function cancelar() {
  const motivo = prompt("Motivo do cancelamento:");
  if (!motivo) return;
  try {
    await apiFetch(`/boletos/${_boleto.id}/cancelar`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ motivo }),
    });
    alert("Boleto cancelado.");
    carregar();   // reload
  } catch (e) {
    alert(`Erro: ${e.message}`);
  }
}

carregar();
