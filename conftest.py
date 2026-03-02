"""
Root conftest.py — sets up esphome mocks before pytest imports any tile_ui tests.

tile_ui/__init__.py imports esphome.codegen at module level. Since tile_ui/tests/
is a subpackage of tile_ui, pytest can't load anything inside tests/ without first
importing tile_ui. By placing mocks here (outside any Python package), pytest
installs them before any tile_ui code runs.
"""
import sys
import os
from unittest.mock import MagicMock

# Add external_components to sys.path so `import tile_ui` resolves correctly.
_ext = os.path.join(os.path.dirname(__file__), 'esphome', 'external_components')
if _ext not in sys.path:
    sys.path.insert(0, _ext)

# Build a single top-level esphome mock whose sub-attributes are registered in
# sys.modules.  Crucially, `import esphome.config_validation as cv` resolves to
# `sys.modules['esphome'].config_validation` (attribute lookup on the parent),
# NOT to `sys.modules['esphome.config_validation']`, so both must be the same
# object for attribute mutations to be visible inside the imported modules.
_esphome = MagicMock(name='esphome')
_cv = MagicMock(name='esphome.config_validation')
_cv.Invalid = ValueError          # must be a real exception class

# Wire sub-mocks as attributes so dotted-import access is consistent
_esphome.codegen = MagicMock(name='esphome.codegen')
_esphome.config_validation = _cv
_esphome.const = MagicMock(name='esphome.const')
_esphome.core = MagicMock(name='esphome.core')
_esphome.components = MagicMock(name='esphome.components')
_esphome.components.display = MagicMock(name='esphome.components.display')

sys.modules.update({
    'esphome':                      _esphome,
    'esphome.codegen':              _esphome.codegen,
    'esphome.config_validation':    _cv,
    'esphome.const':                _esphome.const,
    'esphome.core':                 _esphome.core,
    'esphome.components':           _esphome.components,
    'esphome.components.display':   _esphome.components.display,
})
