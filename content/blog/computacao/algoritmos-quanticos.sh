#!/bin/bash

# Início do script
start_time=$(date +%s)

# Função para executar comandos e enviar progresso para zenity
execute_command() {
    local command="$1"
    local message="$2"
    echo "$message"
    echo "# $message" # Exibe na barra de progresso
    eval $command >>full-log.txt 2>>error.log
    if [ $? -ne 0 ]; then
        echo "Erro ao executar: $message" >&2
        zenity --error --text="Erro ao executar:\n$message\nConsulte error.log para mais detalhes." --width=400
        exit 1
    fi
}

# Obtém o nome do arquivo do script atual, sem o diretório e a extensão
name=$(basename "$0" .sh)

# Limpa arquivos antigos
rm -f $name.aux $name.log $name.out $name.toc $name.pdf error.log full-log.txt

# Lista de comandos com mensagens claras
commands=(
    "python $name.py|Executando o script Python para processar os dados iniciais."
    "pandoc --lua-filter=adjust-images.lua -o $name.html $name-convert.md --mathjax --standalone --include-in-header=style.css --highlight-style tango|Convertendo o arquivo Markdown para HTML com Pandoc."
    "pandoc --lua-filter=adjust-images.lua --pdf-engine=pdflatex --highlight-style tango --table-of-contents --number-sections -V lang=pt-BR -s \"$name.md\" -o \"$name.tex\"|Gerando o arquivo .tex a partir do Markdown com Pandoc."
    "pdflatex -interaction=nonstopmode -halt-on-error \"$name.tex\"|Primeira execução do pdflatex para compilar o arquivo .tex."
    "sleep 3|Aguardando alguns segundos para garantir a sincronização."
    "pdflatex -interaction=nonstopmode -halt-on-error \"$name.tex\"|Segunda execução do pdflatex para ajustar referências cruzadas."
)

# Barra de progresso
(
    for i in "${!commands[@]}"; do
        # Divide o comando e a mensagem usando '|'
        IFS="|" read -r cmd msg <<<"${commands[$i]}"
        execute_command "$cmd" "$msg"
        echo "$(( (i + 1) * 100 / ${#commands[@]} ))" # Atualiza a barra de progresso
    done
) | zenity --progress --title="Progresso da execução" --width=500 --auto-close --no-cancel

# Final do script
end_time=$(date +%s)
elapsed_time=$((end_time - start_time))

# Limpeza final (após execução bem-sucedida)
rm -f $name.aux $name.log $name.out $name.toc $name-convert.md error.log

zenity --info --text="Processo concluído com sucesso.\nTempo total de execução: $elapsed_time segundos." --width=400
