"""Converte APRESENTACAO.md em HTML standalone para impressão como PDF.

Uso:
    python docs/gerar_html.py

Gera `docs/APRESENTACAO.html`. Abrir no Chrome/Edge → Ctrl+P → "Salvar como PDF"
para gerar o arquivo distribuível.

Zero dependências externas — só stdlib do Python.
"""
from __future__ import annotations

import os
import re
import html


# CSS embutido — estilo de slides com tema claro, fonte legível, quebra por página.
CSS = """
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap');

* { box-sizing: border-box; }

body {
    font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
    line-height: 1.5;
    color: #222;
    margin: 0;
    padding: 0;
    background: #f5f5f7;
}

/* Slide em A4 retrato — imprime corretamente em qualquer navegador
   sem precisar mudar Layout/Orientação no diálogo de impressão. */
.slide {
    background: white;
    width: 21cm;
    min-height: 29.4cm;
    margin: 1.5cm auto;
    padding: 2cm 2.2cm;
    box-shadow: 0 4px 24px rgba(0,0,0,0.08);
    border-radius: 8px;
    page-break-after: always;
    overflow: hidden;
}

.slide:last-child { page-break-after: auto; }

h1 {
    color: #1a3a52;
    border-bottom: 4px solid #ff6b35;
    padding-bottom: 0.4em;
    font-size: 1.7em;
    margin-top: 0;
    margin-bottom: 0.8em;
}

h2 {
    color: #1a3a52;
    font-size: 1.35em;
    margin-top: 0;
    margin-bottom: 0.4em;
}

h3 {
    color: #555;
    font-size: 1.05em;
    font-weight: 500;
    margin-top: 0;
}

p { margin: 0.5em 0; font-size: 0.95em; }

ul, ol { padding-left: 1.5em; font-size: 0.95em; }

li { margin: 0.25em 0; }

strong { color: #1a3a52; }

em { color: #555; }

code {
    font-family: 'JetBrains Mono', 'Consolas', monospace;
    background: #f0f2f5;
    padding: 0.1em 0.4em;
    border-radius: 3px;
    font-size: 0.88em;
    color: #c0392b;
}

pre {
    background: #2d3748;
    color: #e2e8f0;
    padding: 0.9em 1.1em;
    border-radius: 6px;
    overflow-x: auto;
    font-family: 'JetBrains Mono', 'Consolas', monospace;
    font-size: 0.72em;
    line-height: 1.45;
    margin: 0.7em 0;
}

pre code {
    background: transparent;
    color: inherit;
    padding: 0;
    font-size: inherit;
}

table {
    border-collapse: collapse;
    margin: 0.7em 0;
    width: 100%;
    font-size: 0.85em;
}

table th, table td {
    border: 1px solid #ddd;
    padding: 0.45em 0.7em;
    text-align: left;
    vertical-align: top;
}

table th {
    background: #1a3a52;
    color: white;
    font-weight: 600;
}

table tr:nth-child(even) { background: #fafafa; }

blockquote {
    border-left: 4px solid #ff6b35;
    margin: 0.7em 0;
    padding: 0.4em 1em;
    background: #fff8f5;
    font-style: italic;
    color: #555;
    font-size: 0.95em;
}

hr { display: none; }

/* Capa especial — também em A4 retrato */
.slide-capa {
    display: flex;
    flex-direction: column;
    justify-content: center;
    align-items: center;
    text-align: center;
    background: linear-gradient(135deg, #1a3a52 0%, #2c5478 100%);
    color: white;
    padding: 4cm 2cm;
}

.slide-capa h1 {
    color: white;
    border-bottom: 4px solid #ff6b35;
    font-size: 2.6em;
    line-height: 1.2;
    margin-bottom: 0.6em;
}

.slide-capa h3 {
    color: #cce0f0;
    font-size: 1.3em;
    font-weight: 400;
    margin-top: 0.5em;
    margin-bottom: 2em;
}

.slide-capa p {
    color: #cce0f0;
    font-size: 1.1em;
}

.slide-capa strong { color: white; }

/* Print: 1 slide por página A4 retrato (orientação default do navegador) */
@media print {
    body { background: white; }
    .slide {
        margin: 0;
        box-shadow: none;
        border-radius: 0;
        width: 100%;
        min-height: 100vh;
        padding: 1.5cm 1.8cm;
    }
}

@page {
    size: A4;
    margin: 0;
}
"""


def converter_inline(texto: str) -> str:
    """Converte markdown inline (negrito, itálico, código, links) em HTML."""
    # Escapa HTML primeiro para evitar injeção (mas preserva caracteres comuns)
    # Depois aplica conversões de markdown.

    # Code inline (`...`) — precisa vir antes para proteger de outras conversões
    def replace_code(m):
        return f"<code>{html.escape(m.group(1))}</code>"
    texto = re.sub(r"`([^`]+)`", replace_code, texto)

    # Links [texto](url)
    texto = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r'<a href="\2">\1</a>', texto)

    # Negrito **...**
    texto = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", texto)

    # Itálico *...*  (cuidado para não casar com ** já tratado)
    texto = re.sub(r"(?<!\*)\*([^*\n]+)\*(?!\*)", r"<em>\1</em>", texto)

    return texto


