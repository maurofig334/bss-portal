/* Dashboard com KPIs e gráficos — visão INTERNA da BSS. */

const u = exigirLogin();

/*
 * Guarda de perfil na própria tela.
 *
 * O index.html já roteia empresa → dashboard-empresa.html, mas ninguém chega
 * sempre pela porta da frente: aba aberta de antes, refresh, favorito, botão
 * voltar, link antigo. Nesses casos o usuário caía AQUI e via
 * "Erro ao carregar dashboard: Acesso restrito à equipe interna" — quatro
 * vezes, uma por endpoint, numa tela de gráficos vazios.
 *
 * O 403 do backend é a segurança e está funcionando. Isto aqui é só cortesia:
 * em vez de exibir erro pra quem está no lugar errado, leva pro lugar certo.
 */
if (u && u.perfil === "empresa") {
  window.location.replace("/app/dashboard-empresa.html");
}

if (u) document.getElementById("usuario-info").textContent = `${u.nome} (${u.perfil})`;

function brl(n) {
  return Number(n || 0).toLocaleString("pt-BR", { style: "currency", currency: "BRL" });
}
function fmtNum(n) {
  return Number(n || 0).toLocaleString("pt-BR");
}
function fmtMes(d) {
  if (!d) return "—";
  const dt = new Date(d);
  const meses = ["jan","fev","mar","abr","mai","jun","jul","ago","set","out","nov","dez"];
  return `${meses[dt.getUTCMonth()]}/${String(dt.getUTCFullYear()).slice(-2)}`;
}

function card(label, valor, sub = "", cor = "slate") {
  const cores = {
    indigo: "border-indigo-200 bg-indigo-50",
    emerald: "border-emerald-200 bg-emerald-50",
    amber:  "border-amber-200 bg-amber-50",
    rose:   "border-rose-200 bg-rose-50",
    slate:  "border-slate-200 bg-white",
  };
  return `
    <div class="rounded-lg border p-4 ${cores[cor] || cores.slate}">
      <div class="text-xs font-semibold text-slate-500 uppercase tracking-wider">${label}</div>
      <div class="text-2xl font-bold text-slate-900 mt-1">${valor}</div>
      ${sub ? `<div class="text-xs text-slate-500 mt-1">${sub}</div>` : ""}
    </div>
  `;
}

async function carregar() {
  try {
    const [k, mes, status, tipos] = await Promise.all([
      apiFetch("/dashboard/kpis"),
      apiFetch("/dashboard/serie-mensal?meses=12"),
      apiFetch("/dashboard/processos-status"),
      apiFetch("/dashboard/tipos-beneficio"),
    ]);

    // Cards
    const pctAdimp = k.empresas_ativas > 0
      ? (((k.empresas_ativas - k.empresas_inadimplentes) / k.empresas_ativas) * 100).toFixed(1)
      : "0";
    document.getElementById("kpis").innerHTML = [
      card("Empresas Ativas", fmtNum(k.empresas_ativas),
           `${pctAdimp}% adimplentes`, "indigo"),
      card("Trabalhadores Ativos", fmtNum(k.trabalhadores_ativos),
           `de ${fmtNum(k.trabalhadores_total)} total`, "indigo"),
      card("Benefícios Abertos", fmtNum(k.processos_abertos),
           `${fmtNum(k.processos_total - k.processos_abertos)} finalizados`, "amber"),
      card("Boletos Pagos", fmtNum(k.boletos_pagos),
           `${fmtNum(k.boletos_total)} no total`, "emerald"),
      card("Faturamento Total", brl(k.faturamento_total),
           "boletos pagos histórico", "emerald"),
    ].join("");

    // Gráfico boletos mensal
    const ctxBol = document.getElementById("grafico-boletos");
    new Chart(ctxBol, {
      type: "bar",
      data: {
        labels: mes.map(m => fmtMes(m.mes_referencia)),
        datasets: [
          {
            label: "Pagos",
            data: mes.map(m => Number(m.pagos_qtd || 0)),
            backgroundColor: "rgba(16,185,129,0.7)",
          },
          {
            label: "Em aberto",
            data: mes.map(m => Number(m.abertos_qtd || 0)),
            backgroundColor: "rgba(245,158,11,0.7)",
          },
        ],
      },
      options: {
        responsive: true, maintainAspectRatio: false,
        scales: { x: { stacked: true }, y: { stacked: true, ticks: { precision: 0 } } },
        plugins: { legend: { position: "bottom" } },
      },
    });

    // Gráfico status (donut)
    const ctxSt = document.getElementById("grafico-status");
    new Chart(ctxSt, {
      type: "doughnut",
      data: {
        labels: status.map(s => s.nome),
        datasets: [{
          data: status.map(s => Number(s.qtd || 0)),
          backgroundColor: status.map(s => s.cor_hex || "#94A3B8"),
        }],
      },
      options: {
        responsive: true, maintainAspectRatio: false,
        plugins: { legend: { position: "right", labels: { boxWidth: 12, font: { size: 11 } } } },
      },
    });

    // Gráfico tipos (horizontal bar)
    const ctxTipo = document.getElementById("grafico-tipos");
    new Chart(ctxTipo, {
      type: "bar",
      data: {
        labels: tipos.map(t => t.nome),
        datasets: [{
          label: "Benefícios",
          data: tipos.map(t => Number(t.qtd || 0)),
          backgroundColor: "rgba(99,102,241,0.7)",
        }],
      },
      options: {
        indexAxis: "y", responsive: true, maintainAspectRatio: false,
        plugins: { legend: { display: false } },
      },
    });

  } catch (e) {
    document.getElementById("kpis").innerHTML = `
      <div class="col-span-full bg-rose-50 border border-rose-200 text-rose-700 rounded-lg p-4">
        Erro ao carregar dashboard: ${e.message}
      </div>
    `;
  }
}

// Não dispara as 4 chamadas se o usuário está sendo redirecionado daqui —
// location.replace() não interrompe o script, e seriam 4 requisições fadadas
// ao 403 antes da navegação acontecer.
if (u && u.perfil !== "empresa") carregar();
