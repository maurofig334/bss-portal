/* Tela de listagem de trabalhadores. */

const u = exigirLogin();
if (u) document.getElementById("usuario-info").textContent = `${u.nome} (${u.perfil})`;

let pagina = 1;
let timer = null;

function formatarCPF(cpf) {
  if (!cpf) return "—";
  const d = String(cpf).replace(/\D/g, "");
  if (d.length !== 11) return cpf;
  return d.replace(/(\d{3})(\d{3})(\d{3})(\d{2})/, "$1.$2.$3-$4");
}

function formatarData(d) {
  if (!d) return "—";
  return new Date(d).toLocaleDateString("pt-BR");
}

function badgeSituacao(s) {
  const cores = {
    ativo:    "bg-emerald-100 text-emerald-800",
    inativo:  "bg-slate-200 text-slate-700",
    carencia: "bg-amber-100 text-amber-800",
  };
  const cls = cores[s] || "bg-slate-100 text-slate-600";
  return `<span class="inline-block px-2 py-0.5 rounded-full text-xs ${cls}">${s || "—"}</span>`;
}


// Cache de dependentes por CPF do titular (evita refetch em hovers repetidos)
const _depCache = new Map();

async function carregarDependentes(cpfTitular) {
  if (_depCache.has(cpfTitular)) return _depCache.get(cpfTitular);
  try {
    const lista = await apiFetch(`/trabalhadores/dependentes/${cpfTitular}`);
    _depCache.set(cpfTitular, lista);
    return lista;
  } catch (e) {
    return [];
  }
}

async function mostrarTooltipDependentes(ev, cpf, qtd) {
  const tt = document.getElementById("dep-tooltip");
  const conteudo = tt.querySelector(".tt-conteudo");
  conteudo.innerHTML = `<div class="text-xs text-slate-500 italic">Carregando…</div>`;
  tt.style.left = (ev.clientX + 12) + "px";
  tt.style.top  = (ev.clientY + 12) + "px";
  tt.classList.remove("hidden");
  const lista = await carregarDependentes(cpf);
  if (!lista.length) {
    conteudo.innerHTML = `<div class="text-xs text-slate-500">Sem dependentes cadastrados.</div>`;
    return;
  }
  const linhas = lista.map(d =>
    `<div class="text-xs text-slate-700 leading-tight">
      <span class="font-mono text-[10px] text-slate-500">${formatarCPF(d.cpf)}</span>
      <span class="ml-1">${d.nome_completo || "—"}</span>
    </div>`
  ).join("");
  conteudo.innerHTML = `
    <div class="text-[11px] font-semibold text-slate-600 mb-1">${qtd} dependente${qtd > 1 ? "s" : ""}</div>
    ${linhas}
  `;
}

function esconderTooltip() {
  const tt = document.getElementById("dep-tooltip");
  if (tt) tt.classList.add("hidden");
}

function badgeTit(t) {
  if (t.titularidade === "dependente") {
    const titulo = t.cpf_titular ? `Dependente de ${formatarCPF(t.cpf_titular)}` : "Dependente";
    return `<span class="inline-block w-6 h-6 leading-6 rounded-full text-center text-xs font-bold bg-amber-100 text-amber-800" title="${titulo}">D</span>`;
  }
  // Titular: T com hover lista dependentes (se tiver)
  const qtd = t.qtd_dependentes_ativos || 0;
  if (qtd > 0) {
    return `<span class="inline-block w-6 h-6 leading-6 rounded-full text-center text-xs font-bold bg-indigo-100 text-indigo-800 cursor-help"
              onmouseenter="mostrarTooltipDependentes(event, '${t.cpf}', ${qtd})"
              onmousemove="(function(ev){const tt=document.getElementById('dep-tooltip');if(!tt.classList.contains('hidden')){tt.style.left=(ev.clientX+12)+'px';tt.style.top=(ev.clientY+12)+'px';}})(event)"
              onmouseleave="esconderTooltip()">T</span>`;
  }
  return `<span class="inline-block w-6 h-6 leading-6 rounded-full text-center text-xs font-bold bg-slate-100 text-slate-600" title="Titular sem dependentes">T</span>`;
}

