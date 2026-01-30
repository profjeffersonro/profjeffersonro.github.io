import base64
import os
import re

def convert_image_to_base64(image_path):
    """Converte uma imagem para base64."""
    with open(image_path, "rb") as image_file:
        return base64.b64encode(image_file.read()).decode('utf-8')

def process_markdown(markdown_path, images_folder, output_path):
    """Substitui imagens no arquivo Markdown por base64 e salva o resultado."""
    with open(markdown_path, "r") as file:
        content = file.read()

    # Regex para encontrar imagens no Markdown
    pattern = r'!\[([^\]]*)\]\((images/[^)]+)\)'
    matches = re.findall(pattern, content)

    for alt_text, image_path in matches:
        # Ajusta o caminho da imagem
        full_image_path = os.path.join(images_folder, image_path.replace('images/', ''))

        # Verifica se a imagem existe
        if os.path.exists(full_image_path):
            base64_str = convert_image_to_base64(full_image_path)
            data_uri = f"data:image/png;base64,{base64_str}"
            content = content.replace(f'![{alt_text}]({image_path})', f'![{alt_text}]({data_uri})')
        else:
            print(f"Imagem não encontrada: {full_image_path}")

    with open(output_path, "w") as file:
        file.write(content)

# Obtém o nome do arquivo Python atual, sem extensão
python_file_name = os.path.splitext(os.path.basename(__file__))[0]

# Define os caminhos para a pasta de imagens e o arquivo Markdown
images_folder = 'images/'
markdown_path = f'{python_file_name}.md'
output_path = f'{python_file_name}-convert.md'

# Executa o processamento
process_markdown(markdown_path, images_folder, output_path)