def converter_slide(md: str, is_capa: bool = False) -> str:
    """Converte um bloco markdown (1 slide) em HTML."""
    linhas = md.strip().split("\n")
    html_partes: list[str] = []
    i = 0
    em_lista = False
    em_pre = False
    em_tabela = False
    buffer_pre: list[str] = []
    buffer_tabela: list[list[str]] = []

    def fechar_lista():
        nonlocal em_lista
        if em_lista:
            html_partes.append("</ul>")
            em_lista = False

    def fechar_tabela():
        nonlocal em_tabela
        if em_tabela and buffer_tabela:
            html_partes.append("<table>")
            # 1ª linha = header
            html_partes.append("<thead><tr>")
            for cell in buffer_tabela[0]:
                html_partes.append(f"<th>{converter_inline(cell.strip())}</th>")
            html_partes.append("</tr></thead>")
            # Pula linha de separador "|---|---|"
            html_partes.append("<tbody>")
            for row in buffer_tabela[2:]:
                html_partes.append("<tr>")
                for cell in row:
                    html_partes.append(f"<td>{converter_inline(cell.strip())}</td>")
                html_partes.append("</tr>")
            html_partes.append("</tbody>")
            html_partes.append("</table>")
            buffer_tabela.clear()
            em_tabela = False

    while i < len(linhas):
        linha = linhas[i]

        # Bloco de código
        if linha.strip().startswith("```"):
            if em_pre:
                # Fim do bloco
                html_partes.append(
                    f'<pre><code>{html.escape(chr(10).join(buffer_pre))}</code></pre>'
                )
                buffer_pre.clear()
                em_pre = False
            else:
                fechar_lista()
                fechar_tabela()
                em_pre = True
            i += 1
            continue

        if em_pre:
            buffer_pre.append(linha)
            i += 1
            continue

        # Tabela: linhas que começam com `|`
        if linha.strip().startswith("|"):
            fechar_lista()
            if not em_tabela:
                em_tabela = True
                buffer_tabela.clear()
            # Divide pelas barras, descarta primeira e última (vazias)
            cells = [c for c in linha.strip().strip("|").split("|")]
            buffer_tabela.append(cells)
            i += 1
            continue
        elif em_tabela:
            fechar_tabela()

        # Headers
        if linha.startswith("# "):
            fechar_lista()
            html_partes.append(f"<h1>{converter_inline(linha[2:].strip())}</h1>")
        elif linha.startswith("## "):
            fechar_lista()
            html_partes.append(f"<h2>{converter_inline(linha[3:].strip())}</h2>")
        elif linha.startswith("### "):
            fechar_lista()
            html_partes.append(f"<h3>{converter_inline(linha[4:].strip())}</h3>")
        # Blockquote
        elif linha.startswith("> "):
            fechar_lista()
            html_partes.append(f"<blockquote>{converter_inline(linha[2:].strip())}</blockquote>")
        # Item de lista
        elif re.match(r"^[-*]\s+", linha):
            if not em_lista:
                html_partes.append("<ul>")
                em_lista = True
            conteudo = re.sub(r"^[-*]\s+", "", linha)
            html_partes.append(f"<li>{converter_inline(conteudo)}</li>")
        # Item de lista numerada
        elif re.match(r"^\d+\.\s+", linha):
            if not em_lista:
                html_partes.append("<ol>")
                em_lista = True
            conteudo = re.sub(r"^\d+\.\s+", "", linha)
            html_partes.append(f"<li>{converter_inline(conteudo)}</li>")
        # Linha em branco
        elif not linha.strip():
            fechar_lista()
        # Parágrafo
        else:
            fechar_lista()
            html_partes.append(f"<p>{converter_inline(linha.strip())}</p>")

        i += 1

    fechar_lista()
    fechar_tabela()

    cls = "slide slide-capa" if is_capa else "slide"
    return f'<div class="{cls}">\n' + "\n".join(html_partes) + "\n</div>"


def main():
    base_dir = os.path.dirname(os.path.abspath(__file__))
    entrada = os.path.join(base_dir, "APRESENTACAO.md")
    saida = os.path.join(base_dir, "APRESENTACAO.html")

    with open(entrada, encoding="utf-8") as f:
        md_completo = f.read()

    # Remove comentário HTML do topo (se houver)
    md_completo = re.sub(r"^<!--.*?-->\s*", "", md_completo, flags=re.DOTALL)

    # Separa por `---` (cada bloco é um slide)
    blocos = re.split(r"^---\s*$", md_completo, flags=re.MULTILINE)
    blocos = [b.strip() for b in blocos if b.strip()]

    slides_html = []
    for idx, bloco in enumerate(blocos):
        is_capa = idx == 0  # primeiro slide tem estilo especial
        slides_html.append(converter_slide(bloco, is_capa=is_capa))

    html_final = f"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Motor Prescritivo PRB — Apresentação Executiva</title>
    <style>{CSS}</style>
</head>
<body>
{chr(10).join(slides_html)}
</body>
</html>
"""

    with open(saida, "w", encoding="utf-8") as f:
        f.write(html_final)

    print(f"OK Gerado: {saida}")
    print(f"  Total: {len(slides_html)} slides")
    print()
    print("Proximo passo:")
    print("  1. Abra o arquivo no Chrome ou Edge:")
    print(f"     start {saida}")
    print("  2. Ctrl+P -> Destino: 'Salvar como PDF' -> Layout: 'Paisagem'")
    print("  3. Salve como APRESENTACAO.pdf")


if __name__ == "__main__":
    main()