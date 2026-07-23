/* Contas a Pagar — listar, liquidar, exportar. Só interno (o backend barra). */

const u = exigirLogin();
if (u) document.getElementById("usuario-info").textContent = `${u.nome} (${u.perfil})`;

let pagina = 1;
let timer = null;
const _selecionados = new Set();   // ids marcados (persistem entre páginas)

function esc(s) {
  return String(s ?? "").replace(/[&<>"']/g, c => (
    { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}
function brl(n) {
  return Number(n || 0).toLocaleString("pt-BR", { style: "currency", currency: "BRL" });
}
function fmtData(d) { return d ? new Date(d).toLocaleDateString("pt-BR") : "—"; }
function fmtCpf(c) {
  const d = String(c || "").replace(/\D/g, "");
  return d.length === 11 ? d.replace(/(\d{3})(\d{3})(\d{3})(\d{2})/, "$1.$2.$3-$4") : (c || "—");
}

function ler() {
  return {
    busca: document.getElementById("f-busca").value.trim(),
    status: document.getElementById("f-status").value,
    forma: document.getElementById("f-forma").value,
    data_de: document.getElementById("f-data-de").value,
    data_ate: document.getElementById("f-data-ate").value,
  };
}

function montarQuery(extra = {}) {
  const f = { ...ler(), ...extra };
  const p = new URLSearchParams();
  for (const [k, v] of Object.entries(f)) if (v !== "" && v != null) p.append(k, v);
  return p.toString();
}

const STATUS_BADGE = {
  pendente:  "bg-amber-50 text-amber-700",
  pago:      "bg-emerald-50 text-emerald-700",
  cancelado: "bg-slate-100 text-slate-500",
};

async function carregar() {
  const tbody = document.getElementById("tbody");
  tbody.innerHTML = `<tr><td colspan="10" class="px-3 py-6 text-center text-slate-400">Carregando…</td></tr>`;
  const t0 = performance.now();
  try {
    const d = await apiFetch(`/contas-pagar?${montarQuery({ pagina, por_pagina: 50 })}`);
    const dur = (performance.now() - t0).toFixed(0);
    document.getElementById("tempo").textContent = `⚡ ${dur}ms`;
    document.getElementById("stats").textContent =
      `${d.total.toLocaleString("pt-BR")} parcelas`;
    document.getElementById("soma").textContent = `Σ ${brl(d.soma_valor)}`;

    if (!d.linhas.length) {
      tbody.innerHTML = `<tr><td colspan="10" class="px-3 py-6 text-center text-slate-400">Nenhum resultado</td></tr>`;
      document.getElementById("paginacao").innerHTML = "";
      return;
    }

    tbody.innerHTML = d.linhas.map(p => {
      const marcavel = p.status === "pendente";
      const check = marcavel
        ? `<input type="checkbox" class="chk-linha" data-id="${p.id}" ${_selecionados.has(p.id) ? "checked" : ""}
                  onchange="marcarLinha(${p.id}, this.checked)">`
        : "";
      return `
      <tr class="border-t border-slate-100 hover:bg-slate-50">
        <td class="px-3 py-2 text-center">${check}</td>
        <td class="px-3 py-2 font-mono text-xs">
          <a href="/app/processo-detalhe.html?id=${p.id_processo}" class="text-indigo-700 hover:underline">
            ${esc(p.protocolo || "—")}</a></td>
        <td class="px-3 py-2 text-center">${p.parcela}</td>
        <td class="px-3 py-2">${esc(p.beneficiario_nome || "—")}
          <div class="text-[11px] text-slate-400 font-mono">${fmtCpf(p.beneficiario_cpf)}</div></td>
        <td class="px-3 py-2 text-xs text-slate-600 max-w-[16rem] truncate" title="${esc(p.empresa)}">${esc(p.empresa || "—")}</td>
        <td class="px-3 py-2 text-xs">${esc(p.tipo_beneficio || "—")}</td>
        <td class="px-3 py-2 text-right font-mono">${brl(p.valor)}</td>
        <td class="px-3 py-2 text-center text-xs text-slate-500">${fmtData(p.data_referencia)}</td>
        <td class="px-3 py-2 text-center text-xs">${(p.forma_pagamento || "—").toUpperCase()}</td>
        <td class="px-3 py-2 text-center">
          <span class="px-2 py-0.5 rounded-full text-xs ${STATUS_BADGE[p.status] || "bg-slate-100"}">${p.status}</span>
        </td>
      </tr>`;
    }).join("");

    document.getElementById("paginacao").innerHTML = `
      <div class="flex items-center justify-between text-sm text-slate-600">
        <span>Página ${d.pagina} de ${d.paginas}</span>
        <div class="flex gap-2">
          <button onclick="irPagina(${pagina - 1})" ${pagina <= 1 ? "disabled" : ""}
                  class="px-3 py-1 border rounded ${pagina <= 1 ? "text-slate-300" : "hover:bg-slate-100"}">‹ Anterior</button>
          <button onclick="irPagina(${pagina + 1})" ${pagina >= d.paginas ? "disabled" : ""}
                  class="px-3 py-1 border rounded ${pagina >= d.paginas ? "text-slate-300" : "hover:bg-slate-100"}">Próxima ›</button>
        </div>
      </div>`;
    document.getElementById("chk-todos").checked = false;
  } catch (e) {
    tbody.innerHTML = `<tr><td colspan="10" class="px-3 py-6 text-center text-rose-600">${esc(e.message)}</td></tr>`;
  }
}

/* ------------------------------ seleção --------------------------------- */

function marcarLinha(id, on) {
  if (on) _selecionados.add(id); else _selecionados.delete(id);
  atualizarBotao();
}
function marcarTodos(on) {
  document.querySelectorAll(".chk-linha").forEach(c => {
    c.checked = on;
    marcarLinha(Number(c.dataset.id), on);
  });
}
function atualizarBotao() {
  const n = _selecionados.size;
  document.getElementById("sel-count").textContent = n;
  document.getElementById("btn-liquidar").disabled = n === 0;
}

async function liquidarSelecionados() {
  const ids = [..._selecionados];
  if (!ids.length) return;
  if (!confirm(`Marcar ${ids.length} parcela(s) como PAGA(s) com a data de hoje?`)) return;

  const btn = document.getElementById("btn-liquidar");
  btn.disabled = true;
  try {
    const r = await apiFetch("/contas-pagar/liquidar", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ ids }),
    });
    _selecionados.clear();
    atualizarBotao();
    alert(`${r.liquidadas} de ${r.solicitadas} liquidada(s).`);
    carregar();
  } catch (e) {
    alert("Erro: " + e.message);
    btn.disabled = false;
  }
}

/* ------------------------------ export ---------------------------------- */

async function exportar() {
  try {
    await apiBaixarArquivo(`/contas-pagar/exportar?${montarQuery()}`, "contas_a_pagar.xlsx");
  } catch (e) {
    alert("Erro ao exportar: " + e.message);
  }
}

/* ------------------------------ navegação ------------------------------- */

function recarregar() { pagina = 1; carregar(); }
function irPagina(p) { pagina = Math.max(1, p); carregar(); }
function agendarBusca() { clearTimeout(timer); timer = setTimeout(recarregar, 300); }
function limpar() {
  document.getElementById("f-busca").value = "";
  document.getElementById("f-status").value = "pendente";
  document.getElementById("f-forma").value = "";
  document.getElementById("f-data-de").value = "";
  document.getElementById("f-data-ate").value = "";
  recarregar();
}

carregar();
