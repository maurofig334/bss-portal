/*
 * sidebar.js — menu lateral compartilhado entre todas as páginas do BSS.
 *
 * Uso:
 *   <aside id="sidebar"></aside>
 *   <script src="/app/js/sidebar.js"></script>
 *   <script>renderizarSidebar("trabalhadores");</script>
 */

const MENU = [
  {
    grupo: "Início",
    itens: [
      { slug: "dashboard", label: "Dashboard", href: "/app/dashboard.html",
        icone: '<path d="M3 4a1 1 0 011-1h12a1 1 0 011 1v2a1 1 0 01-1 1H4a1 1 0 01-1-1V4zM3 10a1 1 0 011-1h6a1 1 0 011 1v6a1 1 0 01-1 1H4a1 1 0 01-1-1v-6zM14 9a1 1 0 00-1 1v6a1 1 0 001 1h2a1 1 0 001-1v-6a1 1 0 00-1-1h-2z"/>' },
    ],
  },
  {
    grupo: "Cadastros",
    itens: [
      { slug: "empresas", label: "Empresas", href: "/app/empresas.html",
        icone: '<path fill-rule="evenodd" d="M4 4a2 2 0 012-2h8a2 2 0 012 2v12h1a1 1 0 110 2H3a1 1 0 110-2h1V4zm3 1h2v2H7V5zm2 4H7v2h2V9zm2-4h2v2h-2V5zm2 4h-2v2h2V9zm-6 4h2v4H7v-4zm4 0h2v4h-2v-4z" clip-rule="evenodd"/>' },
      { slug: "trabalhadores", label: "Trabalhadores", href: "/app/trabalhadores.html",
        icone: '<path d="M9 6a3 3 0 11-6 0 3 3 0 016 0zM17 6a3 3 0 11-6 0 3 3 0 016 0zM12.93 17c.046-.327.07-.66.07-1a6.97 6.97 0 00-1.5-4.33A5 5 0 0119 16v1h-6.07zM6 11a5 5 0 015 5v1H1v-1a5 5 0 015-5z"/>' },
      { slug: "sindicatos", label: "Sindicatos", href: "/app/sindicatos.html",
        icone: '<path fill-rule="evenodd" d="M3 6a2 2 0 012-2h10a2 2 0 012 2v8a2 2 0 01-2 2H5a2 2 0 01-2-2V6zm5 1a1 1 0 100 2h4a1 1 0 100-2H8zm-1 4a1 1 0 011-1h4a1 1 0 110 2H8a1 1 0 01-1-1zm1 3a1 1 0 100 2h4a1 1 0 100-2H8z" clip-rule="evenodd"/>' },
      // Contatos = usuários externos (bss_users perfil='empresa'). Cada um
      // administra N CNPJs via bss.usuario_empresa. Ver docs/AUTOCADASTRO.md.
      { slug: "contatos", label: "Contatos", href: "/app/contatos.html",
        icone: '<path fill-rule="evenodd" d="M10 9a3 3 0 100-6 3 3 0 000 6zm-7 9a7 7 0 1114 0H3z" clip-rule="evenodd"/>' },
    ],
  },
  {
    grupo: "Operação",
    itens: [
      { slug: "processos", label: "Benefícios", href: "/app/processos.html",
        icone: '<path d="M9 2a1 1 0 000 2h2a1 1 0 100-2H9z"/><path fill-rule="evenodd" d="M4 5a2 2 0 012-2 3 3 0 003 3h2a3 3 0 003-3 2 2 0 012 2v11a2 2 0 01-2 2H6a2 2 0 01-2-2V5zm3 4a1 1 0 000 2h.01a1 1 0 100-2H7zm3 0a1 1 0 100 2h3a1 1 0 100-2h-3zm-3 4a1 1 0 100 2h.01a1 1 0 100-2H7zm3 0a1 1 0 100 2h3a1 1 0 100-2h-3z" clip-rule="evenodd"/>' },
      { slug: "boletos", label: "Boletos", href: "/app/boletos.html",
        icone: '<path fill-rule="evenodd" d="M4 4a2 2 0 012-2h8a2 2 0 012 2v12a2 2 0 01-2 2H6a2 2 0 01-2-2V4zm3 1h6v2H7V5zm6 4H7v2h6V9zm-2 4H7v2h4v-2z" clip-rule="evenodd"/>' },
    ],
  },
];

async function renderizarSidebar(slugAtivo) {
  const aside = document.getElementById("sidebar");
  if (!aside) return;

  let html = `
    <div class="h-full bg-white border-r border-slate-200 px-3 py-4 overflow-y-auto">
      <div class="px-2 pb-4 mb-2 border-b border-slate-100">
        <div class="text-xs text-slate-400 uppercase tracking-wider">Sistema</div>
        <div class="text-base font-bold text-slate-800">BSS</div>
        <div class="text-[10px] text-slate-400">Benefício Social Sindical</div>
      </div>
      <ul class="space-y-1 font-medium">
  `;

  for (const grupo of MENU) {
    html += `<li class="pt-3 pb-1 px-2 text-xs font-semibold text-slate-400 uppercase tracking-wider">${grupo.grupo}</li>`;
    for (const item of grupo.itens) {
      const ativo = item.slug === slugAtivo;
      const cls = ativo
        ? "bg-indigo-50 text-indigo-900 font-medium border-l-2 border-indigo-500 ps-2"
        : "text-slate-600 hover:bg-slate-50 hover:text-slate-900";
      const corIcone = ativo ? "text-indigo-600" : "text-slate-400 group-hover:text-slate-700";
      html += `
        <li>
          <a href="${item.href}" class="flex items-center px-3 py-2 rounded-lg group transition-colors ${cls}">
            <svg class="w-5 h-5 ${corIcone} flex-shrink-0" fill="currentColor" viewBox="0 0 20 20">${item.icone}</svg>
            <span class="ms-3 flex-1 whitespace-nowrap">${item.label}</span>
          </a>
        </li>
      `;
    }
  }

  html += `
      </ul>
    </div>
  `;

  aside.innerHTML = html;
}
