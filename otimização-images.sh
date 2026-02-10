#!/bin/bash

# Script para otimizar imagens PNG reduzindo dimensões e tamanho de arquivo
# Compatível com GitHub Pages - Processa imagens recursivamente

# Configurações
MAX_DIMENSION=640            # Dimensão máxima (largura ou altura)
QUALITY=85                   # Qualidade (85% é um bom balanço)
OPTIMIZE_LEVEL=1            # Nível de otimização (0-1 para rápido, 2 para melhor)

# Cores para output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Contadores
total_images=0
processed_images=0
skipped_images=0
error_images=0
total_saved=0

# Função para mostrar uso
show_usage() {
    echo "Uso: $0 [OPÇÕES]"
    echo ""
    echo "Opções:"
    echo "  -d NÚMERO    Dimensão máxima (padrão: 640)"
    echo "  -q NÚMERO    Qualidade (1-100, padrão: 85)"
    echo "  -o NÍVEL     Nível de otimização (0-2, padrão: 1)"
    echo "  -t           Teste (não altera arquivos)"
    echo "  -r           Remover arquivos originais (cria backup)"
    echo "  -h           Mostra esta ajuda"
    echo ""
    echo "Exemplos:"
    echo "  $0                     # Processa com configurações padrão"
    echo "  $0 -d 800 -q 90        # Dimensão 800px, qualidade 90%"
    echo "  $0 -t                  # Modo teste"
}

# Função para verificar se o ImageMagick está instalado
check_dependencies() {
    if ! command -v convert &> /dev/null; then
        echo -e "${RED}Erro: ImageMagick não está instalado.${NC}"
        echo "Instale com:"
        echo "  Ubuntu/Debian: sudo apt-get install imagemagick"
        echo "  macOS: brew install imagemagick"
        echo "  Windows: https://imagemagick.org/script/download.php"
        exit 1
    fi
    
    if ! command -v identify &> /dev/null; then
        echo -e "${RED}Erro: ImageMagick não está completamente instalado.${NC}"
        exit 1
    fi
}

# Função para processar uma única imagem
process_image() {
    local image="$1"
    local test_mode="$2"
    local remove_original="$3"
    
    # Verifica se é um arquivo PNG
    if [[ ! "$image" =~ \.png$ ]]; then
        return
    fi
    
    ((total_images++))
    
    # Obtém informações da imagem
    local original_size=$(stat -f%z "$image" 2>/dev/null || stat -c%s "$image" 2>/dev/null)
    local dimensions=$(identify -format "%wx%h" "$image" 2>/dev/null)
    
    if [ -z "$dimensions" ]; then
        echo -e "${RED}Erro ao ler imagem: $image${NC}"
        ((error_images++))
        return
    fi
    
    local width=$(echo "$dimensions" | cut -d'x' -f1)
    local height=$(echo "$dimensions" | cut -d'x' -f2)
    
    # Verifica se precisa redimensionar
    local need_resize=0
    if [ "$width" -gt "$MAX_DIMENSION" ] || [ "$height" -gt "$MAX_DIMENSION" ]; then
        need_resize=1
    fi
    
    # Verifica se o arquivo é grande (> 300KB)
    local need_optimize=0
    if [ "$original_size" -gt 300000 ]; then
        need_optimize=1
    fi
    
    # Se não precisa de processamento, pula
    if [ "$need_resize" -eq 0 ] && [ "$need_optimize" -eq 0 ]; then
        echo -e "${GREEN}[OK]${NC} $image (${dimensions}, $(numfmt --to=si "$original_size")) - Já otimizada"
        ((skipped_images++))
        return
    fi
    
    # Cria nome do arquivo temporário
    local temp_file="${image%.png}_temp.png"
    
    # Comando base do ImageMagick
    local cmd="convert \"$image\""
    
    # Adiciona redimensionamento se necessário
    if [ "$need_resize" -eq 1 ]; then
        cmd="$cmd -resize ${MAX_DIMENSION}x${MAX_DIMENSION}>"
    fi
    
    # Adiciona otimizações
    cmd="$cmd -strip"                              # Remove metadados
    cmd="$cmd -alpha on"                           # Mantém transparência
    cmd="$cmd -quality $QUALITY"                   # Define qualidade
    cmd="$cmd -define png:compression-level=$OPTIMIZE_LEVEL"  # Nível de compressão
    cmd="$cmd -define png:compression-filter=5"    # Filtro de compressão
    cmd="$cmd -define png:compression-strategy=1"  # Estratégia de compressão
    
    # Arquivo de saída
    cmd="$cmd \"$temp_file\""
    
    # Modo teste - apenas mostra o que seria feito
    if [ "$test_mode" -eq 1 ]; then
        echo -e "${YELLOW}[TESTE]${NC} Processaria: $image"
        echo "  Dimensões atuais: ${dimensions}"
        echo "  Tamanho atual: $(numfmt --to=si "$original_size")"
        echo "  Comando: $cmd"
        ((processed_images++))
        return
    fi
    
    # Executa o comando
    echo -n "Processando: $image ... "
    
    if eval "$cmd" 2>/dev/null; then
        # Verifica se a nova imagem é menor
        local new_size=$(stat -f%z "$temp_file" 2>/dev/null || stat -c%s "$temp_file" 2>/dev/null)
        local saved=$((original_size - new_size))
        
        if [ "$new_size" -lt "$original_size" ] || [ "$need_resize" -eq 1 ]; then
            # Se remove original, faz backup
            if [ "$remove_original" -eq 1 ]; then
                mv "$image" "${image%.png}_backup.png"
            fi
            
            # Substitui a imagem original
            mv "$temp_file" "$image"
            
            ((processed_images++))
            total_saved=$((total_saved + saved))
            
            if [ "$saved" -gt 0 ]; then
                echo -e "${GREEN}OK${NC} (Economia: $(numfmt --to=si "$saved"))"
            else
                echo -e "${GREEN}OK${NC} (Redimensionada)"
            fi
        else
            # Se a nova imagem for maior, mantém a original
            rm "$temp_file"
            echo -e "${YELLOW}PULOU${NC} (nova imagem seria maior)"
            ((skipped_images++))
        fi
    else
        echo -e "${RED}ERRO${NC}"
        ((error_images++))
        # Remove arquivo temporário se existir
        [ -f "$temp_file" ] && rm "$temp_file"
    fi
}

