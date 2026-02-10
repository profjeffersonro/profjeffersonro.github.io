#!/bin/bash

# Verificar dependências
if ! command -v python &> /dev/null && ! command -v python3 &> /dev/null; then
    echo "❌ Python não encontrado. Instale o Python para continuar."
    exit 1
fi

# Tentar encontrar python ou python3
PYTHON_CMD=""
if command -v python &> /dev/null; then
    PYTHON_CMD="python"
elif command -v python3 &> /dev/null; then
    PYTHON_CMD="python3"
fi

# Porta padrão
PORT=${2:-8000}
URL="http://localhost:$PORT"

# Detectar nome do repo (para simular GitHub Pages localmente)
REPO_NAME=$(basename -s .git "$(git config --get remote.origin.url 2>/dev/null)")
if [[ -n "$REPO_NAME" && "$REPO_NAME" != "profjeffersonro.github.io" ]]; then
    URL="http://localhost:$PORT/$REPO_NAME/"
fi

# Função para verificar se a porta está livre
check_port() {
    if lsof -i :$PORT > /dev/null 2>&1; then
        echo "❌ A porta $PORT já está em uso. Libere-a antes de iniciar o servidor."
        echo "   Use: sudo lsof -i :$PORT  # para ver qual processo está usando"
        echo "   Use: kill -9 <PID>        # para matar o processo"
        echo "   Ou use: $0 serve $((PORT+1))  # para usar outra porta"
        exit 1
    fi
}

# Função para encontrar navegador Chromium/Chrome
find_chromium() {
    # Lista de possíveis executáveis do Chromium/Chrome
    local browsers=(
        "chromium-browser"
        "chromium"
        "google-chrome"
        "google-chrome-stable"
        "chrome"
        "microsoft-edge"
        "brave-browser"
    )
    
    for browser in "${browsers[@]}"; do
        if command -v "$browser" &> /dev/null; then
            echo "$browser"
            return 0
        fi
    done
    
    echo ""
    return 1
}

# Função para matar processos na porta
kill_port() {
    echo "🛑 Limpando processos na porta $PORT..."
    local pids=$(lsof -ti :$PORT 2>/dev/null)
    
    if [ -n "$pids" ]; then
        echo "   Encontrado PID(s): $pids"
        kill -9 $pids 2>/dev/null
        sleep 1
        echo "✅ Processos terminados."
    fi
}

