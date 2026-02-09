#!/usr/bin/env python3
"""
Script para gerar o site estático a partir dos arquivos de conteúdo.
Com sistema de cache inteligente para builds incrementais e suporte GitHub Pages.
"""

import os
import shutil
import yaml
import json
import hashlib
import argparse
import datetime
from pathlib import Path
from datetime import datetime
import re
import unicodedata

# ============================================================================
# CONFIGURAÇÃO PARA AUTOMAÇÃO NO GITHUB
# ============================================================================

def adjust_paths_for_github_pages(html_content, repo_name=None):
    """
    Ajusta caminhos para funcionar no GitHub Pages.
    
    Para repositórios .github.io (na raiz), não precisa ajustar.
    Para repositórios normais, precisa adicionar /repo_name/ antes dos caminhos.
    
    Args:
        html_content: Conteúdo HTML gerado
        repo_name: Nome do repositório (se for repositório normal)
    
    Returns:
        HTML com caminhos ajustados
    """
    if not repo_name:
        # Se for .github.io, está na raiz, não precisa ajustar
        return html_content
    
    # Remove barras duplicadas
    repo_name = repo_name.strip('/')
    
    # Substituições para caminhos absolutos que começam com /
    patterns = [
        (r'(href|src|action)="/([^"]*)"', rf'\1="/{repo_name}/\2"'),
        (r'url\(/([^)]*)\)', rf'url(/{repo_name}/\1)'),
    ]
    
    result = html_content
    for pattern, replacement in patterns:
        result = re.sub(pattern, replacement, result)
    
    return result

def get_github_repo_info():
    """
    Detecta informações do repositório GitHub baseado no ambiente.
    
    Returns:
        tuple: (repo_name, is_github_pages, base_url)
    """
    # Verificar se está rodando no GitHub Actions
    if os.environ.get('GITHUB_ACTIONS') == 'true':
        repo = os.environ.get('GITHUB_REPOSITORY', '')
        if repo:
            repo_name = repo.split('/')[-1]
            
            # Verificar se é um repositório .github.io (está na raiz)
            if repo_name.endswith('.github.io'):
                return repo_name, True, '/'
            else:
                # Repositório normal, precisa de base path
                return repo_name, True, f'/{repo_name}/'
    
    # Local development
    return None, False, '/'

def generate_sitemap(config, output_dir, base_url="https://profjeffersonro.github.io/"):
    """
    Gera sitemap.xml para melhor SEO no GitHub Pages.
    """
    sitemap = '''<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'''
    
    # Página principal
    today = datetime.now().strftime('%Y-%m-%d')
    sitemap += f'''
    <url>
        <loc>{base_url}</loc>
        <lastmod>{today}</lastmod>
        <changefreq>weekly</changefreq>
        <priority>1.0</priority>
    </url>'''
    
    # Página de disciplinas
    sitemap += f'''
    <url>
        <loc>{base_url}disciplinas/</loc>
        <lastmod>{today}</lastmod>
        <changefreq>weekly</changefreq>
        <priority>0.8</priority>
    </url>'''
    
    # Páginas individuais de aulas
    for disciplina in config['disciplinas']:
        for aula in disciplina['aulas']:
            aula_slug = create_slug(aula['name'])
            sitemap += f'''
    <url>
        <loc>{base_url}disciplinas/{aula_slug}.html</loc>
        <lastmod>{today}</lastmod>
        <changefreq>monthly</changefreq>
        <priority>0.6</priority>
    </url>'''
    
    # Página do blog
    if 'blog' in config:
        sitemap += f'''
    <url>
        <loc>{base_url}blog/</loc>
        <lastmod>{today}</lastmod>
        <changefreq>weekly</changefreq>
        <priority>0.7</priority>
    </url>'''
        
        # Posts do blog
        if 'posts' in config['blog']:
            for post in config['blog']['posts']:
                post_slug = post["title"].lower().replace(" ", "-").replace("ç", "c").replace("ã", "a").replace("õ", "o")
                sitemap += f'''
    <url>
        <loc>{base_url}blog/{post_slug}.html</loc>
        <lastmod>{today}</lastmod>
        <changefreq>monthly</changefreq>
        <priority>0.5</priority>
    </url>'''
    
    sitemap += '''
</urlset>'''
    
    # Salvar sitemap
    sitemap_file = output_dir / 'sitemap.xml'
    with open(sitemap_file, 'w', encoding='utf-8') as f:
        f.write(sitemap)
    
    return sitemap_file

# ============================================================================
# CONFIGURAÇÃO DO PARSER DE ARGUMENTOS
# ============================================================================

parser = argparse.ArgumentParser(description='Construir site estático')
parser.add_argument('--incremental', action='store_true', 
                    help='Build incremental (apenas arquivos alterados)')
parser.add_argument('--full', action='store_true',
                    help='Build completo (ignora cache)')
args = parser.parse_args()

# Modo padrão: incremental se não especificado
BUILD_MODE = 'incremental' if (args.incremental or not args.full) else 'full'

# ============================================================================
# SISTEMA DE CACHE
# ============================================================================

CACHE_FILE = '.build_cache.json'
HASH_FILE = '.file_hashes.json'

