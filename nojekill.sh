#!/bin/bash
# force-github-actions.sh

echo "🚀 Forçando configuração do GitHub Actions..."

cd ~/Documentos/GitHubPages/novo-portal

# 1. Remover qualquer cache do Jekyll
echo "1. 🧹 Removendo cache antigo..."
rm -rf .jekyll-cache 2>/dev/null
rm -rf _site 2>/dev/null

# 2. Garantir estrutura correta
echo "2. 📁 Verificando estrutura..."
mkdir -p .github/workflows

# 3. Verificar se deploy.yml está correto
if [ -f ".github/workflows/deploy.yml" ]; then
    echo "3. ✅ deploy.yml encontrado"
    
    # Verificar permissões
    if ! grep -q "pages: write" .github/workflows/deploy.yml; then
        echo "   ⚠️  Adicionando permissões..."
        # Adicionar seção de permissões se não tiver
        sed -i '/^name:/a\\npermissions:\n  contents: read\n  pages: write\n  id-token: write' .github/workflows/deploy.yml
    fi
else
    echo "3. ❌ deploy.yml não encontrado!"
    exit 1
fi

# 4. Commit vazio para forçar novo workflow run
echo "4. 📝 Criando commit para forçar Actions..."
git add .
git commit --allow-empty -m "🚀 Forçar execução do GitHub Actions - $(date '+%d/%m/%Y %H:%M:%S')"

# 5. Push
echo "5. 📤 Enviando para GitHub..."
git push

echo ""
echo "✅ PRONTO!"
echo "=========="
echo "Agora configure manualmente:"
echo "1. Acesse: https://github.com/profjeffersonro/profjeffersonro.github.io/settings/pages"
echo "2. Em 'Build and deployment', selecione: 'GitHub Actions'"
echo "3. Clique em 'Save'"
echo ""
echo "🌍 Depois verifique:"
echo "   - Actions: https://github.com/profjeffersonro/profjeffersonro.github.io/actions"
echo "   - Site: https://profjeffersonro.github.io/"
