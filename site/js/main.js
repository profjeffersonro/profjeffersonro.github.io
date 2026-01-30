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
    
    // Adicionar tooltips para botões PDF
    const pdfButtons = document.querySelectorAll('a[href*=".pdf"]');
    pdfButtons.forEach(button => {
        button.setAttribute('title', 'Abrir PDF em nova aba');
        button.setAttribute('target', '_blank');
        button.setAttribute('rel', 'noopener noreferrer');
    });
    
    // Função para inicializar MathJax
    function initializeMathJax() {
        if (typeof MathJax !== 'undefined') {
            console.log('MathJax carregado para GitHub Pages');
            
            MathJax.startup.promise.then(() => {
                console.log('MathJax inicializado com sucesso');
                
                if (document.querySelector('.tex2jax_process')) {
                    MathJax.typesetPromise().catch((err) => {
                        console.log('MathJax erro:', err.message);
                    });
                }
            }).catch((err) => {
                console.error('MathJax falhou ao carregar:', err);
            });
        } else {
            console.warn('MathJax não está disponível');
        }
    }
    
    // Inicializar MathJax
    setTimeout(initializeMathJax, 500);
    
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