def load_cache():
    """Carrega o cache de builds anteriores"""
    if Path(CACHE_FILE).exists():
        try:
            with open(CACHE_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except:
            return {}
    return {}

def save_cache(cache):
    """Salva o cache atual"""
    with open(CACHE_FILE, 'w', encoding='utf-8') as f:
        json.dump(cache, f, indent=2)

def load_file_hashes():
    """Carrega os hashes dos arquivos"""
    if Path(HASH_FILE).exists():
        try:
            with open(HASH_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except:
            return {}
    return {}

def save_file_hashes(hashes):
    """Salva os hashes dos arquivos"""
    with open(HASH_FILE, 'w', encoding='utf-8') as f:
        json.dump(hashes, f, indent=2)

def calculate_file_hash(filepath):
    """Calcula hash MD5 de um arquivo"""
    if not Path(filepath).exists():
        return None
    
    hash_md5 = hashlib.md5()
    try:
        with open(filepath, "rb") as f:
            for chunk in iter(lambda: f.read(4096), b""):
                hash_md5.update(chunk)
        return hash_md5.hexdigest()
    except:
        return None

def needs_rebuild(filepath, file_type, current_hash, cache, file_hashes):
    """
    Verifica se um arquivo precisa ser reconstruído.
    Retorna (precisa_reconstruir, motivo)
    """
    # Se for build completo, sempre reconstrói
    if BUILD_MODE == 'full':
        return True, "Build completo forçado"
    
    # Se o arquivo não existe, precisa construir
    if not Path(filepath).exists():
        return True, "Arquivo fonte não existe"
    
    # Verificar se hash mudou
    old_hash = file_hashes.get(filepath)
    if old_hash != current_hash:
        return True, f"Hash mudou: {old_hash} -> {current_hash}"
    
    # Verificar se é um template/arquivo de dependência que mudou
    if file_type == 'template':
        # Templates afetam muitas páginas
        for cached_file in cache.get('files', {}):
            if cached_file.get('depends_on', {}).get(filepath):
                return True, f"Template '{filepath}' mudou"
    
    # Verificar dependências
    dependencies = cache.get('dependencies', {}).get(filepath, [])
    for dep in dependencies:
        if needs_rebuild(dep, 'dependency', calculate_file_hash(dep), cache, file_hashes)[0]:
            return True, f"Dependência '{dep}' mudou"
    
    return False, "Sem mudanças"

def update_cache_entry(cache, output_file, source_files, dependencies=None):
    """Atualiza entrada no cache"""
    if 'files' not in cache:
        cache['files'] = {}
    
    cache['files'][output_file] = {
        'built_at': datetime.now().isoformat(),
        'sources': source_files,
        'depends_on': dependencies or []
    }
    
    # Atualizar dependências reversas
    if 'dependencies' not in cache:
        cache['dependencies'] = {}
    
    for dep in (dependencies or []):
        if dep not in cache['dependencies']:
            cache['dependencies'][dep] = []
        if output_file not in cache['dependencies'][dep]:
            cache['dependencies'][dep].append(output_file)

# ============================================================================
# FUNÇÕES PRINCIPAIS (MANTIDAS COM PEQUENAS MODIFICAÇÕES)
# ============================================================================

def load_config():
    with open('config.yaml', 'r', encoding='utf-8') as f:
        return yaml.safe_load(f)

def create_output_structure():
    output_dir = Path('site')
    
    # Se for build completo ou diretório não existe
    if BUILD_MODE == 'full' or not output_dir.exists():
        if output_dir.exists():
            shutil.rmtree(output_dir)
        
        # Criar diretórios principais
        output_dir.mkdir(exist_ok=True)
        
        # Criar subdiretórios
        (output_dir / 'css').mkdir(exist_ok=True)
        (output_dir / 'js').mkdir(exist_ok=True)
        (output_dir / 'disciplinas').mkdir(exist_ok=True)
        (output_dir / 'blog').mkdir(exist_ok=True)
        
        # IMPORTANTE: Criar arquivo .nojekyll para GitHub Pages
        (output_dir / '.nojekyll').touch()
        
        print("  📁 Estrutura criada do zero")
    else:
        # Apenas garantir que diretórios existem
        output_dir.mkdir(exist_ok=True)
        (output_dir / 'css').mkdir(exist_ok=True)
        (output_dir / 'js').mkdir(exist_ok=True)
        (output_dir / 'disciplinas').mkdir(exist_ok=True)
        (output_dir / 'blog').mkdir(exist_ok=True)
        
        # Garantir que .nojekyll existe
        (output_dir / '.nojekyll').touch()
        
        print("  📁 Estrutura verificada")
    
    return output_dir

# ============================================================================
# FUNÇÕES DE LIMPEZA HTML (MANTIDAS)
# ============================================================================

def remove_mathjax_from_html(html_content):
    """
    Remove todas as referências ao MathJax do HTML.
    Mantém apenas o conteúdo matemático em formato correto.
    """
    patterns = [
        r'<script[^>]*>\s*(//<!\[CDATA\[\s*)?\s*window\.MathJax[^<]*</script>',
        r'<script[^>]*src=["\'][^"\']*mathjax[^"\']*["\'][^>]*></script>',
        r'<script[^>]*id=["\']MathJax-script["\'][^>]*>.*?</script>',
        r'<script[^>]*>\s*MathJax\.(hub\.)?Config\s*\{[^}]*\}\s*</script>',
        r'<script[^>]*>\s*MathJax\.(hub\.)?Queue\s*\[[^\]]*\]\s*</script>',
        r'document\.addEventListener\s*\([^)]*mathjax[^)]*\)',
        r'MathJax\.(typesetPromise|tex2svg|startup)',
        r'<!--\s*MathJax\s*.*?-->',
        r'<!--\s*\(c\)\s*Copyright.*?MathJax.*?-->',
        r'//<!\[CDATA\[\s*[\s\S]*?//\]\]>',
        r'<script[^>]*src="[^"]*tex-mml-chtml\.js"[^>]*></script>',
        r'<script[^>]*src="[^"]*MathJax\.js"[^>]*></script>',
    ]
    
    cleaned = html_content
    for pattern in patterns:
        cleaned = re.sub(pattern, '', cleaned, flags=re.DOTALL | re.IGNORECASE)
    
    cleaned = re.sub(r'\\\(([^\\]+)\\\)', r'$\1$', cleaned)
    cleaned = re.sub(r'\\\[([^\\]+)\\\]', r'$$\1$$', cleaned)
    
    return cleaned

def normalize_latex_delimiters(content):
    """
    Normaliza delimitadores LaTeX para formato consistente.
    """
    content = re.sub(r'\\\(([^\\]+)\\\)', r'$\1$', content)
    content = re.sub(r'\\\[([^\\]+)\\\]', r'$$\1$$', content)
    content = re.sub(r'\$\s+([^$]+)\s+\$', r'$\1$', content)
    content = re.sub(r'\$\$\s+([^$]+)\s+\$\$', r'$$\1$$', content)
    return content

def clean_pandoc_html_basic(html_content):
    """
    Limpeza básica de HTML do Pandoc sem dependências externas.
    Remove cabeçalhos, rodapés, scripts do MathJax e adapta ao estilo do site.
    """
    content = remove_mathjax_from_html(html_content)
    
    body_match = re.search(r'<body[^>]*>(.*?)</body>', content, re.DOTALL | re.IGNORECASE)
    if body_match:
        content = body_match.group(1)
    
    patterns_to_remove = [
        r'<header[^>]*>.*?</header>',
        r'<footer[^>]*>.*?</footer>',
        r'<nav[^>]*>.*?</nav>',
        r'<div[^>]*class="[^"]*document-header[^"]*"[^>]*>.*?</div>',
        r'<div[^>]*class="[^"]*document-footer[^"]*"[^>]*>.*?</div>',
        r'<div[^>]*id="TOC"[^>]*>.*?</div>',
        r'<script[^>]*>.*?</script>',
        r'<style[^>]*>.*?</style>',
        r'<link[^>]*>',
        r'<meta[^>]*>',
    ]
    
    for pattern in patterns_to_remove:
        content = re.sub(pattern, '', content, flags=re.DOTALL | re.IGNORECASE)
    
    content = re.sub(r'\sclass="[^"]*(container-fluid|mx-auto|justify-content-center|document-)[^"]*"', '', content)
    content = re.sub(r'\sstyle="[^"]*"', '', content)
    content = re.sub(r'\sdata-[a-z-]+="[^"]*"', '', content)
    
    content = normalize_latex_delimiters(content)
    
    replacements = [
        (r'<img([^>]+)>', r'<img\1 class="img-fluid rounded shadow mb-3">'),
        (r'<table>', r'<table class="table table-bordered table-hover mt-3 mb-4">'),
        (r'<pre>', r'<pre class="bg-light p-3 rounded border"><code>'),
        (r'</pre>', r'</code></pre>'),
        (r'<blockquote>', r'<blockquote class="blockquote bg-light p-3 border-start border-3 border-primary">'),
        (r'<h1([^>]*)>', r'<h1\1 class="mt-4 mb-3 text-primary">'),
        (r'<h2([^>]*)>', r'<h2\1 class="mt-4 mb-3 text-secondary">'),
        (r'<h3([^>]*)>', r'<h3\1 class="mt-3 mb-2">'),
        (r'<h4([^>]*)>', r'<h4\1 class="mt-2 mb-1">'),
        (r'<figure>', r'<figure class="text-center my-4">'),
        (r'<figcaption>', r'<figcaption class="text-muted small mt-2">'),
        (r'<ul>', r'<ul class="mb-3">'),
        (r'<ol>', r'<ol class="mb-3">'),
        (r'<p>', r'<p class="mb-3">'),
    ]
    
    for pattern, replacement in replacements:
        content = re.sub(pattern, replacement, content, flags=re.IGNORECASE)
    
    content = re.sub(r'\s+', ' ', content)
    content = re.sub(r'>\s+<', '><', content)
    
    return f'<div class="aula-content tex2jax_process">{content.strip()}</div>'

def is_pandoc_html(content):
    """Detecta se o HTML foi gerado pelo Pandoc"""
    pandoc_indicators = [
        '<!DOCTYPE html>',
        '<html lang="pt-BR"',
        'data-bs-theme',
        'generator.*pandoc',
        'container-main',
        'document-header',
        'document-footer'
    ]
    
    content_lower = content.lower()
    for indicator in pandoc_indicators:
        if indicator.lower() in content_lower:
            return True
    return False

def read_html_file(file_path, clean_html=True):
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        if clean_html and is_pandoc_html(content):
            content = clean_pandoc_html_basic(content)
        
        return content
    except FileNotFoundError:
        return f"<p>Conteúdo não encontrado: {file_path}</p>"
    except UnicodeDecodeError:
        try:
            with open(file_path, 'r', encoding='latin-1') as f:
                content = f.read()
            if clean_html and is_pandoc_html(content):
                content = clean_pandoc_html_basic(content)
            return content
        except:
            return f"<p>Erro ao ler arquivo: {file_path}</p>"

# ============================================================================
# FUNÇÕES COM CACHE
# ============================================================================

def copy_images_with_cache(content_path, output_path, cache, file_hashes, content_type='disciplina'):
    """Copia a pasta images/ do conteúdo (recursiva) para o site, preservando subpastas (ex.: thumbs/).

    Por que isso é necessário?
    - Seu caso: images/ pode conter apenas subpastas (ex.: images/thumbs/). O glob('*') antigo via só diretórios
      e copiava 0 arquivos.

    Mantém:
    - filtro por extensões
    - cache por hash
    """
    content_dir = Path(content_path)
    images_dir = content_dir / 'images'
    if not images_dir.exists():
        return 0

    # Determinar diretório de destino correto
    if content_type == 'disciplina':
        dest_dir = Path(output_path) / 'disciplinas' / 'images'
    else:  # blog
        dest_dir = Path(output_path) / 'blog' / 'images'

    dest_dir.mkdir(parents=True, exist_ok=True)

    allowed_exts = {'.jpg', '.jpeg', '.png', '.gif', '.svg', '.webp', '.bmp'}

    copied = 0

    # ✅ RECURSIVO: inclui subpastas (thumbs/, etc.)
    for img_file in images_dir.rglob('*'):
        if not img_file.is_file():
            continue
        if img_file.suffix.lower() not in allowed_exts:
            continue

        rel = img_file.relative_to(images_dir)   # ex.: thumbs/x.png
        dest_file = dest_dir / rel               # ex.: site/disciplinas/images/thumbs/x.png
        dest_file.parent.mkdir(parents=True, exist_ok=True)

        current_hash = calculate_file_hash(str(img_file))

        needs_copy = True
        if dest_file.exists() and BUILD_MODE == 'incremental':
            old_hash = file_hashes.get(str(img_file))
            if old_hash == current_hash:
                needs_copy = False

        if needs_copy:
            try:
                shutil.copy2(img_file, dest_file)
                file_hashes[str(img_file)] = current_hash
                copied += 1
                if BUILD_MODE == 'full' or copied <= 15:
                    print(f"    📸 Copiada: images/{rel.as_posix()}")
            except Exception as e:
                print(f"    ❌ Erro ao copiar {img_file}: {e}")

        # registrar no cache
        update_cache_entry(cache, str(dest_file), [str(img_file)])

    return copied

def create_slug(text):
    text = unicodedata.normalize('NFD', text)
    text = ''.join(c for c in text if unicodedata.category(c) != 'Mn')
    text = text.lower()
    text = re.sub(r'aula\s+(\d+)', r'aula-\1', text)
    text = re.sub(r'[^a-z0-9\s-]', '', text)
    text = re.sub(r'\s+', '-', text)
    text = re.sub(r'-+', '-', text)
    return text

# ============================================================================
# GERADOR DE PÁGINAS COM CACHE (ATUALIZADO PARA GITHUB PAGES)
# ============================================================================

def generate_html_page(title, content, config, active_page=None):
    active_home = 'active' if active_page == 'home' else ''
    active_disciplinas = 'active' if active_page == 'disciplinas' else ''
    active_blog = 'active' if active_page == 'blog' else ''
    
    # Detectar informações do GitHub
    repo_name, is_github_pages, base_url = get_github_repo_info()
    
    # Usar base_url para todos os caminhos
    mathjax_config = '''
    <!-- MathJax Centralizado -->
    <script>
    window.MathJax = {
        tex: {
            inlineMath: [['$', '$'], ['\\(', '\\)']],
            displayMath: [['$$', '$$'], ['\\[', '\\]']],
            processEscapes: true,
            processEnvironments: true
        },
        options: {
            skipHtmlTags: ['script', 'noscript', 'style', 'textarea', 'pre', 'code'],
            ignoreHtmlClass: 'tex2jax_ignore',
            processHtmlClass: 'tex2jax_process'
        },
        svg: {
            fontCache: 'global'
        },
        loader: {
            load: ['[tex]/ams', '[tex]/physics']
        },
        tex: {
            packages: {'[+]': ['ams', 'physics']}
        },
        startup: {
            ready: () => {
                console.log('MathJax is loaded and ready');
                MathJax.startup.defaultReady();
                window.dispatchEvent(new Event('MathJaxLoaded'));
            }
        }
    };
    </script>
    <script defer src="https://cdn.jsdelivr.net/npm/mathjax@4/tex-mml-chtml.js"></script>
    '''
    
    html = f'''<!DOCTYPE html>
<html lang="pt-BR">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{title} | {config['site_title']}</title>
    
    <!-- Bootstrap 5 CSS -->
    <link href="{config['css']}" rel="stylesheet">
    
    <!-- Bootstrap Icons -->
    <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/bootstrap-icons@1.10.0/font/bootstrap-icons.css">
    
    <!-- CSS Personalizado -->
    <link rel="stylesheet" href="{base_url}css/style.css">
    
    <!-- Favicon -->
    <link rel="icon" type="image/x-icon" href="{base_url}favicon.ico">
    
    {mathjax_config}
</head>
<body>
    <!-- Navbar -->
    <nav class="navbar navbar-expand-lg navbar-dark bg-primary sticky-top">
        <div class="container">
            <a class="navbar-brand" href="{base_url}">
                <i class="bi bi-easel"></i> {config['site_title']}
            </a>
            <button class="navbar-toggler" type="button" data-bs-toggle="collapse" data-bs-target="#navbarNav">
                <span class="navbar-toggler-icon"></span>
            </button>
            <div class="collapse navbar-collapse" id="navbarNav">
                <ul class="navbar-nav ms-auto">
                    <li class="nav-item">
                        <a class="nav-link {active_home}" href="{base_url}">Home</a>
                    </li>
                    <li class="nav-item">
                        <a class="nav-link {active_disciplinas}" href="{base_url}disciplinas/">Disciplinas</a>
                    </li>
                    <li class="nav-item">
                        <a class="nav-link {active_blog}" href="{base_url}blog/">Blog</a>
                    </li>
                </ul>
            </div>
        </div>
    </nav>

    <!-- Conteúdo Principal -->
    <main class="container mt-4">
        {content}
    </main>

    <!-- Footer -->
    <footer class="bg-dark text-white mt-5 py-3">
        <div class="container">
            <div class="row">
                <div class="col-md-6">
                    <h5 class="h6">{config['site_title']}</h5>
                    <p class="small mb-2">Portal de notas de aulas de física criado por {config['author']}.</p>
                </div>
                <div class="col-md-6 text-md-end">
                    <h5 class="h6">Contato</h5>
                    <p class="small mb-2">
                        <i class="bi bi-envelope"></i> {config['email']}<br>
                        <i class="bi bi-github"></i> 
                        <a href="https://github.com/profjeffersonro" class="text-white">GitHub</a>
                    </p>
                </div>
            </div>
            <div class="text-center mt-2">
                <p class="mb-0 small">&copy; {datetime.now().year} {config['site_title']}. Todos os direitos reservados.</p>
            </div>
        </div>
    </footer>

    <!-- Bootstrap JS Bundle -->
    <script src="{config['javascript']}"></script>
    
    <!-- JS Personalizado -->
    <script src="{base_url}js/main.js"></script>
    
    <script>
    document.addEventListener('DOMContentLoaded', function() {{
        function initializeMathJax() {{
            if (typeof MathJax !== 'undefined') {{
                MathJax.startup.promise.then(() => {{
                    if (document.querySelector('.tex2jax_process')) {{
                        MathJax.typesetPromise().catch((err) => {{
                            console.log('MathJax erro:', err.message);
                        }});
                    }}
                }}).catch((err) => {{
                    console.error('MathJax falhou ao carregar:', err);
                }});
                window.dispatchEvent(new Event('MathJaxLoaded'));
            }} else {{
                console.warn('MathJax não está disponível');
            }}
        }}
        
        if (typeof MathJax !== 'undefined') {{
            initializeMathJax();
        }} else {{
            window.addEventListener('MathJaxLoaded', initializeMathJax);
        }}
    }});
    </script>
</body>
</html>'''
    
    # Ajustar caminhos para GitHub Pages se necessário
    if is_github_pages and repo_name and not repo_name.endswith('.github.io'):
        html = adjust_paths_for_github_pages(html, repo_name)
    
    return html

# ============================================================================
# FUNÇÕES DE BUILD COM CACHE (MANTIDAS COM PEQUENAS MODIFICAÇÕES)
# ============================================================================

def generate_home_page_with_cache(config, output_dir, cache, file_hashes):
    """Gera página home com verificação de cache"""
    output_file = output_dir / 'index.html'
    source_file = config['home']['html']
    current_hash = calculate_file_hash(source_file)
    
    # Verificar se precisa reconstruir
    rebuild, reason = needs_rebuild(source_file, 'content', current_hash, cache, file_hashes)
    
    if not rebuild and output_file.exists() and BUILD_MODE == 'incremental':
        print(f"  ⏭️  Home (cache válido): {reason}")
        return 0
    
    print(f"  🏠 Gerando Home: {reason}")
    
    # Gerar conteúdo
    home_content = read_html_file(source_file, clean_html=False)
    
    if len(home_content.strip()) < 500:
        navigation_section = f'''
        <div class="row mt-5">
            <div class="col-md-6 mb-3">
                <div class="card h-100 text-center">
                    <div class="card-body">
                        <i class="bi bi-bookshelf display-4 text-primary mb-3"></i>
                        <h3 class="card-title">Disciplinas</h3>
                        <p class="card-text">Acesse todas as aulas organizadas por disciplina.</p>
                        <a href="/disciplinas/" class="btn btn-primary btn-lg">
                            <i class="bi bi-arrow-right"></i> Ver Disciplinas
                        </a>
                    </div>
                </div>
            </div>
            <div class="col-md-6 mb-3">
                <div class="card h-100 text-center">
                    <div class="card-body">
                        <i class="bi bi-newspaper display-4 text-primary mb-3"></i>
                        <h3 class="card-title">Blog</h3>
                        <p class="card-text">Leia artigos e reflexões sobre física.</p>
                        <a href="/blog/" class="btn btn-primary btn-lg">
                            <i class="bi bi-arrow-right"></i> Ver Blog
                        </a>
                    </div>
                </div>
            </div>
        </div>
        '''
        content = home_content + navigation_section
    else:
        content = home_content
    
    html = generate_html_page('Home', content, config, active_page='home')
    
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write(html)
    
    # Atualizar cache
    file_hashes[source_file] = current_hash
    update_cache_entry(cache, str(output_file), [source_file])
    return 1

def generate_disciplinas_page_with_cache(config, output_dir, cache, file_hashes):
    """Gera página de disciplinas com cache"""
    output_file = output_dir / 'disciplinas' / 'index.html'
    source_files = ['config.yaml']
    
    # Verificar se precisa reconstruir
    rebuild = BUILD_MODE == 'full'
    reason = "Build completo" if rebuild else "Cache válido"
    
    if BUILD_MODE == 'incremental':
        for source in source_files:
            current_hash = calculate_file_hash(source)
            needs, r = needs_rebuild(source, 'config', current_hash, cache, file_hashes)
            if needs:
                rebuild = True
                reason = r
                break
    
    if not rebuild and output_file.exists():
        print(f"  ⏭️  Página de Disciplinas (cache válido): {reason}")
        return 0
    
    print(f"  📚 Gerando Página de Disciplinas: {reason}")
    
    # Gerar conteúdo
    disciplinas_html = ''
    
    for disciplina in config['disciplinas']:
        disciplinas_html += f'''
        <div class="card mb-4">
            <div class="card-header bg-primary text-white">
                <h3 class="mb-0">
                    <i class="bi bi-journal-bookmark"></i> {disciplina['disciplina']}
                </h3>
            </div>
            <div class="card-body">
                <div class="row">
        '''
        
        for aula in disciplina['aulas']:
            aula_slug = create_slug(aula['name'])
            
            disciplinas_html += f'''
                    <div class="col-md-6 mb-3">
                        <div class="card h-100">
                            <div class="card-body">
                                <h5 class="card-title">
                                    <i class="bi bi-journal-text text-primary"></i> {aula['name']}
                                </h5>
                                <div class="mt-3">
                                    <a href="/disciplinas/{aula_slug}.html" class="btn btn-outline-primary btn-sm me-2">
                                        <i class="bi bi-file-text"></i> Ver Aula
                                    </a>
            '''
            
            if aula.get('pdf'):
                disciplinas_html += f'''
                                    <a href="{aula['pdf']}" class="btn btn-outline-success btn-sm" target="_blank">
                                        <i class="bi bi-file-earmark-pdf"></i> PDF
                                    </a>
                '''
            
            disciplinas_html += '''
                                </div>
                            </div>
                        </div>
                    </div>
            '''
        
        disciplinas_html += '''
                </div>
            </div>
        </div>
        '''
    
    content = f'''
    <nav aria-label="breadcrumb">
        <ol class="breadcrumb">
            <li class="breadcrumb-item"><a href="/">Home</a></li>
            <li class="breadcrumb-item active">Disciplinas</li>
        </ol>
    </nav>
    
    <h1 class="mb-4"><i class="bi bi-bookshelf"></i> Disciplinas</h1>
    <p class="lead mb-4">Selecione uma disciplina e aula para começar seus estudos.</p>
    
    {disciplinas_html}
    
    <div class="text-center mt-4">
        <a href="/" class="btn btn-outline-primary">
            <i class="bi bi-arrow-left"></i> Voltar para Home
        </a>
    </div>
    '''
    
    html = generate_html_page('Disciplinas', content, config, active_page='disciplinas')
    
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write(html)
    
    # Atualizar cache
    for source in source_files:
        file_hashes[source] = calculate_file_hash(source)
    update_cache_entry(cache, str(output_file), source_files)
    return 1

def generate_aula_pages_with_cache(config, output_dir, cache, file_hashes):
    """Gera páginas individuais de aulas com cache - VERSÃO CORRIGIDA"""
    total_generated = 0
    total_skipped = 0
    
    for disciplina in config['disciplinas']:
        print(f"\n  📘 Disciplina: {disciplina['disciplina']}")
        
        for aula in disciplina['aulas']:
            # Criar slug para a aula
            aula_slug = create_slug(aula['name'])
            output_file = output_dir / 'disciplinas' / f'{aula_slug}.html'
            source_file = aula['html']
            current_hash = calculate_file_hash(source_file)
            
            # Verificar se precisa reconstruir
            rebuild, reason = needs_rebuild(source_file, 'content', current_hash, cache, file_hashes)
            
            # Verificar se imagens foram alteradas
            aula_path = Path(source_file).parent
            images_dir = aula_path / 'images'
            if images_dir.exists():
                for img_file in images_dir.glob('*'):
                    if img_file.suffix.lower() in ['.jpg', '.jpeg', '.png', '.gif', '.svg', '.webp', '.bmp']:
                        img_hash = calculate_file_hash(str(img_file))
                        old_hash = file_hashes.get(str(img_file))
                        if old_hash != img_hash:
                            rebuild = True
                            reason = f"Imagem {img_file.name} alterada"
                            break
            
            if not rebuild and output_file.exists() and BUILD_MODE == 'incremental':
                print(f"    ⏭️  {aula['name']} (cache válido)")
                total_skipped += 1
                continue
            
            print(f"    📖 Gerando {aula['name']}")
            if reason != "Build completo forçado":
                print(f"       Motivo: {reason}")
            
            # Ler conteúdo da aula COM limpeza
            aula_content = read_html_file(source_file, clean_html=True)
            
            # Copiar imagens (sempre verifica se precisa)
            aula_path = Path(source_file).parent
            copied_images = copy_images_with_cache(aula_path, output_dir, cache, file_hashes, content_type='disciplina')
            if copied_images > 0:
                print(f"       📸 Copiadas {copied_images} imagens")
            
            # Gerar botão para PDF
            pdf_button = ''
            if aula.get('pdf'):
                pdf_button = f'''
                <div class="text-center mb-4">
                    <a href="{aula['pdf']}" 
                       class="btn btn-success btn-lg" 
                       target="_blank" 
                       rel="noopener noreferrer">
                        <i class="bi bi-file-earmark-pdf"></i> Acessar PDF
                    </a>
                </div>
                '''
            
            content = f'''
            <nav aria-label="breadcrumb">
                <ol class="breadcrumb">
                    <li class="breadcrumb-item"><a href="/">Home</a></li>
                    <li class="breadcrumb-item"><a href="/disciplinas/">Disciplinas</a></li>
                    <li class="breadcrumb-item active">{disciplina['disciplina']}</li>
                </ol>
            </nav>
            
            <div class="card mb-4">
                <div class="card-header bg-primary text-white">
                    <h2 class="mb-0">{aula['name']}</h2>
                    <p class="mb-0 mt-2"><i class="bi bi-journal-bookmark"></i> {disciplina['disciplina']}</p>
                </div>
                <div class="card-body">
                    {pdf_button}
                    <div class="aula-content">
                        {aula_content}
                    </div>
                </div>
            </div>
            
            <div class="d-flex justify-content-between">
                <a href="/disciplinas/" class="btn btn-outline-primary">
                    <i class="bi bi-arrow-left"></i> Voltar para Disciplinas
                </a>
                <a href="/" class="btn btn-outline-secondary">
                    <i class="bi bi-house"></i> Ir para Home
                </a>
            </div>
            '''
            
            html = generate_html_page(aula['name'], content, config, active_page='disciplinas')
            
            with open(output_file, 'w', encoding='utf-8') as f:
                f.write(html)
            
            # Atualizar cache
            file_hashes[source_file] = current_hash
            update_cache_entry(cache, str(output_file), [source_file])
            total_generated += 1
    
    return total_generated, total_skipped

def generate_blog_page_with_cache(config, output_dir, cache, file_hashes):
    """Gera página de listagem do blog com cache"""
    output_file = output_dir / 'blog' / 'index.html'
    source_files = ['config.yaml']
    
    # Verificar se precisa reconstruir
    rebuild = BUILD_MODE == 'full'
    reason = "Build completo" if rebuild else "Cache válido"
    
    if BUILD_MODE == 'incremental':
        for source in source_files:
            current_hash = calculate_file_hash(source)
            needs, r = needs_rebuild(source, 'config', current_hash, cache, file_hashes)
            if needs:
                rebuild = True
                reason = r
                break
    
    if not rebuild and output_file.exists():
        print(f"  ⏭️  Página do Blog (cache válido): {reason}")
        return 0
    
    print(f"  📰 Gerando Página do Blog: {reason}")
    
    # Gerar conteúdo
    posts_list = ''
    
    if 'blog' in config and 'posts' in config['blog']:
        for post in config['blog']['posts']:
            post_slug = post["title"].lower().replace(" ", "-").replace("ç", "c").replace("ã", "a").replace("õ", "o")
            
            posts_list += f'''
            <div class="card mb-4">
                <div class="card-body">
                    <h3 class="card-title">{post['title']}</h3>
                    <p class="card-text">
                        <small class="text-muted">
                            <i class="bi bi-calendar"></i> Publicado em: {post['date']}
                        </small>
                    </p>
                    <div class="mt-3">
                        <a href="/blog/{post_slug}.html" class="btn btn-primary me-2">
                            <i class="bi bi-book"></i> Ler artigo completo
                        </a>
            '''
            
            if post.get('pdf'):
                posts_list += f'''
                        <a href="{post['pdf']}" class="btn btn-outline-success" target="_blank">
                            <i class="bi bi-file-earmark-pdf"></i> Ver PDF
                        </a>
                '''
            
            posts_list += '''
                    </div>
                </div>
            </div>
            '''
    else:
        posts_list = '<p class="text-center">Nenhum post disponível no momento.</p>'
    
    content = f'''
    <nav aria-label="breadcrumb">
        <ol class="breadcrumb">
            <li class="breadcrumb-item"><a href="/">Home</a></li>
            <li class="breadcrumb-item active">Blog</li>
        </ol>
    </nav>
    
    <h1 class="mb-4"><i class="bi bi-newspaper"></i> Blog</h1>
    <p class="lead mb-4">Artigos, tutoriais e reflexões sobre física e ciência.</p>
    
    <div class="row">
        <div class="col-12">
            {posts_list}
        </div>
    </div>
    
    <div class="text-center mt-4">
        <a href="/" class="btn btn-outline-primary">
            <i class="bi bi-arrow-left"></i> Voltar para Home
        </a>
    </div>
    '''
    
    html = generate_html_page('Blog', content, config, active_page='blog')
    
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write(html)
    
    # Atualizar cache
    for source in source_files:
        file_hashes[source] = calculate_file_hash(source)
    update_cache_entry(cache, str(output_file), source_files)
    return 1

def generate_blog_post_pages_with_cache(config, output_dir, cache, file_hashes):
    """Gera páginas individuais dos posts do blog com cache - VERSÃO CORRIGIDA"""
    total_generated = 0
    total_skipped = 0
    
    if config.get('blog') and config['blog'].get('posts'):
        print(f"\n  📝 Posts do Blog:")
        
        for post in config['blog']['posts']:
            # Criar slug para o post
            post_slug = post["title"].lower().replace(" ", "-").replace("ç", "c").replace("ã", "a").replace("õ", "o")
            output_file = output_dir / 'blog' / f'{post_slug}.html'
            source_file = post['html']
            current_hash = calculate_file_hash(source_file)
            
            # Verificar se precisa reconstruir
            rebuild, reason = needs_rebuild(source_file, 'content', current_hash, cache, file_hashes)
            
            # Verificar se imagens foram alteradas
            post_path = Path(source_file).parent
            images_dir = post_path / 'images'
            if images_dir.exists():
                for img_file in images_dir.glob('*'):
                    if img_file.suffix.lower() in ['.jpg', '.jpeg', '.png', '.gif', '.svg', '.webp', '.bmp']:
                        img_hash = calculate_file_hash(str(img_file))
                        old_hash = file_hashes.get(str(img_file))
                        if old_hash != img_hash:
                            rebuild = True
                            reason = f"Imagem {img_file.name} alterada"
                            break
            
            if not rebuild and output_file.exists() and BUILD_MODE == 'incremental':
                print(f"    ⏭️  {post['title']} (cache válido)")
                total_skipped += 1
                continue
            
            print(f"    📝 Gerando {post['title']}")
            if reason != "Build completo forçado":
                print(f"       Motivo: {reason}")
            
            # Ler conteúdo do post
            post_content = read_html_file(source_file, clean_html=True)
            
            # Copiar imagens
            post_path = Path(source_file).parent
            copied_images = copy_images_with_cache(post_path, output_dir, cache, file_hashes, content_type='blog')
            if copied_images > 0:
                print(f"       📸 Copiadas {copied_images} imagens")
            
            # Gerar botão para PDF
            pdf_button = ''
            if post.get('pdf'):
                pdf_button = f'''
                <div class="text-center mb-4">
                    <a href="{post['pdf']}" 
                       class="btn btn-success btn-lg" 
                       target="_blank" 
                       rel="noopener noreferrer">
                        <i class="bi bi-file-earmark-pdf"></i> Acessar PDF
                    </a>
                </div>
                '''
            
            content = f'''
            <nav aria-label="breadcrumb">
                <ol class="breadcrumb">
                    <li class="breadcrumb-item"><a href="/">Home</a></li>
                    <li class="breadcrumb-item"><a href="/blog/">Blog</a></li>
                    <li class="breadcrumb-item active">{post['title']}</li>
                </ol>
            </nav>
            
            <div class="card mb-4">
                <div class="card-header bg-primary text-white">
                    <h1 class="mb-0">{post['title']}</h1>
                    <p class="mb-0 mt-2">
                        <i class="bi bi-calendar"></i> Publicado em: {post['date']}
                    </p>
                </div>
                <div class="card-body">
                    {pdf_button}
                    <div class="blog-content">
                        {post_content}
                    </div>
                </div>
            </div>
            
            <div class="d-flex justify-content-between">
                <a href="/blog/" class="btn btn-outline-primary">
                    <i class="bi bi-arrow-left"></i> Voltar para Blog
                </a>
                <a href="/" class="btn btn-outline-secondary">
                    <i class="bi bi-house"></i> Ir para Home
                </a>
            </div>
            '''
            
            html = generate_html_page(post['title'], content, config, active_page='blog')
            
            with open(output_file, 'w', encoding='utf-8') as f:
                f.write(html)
            
            # Atualizar cache
            file_hashes[source_file] = current_hash
            update_cache_entry(cache, str(output_file), [source_file])
            total_generated += 1
    
    return total_generated, total_skipped

def copy_static_files_with_cache(output_dir, cache, file_hashes):
    """Copia arquivos estáticos apenas se necessário - ATUALIZADO PARA GITHUB PAGES"""
    copied_files = 0
    skipped_files = 0
    
    # CSS personalizado
    if Path('style.css').exists():
        source_css = 'style.css'
        dest_css = output_dir / 'css' / 'style.css'
        current_hash = calculate_file_hash(source_css)
        
        # Verificar se precisa copiar
        needs_copy = True
        if dest_css.exists() and BUILD_MODE == 'incremental':
            old_hash = file_hashes.get(source_css)
            if old_hash == current_hash:
                needs_copy = False
                skipped_files += 1
        
        if needs_copy:
            shutil.copy2(source_css, dest_css)
            file_hashes[source_css] = current_hash
            copied_files += 1
    else:
        # Criar CSS básico se não existir
        dest_css = output_dir / 'css' / 'style.css'
        css_content = '''/* CSS Personalizado para GitHub Pages */
body {
    font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
    line-height: 1.6;
}

.card {
    transition: transform 0.3s;
}

.card:hover {
    transform: translateY(-5px);
}

.aula-content, .blog-content {
    font-size: 1.1rem;
    line-height: 1.7;
}

.aula-content img, .blog-content img {
    max-width: 100%;
    height: auto;
    border-radius: 8px;
    margin: 1rem 0;
}

.aula-content figure, .blog-content figure {
    text-align: center;
    margin: 1.5rem 0;
}

.aula-content figcaption, .blog-content figcaption {
    font-style: italic;
    color: #666;
    margin-top: 0.5rem;
}

pre {
    background-color: #f8f9fa;
    padding: 1rem;
    border-radius: 5px;
    overflow-x: auto;
}

code {
    background-color: #f8f9fa;
    padding: 0.2rem 0.4rem;
    border-radius: 3px;
}

.table {
    background-color: white;
}

.jumbotron {
    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
    color: white;
}

.navbar-brand {
    font-weight: bold;
}

.navbar-nav .nav-link.active {
    font-weight: bold;
    background-color: rgba(255, 255, 255, 0.1);
    border-radius: 5px;
}

.footer {
    margin-top: auto;
}

/* Estilos para conteúdo limpo do Pandoc */
.aula-content h1 {
    color: #0d6efd;
    border-bottom: 2px solid #0d6efd;
    padding-bottom: 0.5rem;
    margin-bottom: 1.5rem;
}

.aula-content h2 {
    color: #6c757d;
    margin-top: 2rem;
    margin-bottom: 1rem;
}

.aula-content ul, .aula-content ol {
    padding-left: 1.5rem;
    margin-bottom: 1rem;
}

.aula-content li {
    margin-bottom: 0.5rem;
}

/* Estilos para MathJax */
.math {
    font-size: 1.1em;
}

.MathJax {
    outline: none;
}

/* Garantir que fórmulas não quebrem layout */
.mjx-chtml {
    overflow-x: auto;
    overflow-y: hidden;
    max-width: 100%;
}

/* Fórmulas inline */
.MathJax_Preview, .MJXc-display {
    margin: 1em 0;
}

/* Fórmulas em display mode */
div.math.display {
    text-align: center;
    margin: 1.5em 0;
    padding: 0.5em;
    background-color: #f8f9fa;
    border-radius: 5px;
    overflow-x: auto;
}

/* Classes para controlar processamento do MathJax */
.tex2jax_ignore {
    /* Conteúdo ignorado pelo MathJax */
}

.tex2jax_process {
    /* Conteúdo processado pelo MathJax */
}

/* Responsividade para fórmulas matemáticas */
@media (max-width: 768px) {
    .display-4 {
        font-size: 2rem;
    }
    
    .jumbotron {
        padding: 2rem 1rem !important;
    }
    
    .aula-content, .blog-content {
        font-size: 1rem;
    }
    
    .MathJax {
        font-size: 90%;
    }
    
    .mjx-chtml {
        font-size: 110% !important;
    }
}

/* Estilo para equações numeradas */
.mjx-denominator {
    font-size: 0.9em;
}

.mjx-numerator {
    font-size: 0.9em;
}
'''
        
        # Verificar se CSS precisa ser atualizado
        current_css_hash = hashlib.md5(css_content.encode()).hexdigest()
        old_css_hash = file_hashes.get('generated_css')
        
        if not dest_css.exists() or BUILD_MODE == 'full' or current_css_hash != old_css_hash:
            with open(dest_css, 'w', encoding='utf-8') as f:
                f.write(css_content)
            file_hashes['generated_css'] = current_css_hash
            copied_files += 1
        else:
            skipped_files += 1
    
    # JS personalizado - ATUALIZADO PARA GITHUB PAGES
    repo_name, is_github_pages, base_url = get_github_repo_info()
    
    dest_js = output_dir / 'js' / 'main.js'
    js_content = f'''// JavaScript Personalizado para GitHub Pages

const BASE_URL = '{base_url}';

document.addEventListener('DOMContentLoaded', function() {{
    // Adicionar classe active para links corretamente
    const currentPath = window.location.pathname;
    const navLinks = document.querySelectorAll('.nav-link');
    
    navLinks.forEach(link => {{
        const linkPath = link.getAttribute('href');
        if (linkPath === currentPath || 
            (currentPath === BASE_URL && linkPath === BASE_URL) ||
            (currentPath.startsWith(BASE_URL + 'disciplinas/') && linkPath === BASE_URL + 'disciplinas/') ||
            (currentPath.startsWith(BASE_URL + 'blog/') && linkPath === BASE_URL + 'blog/')) {{
            link.classList.add('active');
        }}
    }});
    
    // Melhorar a experiência em dispositivos móveis
    if (window.innerWidth < 768) {{
        // Ajustes específicos para mobile
        document.querySelectorAll('.card-body').forEach(card => {{
            card.style.padding = '1rem';
        }});
    }}
    
    // Adicionar tooltips para botões PDF
    const pdfButtons = document.querySelectorAll('a[href*=".pdf"]');
    pdfButtons.forEach(button => {{
        button.setAttribute('title', 'Abrir PDF em nova aba');
        button.setAttribute('target', '_blank');
        button.setAttribute('rel', 'noopener noreferrer');
    }});
    
    // Função para inicializar MathJax
    function initializeMathJax() {{
        if (typeof MathJax !== 'undefined') {{
            console.log('MathJax carregado para GitHub Pages');
            
            MathJax.startup.promise.then(() => {{
                console.log('MathJax inicializado com sucesso');
                
                if (document.querySelector('.tex2jax_process')) {{
                    MathJax.typesetPromise().catch((err) => {{
                        console.log('MathJax erro:', err.message);
                    }});
                }}
            }}).catch((err) => {{
                console.error('MathJax falhou ao carregar:', err);
            }});
        }} else {{
            console.warn('MathJax não está disponível');
        }}
    }}
    
    // Inicializar MathJax
    setTimeout(initializeMathJax, 500);
    
    // Log para debug (apenas em desenvolvimento)
    if (window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1') {{
        console.log('Desenvolvimento local - Base URL:', BASE_URL);
    }}
}});

// Função para corrigir links se necessário
function fixExternalLinks() {{
    document.querySelectorAll('a[href^="http"]').forEach(link => {{
        if (!link.href.includes(window.location.hostname)) {{
            link.target = '_blank';
            link.rel = 'noopener noreferrer';
        }}
    }});
}}

// Executar após carregamento completo
window.addEventListener('load', fixExternalLinks);
'''
    
    # Verificar se JS precisa ser atualizado
    current_js_hash = hashlib.md5(js_content.encode()).hexdigest()
    old_js_hash = file_hashes.get('github_pages_js')
    
    if not dest_js.exists() or BUILD_MODE == 'full' or current_js_hash != old_js_hash:
        with open(dest_js, 'w', encoding='utf-8') as f:
            f.write(js_content)
        file_hashes['github_pages_js'] = current_js_hash
        copied_files += 1
        print(f"    📝 JS atualizado para GitHub Pages")
    else:
        skipped_files += 1
    
    # Favicon placeholder
    favicon_file = output_dir / 'favicon.ico'
    if not favicon_file.exists() or BUILD_MODE == 'full':
        # Criar favicon simples
        with open(favicon_file, 'wb') as f:
            # Ícone vazio (será substituído se tiver um favicon real)
            pass
        copied_files += 1
    else:
        skipped_files += 1
    
    # Criar robots.txt para SEO
    robots_file = output_dir / 'robots.txt'
    robots_content = f'''# robots.txt para GitHub Pages
User-agent: *
Allow: /
Disallow: /admin/
Disallow: /private/

Sitemap: https://profjeffersonro.github.io/sitemap.xml
'''
    
    if not robots_file.exists() or BUILD_MODE == 'full':
        with open(robots_file, 'w', encoding='utf-8') as f:
            f.write(robots_content)
        copied_files += 1
        print(f"    🤖 robots.txt criado")
    
    return copied_files, skipped_files

def clean_cache():
    """Limpa todos os arquivos de cache"""
    cache_files = [CACHE_FILE, HASH_FILE]
    for cache_file in cache_files:
        if Path(cache_file).exists():
            Path(cache_file).unlink()
            print(f"🗑️  Cache limpo: {cache_file}")

def remove_orphaned_files(output_dir, cache):
    """Remove arquivos no site que não estão mais no cache"""
    if BUILD_MODE != 'incremental':
        return 0
    
    removed = 0
    
    # Listar todos os arquivos no site
    site_files = []
    for file_path in output_dir.rglob('*'):
        if file_path.is_file():
            site_files.append(str(file_path))
    
    # Verificar quais arquivos estão no cache
    cached_files = list(cache.get('files', {}).keys())
    
    # Remover arquivos que não estão no cache
    for site_file in site_files:
        if site_file not in cached_files and not any(site_file.endswith(ext) for ext in ['.ico', '.nojekyll', 'sitemap.xml', 'robots.txt']):
            try:
                Path(site_file).unlink()
                print(f"🧹 Removido arquivo órfão: {site_file}")
                removed += 1
                
                # Remover diretórios vazios
                parent_dir = Path(site_file).parent
                try:
                    if parent_dir.exists() and not any(parent_dir.iterdir()):
                        parent_dir.rmdir()
                        print(f"🧹 Removido diretório vazio: {parent_dir}")
                except:
                    pass
            except:
                pass
    
    return removed

# ============================================================================
# FUNÇÃO PRINCIPAL ATUALIZADA PARA GITHUB PAGES
# ============================================================================

def main():
    print("🛠️ Iniciando construção do site...")
    print(f"🔧 Modo: {BUILD_MODE.upper()}")
    
    # Detectar se está no GitHub Pages
    repo_name, is_github_pages, base_url = get_github_repo_info()
    if is_github_pages:
        print(f"🌐 GitHub Pages detectado: {repo_name}")
        print(f"📍 Base URL: {base_url}")
    else:
        print("💻 Desenvolvimento local")
    
    print("📚 MathJax centralizado ativado")
    
    try:
        # Carregar configuração
        config = load_config()
        print("✅ Configuração carregada")
        
        # Carregar cache
        cache = load_cache()
        file_hashes = load_file_hashes()
        
        # Criar estrutura de output
        output_dir = create_output_structure()
        print("✅ Estrutura de diretórios criada/verificada")        
     
        # Contadores
        total_generated = 0
        total_skipped = 0
        
        # Gerar páginas
        print("\n📄 Gerando páginas:")
        generated = generate_home_page_with_cache(config, output_dir, cache, file_hashes)
        total_generated += generated
        total_skipped += 1 - generated
        
        generated = generate_disciplinas_page_with_cache(config, output_dir, cache, file_hashes)
        total_generated += generated
        total_skipped += 1 - generated
        
        aulas_generated, aulas_skipped = generate_aula_pages_with_cache(config, output_dir, cache, file_hashes)
        total_generated += aulas_generated
        total_skipped += aulas_skipped
        
        generated = generate_blog_page_with_cache(config, output_dir, cache, file_hashes)
        total_generated += generated
        total_skipped += 1 - generated
        
        posts_generated, posts_skipped = generate_blog_post_pages_with_cache(config, output_dir, cache, file_hashes)
        total_generated += posts_generated
        total_skipped += posts_skipped
        
        # Copiar arquivos estáticos
        print("\n📦 Copiando arquivos estáticos:")
        static_copied, static_skipped = copy_static_files_with_cache(output_dir, cache, file_hashes)
        total_generated += static_copied
        total_skipped += static_skipped
        
        # Gerar sitemap.xml para SEO
        if is_github_pages or BUILD_MODE == 'full':
            print("\n🗺️  Gerando sitemap.xml para SEO...")
            try:
                sitemap_file = generate_sitemap(config, output_dir)
                total_generated += 1
                print(f"    ✅ Sitemap gerado: {sitemap_file}")
            except Exception as e:
                print(f"    ⚠️  Erro ao gerar sitemap: {e}")
        
        # Remover arquivos órfãos (apenas no modo incremental)
        if BUILD_MODE == 'incremental':
            print("\n🧹 Limpando arquivos órfãos:")
            orphaned_removed = remove_orphaned_files(output_dir, cache)
            if orphaned_removed > 0:
                print(f"   Removidos {orphaned_removed} arquivos órfãos")
        
        # Salvar cache
        cache['last_build'] = datetime.now().isoformat()
        cache['build_mode'] = BUILD_MODE
        if is_github_pages:
            cache['github_pages'] = True
            cache['repo_name'] = repo_name
        save_cache(cache)
        save_file_hashes(file_hashes)
        
        print(f"\n🎉 Site construído com sucesso!")
        print(f"📍 Diretório de saída: {output_dir.absolute()}")
        print(f"📊 Estatísticas do build:")
        print(f"   📄 Páginas geradas: {total_generated}")
        print(f"   ⏭️  Páginas em cache: {total_skipped}")
        print(f"   📖 Aulas: {aulas_generated} geradas, {aulas_skipped} em cache")
        print(f"   📝 Posts: {posts_generated} gerados, {posts_skipped} em cache")
        print(f"   📦 Arquivos estáticos: {static_copied} copiados, {static_skipped} em cache")
        
        # Verificar se há imagens no site
        image_count = 0
        for ext in ['*.jpg', '*.jpeg', '*.png', '*.gif', '*.svg', '*.webp', '*.bmp']:
            image_count += len(list(output_dir.rglob(ext)))
        
        if image_count > 0:
            print(f"   🖼️  Imagens encontradas no site: {image_count}")
        
        # Verificar arquivos importantes para GitHub Pages
        print(f"\n🔍 Verificando arquivos importantes:")
        important_files = ['.nojekyll', 'sitemap.xml', 'robots.txt', 'favicon.ico']
        for file in important_files:
            file_path = output_dir / file
            if file_path.exists():
                print(f"   ✅ {file}")
            else:
                print(f"   ⚠️  {file} (não encontrado)")
        
        if BUILD_MODE == 'incremental':
            print(f"\n💾 Cache salvo para builds futuros")
            print(f"   Para limpar o cache: $ python build.py --full")
        
        if is_github_pages:
            print(f"\n🚀 Pronto para GitHub Pages!")
            print(f"   URL: https://{repo_name}/")
            print(f"   Actions: https://github.com/profjeffersonro/{repo_name}/actions")
        else:
            print(f"\n🚀 Para visualizar o site localmente:")
            print(f"   $ ./make.sh serve")
        
    except Exception as e:
        print(f"❌ Erro durante a construção: {str(e)}")
        import traceback
        traceback.print_exc()
        exit(1)

if __name__ == '__main__':
    main()
