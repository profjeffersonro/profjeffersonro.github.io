function Image(el)
  -- Ajuste para HTML
  if FORMAT == 'html' and el.attributes['html-width'] then
    el.attributes.width = el.attributes['html-width']
    el.attributes['html-width'] = nil -- Remove o atributo após uso
    el.attributes['pdf-width'] = nil -- Remove pdf-width no HTML

  -- Ajuste para PDF (LaTeX)
  elseif FORMAT == 'latex' and el.attributes['pdf-width'] then
    -- Converte porcentagem para decimal com \linewidth
    local pdf_width = el.attributes['pdf-width']
    if pdf_width:match("%%$") then
      local percentage = tonumber(pdf_width:match("^(%d+)%%$"))
      if percentage then
        pdf_width = tostring(percentage / 100) .. "\\linewidth"
      else
        pdf_width = "0.5\\linewidth" -- Valor padrão de segurança
      end
    end
    
    -- Comando para incluir a imagem no LaTeX
    return pandoc.RawInline('latex', 
      '\\includegraphics[width=' .. pdf_width .. ',height=\\textheight,keepaspectratio]{' .. el.src .. '}'
    )
  end

  return el
end
