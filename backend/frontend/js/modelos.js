/* Editor de modelos de e-mail em massa. Só admin/interno (o backend barra). */

const u = exigirLogin();
if (u) document.getElementById("usuario-info").textContent = `${u.nome} (${u.perfil})`;

let _modelos = [];
let _atual = null;          // modelo em edição
let _catalogo = [];         // variáveis do destinatário atual
let _alvos = [];            // opções de preview (contatos ou empresas)

function esc(s) {
  return String(s ?? "").replace(/[&<>"']/g, c => (
    { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

/* ------------------------------- lista ---------------------------------- */

const CAT_LABEL = {
  inadimplencia: "Inadimplência", irregularidade: "Irregularidade",
  boleto: "Boletos", cadastro: "Cadastro", beneficio: "Benefícios",
};

async function carregarLista() {
  try {
    _modelos = await apiFetch("/modelos");
  } catch (e) {
    document.getElementById("lista-modelos").innerHTML =
      `<div class="p-4 text-sm text-rose-600">Erro: ${esc(e.message)}</div>`;
    return;
  }

  // Agrupa por categoria, na ordem em que aparecem.
  const grupos = {};
  for (const m of _modelos) (grupos[m.categoria] ??= []).push(m);

  let html = "";
  for (const [cat, itens] of Object.entries(grupos)) {
    html += `<div class="px-4 pt-3 pb-1 text-xs font-semibold text-slate-400 uppercase tracking-wider">
               ${esc(CAT_LABEL[cat] || cat || "Outros")}</div>`;
    for (const m of itens) {
      const status = m.ativo
        ? `<span class="w-2 h-2 rounded-full bg-emerald-500" title="Ativo"></span>`
        : (m.preenchido
            ? `<span class="w-2 h-2 rounded-full bg-amber-400" title="Rascunho preenchido"></span>`
            : `<span class="w-2 h-2 rounded-full bg-slate-300" title="Vazio"></span>`);
      html += `
        <button onclick="abrir(${m.id})" data-id="${m.id}"
                class="w-full text-left px-4 py-2.5 hover:bg-slate-50 flex items-center gap-2 modelo-item">
          ${status}
          <span class="flex-1 text-sm text-slate-700">${esc(m.nome)}</span>
          <span class="text-[10px] px-1.5 py-0.5 rounded ${m.destinatario === 'empresa'
              ? 'bg-blue-50 text-blue-700' : 'bg-purple-50 text-purple-700'}">
            ${m.destinatario === 'empresa' ? 'Empresa' : 'Contato'}</span>
        </button>`;
    }
  }
  document.getElementById("lista-modelos").innerHTML = html;
}

/* ------------------------------- editor --------------------------------- */

async function abrir(id) {
  document.querySelectorAll(".modelo-item").forEach(b =>
    b.classList.toggle("bg-indigo-50", Number(b.dataset.id) === id));

  try {
    _atual = await apiFetch(`/modelos/${id}`);
    _catalogo = await apiFetch(`/modelos/variaveis?destinatario=${_atual.destinatario}`);
  } catch (e) {
    alert("Erro ao abrir: " + e.message);
    return;
  }

  document.getElementById("editor-vazio").classList.add("hidden");
  document.getElementById("editor").classList.remove("hidden");

  document.getElementById("ed-nome").textContent = _atual.nome;
  document.getElementById("ed-codigo").textContent = _atual.codigo;
  document.getElementById("ed-destinatario").textContent =
    _atual.destinatario === "empresa" ? "→ e-mail da empresa" : "→ contato gestor";
  document.getElementById("ed-ativo").checked = _atual.ativo;
  document.getElementById("ed-assunto").value = _atual.assunto || "";
  document.getElementById("ed-corpo").value = _atual.corpo || "";
  document.getElementById("ed-obs").value = _atual.observacao || "";
  document.getElementById("ed-status").textContent = "";

  renderPaleta();
}

function renderPaleta() {
  document.getElementById("paleta").innerHTML = _catalogo.map(v => {
    const cor = v.tipo === "lista" ? "bg-amber-100 text-amber-800 hover:bg-amber-200"
                                   : "bg-white text-slate-700 hover:bg-indigo-100";
    return `<button onclick="inserirVar('${v.nome}')" title="${esc(v.descricao)}"
                    class="px-2 py-1 text-xs rounded border border-slate-200 ${cor} font-mono">
              {{${v.nome}}}${v.tipo === "lista" ? " ▤" : ""}</button>`;
  }).join("");
}

/** Insere a variável na posição do cursor do corpo. */
function inserirVar(nome) {
  const ta = document.getElementById("ed-corpo");
  const ins = `{{${nome}}}`;
  const i = ta.selectionStart ?? ta.value.length;
  const j = ta.selectionEnd ?? ta.value.length;
  ta.value = ta.value.slice(0, i) + ins + ta.value.slice(j);
  ta.focus();
  ta.selectionStart = ta.selectionEnd = i + ins.length;
}

async function salvar() {
  const btn = document.getElementById("btn-salvar");
  const st = document.getElementById("ed-status");
  btn.disabled = true;
  st.textContent = "Salvando…";
  st.className = "text-xs text-slate-500";
  try {
    const salvo = await apiFetch(`/modelos/${_atual.id}`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        assunto: document.getElementById("ed-assunto").value,
        corpo: document.getElementById("ed-corpo").value,
        ativo: document.getElementById("ed-ativo").checked,
        observacao: document.getElementById("ed-obs").value || null,
      }),
    });
    _atual = salvo;
    st.textContent = "✓ Salvo";
    st.className = "text-xs text-emerald-600";
    carregarLista();   // atualiza o farol de status na lista
  } catch (e) {
    st.textContent = e.message;
    st.className = "text-xs text-rose-600";
    // Erro de órfã volta o checkbox: não ficou ativo de verdade.
    if (e.message.includes("ativar")) document.getElementById("ed-ativo").checked = false;
  } finally {
    btn.disabled = false;
  }
}

/* ------------------------------ preview --------------------------------- */

let _buscaTimer = null;

async function abrirPreview() {
  document.getElementById("modal-preview").classList.remove("hidden");
  document.getElementById("lbl-alvo").textContent =
    _atual.destinatario === "empresa"
      ? "Resolver contra a empresa:" : "Resolver contra o contato:";

  const busca = document.getElementById("preview-busca");
  busca.value = "";
  busca.placeholder = _atual.destinatario === "empresa"
    ? "Buscar empresa por razão social ou CNPJ…"
    : "Buscar contato por nome, e-mail ou CNPJ…";
  // Debounce: não dispara uma busca por tecla.
  busca.oninput = () => { clearTimeout(_buscaTimer); _buscaTimer = setTimeout(buscarAlvos, 300); };

  buscarAlvos();   // carga inicial (primeira página) até o usuário digitar
}

/**
 * Busca alvos no BACKEND — não filtra uma lista de 50 no cliente. São 2.515
 * contatos e ~5.250 empresas; a página fixa alfabética só mostrava os "A", e o
 * maurofig ficava inalcançável. O /contatos e /empresas já aceitam `busca`.
 */
async function buscarAlvos() {
  const termo = document.getElementById("preview-busca").value.trim();
  const sel = document.getElementById("preview-alvo");
  const q = termo ? `&busca=${encodeURIComponent(termo)}` : "";
  try {
    if (_atual.destinatario === "empresa") {
      const r = await apiFetch(`/empresas?por_pagina=30&ordem=razao_social${q}`);
      _alvos = (r.linhas || []).map(e => ({ id: e.id, rotulo: e.razao_social }));
    } else {
      const r = await apiFetch(`/contatos?por_pagina=30${q}`);
      _alvos = (r.linhas || []).map(c => ({ id: c.id, rotulo: `${c.nome} (${c.email})` }));
    }
  } catch (e) {
    sel.innerHTML = `<option>Erro: ${esc(e.message)}</option>`;
    return;
  }

  if (!_alvos.length) {
    sel.innerHTML = `<option value="">Nenhum resultado</option>`;
    document.getElementById("preview-conteudo").innerHTML =
      `<div class="text-sm text-slate-400">Nenhum alvo encontrado para "${esc(termo)}".</div>`;
    return;
  }
  sel.innerHTML = _alvos.map(a => `<option value="${a.id}">${esc(a.rotulo)}</option>`).join("");
  sel.selectedIndex = 0;
  carregarPreview();
}

async function carregarPreview() {
  const alvoId = Number(document.getElementById("preview-alvo").value);
  const div = document.getElementById("preview-conteudo");
  div.innerHTML = `<div class="text-sm text-slate-400">Resolvendo…</div>`;

  const body = {
    assunto: document.getElementById("ed-assunto").value,
    corpo: document.getElementById("ed-corpo").value,
  };
  if (_atual.destinatario === "empresa") body.id_empresa = alvoId;
  else body.id_contato = alvoId;

  try {
    const p = await apiFetch(`/modelos/${_atual.id}/preview`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });

    const orfas = p.orfas.length
      ? `<div class="mb-3 text-xs bg-rose-50 text-rose-700 rounded-lg px-3 py-2">
           ⚠ Variáveis que não resolvem (vão sair como texto no e-mail):
           ${p.orfas.map(o => `<code>{{${esc(o)}}}</code>`).join(", ")}</div>` : "";

    div.innerHTML = `
      ${orfas}
      <div class="text-xs text-slate-400 mb-1">Assunto</div>
      <div class="text-sm font-medium text-slate-800 mb-4 pb-3 border-b border-slate-100">
        ${esc(p.assunto) || "<span class='text-slate-300'>(vazio)</span>"}</div>
      <div class="text-xs text-slate-400 mb-1">Corpo</div>
      <pre class="text-sm text-slate-700 whitespace-pre-wrap font-sans">${esc(p.corpo)}</pre>
      <div class="text-xs text-slate-400 mt-4 pt-3 border-t border-slate-100">
        Boletos vencidos no contexto: <strong>${p.qtd_boletos_vencidos}</strong>
      </div>`;
  } catch (e) {
    div.innerHTML = `<div class="text-sm text-rose-600">${esc(e.message)}</div>`;
  }
}

carregarLista();
