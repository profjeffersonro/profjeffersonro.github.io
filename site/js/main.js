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
            const lessonCard = button.closest('.lesson-card-column');
            if (lessonCard) lessonCard.dataset.answersReleased = 'true';
        }
    });

    document.addEventListener('click', event => {
        const lockedButton = event.target.closest('.resource-button-locked');
        if (lockedButton) event.preventDefault();
    });

    // Busca, filtros e expansao inteligente da pagina de disciplinas
    const lessonSearch = document.getElementById('lesson-search');
    const lessonCards = Array.from(document.querySelectorAll('.lesson-card-column'));
    const disciplineSections = Array.from(document.querySelectorAll('.discipline-section'));
    const filterButtons = Array.from(document.querySelectorAll('.lesson-filter'));
    const resultsSummary = document.getElementById('lesson-results-summary');
    const noResults = document.getElementById('lesson-no-results');
    let activeFilter = 'all';

    const normalizeSearch = value => value.normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase().trim();

    function updateLessonFilters() {
        if (!lessonSearch) return;
        const term = normalizeSearch(lessonSearch.value);
        let visibleCount = 0;

        lessonCards.forEach(card => {
            const matchesText = normalizeSearch(card.dataset.search || '').includes(term);
            const matchesFilter = activeFilter === 'all'
                || (activeFilter === 'answers' && card.dataset.answersReleased === 'true')
                || (activeFilter === 'study' && card.dataset.hasStudy === 'true');
            const visible = matchesText && matchesFilter;
            card.classList.toggle('d-none', !visible);
            if (visible) visibleCount += 1;
        });

        disciplineSections.forEach(section => {
            const hasVisibleLessons = Boolean(section.querySelector('.lesson-card-column:not(.d-none)'));
            section.classList.toggle('d-none', !hasVisibleLessons);
            if (hasVisibleLessons && (term || activeFilter !== 'all')) {
                const collapse = section.querySelector('.discipline-collapse');
                bootstrap.Collapse.getOrCreateInstance(collapse, { toggle: false }).show();
            }
        });

        if (resultsSummary) resultsSummary.textContent = `${visibleCount} aula${visibleCount === 1 ? '' : 's'} encontrada${visibleCount === 1 ? '' : 's'}.`;
        noResults?.classList.toggle('d-none', visibleCount !== 0);
    }

    lessonSearch?.addEventListener('input', updateLessonFilters);
    document.getElementById('lesson-search-clear')?.addEventListener('click', () => {
        lessonSearch.value = '';
        lessonSearch.focus();
        updateLessonFilters();
    });
    filterButtons.forEach(button => button.addEventListener('click', () => {
        activeFilter = button.dataset.filter;
        filterButtons.forEach(item => {
            const selected = item === button;
            item.classList.toggle('active', selected);
            item.classList.toggle('btn-primary', selected);
            item.classList.toggle('btn-outline-primary', !selected);
        });
        updateLessonFilters();
    }));
    updateLessonFilters();
    
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
