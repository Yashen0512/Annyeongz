# pytest 共用設定:把 _build/ 加進 sys.path,讓測試可以 import build_site / fetch_data / facets_def
import os, sys
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
sys.path.insert(0, os.path.join(ROOT, '_build'))
FIXTURE = os.path.join(ROOT, 'tests', 'fixtures', 'build_input')
