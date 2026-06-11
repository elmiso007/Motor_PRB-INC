# =============================================================================
# Conftest pytest — configuração de path para importar módulos do motor
# =============================================================================
# Pytest descobre este arquivo automaticamente. Mantemos minimal: apenas
# adiciona o diretório-pai ao sys.path para que `from extractor import ...`
# funcione nos testes.
#
# Builders (fábricas de objetos para testes) estão em `tests/builders.py`,
# que pode ser importado pelos testes como `from builders import make_X`.
# =============================================================================
import sys
import os

# Diretório-pai (Motor PRB-INC/) — para importar `extractor`, `models`, etc.
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

# Diretório atual (tests/) — para importar `builders`.
sys.path.insert(0, os.path.dirname(__file__))