# Função principal
main() {
    local test_mode=0
    local remove_original=0
    
    # Processa argumentos
    while getopts "d:q:o:trh" opt; do
        case $opt in
            d) MAX_DIMENSION="$OPTARG" ;;
            q) QUALITY="$OPTARG" ;;
            o) OPTIMIZE_LEVEL="$OPTARG" ;;
            t) test_mode=1 ;;
            r) remove_original=1 ;;
            h) show_usage; exit 0 ;;
            \?) echo "Opção inválida: -$OPTARG" >&2; exit 1 ;;
        esac
    done
    
    # Verifica dependências
    check_dependencies
    
    # Validações
    if [ "$MAX_DIMENSION" -lt 10 ] || [ "$MAX_DIMENSION" -gt 4096 ]; then
        echo -e "${RED}Erro: Dimensão deve estar entre 10 e 4096${NC}"
        exit 1
    fi
    
    if [ "$QUALITY" -lt 1 ] || [ "$QUALITY" -gt 100 ]; then
        echo -e "${RED}Erro: Qualidade deve estar entre 1 e 100${NC}"
        exit 1
    fi
    
    if [ "$OPTIMIZE_LEVEL" -lt 0 ] || [ "$OPTIMIZE_LEVEL" -gt 2 ]; then
        echo -e "${RED}Erro: Nível de otimização deve estar entre 0 e 2${NC}"
        exit 1
    fi
    
    # Cabeçalho
    echo "========================================="
    echo "  Otimizador de Imagens PNG para GitHub"
    echo "========================================="
    echo "Dimensão máxima: ${MAX_DIMENSION}px"
    echo "Qualidade: ${QUALITY}%"
    echo "Nível otimização: ${OPTIMIZE_LEVEL}"
    echo "Modo teste: $([ "$test_mode" -eq 1 ] && echo "SIM" || echo "NÃO")"
    echo "Backup original: $([ "$remove_original" -eq 1 ] && echo "SIM" || echo "NÃO")"
    echo "========================================="
    echo ""
    
    # Encontra e processa todas as imagens PNG recursivamente
    echo "Procurando imagens PNG..."
    echo ""
    
    # Usa find para localizar todos os arquivos PNG
    while IFS= read -r -d '' image; do
        process_image "$image" "$test_mode" "$remove_original"
    done < <(find . -type f -name "*.png" ! -name "*_backup.png" -print0)
    
    # Resumo
    echo ""
    echo "========================================="
    echo "            RESUMO DO PROCESSAMENTO"
    echo "========================================="
    echo "Total de imagens encontradas: $total_images"
    echo "Imagens processadas: $processed_images"
    echo "Imagens puladas: $skipped_images"
    echo "Imagens com erro: $error_images"
    
    if [ "$processed_images" -gt 0 ] && [ "$test_mode" -eq 0 ]; then
        echo "Espaço economizado: $(numfmt --to=si "$total_saved")"
        
        if [ "$remove_original" -eq 1 ]; then
            echo ""
            echo -e "${YELLOW}Atenção: Backups foram criados com '_backup.png'${NC}"
            echo "Você pode removê-los com:"
            echo "  find . -name '*_backup.png' -delete"
        fi
    fi
    
    echo ""
    
    if [ "$test_mode" -eq 1 ]; then
        echo -e "${YELLOW}Modo teste ativado - Nenhum arquivo foi alterado${NC}"
        echo "Execute sem a opção -t para processar as imagens"
    fi
}

# Executa a função principal
main "$@"
