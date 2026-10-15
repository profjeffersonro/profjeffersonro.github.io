// JavaScript Personalizado para GitHub Pages

const BASE_URL = '/';

document.addEventListener('DOMContentLoaded', function() {
    // Adicionar classe active para links corretamente
    const currentPath = window.location.pathname;
    const navLinks = document.querySelectorAll('.nav-link');
    
    navLinks.forEach(link => {
        const linkPath = link.getAttribute('href');
        if (linkPath === currentPath || 
            (currentPath === BASE_URL && linkPath === BASE_URL) ||
            (currentPath.startsWith(BASE_URL + 'disciplinas/') && linkPath === BASE_URL + 'disciplinas/') ||
            (currentPath.startsWith(BASE_URL + 'blog/') && linkPath === BASE_URL + 'blog/')) {
            link.classList.add('active');
        }
    });
    
    // Melhorar a experiência em dispositivos móveis
    if (window.innerWidth < 768) {
        // Ajustes específicos para mobile
        document.querySelectorAll('.card-body').forEach(card => {
            card.style.padding = '1rem';
        });
    }
    
    // Tooltips dos recursos e liberacao automatica das respostas agendadas
    const tooltipElements = document.querySelectorAll('[data-bs-toggle="tooltip"]');
    tooltipElements.forEach(element => new bootstrap.Tooltip(element));

    document.querySelectorAll('.resource-button-locked').forEach(button => {
        const releaseAt = button.dataset.releaseAt;
        const resourceHref = button.dataset.resourceHref;
        if (releaseAt && resourceHref && Date.now() >= new Date(releaseAt).getTime()) {
            button.href = resourceHref;
            button.target = '_blank';
            button.rel = 'noopener noreferrer';
            button.classList.remove('resource-button-locked');
            button.removeAttribute('aria-disabled');
            button.querySelector('i')?.classList.replace('bi-lock', 'bi-check2-square');
            const tooltip = bootstrap.Tooltip.getInstance(button);
            button.setAttribute('data-bs-title', 'PDF com as respostas da aula.');
            button.setAttribute('aria-label', 'PDF com as respostas da aula.');
            tooltip?.setContent({ '.tooltip-inner': 'PDF com as respostas da aula.' });
        }
    });

    document.addEventListener('click', event => {
        const lockedButton = event.target.closest('.resource-button-locked');
        if (lockedButton) event.preventDefault();
    });
    
    // Log para debug (apenas em desenvolvimento)
    if (window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1') {
        console.log('Desenvolvimento local - Base URL:', BASE_URL);
    }
});

// Função para corrigir links se necessário
function fixExternalLinks() {
    document.querySelectorAll('a[href^="http"]').forEach(link => {
        if (!link.href.includes(window.location.hostname)) {
            link.target = '_blank';
            link.rel = 'noopener noreferrer';
        }
    });
}

// Executar após carregamento completo
window.addEventListener('load', fixExternalLinks);
