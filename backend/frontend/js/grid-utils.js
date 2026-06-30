/* ============================================================================
 * grid-utils.js — componente de grid reutilizável (padrão OCSP).
 *
 * Fornece, de forma agnóstica de tela:
 *   - persistência de preferências no localStorage (colunas ocultas + filtros
 *     salvos), namespaced por "tela";
 *   - modal "Escolher colunas" (mostra/oculta);
 *   - modal "Filtro avançado" (construtor de condições campo/operador/valor);
 *   - dropdown "Meus filtros";
 *   - helper de cabeçalho ordenável (seta ↑/↓).
 *
 * Cada listagem (trabalhadores, empresas, …) passa sua config e callbacks.
 * Onda 1: preferências no localStorage; ordenação/busca continuam server-side.
 * ========================================================================== */

const OPERADORES_PADRAO = ["contém", "é igual a", "preenchido", "vazio"];
// Operadores que dispensam campo de valor:
const OPERADORES_SEM_VALOR = new Set(["preenchido", "vazio"]);

/* ----------------------------- localStorage ------------------------------ */

function _chave(tela, sufixo) { return `bss_grid_${tela}_${sufixo}`; }

function gridLerColunasOcultas(tela) {
  try { return JSON.parse(localStorage.getItem(_chave(tela, "cols_ocultas")) || "[]"); }
  catch { return []; }
}
function gridSalvarColunasOcultas(tela, ocultas) {
  localStorage.setItem(_chave(tela, "cols_ocultas"), JSON.stringify(ocultas || []));
}
function gridLerFiltrosSalvos(tela) {
  try { return JSON.parse(localStorage.getItem(_chave(tela, "filtros")) || "[]"); }
  catch { return []; }
}
function gridSalvarFiltrosSalvos(tela, lista) {
  localStorage.setItem(_chave(tela, "filtros"), JSON.stringify(lista || []));
}

/* -------------------------- overlay genérico ----------------------------- */

function _fecharOverlay() {
  const ov = document.getElementById("grid-overlay");
  if (ov) ov.remove();
}

function _abrirOverlay(innerHtml, largura = "max-w-lg") {
  _fecharOverlay();
  const ov = document.createElement("div");
  ov.id = "grid-overlay";
  ov.className = "fixed inset-0 z-50 bg-slate-900/40 flex items-start justify-center pt-24 p-4";
  ov.innerHTML = `
    <div class="bg-white rounded-xl shadow-xl w-full ${largura} max-h-[75vh] flex flex-col overflow-hidden">
      ${innerHtml}
    </div>`;
  ov.addEventListener("mousedown", (e) => { if (e.target === ov) _fecharOverlay(); });
  document.body.appendChild(ov);
  return ov;
}

/* ----------------------- modal: Escolher colunas ------------------------- */
/*
 * colunas: [{ id, label, fixa? }]  — fixa não pode ser ocultada
 * ocultas: [id, …]
 * onSalvar(novasOcultas)
 */
function gridAbrirModalColunas({ colunas, ocultas, onSalvar }) {
  const setOcultas = new Set(ocultas || []);
  const linhas = colunas.map(c => {
    const checked = !setOcultas.has(c.id) ? "checked" : "";
    const disabled = c.fixa ? "disabled" : "";
    return `
      <label class="flex items-center gap-2 py-1.5 ${c.fixa ? "opacity-60" : "cursor-pointer hover:bg-slate-50"} px-2 rounded">
        <input type="checkbox" data-col="${c.id}" ${checked} ${disabled}
               class="w-4 h-4 accent-indigo-600">
        <span class="text-sm text-slate-700">${c.label}</span>
      </label>`;
  }).join("");

  const ov = _abrirOverlay(`
    <div class="px-5 py-4 border-b border-slate-200">
      <h2 class="text-base font-semibold text-slate-800">Escolher colunas</h2>
    </div>
    <div class="px-3 py-3 overflow-y-auto flex-1">${linhas}</div>
    <div class="px-5 py-3 border-t border-slate-200 flex justify-end gap-2 bg-slate-50">
      <button data-act="cancelar" class="px-4 py-1.5 text-sm text-slate-600 hover:text-slate-900">Cancelar</button>
      <button data-act="salvar" class="px-4 py-1.5 text-sm bg-indigo-600 text-white rounded-lg hover:bg-indigo-700 font-medium">Salvar</button>
    </div>
  `);

  ov.querySelector('[data-act="cancelar"]').onclick = _fecharOverlay;
  ov.querySelector('[data-act="salvar"]').onclick = () => {
    const novas = [];
    ov.querySelectorAll("input[data-col]").forEach(inp => {
      if (!inp.checked) novas.push(inp.dataset.col);
    });
    _fecharOverlay();
    onSalvar(novas);
  };
}