function ler() {
  return {
    busca:     document.getElementById("f-busca").value.trim(),
    situacao:  document.getElementById("f-situacao").value,
    uf:        document.getElementById("f-uf").value.trim().toUpperCase(),
  };
}

function montarQuery(extras = {}) {
  const f = { ...ler(), ...extras, pagina, por_pagina: 50 };
  const params = new URLSearchParams();
  for (const [k, v] of Object.entries(f)) {
    if (v !== "" && v != null) params.append(k, v);
  }
  return params.toString();
}

async function recarregar() {
  pagina = 1;
  await carregar();
}

async function carregar() {
  const tbody = document.getElementById("tbody");
  tbody.innerHTML = `<tr><td colspan="8" class="px-3 py-6 text-center text-slate-400">Carregando…</td></tr>`;
  document.getElementById("tempo").textContent = "";

  const t0 = performance.now();
  try {
    const data = await apiFetch(`/trabalhadores?${montarQuery()}`);
    const t1 = performance.now();
    const dur = (t1 - t0).toFixed(0);

    document.getElementById("tempo").textContent = `⚡ ${dur}ms (${data.linhas.length} de ${data.total.toLocaleString("pt-BR")})`;
    document.getElementById("stats").textContent = `${data.total.toLocaleString("pt-BR")} trabalhadores encontrados`;

    if (data.linhas.length === 0) {
      tbody.innerHTML = `<tr><td colspan="8" class="px-3 py-6 text-center text-slate-400">Nenhum resultado</td></tr>`;
      document.getElementById("paginacao").innerHTML = "";
      return;
    }

    tbody.innerHTML = data.linhas.map(t => `
      <tr class="border-t border-slate-100 hover:bg-slate-50">
        <td class="px-3 py-2 text-center">${badgeTit(t)}</td>
        <td class="px-3 py-2 font-mono text-xs">${formatarCPF(t.cpf)}</td>
        <td class="px-3 py-2 font-medium text-slate-900">${t.nome_completo || "—"}</td>
        <td class="px-3 py-2 text-slate-700">${t.empresa || "—"}</td>
        <td class="px-3 py-2 text-slate-600 text-xs">${t.sindicato || "—"}</td>
        <td class="px-3 py-2 text-center">${t.trab_uf || "—"}</td>
        <td class="px-3 py-2 text-center">${badgeSituacao(t.situacao)}</td>
        <td class="px-3 py-2 text-right text-xs text-slate-500">${formatarData(t.ultimo_pagamento_em)}</td>
      </tr>
    `).join("");

    montarPaginacao(data);

  } catch (e) {
    tbody.innerHTML = `<tr><td colspan="8" class="px-3 py-6 text-center text-rose-600">Erro: ${e.message}</td></tr>`;
  }
}

function montarPaginacao(data) {
  const div = document.getElementById("paginacao");
  if (data.paginas <= 1) {
    div.innerHTML = "";
    return;
  }
  div.innerHTML = `
    <div class="text-slate-500">Página ${data.pagina} de ${data.paginas}</div>
    <div class="flex gap-2">
      <button onclick="irPagina(${pagina - 1})" ${pagina <= 1 ? "disabled" : ""}
              class="px-3 py-1 border rounded ${pagina <= 1 ? "text-slate-300" : "hover:bg-slate-100"}">‹ Anterior</button>
      <button onclick="irPagina(${pagina + 1})" ${pagina >= data.paginas ? "disabled" : ""}
              class="px-3 py-1 border rounded ${pagina >= data.paginas ? "text-slate-300" : "hover:bg-slate-100"}">Próxima ›</button>
    </div>
  `;
}

function irPagina(p) {
  pagina = Math.max(1, p);
  carregar();
}

function agendarBusca() {
  // Debounce: aguarda 300ms sem digitar pra rodar
  clearTimeout(timer);
  timer = setTimeout(recarregar, 300);
}

function limparFiltros() {
  document.getElementById("f-busca").value = "";
  document.getElementById("f-situacao").value = "";
  document.getElementById("f-uf").value = "";
  recarregar();
}

// Carga inicial
carregar();
