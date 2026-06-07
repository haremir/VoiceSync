import sys
import spacy_pkuseg

# Expose spacy_pkuseg as pkuseg in sys.modules
sys.modules['pkuseg'] = spacy_pkuseg
from spacy_pkuseg import *