/* ----------------------- modal: Filtro avançado -------------------------- */
/*
 * campos:   [{ id, label, tipo:"text"|"select", opcoes?:[{value,label}],
 *              operadores?:[...] }]
 * condicoes inicial: [{ campo, operador, valor }]
 * onAplicar(condicoes)
 * onSalvarComo(nome, condicoes)
 */
function gridAbrirModalFiltro({ campos, condicoes, onAplicar, onSalvarComo }) {
  let estado = (condicoes && condicoes.length)
    ? condicoes.map(c => ({ ...c }))
    : [{ campo: campos[0].id, operador: (campos[0].operadores || OPERADORES_PADRAO)[0], valor: "" }];

  const ov = _abrirOverlay(`
    <div class="px-5 py-4 border-b border-slate-200">
      <h2 class="text-base font-semibold text-slate-800">Filtro avançado</h2>
    </div>
    <div id="filtro-condicoes" class="px-5 py-4 overflow-y-auto flex-1 space-y-2"></div>
    <div class="px-5 pb-2">
      <button data-act="add" class="text-sm text-indigo-600 hover:underline">+ Adicionar condição</button>
    </div>
    <div class="px-5 py-3 border-t border-slate-200 flex items-center justify-between bg-slate-50">
      <button data-act="limpar" class="px-3 py-1.5 text-sm text-slate-600 hover:text-slate-900">Limpar</button>
      <div class="flex gap-2">
        <button data-act="salvarComo" class="px-4 py-1.5 text-sm text-slate-700 border border-slate-300 rounded-lg hover:bg-slate-100">Salvar como…</button>
        <button data-act="aplicar" class="px-4 py-1.5 text-sm bg-indigo-600 text-white rounded-lg hover:bg-indigo-700 font-medium">Aplicar</button>
      </div>
    </div>
  `, "max-w-2xl");

  const cont = ov.querySelector("#filtro-condicoes");

  function campoCfg(id) { return campos.find(c => c.id === id) || campos[0]; }

  function render() {
    cont.innerHTML = estado.map((c, i) => {
      const cfg = campoCfg(c.campo);
      const ops = cfg.operadores || OPERADORES_PADRAO;
      const optsCampos = campos.map(f =>
        `<option value="${f.id}" ${f.id === c.campo ? "selected" : ""}>${f.label}</option>`).join("");
      const optsOps = ops.map(o =>
        `<option value="${o}" ${o === c.operador ? "selected" : ""}>${o}</option>`).join("");
      let valorHtml;
      if (OPERADORES_SEM_VALOR.has(c.operador)) {
        valorHtml = `<div class="flex-1"></div>`;
      } else if (cfg.tipo === "select") {
        const optsVal = (cfg.opcoes || []).map(o =>
          `<option value="${o.value}" ${o.value === c.valor ? "selected" : ""}>${o.label}</option>`).join("");
        valorHtml = `<select data-i="${i}" data-k="valor" class="flex-1 px-2 py-1.5 border border-slate-300 rounded-lg text-sm">
          <option value="">—</option>${optsVal}</select>`;
      } else {
        valorHtml = `<input data-i="${i}" data-k="valor" value="${(c.valor || "").replace(/"/g, "&quot;")}"
          class="flex-1 px-2 py-1.5 border border-slate-300 rounded-lg text-sm" placeholder="valor">`;
      }
      return `
        <div class="flex items-center gap-2">
          <select data-i="${i}" data-k="campo" class="px-2 py-1.5 border border-slate-300 rounded-lg text-sm">${optsCampos}</select>
          <select data-i="${i}" data-k="operador" class="px-2 py-1.5 border border-slate-300 rounded-lg text-sm">${optsOps}</select>
          ${valorHtml}
          <button data-rm="${i}" class="text-slate-400 hover:text-rose-600 px-1" title="Remover">✕</button>
        </div>`;
    }).join("");

    cont.querySelectorAll("select[data-k], input[data-k]").forEach(el => {
      el.onchange = (e) => {
        const i = +e.target.dataset.i, k = e.target.dataset.k;
        estado[i][k] = e.target.value;
        if (k === "campo") {
          const cfg = campoCfg(e.target.value);
          estado[i].operador = (cfg.operadores || OPERADORES_PADRAO)[0];
          estado[i].valor = "";
          render();
        } else if (k === "operador") {
          render();
        }
      };
    });
    cont.querySelectorAll("button[data-rm]").forEach(b => {
      b.onclick = () => { estado.splice(+b.dataset.rm, 1); if (!estado.length) addCond(); render(); };
    });
  }

  function addCond() {
    estado.push({ campo: campos[0].id, operador: (campos[0].operadores || OPERADORES_PADRAO)[0], valor: "" });
  }

  ov.querySelector('[data-act="add"]').onclick = () => { addCond(); render(); };
  ov.querySelector('[data-act="limpar"]').onclick = () => { estado = []; addCond(); render(); };
  ov.querySelector('[data-act="aplicar"]').onclick = () => {
    _fecharOverlay();
    onAplicar(estado.filter(c => OPERADORES_SEM_VALOR.has(c.operador) || c.valor !== ""));
  };
  ov.querySelector('[data-act="salvarComo"]').onclick = () => {
    const nome = prompt("Nome do filtro:");
    if (nome && nome.trim()) {
      onSalvarComo(nome.trim(), estado.filter(c => OPERADORES_SEM_VALOR.has(c.operador) || c.valor !== ""));
      _fecharOverlay();
    }
  };

  render();
}