# Comandos principais
case "$1" in
    build)
        echo "🛠️ Construindo o site (modo incremental)..."
        echo "   📚 MathJax centralizado ativado"
        echo "   💾 Usando cache para arquivos não modificados"
        $PYTHON_CMD build.py --incremental
        if [ $? -eq 0 ]; then
            echo "✅ Site construído com sucesso!"
        else
            echo "❌ Falha ao construir o site."
            exit 1
        fi
        ;;
        
    build-full)
        echo "🛠️ Construindo o site (reconstrução completa)..."
        echo "   📚 MathJax centralizado ativado"
        echo "   🗑️  Ignorando cache, reconstruindo tudo"
        $PYTHON_CMD build.py --full
        if [ $? -eq 0 ]; then
            echo "✅ Site construído com sucesso!"
        else
            echo "❌ Falha ao construir o site."
            exit 1
        fi
        ;;
        
    serve)
        echo "🚀 Preparando para servir o site em $URL"
        
        # Verificar se o diretório site existe
        if [ ! -d "site" ]; then
            echo "⚠️ Diretório 'site/' não encontrado. Construindo o site primeiro..."
            $0 build
            if [ $? -ne 0 ]; then
                exit 1
            fi
        fi
        
        # Limpar porta se estiver em uso
        kill_port
        check_port
        
        # Encontrar navegador
        BROWSER=$(find_chromium)
        
        if [ -z "$BROWSER" ]; then
            echo "⚠️ Navegador Chromium/Chrome não encontrado."
            echo "   O site será servido, mas não será aberto automaticamente."
            echo "   Acesse manualmente: $URL"
            AUTO_OPEN=false
        else
            echo "✅ Navegador encontrado: $BROWSER"
            AUTO_OPEN=true
        fi
        
        # Iniciar servidor em background
        echo "🌐 Iniciando servidor HTTP na porta $PORT..."
        cd site || exit
        
        # Iniciar servidor Python em background
        $PYTHON_CMD -m http.server $PORT &
        SERVER_PID=$!
        
        # Aguardar servidor iniciar
        sleep 2
        
        # Verificar se servidor está rodando
        if ! kill -0 $SERVER_PID 2>/dev/null; then
            echo "❌ Falha ao iniciar o servidor."
            exit 1
        fi
        
        echo "✅ Servidor iniciado com PID: $SERVER_PID"
        echo "📡 URL: $URL"
        
        # Abrir navegador se disponível
        if [ "$AUTO_OPEN" = true ]; then
            echo "🌍 Abrindo navegador..."
            # Abrir em nova janela (modo app pode ser usado: --app=$URL)
            $BROWSER --new-window "$URL" > /dev/null 2>&1 &
            BROWSER_PID=$!
            echo "✅ Navegador aberto com PID: $BROWSER_PID"
        fi
        
        # Função para limpeza ao sair
        cleanup() {
            echo ""
            echo "🛑 Recebido sinal de término..."
            
            # Matar servidor
            if kill -0 $SERVER_PID 2>/dev/null; then
                echo "   Terminando servidor (PID: $SERVER_PID)..."
                kill $SERVER_PID 2>/dev/null
                wait $SERVER_PID 2>/dev/null
            fi
            
            # Matar navegador se aberto por nós
            if [ "$AUTO_OPEN" = true ] && [ -n "$BROWSER_PID" ]; then
                if kill -0 $BROWSER_PID 2>/dev/null; then
                    echo "   Fechando navegador (PID: $BROWSER_PID)..."
                    kill $BROWSER_PID 2>/dev/null
                fi
            fi
            
            # Limpar porta
            kill_port
            
            echo "✅ Limpeza concluída. Até logo!"
            exit 0
        }
        
        # Configurar traps para sinais de término
        trap cleanup INT TERM EXIT
        
        # Monitorar processo
        echo ""
        echo "========================================"
        echo "📋 Servidor rodando! Pressione:"
        echo "   Ctrl+C  - Para parar servidor"
        echo "   Ctrl+Z  - Para colocar em background"
        echo "   fg      - Para trazer de volta ao foreground"
        echo "========================================"
        echo ""
        
        # Aguardar servidor (mantém script rodando)
        wait $SERVER_PID
        ;;
        
    serve-only)
        echo "🌐 Servindo site em $URL (sem abrir navegador)"
        check_port
        cd site || exit
        $PYTHON_CMD -m http.server $PORT
        ;;
        
    open)
        echo "🌍 Abrindo site no navegador..."
        BROWSER=$(find_chromium)
        
        if [ -z "$BROWSER" ]; then
            echo "❌ Navegador Chromium/Chrome não encontrado."
            echo "   Por favor, abra manualmente: $URL"
            exit 1
        fi
        
        $BROWSER "$URL" > /dev/null 2>&1 &
        echo "✅ Site aberto no $BROWSER"
        ;;
        
    clean)
        echo "🧹 Limpando diretório de build..."
        rm -rf site
        rm -f .build_cache.json 2>/dev/null
        rm -f .file_hashes.json 2>/dev/null
        rm -rf __pycache__ 2>/dev/null
        rm -f *.pyc 2>/dev/null
        echo "✅ Diretório de build limpo e cache removido!"
        ;;
        
    clean-cache)
        echo "🗑️ Limpando apenas cache..."
        rm -f .build_cache.json 2>/dev/null
        rm -f .file_hashes.json 2>/dev/null
        echo "✅ Cache limpo!"
        ;;
        
    status)
        echo "📊 Status do build:"
        
        # Verificar arquivos de cache
        if [ -f ".build_cache.json" ]; then
            echo "✅ Cache disponível"
            if command -v jq &> /dev/null; then
                LAST_BUILD=$(cat .build_cache.json | grep -o '"last_build":"[^"]*"' | cut -d'"' -f4)
                if [ -n "$LAST_BUILD" ]; then
                    echo "   Último build: $LAST_BUILD"
                fi
                BUILD_MODE=$(cat .build_cache.json | grep -o '"build_mode":"[^"]*"' | cut -d'"' -f4)
                if [ -n "$BUILD_MODE" ]; then
                    echo "   Modo do último build: $BUILD_MODE"
                fi
            else
                echo "   Último build: $(stat -c %y .build_cache.json 2>/dev/null || echo 'N/A')"
            fi
        else
            echo "⚠️ Sem cache - próximo build será completo"
        fi
        
        # Verificar site
        if [ -d "site" ]; then
            echo "✅ Diretório 'site/' existe"
            SITE_FILES=$(find site -type f 2>/dev/null | wc -l)
            echo "   Número de arquivos: $SITE_FILES"
            
            # Contar tipos de arquivos
            if [ $SITE_FILES -gt 0 ]; then
                HTML_FILES=$(find site -name "*.html" -type f 2>/dev/null | wc -l)
                CSS_FILES=$(find site -name "*.css" -type f 2>/dev/null | wc -l)
                JS_FILES=$(find site -name "*.js" -type f 2>/dev/null | wc -l)
                IMG_FILES=$(find site -type f \( -name "*.jpg" -o -name "*.jpeg" -o -name "*.png" -o -name "*.gif" -o -name "*.svg" -o -name "*.webp" \) 2>/dev/null | wc -l)
                
                echo "   Detalhes:"
                echo "     HTML: $HTML_FILES"
                echo "     CSS: $CSS_FILES"
                echo "     JavaScript: $JS_FILES"
                echo "     Imagens: $IMG_FILES"
            fi
        else
            echo "❌ Diretório 'site/' não existe"
        fi
        
        # Verificar config.yaml
        if [ -f "config.yaml" ]; then
            echo "✅ Configuração encontrada: config.yaml"
            # Contar elementos
            if command -v python3 &> /dev/null; then
                DISCIPLINAS=$(python3 -c "import yaml; data = yaml.safe_load(open('config.yaml')); print(len(data.get('disciplinas', [])))" 2>/dev/null || echo "0")
                AULAS=$(python3 -c "import yaml; data = yaml.safe_load(open('config.yaml')); total = sum(len(d.get('aulas', [])) for d in data.get('disciplinas', [])); print(total)" 2>/dev/null || echo "0")
                POSTS=$(python3 -c "import yaml; data = yaml.safe_load(open('config.yaml')); print(len(data.get('blog', {}).get('posts', [])))" 2>/dev/null || echo "0")
                
                echo "   Conteúdo configurado:"
                echo "     Disciplinas: $DISCIPLINAS"
                echo "     Aulas: $AULAS"
                echo "     Posts do blog: $POSTS"
            fi
        else
            echo "❌ Arquivo config.yaml não encontrado"
        fi
        ;;
        
    kill-port)
        kill_port
        ;;
        
    help|--help|-h)
        echo "📚 Uso: $0 {build|build-full|serve|serve-only|open|clean|clean-cache|status|kill-port|help} [porta]"
        echo ""
        echo "   build         - Constrói incrementalmente (apenas arquivos alterados)"
        echo "                   💾 Usa cache para máxima velocidade"
        echo "   build-full    - Reconstrução completa (ignora cache)"
        echo "                   🗑️  Limpa cache e reconstrói tudo"
        echo "   serve         - Inicia servidor e ABRE navegador (padrão: porta 8000)"
        echo "                    Exemplo: $0 serve 8080"
        echo "   serve-only    - Inicia servidor SEM abrir navegador"
        echo "   open          - Abre site no navegador (assume servidor rodando)"
        echo "   clean         - Remove TUDO: diretório site e cache"
        echo "   clean-cache   - Remove apenas cache, mantém site/"
        echo "   status        - Mostra status detalhado do build e cache"
        echo "   kill-port     - Mata processos usando a porta especificada"
        echo "   help          - Mostra esta mensagem de ajuda"
        echo ""
        echo "🔧 Funcionalidades avançadas:"
        echo "   - 🚀 Sistema de cache inteligente com hashes MD5"
        echo "   - 📚 MathJax centralizado para melhor performance"
        echo "   - 🌐 Abre Chromium/Chrome automaticamente"
        echo "   - 🔄 Reconstrução incremental vs completa"
        echo "   - 📊 Status detalhado com contagem de arquivos"
        echo "   - 🧹 Limpeza granular e automática"
        echo "   - 🛑 Gerenciamento de processos e portas"
        echo ""
        echo "💡 Dicas de uso:"
        echo "   - Durante desenvolvimento: use '$0 build' (rápido)"
        echo "   - Para produção: use '$0 build-full' (completo)"
        echo "   - Para testar: '$0 serve' (abre navegador automaticamente)"
        echo "   - Para ver detalhes: '$0 status'"
        echo ""
        echo "🔗 URLs importantes (quando servidor estiver rodando):"
        echo "   - Site principal: http://localhost:$PORT"
        echo "   - Disciplinas: http://localhost:$PORT/disciplinas/"
        echo "   - Blog: http://localhost:$PORT/blog/"
        echo ""
        echo "🎯 Comandos rápidos:"
        echo "   $0              # Equivale a '$0 build'"
        echo "   $0 build        # Build incremental"
        echo "   $0 serve        # Build + serve + abre navegador"
        echo "   $0 clean        # Limpa tudo"
        ;;
        
    *)
        # Se nenhum comando for especificado, faz build incremental
        if [ -z "$1" ]; then
            echo "🛠️ Executando build incremental (comando padrão)..."
            $0 build
        else
            echo "❌ Comando inválido: $1"
            echo "Use '$0 help' para mais informações."
            exit 1
        fi
        ;;
esac