/* ----------------------- dropdown: Meus filtros -------------------------- */
/*
 * Abre um menu simples ancorado ao botão. lista = [{nome, condicoes}]
 * onAplicar(condicoes), onExcluir(indice)
 */
function gridAbrirMeusFiltros({ ancora, lista, onAplicar, onExcluir }) {
  _fecharOverlay();
  const r = ancora.getBoundingClientRect();
  const ov = document.createElement("div");
  ov.id = "grid-overlay";
  ov.className = "fixed inset-0 z-50";
  const itens = lista.length
    ? lista.map((f, i) => `
        <div class="flex items-center justify-between gap-2 px-3 py-2 hover:bg-slate-50">
          <button data-ap="${i}" class="text-sm text-slate-700 text-left flex-1 truncate">${f.nome}</button>
          <button data-ex="${i}" class="text-slate-300 hover:text-rose-600 text-xs" title="Excluir">✕</button>
        </div>`).join("")
    : `<div class="px-3 py-3 text-sm text-slate-400">Nenhum filtro salvo.</div>`;
  ov.innerHTML = `
    <div class="absolute bg-white rounded-lg shadow-xl border border-slate-200 w-64 py-1"
         style="top:${r.bottom + 4}px; left:${Math.max(8, r.right - 256)}px">${itens}</div>`;
  ov.addEventListener("mousedown", (e) => { if (e.target === ov) _fecharOverlay(); });
  document.body.appendChild(ov);
  ov.querySelectorAll("button[data-ap]").forEach(b =>
    b.onclick = () => { _fecharOverlay(); onAplicar(lista[+b.dataset.ap].condicoes); });
  ov.querySelectorAll("button[data-ex]").forEach(b =>
    b.onclick = (e) => { e.stopPropagation(); onExcluir(+b.dataset.ex); _fecharOverlay(); });
}

/* ----------------------- cabeçalho ordenável ----------------------------- */
/*
 * Retorna o conteúdo de um <th> clicável com seta. ord = {campo, desc}.
 * Use onclick="ordenarPor('campo')" no próprio th (a tela define ordenarPor).
 */
function gridSeta(campoCol, ord) {
  if (!ord || ord.campo !== campoCol) return `<span class="text-slate-300"> ⇅</span>`;
  return ord.desc ? `<span class="text-indigo-600"> ↓</span>` : `<span class="text-indigo-600"> ↑</span>`;
}
